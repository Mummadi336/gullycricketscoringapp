from __future__ import annotations

from sqlalchemy import CheckConstraint, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class Team(TimestampMixin, Base):
    __tablename__ = "teams"
    __table_args__ = (
        CheckConstraint(
            "length(trim(name)) BETWEEN 1 AND 80",
            name="ck_teams_name_length",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    short_name: Mapped[str | None] = mapped_column(String(12))

    players: Mapped[list[TeamPlayer]] = relationship(
        back_populates="team",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    home_matches: Mapped[list[Match]] = relationship(
        back_populates="home_team",
        foreign_keys="Match.home_team_id",
    )
    away_matches: Mapped[list[Match]] = relationship(
        back_populates="away_team",
        foreign_keys="Match.away_team_id",
    )


Index("uq_teams_name_case_insensitive", func.lower(Team.name), unique=True)
