from pydantic import BaseModel, ConfigDict, Field, field_validator


def normalize_required_text(value: str) -> str:
    normalized = " ".join(value.split())
    if not normalized:
        raise ValueError("This field must not be blank.")
    return normalized


class TeamCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    short_name: str | None = Field(default=None, max_length=12)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return normalize_required_text(value)

    @field_validator("short_name")
    @classmethod
    def normalize_short_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        return normalized or None


class TeamUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    short_name: str | None = Field(default=None, max_length=12)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return normalize_required_text(value)

    @field_validator("short_name")
    @classmethod
    def normalize_short_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        return normalized or None


class TeamRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    short_name: str | None
    player_count: int


class PlayerCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=80)
    jersey_number: int | None = Field(default=None, ge=0, le=999)
    role: str | None = Field(default=None, max_length=40)

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        return normalize_required_text(value)

    @field_validator("role")
    @classmethod
    def normalize_role(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None


class PlayerUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=80)

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        return normalize_required_text(value)


class RosterDetailsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=80)
    jersey_number: int | None = Field(default=None, ge=0, le=999)
    role: str | None = Field(default=None, max_length=40)

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        return normalize_required_text(value)

    @field_validator("role")
    @classmethod
    def normalize_role(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None


class RosterPlayerRead(BaseModel):
    id: int
    display_name: str
    jersey_number: int | None
    role: str | None


class TeamRosterRead(BaseModel):
    id: int
    name: str
    short_name: str | None
    players: list[RosterPlayerRead]
