from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import ExtraType, WicketType


class Delivery(Base):
    __tablename__ = "deliveries"
    __table_args__ = (
        CheckConstraint(
            "delivery_number >= 1",
            name="ck_deliveries_delivery_number",
        ),
        CheckConstraint(
            "batter_runs >= 0",
            name="ck_deliveries_batter_runs",
        ),
        CheckConstraint(
            "extras_runs >= 0",
            name="ck_deliveries_extras_runs",
        ),
        CheckConstraint(
            "completed_runs >= 0",
            name="ck_deliveries_completed_runs",
        ),
        CheckConstraint(
            "(extras_type IS NULL AND extras_runs = 0) OR "
            "(extras_type IS NOT NULL AND extras_runs > 0)",
            name="ck_deliveries_extra_type_and_runs",
        ),
        CheckConstraint(
            "(extras_type IS NULL AND is_legal_ball = 1) OR "
            "(extras_type IN ('WIDE', 'NO_BALL') AND is_legal_ball = 0) OR "
            "(extras_type IN ('BYE', 'LEG_BYE') AND is_legal_ball = 1) OR "
            "(extras_type = 'PENALTY')",
            name="ck_deliveries_extra_legality",
        ),
        CheckConstraint(
            "(extras_type IS NULL AND extras_runs = 0 AND completed_runs = 0) OR "
            "(extras_type = 'WIDE' AND batter_runs = 0 AND extras_runs >= 1 "
            "AND completed_runs <= extras_runs - 1) OR "
            "(extras_type = 'NO_BALL' AND extras_runs >= 1 "
            "AND completed_runs <= extras_runs - 1) OR "
            "(extras_type IN ('BYE', 'LEG_BYE') AND batter_runs = 0 "
            "AND extras_runs >= 1 AND completed_runs = extras_runs)",
            name="ck_deliveries_scoring_semantics",
        ),
        CheckConstraint(
            "(wicket_type IS NULL AND dismissed_player_id IS NULL) OR "
            "(wicket_type IS NOT NULL AND dismissed_player_id IS NOT NULL)",
            name="ck_deliveries_dismissal_details",
        ),
        UniqueConstraint("innings_id", "delivery_number", name="uq_deliveries_innings_number"),
        Index(
            "uq_deliveries_innings_request",
            "innings_id",
            "request_id",
            unique=True,
        ),
        Index(
            "uq_deliveries_innings_undo_request",
            "innings_id",
            "undo_request_id",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    innings_id: Mapped[int] = mapped_column(
        ForeignKey("innings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    delivery_number: Mapped[int] = mapped_column(Integer, nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(36))
    undo_request_id: Mapped[str | None] = mapped_column(String(36))
    request_fingerprint: Mapped[str | None] = mapped_column(String(64))
    state_before: Mapped[str | None] = mapped_column(Text)
    batter_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    bowler_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    batter_runs: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    extras_type: Mapped[ExtraType | None] = mapped_column(
        Enum(
            ExtraType,
            name="delivery_extra_type",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum_type: [item.value for item in enum_type],
        ),
    )
    extras_runs: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    completed_runs: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    is_legal_ball: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="1",
    )
    wicket_type: Mapped[WicketType | None] = mapped_column(
        Enum(
            WicketType,
            name="delivery_wicket_type",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum_type: [item.value for item in enum_type],
        ),
    )
    dismissed_player_id: Mapped[int | None] = mapped_column(
        ForeignKey("players.id", ondelete="RESTRICT"),
        index=True,
    )
    is_undone: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.current_timestamp(),
        nullable=False,
    )

    innings: Mapped[Innings] = relationship(back_populates="deliveries")
    batter: Mapped[Player] = relationship(
        back_populates="deliveries_as_batter",
        foreign_keys=[batter_id],
    )
    bowler: Mapped[Player] = relationship(
        back_populates="deliveries_as_bowler",
        foreign_keys=[bowler_id],
    )
    dismissed_player: Mapped[Player | None] = relationship(
        back_populates="deliveries_dismissed",
        foreign_keys=[dismissed_player_id],
    )
