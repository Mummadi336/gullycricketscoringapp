from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import ExtraType, InningsStatus, WicketType


_SUPPORTED_EXTRAS = {
    ExtraType.WIDE,
    ExtraType.NO_BALL,
    ExtraType.BYE,
    ExtraType.LEG_BYE,
}
_SUPPORTED_DISMISSALS = set(WicketType) - {WicketType.RETIRED_HURT}


class InningsStart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    striker_id: int = Field(gt=0)
    non_striker_id: int = Field(gt=0)
    bowler_id: int = Field(gt=0)

    @model_validator(mode="after")
    def require_distinct_players(self) -> "InningsStart":
        if len({self.striker_id, self.non_striker_id, self.bowler_id}) != 3:
            raise ValueError("Striker, non-striker, and bowler must be different players.")
        return self


class DeliveryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: UUID
    batter_id: int = Field(gt=0)
    bowler_id: int = Field(gt=0)
    batter_runs: int = Field(default=0, ge=0, le=6)
    extras_type: ExtraType | None = None
    extras_runs: int = Field(default=0, ge=0)
    completed_runs: int = Field(default=0, ge=0)
    wicket_type: WicketType | None = None
    dismissed_player_id: int | None = Field(default=None, gt=0)
    incoming_batter_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_delivery(self) -> "DeliveryCreate":
        if self.extras_type is not None and self.extras_type not in _SUPPORTED_EXTRAS:
            raise ValueError("This extra type is not supported by the scoring engine.")
        if self.wicket_type is not None and self.wicket_type not in _SUPPORTED_DISMISSALS:
            raise ValueError("Retired hurt is not a dismissal.")
        if (self.wicket_type is None) != (self.dismissed_player_id is None):
            raise ValueError("A wicket type and dismissed player must be provided together.")
        if self.wicket_type is None and self.incoming_batter_id is not None:
            raise ValueError("An incoming batter is only allowed with a dismissal.")

        if self.extras_type is None:
            if self.extras_runs or self.completed_runs:
                raise ValueError("An ordinary delivery cannot include extras or extra completed runs.")
        elif self.extras_type == ExtraType.WIDE:
            if self.extras_runs < 1:
                raise ValueError("A wide must include at least one wide run.")
            if self.batter_runs:
                raise ValueError("Batter runs cannot be added to a wide delivery.")
            if self.completed_runs > self.extras_runs - 1:
                raise ValueError("Completed wide runs cannot exceed runs beyond the wide penalty.")
        elif self.extras_type == ExtraType.NO_BALL:
            if self.extras_runs < 1:
                raise ValueError("A no-ball must include its one-run penalty.")
            if self.completed_runs > self.extras_runs - 1:
                raise ValueError("Completed no-ball runs cannot exceed runs beyond the penalty.")
        else:
            if self.extras_runs < 1:
                raise ValueError("A bye or leg bye must include at least one run.")
            if self.batter_runs:
                raise ValueError("Batter runs cannot be added to a bye or leg-bye delivery.")
            if self.completed_runs != self.extras_runs:
                raise ValueError("All bye and leg-bye runs must be completed runs.")

        if self.wicket_type in {
            WicketType.BOWLED,
            WicketType.CAUGHT,
            WicketType.CAUGHT_AND_BOWLED,
            WicketType.LBW,
            WicketType.STUMPED,
            WicketType.HIT_WICKET,
            WicketType.RETIRED_OUT,
            WicketType.TIMED_OUT,
        } and (self.batter_runs or self.completed_runs):
            raise ValueError(
                "This dismissal cannot be combined with completed runs or batter runs."
            )

        if self.wicket_type is not None and self.extras_type is None and self.completed_runs:
            raise ValueError("Completed extra runs require an extra type.")
        if self.extras_type == ExtraType.WIDE and self.wicket_type not in {
            None,
            WicketType.RUN_OUT,
            WicketType.STUMPED,
            WicketType.HIT_WICKET,
            WicketType.OBSTRUCTING_THE_FIELD,
        }:
            raise ValueError("This dismissal cannot occur from a wide.")
        if self.extras_type == ExtraType.NO_BALL and self.wicket_type not in {
            None,
            WicketType.RUN_OUT,
            WicketType.RETIRED_OUT,
            WicketType.OBSTRUCTING_THE_FIELD,
            WicketType.HIT_THE_BALL_TWICE,
            WicketType.TIMED_OUT,
        }:
            raise ValueError("This dismissal cannot occur from a no-ball.")
        return self


class ScoreStateRead(BaseModel):
    innings_id: int
    status: InningsStatus
    total_runs: int
    wickets: int
    legal_balls: int
    overs: str
    extras: int
    maiden_overs: int
    striker_id: int | None
    non_striker_id: int | None
    current_bowler_id: int | None


class DeliveryResult(BaseModel):
    delivery_id: int
    replayed: bool
    state: ScoreStateRead


class UndoResult(BaseModel):
    undone_delivery_id: int
    state: ScoreStateRead


class UndoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: UUID


class ScorecardPlayer(BaseModel):
    id: int
    name: str
    runs: int
    balls: int
    fours: int
    sixes: int
    wickets: int
    runs_conceded: int
    balls_bowled: int
    maidens: int
    at_crease: bool
    dismissed: bool


class ScorecardDelivery(BaseModel):
    id: int
    delivery_number: int
    request_id: str | None
    over: str
    batter_runs: int
    extras_type: ExtraType | None
    extras_runs: int
    wicket_type: WicketType | None
    dismissed_player_id: int | None


class InningsScorecard(BaseModel):
    id: int
    innings_number: int
    status: InningsStatus
    batting_team_id: int
    bowling_team_id: int
    total_runs: int
    wickets: int
    legal_balls: int
    overs: str
    overs_limit: int
    wickets_limit: int
    target: int | None
    maiden_overs: int
    extras: int
    striker_id: int | None
    non_striker_id: int | None
    current_bowler_id: int | None
    batting_xi: list[ScorecardPlayer]
    bowling_xi: list[ScorecardPlayer]
    batters: list[ScorecardPlayer]
    bowlers: list[ScorecardPlayer]
    deliveries: list[ScorecardDelivery]


class MatchScorecard(BaseModel):
    match_id: int
    name: str | None
    venue: str | None
    status: str
    winner_team_id: int | None
    result_summary: str | None
    home_team_id: int
    home_team_name: str
    home_team_short_name: str | None
    away_team_id: int
    away_team_name: str
    away_team_short_name: str | None
    innings: list[InningsScorecard]
