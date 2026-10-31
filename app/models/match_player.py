from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.orm import Mapped, foreign, mapped_column, relationship

from app.database import Base


class MatchPlayer(Base):
    __tablename__ = "match_players"
    __table_args__ = (
        ForeignKeyConstraint(
            ["match_id", "home_team_id", "away_team_id"],
            ["matches.id", "matches.home_team_id", "matches.away_team_id"],
            ondelete="CASCADE",
            name="fk_match_players_match_participants",
        ),
        ForeignKeyConstraint(
            ["player_id"],
            ["players.id"],
            ondelete="RESTRICT",
            name="fk_match_players_player",
        ),
        CheckConstraint(
            "team_id IN (home_team_id, away_team_id)",
            name="ck_match_players_team_is_participant",
        ),
        CheckConstraint(
            "batting_order BETWEEN 1 AND 11",
            name="ck_match_players_batting_order",
        ),
        UniqueConstraint(
            "match_id",
            "team_id",
            "player_id",
            name="uq_match_players_match_team_player",
        ),
        UniqueConstraint(
            "match_id",
            "team_id",
            "batting_order",
            name="uq_match_players_batting_order",
        ),
        UniqueConstraint(
            "match_id",
            "player_id",
            name="uq_match_players_player_per_match",
        ),
    )

    match_id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(primary_key=True)
    home_team_id: Mapped[int] = mapped_column(nullable=False)
    away_team_id: Mapped[int] = mapped_column(nullable=False)
    batting_order: Mapped[int] = mapped_column(nullable=False)

    match: Mapped[Match] = relationship(
        back_populates="lineups",
        foreign_keys=[match_id],
    )
    team: Mapped[Team] = relationship(
        primaryjoin="foreign(MatchPlayer.team_id) == Team.id",
        viewonly=True,
    )
    player: Mapped[Player] = relationship(
        primaryjoin="foreign(MatchPlayer.player_id) == Player.id",
        viewonly=True,
    )
