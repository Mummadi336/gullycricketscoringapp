from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.statistics import PlayerProfileRead, PlayerStatisticsRead
from app.security import require_api_auth
from app.services.statistics import get_player_profile, get_player_statistics


router = APIRouter(tags=["statistics"], dependencies=[Depends(require_api_auth)])


@router.get(
    "/statistics/players",
    response_model=list[PlayerStatisticsRead],
    summary="List persisted player career statistics",
)
def player_statistics(
    category: str = Query(default="batting", pattern="^(batting|bowling|fielding)$"),
    search: str | None = Query(default=None, max_length=80),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db),
) -> list[PlayerStatisticsRead]:
    return get_player_statistics(
        session,
        order_by=category,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/players/{player_id}/statistics",
    response_model=PlayerProfileRead,
    summary="Get player career statistics and match appearances",
)
def player_profile(
    player_id: int,
    session: Session = Depends(get_db),
) -> PlayerProfileRead:
    profile = get_player_profile(session, player_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Player {player_id} was not found.")
    return profile
