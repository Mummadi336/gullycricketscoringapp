import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.teams import router
from app.database import Base, get_db
from app.models import Match, MatchStatus, Player, Team, TeamPlayer

class TeamApiTests(unittest.TestCase):
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

        def override_get_db():
            with self.session_factory() as session:
                yield session

        self.app = FastAPI()
        self.app.include_router(router, prefix="/api")
        self.app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.client.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def create_team(self, name: str = "Salt Lake Strikers") -> dict:
        response = self.client.post(
            "/api/teams",
            json={"name": name, "short_name": "ss"},
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_team_crud_and_roster_management(self) -> None:
        team = self.create_team()
        team_id = team["id"]
        self.assertEqual(team["short_name"], "SS")

        added = self.client.post(
            f"/api/teams/{team_id}/players",
            json={"display_name": "  Arjun   Mehta ", "jersey_number": 7, "role": "Opener"},
        )
        self.assertEqual(added.status_code, 201, added.text)
        player = added.json()
        self.assertEqual(player["display_name"], "Arjun Mehta")

        updated_player = self.client.patch(
            f"/api/teams/{team_id}/players/{player['id']}",
            json={"display_name": "Arjun Mehta", "jersey_number": 18, "role": "Captain"},
        )
        self.assertEqual(updated_player.status_code, 200, updated_player.text)
        self.assertEqual(updated_player.json()["jersey_number"], 18)

        renamed_player = self.client.put(
            f"/api/teams/{team_id}/players/{player['id']}",
            json={"display_name": "Arjun M."},
        )
        self.assertEqual(renamed_player.status_code, 200, renamed_player.text)
        self.assertEqual(renamed_player.json()["display_name"], "Arjun M.")

        roster = self.client.get(f"/api/teams/{team_id}")
        self.assertEqual(roster.status_code, 200)
        self.assertEqual(roster.json()["players"][0]["role"], "Captain")

        team_update = self.client.put(
            f"/api/teams/{team_id}",
            json={"name": "Salt Lake Stars", "short_name": "SLS"},
        )
        self.assertEqual(team_update.status_code, 200, team_update.text)
        self.assertEqual(team_update.json()["player_count"], 1)

        team_list = self.client.get("/api/teams")
        self.assertEqual(team_list.status_code, 200)
        self.assertEqual(team_list.json()[0]["name"], "Salt Lake Stars")

        removed = self.client.delete(f"/api/teams/{team_id}/players/{player['id']}")
        self.assertEqual(removed.status_code, 204)
        self.assertEqual(self.client.get(f"/api/teams/{team_id}").json()["players"], [])

        deleted = self.client.delete(f"/api/teams/{team_id}")
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(self.client.get("/api/teams").json(), [])

    def test_validation_duplicate_names_and_not_found_responses(self) -> None:
        self.create_team()
        duplicate = self.client.post(
            "/api/teams",
            json={"name": "salt lake strikers"},
        )
        self.assertEqual(duplicate.status_code, 409)
        self.assertIn("already exists", duplicate.json()["detail"])

        blank_team = self.client.post("/api/teams", json={"name": "   "})
        self.assertEqual(blank_team.status_code, 422)

        missing_team = self.client.get("/api/teams/999")
        self.assertEqual(missing_team.status_code, 404)

    def test_duplicate_roster_entries_and_jersey_numbers_are_rejected(self) -> None:
        team_id = self.create_team()["id"]
        self.assertEqual(
            self.client.post(
                f"/api/teams/{team_id}/players",
                json={"display_name": "Arjun Mehta", "jersey_number": 7},
            ).status_code,
            201,
        )
        duplicate_name = self.client.post(
            f"/api/teams/{team_id}/players",
            json={"display_name": "arjun mehta", "jersey_number": 8},
        )
        self.assertEqual(duplicate_name.status_code, 409)

        duplicate_jersey = self.client.post(
            f"/api/teams/{team_id}/players",
            json={"display_name": "Rohan Das", "jersey_number": 7},
        )
        self.assertEqual(duplicate_jersey.status_code, 409)

        invalid_jersey = self.client.post(
            f"/api/teams/{team_id}/players",
            json={"display_name": "Kabir Sen", "jersey_number": 1000},
        )
        self.assertEqual(invalid_jersey.status_code, 422)

    def test_team_with_match_history_cannot_be_deleted(self) -> None:
        home = self.create_team("Home XI")
        away = self.create_team("Away XI")
        with self.session_factory() as session:
            session.add(
                Match(
                    home_team_id=home["id"],
                    away_team_id=away["id"],
                    overs_limit=20,
                    wickets_limit=10,
                    status=MatchStatus.UPCOMING,
                )
            )
            session.commit()

        response = self.client.delete(f"/api/teams/{home['id']}")
        self.assertEqual(response.status_code, 409)
        self.assertIn("match history", response.json()["detail"])
        self.assertEqual(self.client.get(f"/api/teams/{home['id']}").status_code, 200)

    def test_player_name_update_preserves_unique_names_across_all_rosters(self) -> None:
        first_team = self.create_team("First XI")
        second_team = self.create_team("Second XI")
        player = self.client.post(
            f"/api/teams/{first_team['id']}/players",
            json={"display_name": "Arjun Mehta"},
        ).json()
        with self.session_factory() as session:
            session.add(
                TeamPlayer(
                    team_id=second_team["id"],
                    player_id=player["id"],
                )
            )
            session.add(Player(display_name="Rohan Das"))
            session.flush()
            second_player = session.scalar(
                select(Player).where(Player.display_name == "Rohan Das")
            )
            self.assertIsNotNone(second_player)
            session.add(
                TeamPlayer(
                    team_id=second_team["id"],
                    player_id=second_player.id,
                )
            )
            session.commit()

        conflict = self.client.put(
            f"/api/teams/{first_team['id']}/players/{player['id']}",
            json={"display_name": "Rohan Das"},
        )
        self.assertEqual(conflict.status_code, 409)


if __name__ == "__main__":
    unittest.main()
