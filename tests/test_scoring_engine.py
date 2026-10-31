import base64
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.scoring import router
from app.api.matches import router as matches_router
from app.api.statistics import router as statistics_router
from app.database import Base, get_db
from app.models import (
    Delivery,
    ExtraType,
    Innings,
    InningsStatus,
    Match,
    MatchPlayer,
    MatchStatus,
    Player,
    PlayerMatchStatistics,
    Team,
    TeamPlayer,
    TossDecision,
    WicketType,
)

_TEST_USERNAME = "test-user"
_TEST_PASSWORD = "test-password-1234"
_TEST_AUTH_HEADER = "Basic " + base64.b64encode(
    f"{_TEST_USERNAME}:{_TEST_PASSWORD}".encode("utf-8")
).decode("ascii")


class ScoringEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        auth_environment = patch.dict(
            os.environ,
            {
                "GULLYSCORE_USERNAME": _TEST_USERNAME,
                "GULLYSCORE_PASSWORD": _TEST_PASSWORD,
            },
        )
        auth_environment.start()
        self.addCleanup(auth_environment.stop)
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
            self.home = Team(name="Salt Lake Strikers", short_name="SS")
            self.away = Team(name="Park Street Panthers", short_name="PP")
            session.add_all([self.home, self.away])
            session.flush()
            self.team_ids = (self.home.id, self.away.id)
            self.players = ([], [])
            for side, team in enumerate((self.home, self.away)):
                for index in range(11):
                    player = Player(display_name=f"Player {side}-{index + 1}")
                    session.add(player)
                    session.flush()
                    session.add(TeamPlayer(team_id=team.id, player_id=player.id))
                    self.players[side].append(player.id)
            match = Match(
                name="Scoring test",
                home_team_id=self.home.id,
                away_team_id=self.away.id,
                overs_limit=2,
                wickets_limit=10,
                status=MatchStatus.LIVE,
                toss_winner_team_id=self.home.id,
                toss_decision=TossDecision.BAT,
            )
            session.add(match)
            session.flush()
            self.match_id = match.id
            innings = Innings(
                match_id=match.id,
                home_team_id=self.home.id,
                away_team_id=self.away.id,
                innings_number=1,
                batting_team_id=self.home.id,
                bowling_team_id=self.away.id,
                overs_limit=2,
                wickets_limit=10,
                target=None,
                status=InningsStatus.LIVE,
            )
            session.add(innings)
            session.flush()
            self.innings_id = innings.id
            for team_id, players in zip(self.team_ids, self.players, strict=True):
                for order, player_id in enumerate(players, start=1):
                    session.add(
                        MatchPlayer(
                            match_id=match.id,
                            home_team_id=self.home.id,
                            away_team_id=self.away.id,
                            team_id=team_id,
                            player_id=player_id,
                            batting_order=order,
                        )
                    )
            session.commit()

        def override_get_db():
            with self.session_factory() as session:
                yield session

        self.app = FastAPI()
        self.app.include_router(router, prefix="/api")
        self.app.include_router(matches_router, prefix="/api")
        self.app.include_router(statistics_router, prefix="/api")
        self.app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(
            self.app,
            headers={"Authorization": _TEST_AUTH_HEADER},
        )
        self.striker = self.players[0][0]
        self.non_striker = self.players[0][1]
        self.bowler = self.players[1][0]
        self.start()

    def tearDown(self) -> None:
        self.client.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def start(self) -> dict:
        response = self.client.post(
            f"/api/innings/{self.innings_id}/start",
            json={
                "striker_id": self.striker,
                "non_striker_id": self.non_striker,
                "bowler_id": self.bowler,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def delivery(
        self,
        *,
        request_id: str | None = None,
        batter_id: int | None = None,
        bowler_id: int | None = None,
        batter_runs: int = 0,
        extras_type: str | None = None,
        extras_runs: int = 0,
        completed_runs: int = 0,
        wicket_type: str | None = None,
        dismissed_player_id: int | None = None,
        incoming_batter_id: int | None = None,
        innings_id: int | None = None,
    ):
        payload = {
            "request_id": request_id or str(uuid4()),
            "batter_id": batter_id or self.current_state()["striker_id"],
            "bowler_id": bowler_id or self.bowler,
            "batter_runs": batter_runs,
            "extras_type": extras_type,
            "extras_runs": extras_runs,
            "completed_runs": completed_runs,
            "wicket_type": wicket_type,
            "dismissed_player_id": dismissed_player_id,
            "incoming_batter_id": incoming_batter_id,
        }
        return self.client.post(
            f"/api/innings/{innings_id or self.innings_id}/deliveries",
            json=payload,
        )

    def current_state(self) -> dict:
        with self.session_factory() as session:
            innings = session.get(Innings, self.innings_id)
            extras = session.scalar(
                select(func.coalesce(func.sum(Delivery.extras_runs), 0))
                .where(
                    Delivery.innings_id == self.innings_id,
                    Delivery.is_undone.is_(False),
                )
            )
            return {
                "total_runs": innings.total_runs,
                "wickets": innings.wickets_down,
                "legal_balls": innings.legal_balls,
                "striker_id": innings.striker_id,
                "non_striker_id": innings.non_striker_id,
                "extras": extras or 0,
            }

    def undo(self, request_id: str | None = None):
        return self.client.post(
            f"/api/innings/{self.innings_id}/undo",
            json={"request_id": request_id or str(uuid4())},
        )

    def stat(self, player_id: int) -> PlayerMatchStatistics:
        with self.session_factory() as session:
            row = session.scalar(
                select(PlayerMatchStatistics).where(
                    PlayerMatchStatistics.innings_id == self.innings_id,
                    PlayerMatchStatistics.player_id == player_id,
                )
            )
            self.assertIsNotNone(row)
            session.expunge(row)
            return row

    def test_dot_and_batter_runs_update_score_balls_and_strike(self) -> None:
        response = self.delivery(batter_runs=0)
        self.assertEqual(response.status_code, 201, response.text)
        state = response.json()["state"]
        self.assertEqual((state["total_runs"], state["legal_balls"], state["overs"]), (0, 1, "0.1"))
        self.assertEqual(self.stat(self.striker).balls_faced, 1)

        response = self.delivery(batter_runs=3)
        self.assertEqual(response.status_code, 201, response.text)
        state = response.json()["state"]
        self.assertEqual(state["total_runs"], 3)
        self.assertEqual(state["striker_id"], self.non_striker)
        self.assertEqual(self.stat(self.striker).runs, 3)

    def test_batter_runs_boundaries_and_balls_faced(self) -> None:
        for runs in (1, 2, 4, 6):
            response = self.delivery(batter_runs=runs)
            self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(self.current_state()["total_runs"], 13)
        self.assertEqual(self.current_state()["legal_balls"], 4)
        stats = self.stat(self.non_striker)
        self.assertEqual(self.stat(self.striker).runs + stats.runs, 13)
        self.assertEqual(stats.fours, 1)
        self.assertEqual(stats.sixes, 1)
        self.assertEqual(self.stat(self.striker).balls_faced + stats.balls_faced, 4)

    def test_wide_scores_extra_is_illegal_and_not_faced_by_batter(self) -> None:
        response = self.delivery(
            extras_type=ExtraType.WIDE.value,
            extras_runs=3,
            completed_runs=2,
        )
        self.assertEqual(response.status_code, 201, response.text)
        state = response.json()["state"]
        self.assertEqual(state["total_runs"], 3)
        self.assertEqual(state["extras"], 3)
        self.assertEqual(state["legal_balls"], 0)
        self.assertEqual(state["striker_id"], self.striker)
        self.assertEqual(self.stat(self.striker).balls_faced, 0)
        self.assertEqual(self.stat(self.bowler).runs_conceded, 3)
        self.assertEqual(self.stat(self.bowler).balls_bowled, 0)

    def test_no_ball_penalty_and_batter_runs_are_counted(self) -> None:
        response = self.delivery(
            batter_runs=4,
            extras_type=ExtraType.NO_BALL.value,
            extras_runs=1,
        )
        self.assertEqual(response.status_code, 201, response.text)
        state = response.json()["state"]
        self.assertEqual((state["total_runs"], state["extras"], state["legal_balls"]), (5, 1, 0))
        self.assertEqual(self.stat(self.striker).runs, 4)
        self.assertEqual(self.stat(self.striker).balls_faced, 0)
        self.assertEqual(self.stat(self.bowler).runs_conceded, 5)
        self.assertEqual(self.stat(self.bowler).balls_bowled, 0)

    def test_byes_on_no_ball_are_not_charged_to_bowler(self) -> None:
        response = self.delivery(
            extras_type=ExtraType.NO_BALL.value,
            extras_runs=3,
            completed_runs=2,
        )
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["state"]["total_runs"], 3)
        self.assertEqual(self.stat(self.bowler).runs_conceded, 1)
        self.assertEqual(self.stat(self.striker).balls_faced, 0)

    def test_odd_completed_runs_on_wide_and_no_ball_rotate_strike(self) -> None:
        wide = self.delivery(
            extras_type=ExtraType.WIDE.value,
            extras_runs=2,
            completed_runs=1,
        )
        self.assertEqual(wide.status_code, 201, wide.text)
        self.assertEqual(wide.json()["state"]["striker_id"], self.non_striker)

        no_ball = self.delivery(
            batter_runs=1,
            extras_type=ExtraType.NO_BALL.value,
            extras_runs=1,
        )
        self.assertEqual(no_ball.status_code, 201, no_ball.text)
        self.assertEqual(no_ball.json()["state"]["striker_id"], self.striker)
        self.assertEqual(no_ball.json()["state"]["legal_balls"], 0)

    def test_byes_and_leg_byes_are_extras_legal_and_do_not_concede_to_bowler(self) -> None:
        for kind, count in ((ExtraType.BYE, 2), (ExtraType.LEG_BYE, 1)):
            response = self.delivery(
                extras_type=kind.value,
                extras_runs=count,
                completed_runs=count,
            )
            self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(self.current_state()["total_runs"], 3)
        self.assertEqual(self.current_state()["legal_balls"], 2)
        self.assertEqual(self.stat(self.striker).runs, 0)
        self.assertEqual(self.stat(self.striker).balls_faced, 2)
        self.assertEqual(self.stat(self.bowler).runs_conceded, 0)
        self.assertEqual(self.stat(self.bowler).balls_bowled, 2)
        self.assertEqual(self.current_state()["striker_id"], self.non_striker)

    def test_odd_runs_rotate_and_completed_over_rotates_strike_again(self) -> None:
        for runs in (1, 0, 0, 0, 0, 0):
            response = self.delivery(batter_runs=runs)
            self.assertEqual(response.status_code, 201, response.text)
        state = response.json()["state"]
        self.assertEqual(state["overs"], "1.0")
        self.assertEqual(state["striker_id"], self.striker)
        self.assertEqual(state["non_striker_id"], self.non_striker)

    def test_maiden_over_and_extra_runs_prevent_maiden(self) -> None:
        for _ in range(6):
            response = self.delivery()
            self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["state"]["maiden_overs"], 1)
        self.assertEqual(self.stat(self.bowler).maidens, 1)

        innings = self.create_second_test_innings(overs=2)
        self.innings_id = innings
        self.start()
        response = self.delivery(
            extras_type=ExtraType.WIDE.value,
            extras_runs=1,
        )
        self.assertEqual(response.status_code, 201, response.text)
        for _ in range(6):
            response = self.delivery()
            self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["state"]["maiden_overs"], 0)

    def create_second_test_innings(self, *, overs: int) -> int:
        with self.session_factory() as session:
            innings = Innings(
                match_id=self.match_id,
                home_team_id=self.team_ids[0],
                away_team_id=self.team_ids[1],
                innings_number=2,
                batting_team_id=self.team_ids[0],
                bowling_team_id=self.team_ids[1],
                overs_limit=overs,
                wickets_limit=10,
                target=None,
                status=InningsStatus.LIVE,
            )
            session.add(innings)
            session.flush()
            innings_id = innings.id
            session.commit()
            return innings_id

    def test_bowler_can_change_between_overs_but_not_mid_over(self) -> None:
        response = self.delivery(bowler_id=self.players[1][1])
        self.assertEqual(response.status_code, 409)
        for _ in range(6):
            response = self.delivery()
            self.assertEqual(response.status_code, 201, response.text)
        next_bowler = self.players[1][1]
        response = self.delivery(bowler_id=next_bowler)
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["state"]["current_bowler_id"], next_bowler)

    def test_bowler_credit_excludes_run_out(self) -> None:
        response = self.delivery(
            wicket_type=WicketType.RUN_OUT.value,
            dismissed_player_id=self.striker,
            incoming_batter_id=self.players[0][2],
        )
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["state"]["wickets"], 1)
        self.assertEqual(self.stat(self.bowler).wickets, 0)
        self.assertTrue(self.stat(self.striker).dismissed)
        self.assertFalse(self.stat(self.striker).not_out)
        self.assertTrue(self.stat(self.players[0][2]).not_out)

    def test_bowler_credit_includes_caught_wicket(self) -> None:
        response = self.delivery(
            wicket_type=WicketType.CAUGHT.value,
            dismissed_player_id=self.striker,
            incoming_batter_id=self.players[0][2],
        )
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(self.stat(self.bowler).wickets, 1)

    def test_supported_dismissals_apply_bowler_credit_rules(self) -> None:
        wicket_types = [
            WicketType.BOWLED,
            WicketType.CAUGHT,
            WicketType.CAUGHT_AND_BOWLED,
            WicketType.LBW,
            WicketType.STUMPED,
            WicketType.HIT_WICKET,
            WicketType.RUN_OUT,
            WicketType.RETIRED_OUT,
            WicketType.OBSTRUCTING_THE_FIELD,
            WicketType.HIT_THE_BALL_TWICE,
        ]
        next_batter_index = 2
        for index, wicket_type in enumerate(wicket_types):
            incoming = (
                self.players[0][next_batter_index]
                if index < len(wicket_types) - 1
                else None
            )
            response = self.delivery(
                wicket_type=wicket_type.value,
                dismissed_player_id=self.current_state()["striker_id"],
                incoming_batter_id=incoming,
            )
            self.assertEqual(response.status_code, 201, response.text)
            if incoming is not None:
                next_batter_index += 1
        self.assertEqual(response.json()["state"]["wickets"], 10)
        self.assertEqual(response.json()["state"]["status"], InningsStatus.COMPLETED.value)
        self.assertEqual(self.stat(self.bowler).wickets, 6)

    def test_wide_stumping_and_no_ball_run_out_are_valid_without_extra_bowler_credit(self) -> None:
        wide = self.delivery(
            extras_type=ExtraType.WIDE.value,
            extras_runs=1,
            wicket_type=WicketType.STUMPED.value,
            dismissed_player_id=self.striker,
            incoming_batter_id=self.players[0][2],
        )
        self.assertEqual(wide.status_code, 201, wide.text)
        no_ball_run_out = self.delivery(
            extras_type=ExtraType.NO_BALL.value,
            extras_runs=1,
            wicket_type=WicketType.RUN_OUT.value,
            dismissed_player_id=self.non_striker,
            incoming_batter_id=self.players[0][3],
        )
        self.assertEqual(no_ball_run_out.status_code, 201, no_ball_run_out.text)
        self.assertEqual(self.stat(self.bowler).wickets, 1)
        self.assertEqual(no_ball_run_out.json()["state"]["legal_balls"], 0)
        self.assertEqual(no_ball_run_out.json()["state"]["wickets"], 2)

    def test_all_out_and_over_limit_complete_innings(self) -> None:
        with self.session_factory() as session:
            innings = session.get(Innings, self.innings_id)
            innings.wickets_limit = 1
            session.commit()
        response = self.delivery(
            wicket_type=WicketType.RUN_OUT.value,
            dismissed_player_id=self.striker,
        )
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["state"]["status"], InningsStatus.COMPLETED.value)
        next_ball = self.delivery(batter_id=self.striker)
        self.assertEqual(next_ball.status_code, 409)

        innings_id = self.create_second_test_innings(overs=1)
        self.innings_id = innings_id
        self.start()
        for _ in range(6):
            response = self.delivery()
            self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["state"]["status"], InningsStatus.COMPLETED.value)

    def test_duplicate_request_is_idempotent_and_changed_reuse_is_rejected(self) -> None:
        request_id = str(uuid4())
        first = self.delivery(request_id=request_id, batter_runs=2)
        repeated = self.delivery(request_id=request_id, batter_runs=2)
        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(repeated.status_code, 201, repeated.text)
        self.assertTrue(repeated.json()["replayed"])
        self.assertEqual(self.current_state()["total_runs"], 2)

        changed = self.delivery(request_id=request_id, batter_runs=4)
        self.assertEqual(changed.status_code, 409)
        self.assertEqual(self.current_state()["total_runs"], 2)

    def test_undo_restores_complete_delivery_and_maiden_over(self) -> None:
        first = self.delivery(batter_runs=1)
        self.assertEqual(first.status_code, 201, first.text)
        before_over = self.current_state()
        for _ in range(5):
            self.assertEqual(self.delivery().status_code, 201)
        completed = self.current_state()
        self.assertEqual(completed["legal_balls"], 6)
        with self.session_factory() as session:
            self.assertEqual(session.get(Innings, self.innings_id).maiden_overs, 0)
        undone = self.undo()
        self.assertEqual(undone.status_code, 200, undone.text)
        state = undone.json()["state"]
        self.assertEqual(state["legal_balls"], 5)
        self.assertEqual(state["total_runs"], before_over["total_runs"])
        self.assertEqual(state["striker_id"], self.non_striker)
        self.assertEqual(self.stat(self.striker).runs, 1)
        self.assertEqual(self.stat(self.bowler).balls_bowled, 5)

    def test_undo_wicket_restores_wicket_and_batter_state(self) -> None:
        response = self.delivery(
            wicket_type=WicketType.BOWLED.value,
            dismissed_player_id=self.striker,
            incoming_batter_id=self.players[0][2],
        )
        self.assertEqual(response.status_code, 201, response.text)
        undone = self.undo()
        self.assertEqual(undone.status_code, 200, undone.text)
        self.assertEqual(undone.json()["state"]["wickets"], 0)
        self.assertEqual(undone.json()["state"]["striker_id"], self.striker)
        self.assertEqual(self.stat(self.bowler).wickets, 0)
        self.assertFalse(self.stat(self.striker).dismissed)

    def test_undo_of_maiden_over_restores_bowler_and_innings_statistics(self) -> None:
        for _ in range(6):
            response = self.delivery()
            self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["state"]["maiden_overs"], 1)
        undone = self.undo()
        self.assertEqual(undone.status_code, 200, undone.text)
        self.assertEqual(undone.json()["state"]["legal_balls"], 5)
        self.assertEqual(undone.json()["state"]["maiden_overs"], 0)
        self.assertEqual(self.stat(self.bowler).maidens, 0)

    def test_duplicate_undo_request_does_not_undo_another_delivery(self) -> None:
        self.assertEqual(self.delivery(batter_runs=2).status_code, 201)
        self.assertEqual(self.delivery(batter_runs=1).status_code, 201)
        request_id = str(uuid4())
        first = self.undo(request_id)
        repeated = self.undo(request_id)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(repeated.status_code, 200, repeated.text)
        self.assertEqual(
            repeated.json()["undone_delivery_id"],
            first.json()["undone_delivery_id"],
        )
        self.assertEqual(self.current_state()["total_runs"], 2)

    def test_rejects_invalid_extras_dismissals_batters_and_openers(self) -> None:
        response = self.delivery(
            extras_type=ExtraType.WIDE.value,
            extras_runs=0,
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.current_state()["total_runs"], 0)

        response = self.delivery(
            wicket_type=WicketType.RETIRED_HURT.value,
            dismissed_player_id=self.striker,
        )
        self.assertEqual(response.status_code, 422)

        response = self.delivery(
            batter_id=self.non_striker,
            batter_runs=1,
        )
        self.assertEqual(response.status_code, 409)

        duplicate_start = self.client.post(
            f"/api/innings/{self.innings_id}/start",
            json={
                "striker_id": self.striker,
                "non_striker_id": self.striker,
                "bowler_id": self.bowler,
            },
        )
        self.assertEqual(duplicate_start.status_code, 422)

        fresh_innings_id = self.create_second_test_innings(overs=1)
        not_in_xi = self.client.post(
            f"/api/innings/{fresh_innings_id}/start",
            json={
                "striker_id": self.players[1][1],
                "non_striker_id": self.non_striker,
                "bowler_id": self.bowler,
            },
        )
        self.assertEqual(not_in_xi.status_code, 422)

    def test_rejects_runs_for_dismissals_that_cannot_score_runs(self) -> None:
        response = self.delivery(
            batter_runs=1,
            wicket_type=WicketType.CAUGHT.value,
            dismissed_player_id=self.striker,
            incoming_batter_id=self.players[0][2],
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.current_state()["total_runs"], 0)

    def test_rejects_unknown_delivery_fields_instead_of_scoring_a_default(self) -> None:
        response = self.client.post(
            f"/api/innings/{self.innings_id}/deliveries",
            json={
                "request_id": str(uuid4()),
                "batter_id": self.striker,
                "bowler_id": self.bowler,
                "batter_rnus": 4,
            },
        )
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.current_state()["legal_balls"], 0)

    def test_undo_without_delivery_is_rejected(self) -> None:
        response = self.undo()
        self.assertEqual(response.status_code, 409)

    def test_scorecard_contains_match_lineups_statistics_and_delivery_history(self) -> None:
        request_id = str(uuid4())
        response = self.delivery(request_id=request_id, batter_runs=4)
        self.assertEqual(response.status_code, 201, response.text)

        scorecard_response = self.client.get(
            f"/api/matches/{self.match_id}/scorecard"
        )
        self.assertEqual(scorecard_response.status_code, 200, scorecard_response.text)
        scorecard = scorecard_response.json()
        self.assertEqual(scorecard["match_id"], self.match_id)
        self.assertEqual(scorecard["home_team_name"], "Salt Lake Strikers")
        innings = scorecard["innings"][0]
        self.assertEqual((len(innings["batting_xi"]), len(innings["bowling_xi"])), (11, 11))
        self.assertEqual(innings["total_runs"], 4)
        self.assertEqual(innings["deliveries"][0]["request_id"], request_id)
        self.assertEqual(innings["overs"], "0.1")
        self.assertEqual(innings["batting_xi"][0]["runs"], 4)
        self.assertTrue(innings["batting_xi"][0]["at_crease"])
        self.assertEqual(innings["deliveries"][0]["batter_runs"], 4)

        live_response = self.client.get("/api/matches/live/scorecard")
        self.assertEqual(live_response.status_code, 200, live_response.text)
        self.assertEqual(live_response.json()["match_id"], self.match_id)

    def test_next_innings_starts_chase_with_target_and_opposite_teams(self) -> None:
        for _ in range(12):
            response = self.delivery()
            self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["state"]["status"], "COMPLETED")

        next_response = self.client.post(
            f"/api/matches/{self.match_id}/next-innings"
        )
        self.assertEqual(next_response.status_code, 200, next_response.text)
        scorecard = next_response.json()
        self.assertEqual(len(scorecard["innings"]), 2)
        first, chase = scorecard["innings"]
        self.assertEqual(first["status"], "COMPLETED")
        self.assertEqual(chase["innings_number"], 2)
        self.assertEqual(chase["status"], "LIVE")
        self.assertEqual(chase["target"], first["total_runs"] + 1)
        self.assertEqual(chase["batting_team_id"], first["bowling_team_id"])
        self.assertEqual(chase["bowling_team_id"], first["batting_team_id"])
        self.assertEqual(len(chase["batting_xi"]), 11)

        repeated = self.client.post(
            f"/api/matches/{self.match_id}/next-innings"
        )
        self.assertEqual(repeated.status_code, 409)

    def finish_first_innings(self, runs: int) -> dict:
        state = self.current_state()
        for ball in range(12):
            response = self.delivery(
                batter_runs=runs if ball == 0 else 0,
                batter_id=state["striker_id"],
            )
            self.assertEqual(response.status_code, 201, response.text)
            state = response.json()["state"]
        self.assertEqual(state["status"], InningsStatus.COMPLETED)
        next_response = self.client.post(
            f"/api/matches/{self.match_id}/next-innings"
        )
        self.assertEqual(next_response.status_code, 200, next_response.text)
        chase = next_response.json()["innings"][1]
        self.assertEqual(chase["target"], runs + 1)
        opener, non_striker, bowler = (
            self.players[1][0],
            self.players[1][1],
            self.players[0][0],
        )
        started = self.client.post(
            f"/api/innings/{chase['id']}/start",
            json={
                "striker_id": opener,
                "non_striker_id": non_striker,
                "bowler_id": bowler,
            },
        )
        self.assertEqual(started.status_code, 200, started.text)
        return {"innings_id": chase["id"], "state": started.json()}

    def test_successful_chase_completes_match_with_wicket_margin(self) -> None:
        chase = self.finish_first_innings(0)
        response = self.delivery(
            innings_id=chase["innings_id"],
            batter_id=chase["state"]["striker_id"],
            bowler_id=self.players[0][0],
            batter_runs=1,
        )
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["state"]["status"], InningsStatus.COMPLETED)
        with self.session_factory() as session:
            match = session.get(Match, self.match_id)
            self.assertEqual(match.status, MatchStatus.COMPLETED)
            self.assertEqual(match.winner_team_id, self.team_ids[1])
            self.assertEqual(match.result_summary, "Park Street Panthers won by 10 wickets.")
            self.assertIsNotNone(match.completed_at)

    def test_tied_match_has_no_winner_and_stores_tied_result(self) -> None:
        chase = self.finish_first_innings(1)
        state = chase["state"]
        for ball in range(12):
            response = self.delivery(
                innings_id=chase["innings_id"],
                batter_id=state["striker_id"],
                bowler_id=self.players[0][0],
                batter_runs=1 if ball == 0 else 0,
            )
            self.assertEqual(response.status_code, 201, response.text)
            state = response.json()["state"]
        self.assertEqual(state["status"], InningsStatus.COMPLETED)
        with self.session_factory() as session:
            match = session.get(Match, self.match_id)
            self.assertEqual(match.status, MatchStatus.COMPLETED)
            self.assertIsNone(match.winner_team_id)
            self.assertEqual(match.result_summary, "Match tied at 1 run.")

    def test_first_innings_team_wins_by_runs_and_undo_reopens_final_match(self) -> None:
        chase = self.finish_first_innings(1)
        state = chase["state"]
        for _ in range(12):
            response = self.delivery(
                innings_id=chase["innings_id"],
                batter_id=state["striker_id"],
                bowler_id=self.players[0][0],
            )
            self.assertEqual(response.status_code, 201, response.text)
            state = response.json()["state"]
        with self.session_factory() as session:
            match = session.get(Match, self.match_id)
            self.assertEqual(match.winner_team_id, self.team_ids[0])
            self.assertEqual(match.result_summary, "Salt Lake Strikers won by 1 run.")
            chase_innings_id = chase["innings_id"]

        undone = self.client.post(
            f"/api/innings/{chase_innings_id}/undo",
            json={"request_id": str(uuid4())},
        )
        self.assertEqual(undone.status_code, 200, undone.text)
        with self.session_factory() as session:
            match = session.get(Match, self.match_id)
            self.assertEqual(match.status, MatchStatus.LIVE)
            self.assertIsNone(match.winner_team_id)
            self.assertIsNone(match.result_summary)
            self.assertIsNone(match.completed_at)

    def test_all_out_ends_first_innings_and_sets_target(self) -> None:
        with self.session_factory() as session:
            match = session.get(Match, self.match_id)
            innings = session.get(Innings, self.innings_id)
            match.wickets_limit = 2
            innings.wickets_limit = 2
            session.commit()
        state = self.current_state()
        first_wicket = self.delivery(
            batter_id=state["striker_id"],
            wicket_type=WicketType.BOWLED.value,
            dismissed_player_id=state["striker_id"],
            incoming_batter_id=self.players[0][2],
        )
        self.assertEqual(first_wicket.status_code, 201, first_wicket.text)
        state = first_wicket.json()["state"]
        final_wicket = self.delivery(
            batter_id=state["striker_id"],
            wicket_type=WicketType.BOWLED.value,
            dismissed_player_id=state["striker_id"],
        )
        self.assertEqual(final_wicket.status_code, 201, final_wicket.text)
        self.assertEqual(final_wicket.json()["state"]["wickets"], 2)
        self.assertEqual(final_wicket.json()["state"]["status"], InningsStatus.COMPLETED)
        with self.session_factory() as session:
            match = session.get(Match, self.match_id)
            self.assertEqual(match.status, MatchStatus.LIVE)
            self.assertIsNone(match.result_summary)
        chase = self.client.post(f"/api/matches/{self.match_id}/next-innings")
        self.assertEqual(chase.status_code, 200, chase.text)
        self.assertEqual(chase.json()["innings"][1]["target"], 1)

    def test_persisted_player_statistics_and_match_history_api(self) -> None:
        chase = self.finish_first_innings(0)
        response = self.delivery(
            innings_id=chase["innings_id"],
            batter_id=chase["state"]["striker_id"],
            bowler_id=self.players[0][0],
            batter_runs=1,
        )
        self.assertEqual(response.status_code, 201, response.text)

        batting = self.client.get("/api/statistics/players?category=batting")
        self.assertEqual(batting.status_code, 200, batting.text)
        player = next(
            row for row in batting.json() if row["id"] == self.players[1][0]
        )
        self.assertEqual(player["matches_played"], 1)
        self.assertEqual(player["total_runs"], 1)
        self.assertEqual(player["highest_score"], 1)
        self.assertIsNone(player["batting_average"])
        self.assertEqual(player["strike_rate"], 100.0)

        profile = self.client.get(
            f"/api/players/{self.players[1][0]}/statistics"
        )
        self.assertEqual(profile.status_code, 200, profile.text)
        self.assertEqual(len(profile.json()["matches"]), 1)
        self.assertEqual(profile.json()["matches"][0]["runs"], 1)

        history = self.client.get("/api/matches")
        self.assertEqual(history.status_code, 200, history.text)
        self.assertEqual(history.json()[0]["id"], self.match_id)
        self.assertEqual(history.json()[0]["status"], MatchStatus.COMPLETED.value)
        self.assertIn("won by 10 wickets", history.json()[0]["result_summary"])
        unused_batter_profile = self.client.get(
            f"/api/players/{self.players[0][2]}/statistics"
        )
        self.assertEqual(unused_batter_profile.status_code, 200)
        self.assertEqual(unused_batter_profile.json()["innings_played"], 0)

    def test_first_innings_cannot_be_undone_after_chase_starts(self) -> None:
        self.finish_first_innings(0)
        response = self.client.post(
            f"/api/innings/{self.innings_id}/undo",
            json={"request_id": str(uuid4())},
        )
        self.assertEqual(response.status_code, 409, response.text)
        with self.session_factory() as session:
            first = session.get(Innings, self.innings_id)
            self.assertEqual(first.status, InningsStatus.COMPLETED)

    def test_undo_of_winning_delivery_restores_live_match_state(self) -> None:
        chase = self.finish_first_innings(0)
        winning_ball = self.delivery(
            innings_id=chase["innings_id"],
            batter_id=chase["state"]["striker_id"],
            bowler_id=self.players[0][0],
            batter_runs=1,
        )
        self.assertEqual(winning_ball.status_code, 201)
        undone = self.client.post(
            f"/api/innings/{chase['innings_id']}/undo",
            json={"request_id": str(uuid4())},
        )
        self.assertEqual(undone.status_code, 200, undone.text)
        scorecard = self.client.get(f"/api/matches/{self.match_id}/scorecard")
        self.assertEqual(scorecard.status_code, 200)
        self.assertEqual(scorecard.json()["status"], MatchStatus.LIVE.value)
        self.assertIsNone(scorecard.json()["result_summary"])


if __name__ == "__main__":
    unittest.main()
