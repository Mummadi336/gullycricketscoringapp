import unittest

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import Base
from app.models import (
    Delivery,
    ExtraType,
    Innings,
    Match,
    MatchStatus,
    Player,
    PlayerMatchStatistics,
    Team,
    TeamPlayer,
)


class DatabaseModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://")

        @event.listens_for(self.engine, "connect")
        def enable_foreign_keys(dbapi_connection: object, _record: object) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)

    def tearDown(self) -> None:
        self.session.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def make_match(self) -> tuple[Match, Team, Team, Player, Player]:
        home = Team(name="Salt Lake Strikers", short_name="SS")
        away = Team(name="Park Street Panthers", short_name="PP")
        batter = Player(display_name="Arjun Mehta")
        bowler = Player(display_name="Dev Kapoor")
        home.players.append(TeamPlayer(player=batter, jersey_number=7))
        away.players.append(TeamPlayer(player=bowler, jersey_number=11))
        match = Match(
            name="Sunday League",
            home_team=home,
            away_team=away,
            overs_limit=20,
            wickets_limit=10,
        )
        self.session.add(match)
        self.session.flush()
        return match, home, away, batter, bowler

    def test_create_all_registers_domain_tables(self) -> None:
        table_names = set(inspect(self.engine).get_table_names())
        self.assertTrue(
            {
                "teams",
                "players",
                "team_players",
                "matches",
                "match_players",
                "innings",
                "deliveries",
                "player_match_statistics",
            }.issubset(table_names)
        )

    def test_match_innings_delivery_and_statistics_relationships(self) -> None:
        match, home, away, batter, bowler = self.make_match()
        innings = Innings(
            match=match,
            home_team_id=home.id,
            away_team_id=away.id,
            innings_number=1,
            batting_team_id=home.id,
            bowling_team_id=away.id,
            overs_limit=match.overs_limit,
            wickets_limit=match.wickets_limit,
        )
        self.session.add(innings)
        self.session.flush()

        delivery = Delivery(
            innings=innings,
            delivery_number=1,
            batter=batter,
            bowler=bowler,
            batter_runs=4,
        )
        statistics = PlayerMatchStatistics(
            innings=innings,
            player=batter,
            runs=4,
            balls_faced=1,
            fours=1,
        )
        self.session.add_all([delivery, statistics])
        self.session.commit()

        self.assertEqual(match.status, MatchStatus.UPCOMING)
        self.assertEqual(match.innings[0].batting_team.name, home.name)
        self.assertEqual(innings.deliveries[0].batter.display_name, batter.display_name)
        self.assertEqual(innings.player_statistics[0].runs, 4)

    def test_database_rejects_invalid_team_and_innings_relationships(self) -> None:
        match, home, away, _, _ = self.make_match()
        unrelated_team = Team(name="Unrelated XI")
        self.session.add(unrelated_team)
        self.session.flush()

        invalid_innings = Innings(
            match_id=match.id,
            home_team_id=home.id,
            away_team_id=away.id,
            innings_number=1,
            batting_team_id=unrelated_team.id,
            bowling_team_id=away.id,
            overs_limit=20,
            wickets_limit=10,
        )
        self.session.add(invalid_innings)
        with self.assertRaises(IntegrityError):
            self.session.flush()
        self.session.rollback()

        invalid_match = Match(
            home_team_id=home.id,
            away_team_id=home.id,
            overs_limit=20,
            wickets_limit=10,
        )
        self.session.add(invalid_match)
        with self.assertRaises(IntegrityError):
            self.session.flush()

    def test_delivery_and_statistics_constraints_reject_invalid_records(self) -> None:
        match, home, away, batter, bowler = self.make_match()
        match.status = MatchStatus.LIVE
        innings = Innings(
            match=match,
            home_team_id=home.id,
            away_team_id=away.id,
            innings_number=1,
            batting_team_id=home.id,
            bowling_team_id=away.id,
            overs_limit=match.overs_limit,
            wickets_limit=match.wickets_limit,
        )
        self.session.add(innings)
        self.session.flush()

        illegal_wide = Delivery(
            innings=innings,
            delivery_number=1,
            batter=batter,
            bowler=bowler,
            extras_type=ExtraType.WIDE,
            extras_runs=1,
            is_legal_ball=True,
        )
        self.session.add(illegal_wide)
        with self.assertRaises(IntegrityError):
            self.session.flush()
        self.session.rollback()

        match, home, away, batter, _ = self.make_match()
        innings = Innings(
            match=match,
            home_team_id=home.id,
            away_team_id=away.id,
            innings_number=1,
            batting_team_id=home.id,
            bowling_team_id=away.id,
            overs_limit=match.overs_limit,
            wickets_limit=match.wickets_limit,
        )
        self.session.add(innings)
        self.session.flush()
        invalid_statistics = PlayerMatchStatistics(
            innings=innings,
            player=batter,
            runs=-1,
        )
        self.session.add(invalid_statistics)
        with self.assertRaises(IntegrityError):
            self.session.flush()


if __name__ == "__main__":
    unittest.main()
