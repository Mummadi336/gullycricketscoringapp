from enum import Enum


class MatchStatus(str, Enum):
    UPCOMING = "UPCOMING"
    LIVE = "LIVE"
    COMPLETED = "COMPLETED"


class TossDecision(str, Enum):
    BAT = "BAT"
    BOWL = "BOWL"


class InningsStatus(str, Enum):
    UPCOMING = "UPCOMING"
    LIVE = "LIVE"
    COMPLETED = "COMPLETED"


class ExtraType(str, Enum):
    WIDE = "WIDE"
    NO_BALL = "NO_BALL"
    BYE = "BYE"
    LEG_BYE = "LEG_BYE"
    PENALTY = "PENALTY"


class WicketType(str, Enum):
    BOWLED = "BOWLED"
    CAUGHT = "CAUGHT"
    CAUGHT_AND_BOWLED = "CAUGHT_AND_BOWLED"
    LBW = "LBW"
    RUN_OUT = "RUN_OUT"
    STUMPED = "STUMPED"
    HIT_WICKET = "HIT_WICKET"
    RETIRED_HURT = "RETIRED_HURT"
    RETIRED_OUT = "RETIRED_OUT"
    OBSTRUCTING_THE_FIELD = "OBSTRUCTING_THE_FIELD"
    HIT_THE_BALL_TWICE = "HIT_THE_BALL_TWICE"
    TIMED_OUT = "TIMED_OUT"
