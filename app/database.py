import sqlite3
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import Engine, URL, create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATABASE_PATH = PROJECT_ROOT / "gullyscore.db"

DATABASE_URL = URL.create(
    drivername="sqlite",
    database=str(DATABASE_PATH),
)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def enable_sqlite_foreign_keys(
    dbapi_connection: sqlite3.Connection,
    _connection_record: object,
) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    pass


def _migrate_existing_schema(database_engine: Engine) -> None:
    inspector = inspect(database_engine)
    with database_engine.begin() as connection:
        if inspector.has_table("matches"):
            match_columns = {
                column["name"] for column in inspector.get_columns("matches")
            }
            if "toss_winner_team_id" not in match_columns:
                connection.execute(
                    text(
                        "ALTER TABLE matches ADD COLUMN toss_winner_team_id "
                        "INTEGER REFERENCES teams(id) ON DELETE RESTRICT"
                    )
                )
            if "toss_decision" not in match_columns:
                connection.execute(
                    text(
                        "ALTER TABLE matches ADD COLUMN toss_decision VARCHAR(4) "
                        "CHECK (toss_decision IS NULL OR toss_decision IN ('BAT', 'BOWL'))"
                    )
                )

        if inspector.has_table("innings"):
            innings_columns = {
                column["name"] for column in inspector.get_columns("innings")
            }
            additions = {
                "total_runs": "INTEGER NOT NULL DEFAULT 0",
                "wickets_down": "INTEGER NOT NULL DEFAULT 0",
                "legal_balls": "INTEGER NOT NULL DEFAULT 0",
                "maiden_overs": "INTEGER NOT NULL DEFAULT 0",
                "striker_id": "INTEGER REFERENCES players(id) ON DELETE RESTRICT",
                "non_striker_id": "INTEGER REFERENCES players(id) ON DELETE RESTRICT",
                "current_bowler_id": "INTEGER REFERENCES players(id) ON DELETE RESTRICT",
                "over_bowler_id": "INTEGER REFERENCES players(id) ON DELETE RESTRICT",
                "current_over_runs": "INTEGER NOT NULL DEFAULT 0",
            }
            for column_name, definition in additions.items():
                if column_name not in innings_columns:
                    connection.exec_driver_sql(
                        f"ALTER TABLE innings ADD COLUMN {column_name} {definition}"
                    )

        if inspector.has_table("deliveries"):
            delivery_columns = {
                column["name"] for column in inspector.get_columns("deliveries")
            }
            additions = {
                "request_id": "VARCHAR(36)",
                "undo_request_id": "VARCHAR(36)",
                "request_fingerprint": "VARCHAR(64)",
                "state_before": "TEXT",
                "completed_runs": "INTEGER NOT NULL DEFAULT 0",
            }
            for column_name, definition in additions.items():
                if column_name not in delivery_columns:
                    connection.exec_driver_sql(
                        f"ALTER TABLE deliveries ADD COLUMN {column_name} {definition}"
                    )
            connection.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "uq_deliveries_innings_request "
                "ON deliveries (innings_id, request_id)"
            )
            connection.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "uq_deliveries_innings_undo_request "
                "ON deliveries (innings_id, undo_request_id)"
            )

        if inspector.has_table("player_match_statistics"):
            stats_columns = {
                column["name"]
                for column in inspector.get_columns("player_match_statistics")
            }
            if "maidens" not in stats_columns:
                connection.exec_driver_sql(
                    "ALTER TABLE player_match_statistics "
                    "ADD COLUMN maidens INTEGER NOT NULL DEFAULT 0"
                )
            if "dismissed" not in stats_columns:
                connection.exec_driver_sql(
                    "ALTER TABLE player_match_statistics "
                    "ADD COLUMN dismissed BOOLEAN NOT NULL DEFAULT 0"
                )

        if inspect(connection).has_table("match_players"):
            foreign_keys = inspect(connection).get_foreign_keys("match_players")
            if any(key["referred_table"] == "team_players" for key in foreign_keys):
                connection.exec_driver_sql(
                    "ALTER TABLE match_players RENAME TO match_players_legacy"
                )
                from app.models.match_player import MatchPlayer

                MatchPlayer.__table__.create(connection)
                lineup_columns = (
                    "match_id, team_id, player_id, home_team_id, away_team_id, "
                    "batting_order"
                )
                connection.exec_driver_sql(
                    f"INSERT INTO match_players ({lineup_columns}) "
                    f"SELECT {lineup_columns} FROM match_players_legacy"
                )
                connection.exec_driver_sql("DROP TABLE match_players_legacy")


def initialize_database() -> None:
    from app import models as _models

    _migrate_existing_schema(engine)
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
