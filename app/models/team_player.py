from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class TeamPlayer(TimestampMixin, Base):
    __tablename__ = "team_players"
    __table_args__ = (
        UniqueConstraint("team_id", "player_id", name="uq_team_players_team_player"),
        UniqueConstraint("team_id", "jersey_number", name="uq_team_players_team_jersey"),
        UniqueConstraint("player_id", "team_id", name="uq_team_players_player_team"),
        ForeignKeyConstraint(
            ["player_id"],
            ["players.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "jersey_number IS NULL OR jersey_number BETWEEN 0 AND 999",
            name="ck_team_players_jersey_number",
        ),
        CheckConstraint(
            "role IS NULL OR length(trim(role)) BETWEEN 1 AND 40",
            name="ck_team_players_role_length",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    player_id: Mapped[int] = mapped_column(nullable=False, index=True)
    jersey_number: Mapped[int | None]
    role: Mapped[str | None] = mapped_column(String(40))

    team: Mapped[Team] = relationship(back_populates="players")
    player: Mapped[Player] = relationship(back_populates="teams")
