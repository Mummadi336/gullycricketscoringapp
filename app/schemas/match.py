from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import MatchStatus, TossDecision


class MatchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    team_a_id: int = Field(gt=0)
    team_b_id: int = Field(gt=0)
    team_a_player_ids: list[int] = Field(min_length=11, max_length=11)
    team_b_player_ids: list[int] = Field(min_length=11, max_length=11)
    overs_limit: int = Field(ge=1, le=100)
    wickets_limit: int = Field(ge=1, le=10)
    toss_winner_team_id: int = Field(gt=0)
    toss_decision: TossDecision
    name: str | None = Field(default=None, max_length=100)
    venue: str | None = Field(default=None, max_length=120)
    scheduled_at: datetime | None = None

    @field_validator("team_a_player_ids", "team_b_player_ids")
    @classmethod
    def validate_playing_xi(cls, value: list[int]) -> list[int]:
        if any(player_id <= 0 for player_id in value):
            raise ValueError("Player IDs must be positive integers.")
        if len(set(value)) != len(value):
            raise ValueError("A player can only appear once in a playing XI.")
        return value

    @field_validator("name", "venue")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None

    @model_validator(mode="after")
    def validate_match_participants(self) -> "MatchCreate":
        if self.team_a_id == self.team_b_id:
            raise ValueError("Team A and Team B must be different teams.")
        if self.toss_winner_team_id not in {self.team_a_id, self.team_b_id}:
            raise ValueError("The toss winner must be one of the selected teams.")
        if set(self.team_a_player_ids) & set(self.team_b_player_ids):
            raise ValueError("A player cannot be selected for both playing XIs.")
        return self


class MatchTeamRead(BaseModel):
    id: int
    name: str
    short_name: str | None
    playing_xi: list[int]


class InningsRead(BaseModel):
    id: int
    innings_number: int
    batting_team_id: int
    bowling_team_id: int
    overs_limit: int
    wickets_limit: int
    target: int | None
    status: str


class MatchRead(BaseModel):
    id: int
    name: str | None
    venue: str | None
    scheduled_at: datetime | None
    status: MatchStatus
    overs_limit: int
    wickets_limit: int
    toss_winner_team_id: int
    toss_decision: TossDecision
    home_team: MatchTeamRead
    away_team: MatchTeamRead
    innings: list[InningsRead]
