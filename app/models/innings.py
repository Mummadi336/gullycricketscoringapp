from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin
from app.models.enums import InningsStatus


class Innings(TimestampMixin, Base):
    __tablename__ = "innings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["match_id", "home_team_id", "away_team_id"],
            ["matches.id", "matches.home_team_id", "matches.away_team_id"],
            ondelete="CASCADE",
            name="fk_innings_match_participants",
        ),
        CheckConstraint(
            "innings_number IN (1, 2)",
            name="ck_innings_number",
        ),
        CheckConstraint(
            "home_team_id <> away_team_id",
            name="ck_innings_distinct_teams",
        ),
        CheckConstraint(
            "batting_team_id IN (home_team_id, away_team_id)",
            name="ck_innings_batting_team_is_participant",
        ),
        CheckConstraint(
            "bowling_team_id IN (home_team_id, away_team_id)",
            name="ck_innings_bowling_team_is_participant",
        ),
        CheckConstraint(
            "batting_team_id <> bowling_team_id",
            name="ck_innings_distinct_batting_bowling_teams",
        ),
        CheckConstraint(
            "overs_limit BETWEEN 1 AND 100",
            name="ck_innings_overs_limit",
        ),
        CheckConstraint(
            "wickets_limit BETWEEN 1 AND 10",
            name="ck_innings_wickets_limit",
        ),
        CheckConstraint(
            "target IS NULL OR target >= 1",
            name="ck_innings_target",
        ),
        CheckConstraint(
            "total_runs >= 0 AND wickets_down BETWEEN 0 AND wickets_limit "
            "AND legal_balls BETWEEN 0 AND overs_limit * 6 AND maiden_overs >= 0 "
            "AND current_over_runs >= 0",
            name="ck_innings_score_state",
        ),
        CheckConstraint(
            "striker_id IS NULL OR non_striker_id IS NULL OR striker_id <> non_striker_id",
            name="ck_innings_distinct_active_batters",
        ),
        UniqueConstraint("match_id", "innings_number", name="uq_innings_match_number"),
        UniqueConstraint("id", "batting_team_id", name="uq_innings_id_batting_team"),
        UniqueConstraint("id", "bowling_team_id", name="uq_innings_id_bowling_team"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(nullable=False, index=True)
    home_team_id: Mapped[int] = mapped_column(nullable=False)
    away_team_id: Mapped[int] = mapped_column(nullable=False)
    innings_number: Mapped[int] = mapped_column(nullable=False)
    batting_team_id: Mapped[int] = mapped_column(
        ForeignKey("teams.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    bowling_team_id: Mapped[int] = mapped_column(
        ForeignKey("teams.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    overs_limit: Mapped[int] = mapped_column(nullable=False)
    wickets_limit: Mapped[int] = mapped_column(nullable=False)
    target: Mapped[int | None]
    total_runs: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    wickets_down: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    legal_balls: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    maiden_overs: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    striker_id: Mapped[int | None] = mapped_column(ForeignKey("players.id", ondelete="RESTRICT"))
    non_striker_id: Mapped[int | None] = mapped_column(ForeignKey("players.id", ondelete="RESTRICT"))
    current_bowler_id: Mapped[int | None] = mapped_column(ForeignKey("players.id", ondelete="RESTRICT"))
    over_bowler_id: Mapped[int | None] = mapped_column(ForeignKey("players.id", ondelete="RESTRICT"))
    current_over_runs: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    status: Mapped[InningsStatus] = mapped_column(
        Enum(
            InningsStatus,
            name="innings_status",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum_type: [item.value for item in enum_type],
        ),
        nullable=False,
        default=InningsStatus.UPCOMING,
        server_default=InningsStatus.UPCOMING.value,
    )

    match: Mapped[Match] = relationship(
        back_populates="innings",
        foreign_keys=[match_id],
    )
    batting_team: Mapped[Team] = relationship(foreign_keys=[batting_team_id])
    bowling_team: Mapped[Team] = relationship(foreign_keys=[bowling_team_id])
    deliveries: Mapped[list[Delivery]] = relationship(
        back_populates="innings",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Delivery.delivery_number",
    )
    player_statistics: Mapped[list[PlayerMatchStatistics]] = relationship(
        back_populates="innings",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
