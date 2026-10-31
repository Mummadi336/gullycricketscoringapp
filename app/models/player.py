from __future__ import annotations

from sqlalchemy import CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class Player(TimestampMixin, Base):
    __tablename__ = "players"
    __table_args__ = (
        CheckConstraint(
            "length(trim(display_name)) BETWEEN 1 AND 80",
            name="ck_players_display_name_length",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False, index=True)

    teams: Mapped[list[TeamPlayer]] = relationship(
        back_populates="player",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    deliveries_as_batter: Mapped[list[Delivery]] = relationship(
        back_populates="batter",
        foreign_keys="Delivery.batter_id",
    )
    deliveries_as_bowler: Mapped[list[Delivery]] = relationship(
        back_populates="bowler",
        foreign_keys="Delivery.bowler_id",
    )
    deliveries_dismissed: Mapped[list[Delivery]] = relationship(
        back_populates="dismissed_player",
        foreign_keys="Delivery.dismissed_player_id",
    )
    match_statistics: Mapped[list[PlayerMatchStatistics]] = relationship(
        back_populates="player",
    )
