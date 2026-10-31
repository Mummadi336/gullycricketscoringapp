from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin
from app.models.enums import MatchStatus, TossDecision


class Match(TimestampMixin, Base):
    __tablename__ = "matches"
    __table_args__ = (
        CheckConstraint(
            "home_team_id <> away_team_id",
            name="ck_matches_distinct_teams",
        ),
        CheckConstraint(
            "overs_limit BETWEEN 1 AND 100",
            name="ck_matches_overs_limit",
        ),
        CheckConstraint(
            "wickets_limit BETWEEN 1 AND 10",
            name="ck_matches_wickets_limit",
        ),
        CheckConstraint(
            "winner_team_id IS NULL OR winner_team_id IN (home_team_id, away_team_id)",
            name="ck_matches_winner_is_participant",
        ),
        CheckConstraint(
            "toss_winner_team_id IS NULL OR "
            "toss_winner_team_id IN (home_team_id, away_team_id)",
            name="ck_matches_toss_winner_is_participant",
        ),
        CheckConstraint(
            "(toss_winner_team_id IS NULL AND toss_decision IS NULL) OR "
            "(toss_winner_team_id IS NOT NULL AND toss_decision IS NOT NULL)",
            name="ck_matches_toss_details",
        ),
        CheckConstraint(
            "name IS NULL OR length(trim(name)) BETWEEN 1 AND 100",
            name="ck_matches_name_length",
        ),
        CheckConstraint(
            "venue IS NULL OR length(trim(venue)) BETWEEN 1 AND 120",
            name="ck_matches_venue_length",
        ),
        UniqueConstraint(
            "id",
            "home_team_id",
            "away_team_id",
            name="uq_matches_id_participants",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str | None] = mapped_column(String(100))
    home_team_id: Mapped[int] = mapped_column(
        ForeignKey("teams.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    away_team_id: Mapped[int] = mapped_column(
        ForeignKey("teams.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    venue: Mapped[str | None] = mapped_column(String(120))
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    overs_limit: Mapped[int] = mapped_column(nullable=False, default=20, server_default="20")
    wickets_limit: Mapped[int] = mapped_column(nullable=False, default=10, server_default="10")
    status: Mapped[MatchStatus] = mapped_column(
        Enum(
            MatchStatus,
            name="match_status",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum_type: [item.value for item in enum_type],
        ),
        nullable=False,
        default=MatchStatus.UPCOMING,
        server_default=MatchStatus.UPCOMING.value,
        index=True,
    )
    winner_team_id: Mapped[int | None] = mapped_column(
        ForeignKey("teams.id", ondelete="RESTRICT"),
    )
    toss_winner_team_id: Mapped[int | None] = mapped_column(
        ForeignKey("teams.id", ondelete="RESTRICT"),
    )
    toss_decision: Mapped[TossDecision | None] = mapped_column(
        Enum(
            TossDecision,
            name="toss_decision",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum_type: [item.value for item in enum_type],
        ),
    )
    result_summary: Mapped[str | None] = mapped_column(String(200))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    home_team: Mapped[Team] = relationship(
        back_populates="home_matches",
        foreign_keys=[home_team_id],
    )
    away_team: Mapped[Team] = relationship(
        back_populates="away_matches",
        foreign_keys=[away_team_id],
    )
    winner_team: Mapped[Team | None] = relationship(foreign_keys=[winner_team_id])
    toss_winner_team: Mapped[Team | None] = relationship(
        foreign_keys=[toss_winner_team_id]
    )
    lineups: Mapped[list[MatchPlayer]] = relationship(
        back_populates="match",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="MatchPlayer.team_id, MatchPlayer.batting_order",
        foreign_keys="MatchPlayer.match_id",
    )
    innings: Mapped[list[Innings]] = relationship(
        back_populates="match",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Innings.innings_number",
        foreign_keys="Innings.match_id",
    )
