from datetime import datetime

from pydantic import BaseModel

from app.models.enums import MatchStatus


class MatchInningsSummary(BaseModel):
    innings_number: int
    batting_team_id: int
    batting_team_name: str
    total_runs: int
    wickets: int
    legal_balls: int
    overs_limit: int
    status: str
    target: int | None


class MatchHistoryRead(BaseModel):
    id: int
    name: str | None
    venue: str | None
    started_at: datetime | None
    completed_at: datetime | None
    status: MatchStatus
    home_team_id: int
    home_team_name: str
    home_team_short_name: str | None
    away_team_id: int
    away_team_name: str
    away_team_short_name: str | None
    winner_team_id: int | None
    result_summary: str | None
    innings: list[MatchInningsSummary]


class PlayerStatisticsRead(BaseModel):
    id: int
    name: str
    matches_played: int
    innings_played: int
    total_runs: int
    highest_score: int
    batting_average: float | None
    strike_rate: float | None
    wickets_taken: int
    bowling_economy: float | None
    best_bowling_wickets: int
    best_bowling_runs: int
    catches: int
    run_outs: int
    stumpings: int


class PlayerMatchAppearance(BaseModel):
    match_id: int
    name: str | None
    date: datetime | None
    home_team_name: str
    away_team_name: str
    status: MatchStatus
    result_summary: str | None
    runs: int
    balls_faced: int
    wickets: int
    runs_conceded: int
    balls_bowled: int


class PlayerProfileRead(PlayerStatisticsRead):
    matches: list[PlayerMatchAppearance]
