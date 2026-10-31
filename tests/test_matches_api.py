import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.matches import router
from app.api.teams import router as teams_router
from app.database import Base, get_db
from app.models import (
    Innings,
    InningsStatus,
    Match,
    MatchPlayer,
    MatchStatus,
    Player,
    Team,
    TeamPlayer,
    TossDecision,
)

class MatchApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        @event.listens_for(self.engine, "connect")
        def enable_foreign_keys(dbapi_connection: object, _record: object) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        with self.session_factory() as session:
            self.team_a = Team(name="Salt Lake Strikers", short_name="SS")
            self.team_b = Team(name="Park Street Panthers", short_name="PP")
            session.add_all([self.team_a, self.team_b])
            session.flush()
            self.team_ids = (self.team_a.id, self.team_b.id)
            self.player_ids = ([], [])
            for team_index, team in enumerate((self.team_a, self.team_b)):
                for number in range(11):
                    player = Player(display_name=f"Player {team_index}-{number}")
                    session.add(player)
                    session.flush()
                    session.add(TeamPlayer(team_id=team.id, player_id=player.id))
                    self.player_ids[team_index].append(player.id)
            session.commit()

        def override_get_db():
            with self.session_factory() as session:
                yield session

        self.app = FastAPI()
        self.app.include_router(router, prefix="/api")
        self.app.include_router(teams_router, prefix="/api")
        self.app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.client.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def payload(self, **overrides: object) -> dict:
        data = {
            "team_a_id": self.team_ids[0],
            "team_b_id": self.team_ids[1],
            "team_a_player_ids": self.player_ids[0],
            "team_b_player_ids": self.player_ids[1],
            "overs_limit": 8,
            "wickets_limit": 7,
            "toss_winner_team_id": self.team_ids[0],
            "toss_decision": "BOWL",
            "name": "Sunday League · Week 13",
            "venue": "Central Park Ground",
            "scheduled_at": "2026-03-16T12:00:00Z",
        }
        data.update(overrides)
        return data

    def test_create_match_persists_both_xis_and_starts_innings_from_toss(self) -> None:
        response = self.client.post("/api/matches", json=self.payload())

        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        self.assertEqual(body["status"], MatchStatus.LIVE.value)
        self.assertEqual(body["toss_decision"], TossDecision.BOWL.value)
        self.assertEqual(body["home_team"]["playing_xi"], self.player_ids[0])
        self.assertEqual(body["away_team"]["playing_xi"], self.player_ids[1])
        self.assertEqual(body["innings"][0]["status"], InningsStatus.LIVE.value)
        self.assertEqual(body["innings"][0]["batting_team_id"], self.team_ids[1])
        self.assertEqual(body["innings"][0]["bowling_team_id"], self.team_ids[0])

        with self.session_factory() as session:
            match = session.get(Match, body["id"])
            innings = session.scalar(select(Innings).where(Innings.match_id == body["id"]))
            lineups = session.scalars(
                select(MatchPlayer)
                .where(MatchPlayer.match_id == body["id"])
                .order_by(MatchPlayer.team_id, MatchPlayer.batting_order)
            ).all()
            self.assertIsNotNone(match)
            self.assertEqual(match.toss_winner_team_id, self.team_ids[0])
            self.assertEqual(match.toss_decision, TossDecision.BOWL)
            self.assertEqual(innings.innings_number, 1)
            self.assertEqual(innings.overs_limit, 8)
            self.assertEqual(innings.wickets_limit, 7)
            self.assertEqual(len(lineups), 22)
            self.assertEqual(
                [player.batting_order for player in lineups[:11]],
                list(range(1, 12)),
            )

    def test_batting_toss_decision_makes_toss_winner_bat_first(self) -> None:
        response = self.client.post(
            "/api/matches",
            json=self.payload(toss_decision="BAT"),
        )
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(
            response.json()["innings"][0]["batting_team_id"],
            self.team_ids[0],
        )

    def test_removing_roster_membership_keeps_the_saved_match_lineup(self) -> None:
        created = self.client.post("/api/matches", json=self.payload())
        self.assertEqual(created.status_code, 201, created.text)
        match_id = created.json()["id"]
        player_id = self.player_ids[0][0]

        removed = self.client.delete(
            f"/api/teams/{self.team_ids[0]}/players/{player_id}"
        )
        self.assertEqual(removed.status_code, 204, removed.text)

        with self.session_factory() as session:
            saved = session.scalar(
                select(MatchPlayer).where(
                    MatchPlayer.match_id == match_id,
                    MatchPlayer.player_id == player_id,
                )
            )
            self.assertIsNotNone(saved)

    def test_rejects_non_participant_toss_winner_and_duplicate_teams(self) -> None:
        response = self.client.post(
            "/api/matches",
            json=self.payload(toss_winner_team_id=999),
        )
        self.assertEqual(response.status_code, 422)

        response = self.client.post(
            "/api/matches",
            json=self.payload(team_b_id=self.team_ids[0]),
        )
        self.assertEqual(response.status_code, 422)

    def test_rejects_invalid_xi_size_duplicates_and_roster_membership(self) -> None:
        response = self.client.post(
            "/api/matches",
            json=self.payload(team_a_player_ids=self.player_ids[0][:-1]),
        )
        self.assertEqual(response.status_code, 422)

        duplicate_xi = self.player_ids[0][:-1] + [self.player_ids[0][0]]
        response = self.client.post(
            "/api/matches",
            json=self.payload(team_a_player_ids=duplicate_xi),
        )
        self.assertEqual(response.status_code, 422)

        overlapping_xi = self.player_ids[1][:-1] + [self.player_ids[0][0]]
        response = self.client.post(
            "/api/matches",
            json=self.payload(team_b_player_ids=overlapping_xi),
        )
        self.assertEqual(response.status_code, 422)

        wrong_roster = self.player_ids[0][:-1] + [self.player_ids[1][0]]
        response = self.client.post(
            "/api/matches",
            json=self.payload(team_a_player_ids=wrong_roster),
        )
        self.assertEqual(response.status_code, 422)

    def test_rejects_invalid_match_limits_and_missing_teams(self) -> None:
        response = self.client.post(
            "/api/matches",
            json=self.payload(overs_limit=0),
        )
        self.assertEqual(response.status_code, 422)

        response = self.client.post(
            "/api/matches",
            json=self.payload(team_b_id=999),
        )
        self.assertEqual(response.status_code, 404)

        with self.session_factory() as session:
            self.assertEqual(session.scalar(select(Match.id).limit(1)), None)
