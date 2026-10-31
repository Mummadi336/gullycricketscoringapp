from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class PlayerMatchStatistics(TimestampMixin, Base):
    __tablename__ = "player_match_statistics"
    __table_args__ = (
        UniqueConstraint(
            "innings_id",
            "player_id",
            name="uq_player_match_statistics_innings_player",
        ),
        CheckConstraint("runs >= 0", name="ck_player_stats_runs"),
        CheckConstraint("balls_faced >= 0", name="ck_player_stats_balls_faced"),
        CheckConstraint("fours >= 0", name="ck_player_stats_fours"),
        CheckConstraint("sixes >= 0", name="ck_player_stats_sixes"),
        CheckConstraint("wickets >= 0", name="ck_player_stats_wickets"),
        CheckConstraint("maidens >= 0", name="ck_player_stats_maidens"),
        CheckConstraint("runs_conceded >= 0", name="ck_player_stats_runs_conceded"),
        CheckConstraint("balls_bowled >= 0", name="ck_player_stats_balls_bowled"),
        CheckConstraint("catches >= 0", name="ck_player_stats_catches"),
        CheckConstraint("run_outs >= 0", name="ck_player_stats_run_outs"),
        CheckConstraint("stumpings >= 0", name="ck_player_stats_stumpings"),
        CheckConstraint(
            "not_out IN (0, 1)",
            name="ck_player_stats_not_out",
        ),
        CheckConstraint(
            "dismissed IN (0, 1)",
            name="ck_player_stats_dismissed",
        ),
        CheckConstraint(
            "fours * 4 + sixes * 6 <= runs",
            name="ck_player_stats_boundary_runs",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    innings_id: Mapped[int] = mapped_column(
        ForeignKey("innings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    runs: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    balls_faced: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    fours: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    sixes: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    wickets: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    maidens: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    runs_conceded: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    balls_bowled: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    catches: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    run_outs: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    stumpings: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    not_out: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="0")
    dismissed: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="0")

    innings: Mapped[Innings] = relationship(back_populates="player_statistics")
    player: Mapped[Player] = relationship(back_populates="match_statistics")
