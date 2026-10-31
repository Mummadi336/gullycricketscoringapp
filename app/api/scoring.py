from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.scoring import (
    DeliveryCreate,
    DeliveryResult,
    InningsStart,
    MatchScorecard,
    ScoreStateRead,
    UndoRequest,
    UndoResult,
)
from app.services.scoring import (
    get_match_scorecard,
    record_delivery,
    start_next_innings,
    start_innings,
    undo_last_delivery,
)


router = APIRouter(tags=["cricket scoring"])


@router.get(
    "/matches/live/scorecard",
    response_model=MatchScorecard,
    summary="Get the most recently active match scorecard",
)
def live_scorecard(session: Session = Depends(get_db)) -> MatchScorecard:
    scorecard = get_match_scorecard(session, match_id=None)
    if scorecard is None:
        raise HTTPException(status_code=404, detail="There are no live matches to score.")
    return scorecard


@router.get(
    "/matches/{match_id}/scorecard",
    response_model=MatchScorecard,
    summary="Get a match scorecard",
)
def match_scorecard(
    match_id: int,
    session: Session = Depends(get_db),
) -> MatchScorecard:
    scorecard = get_match_scorecard(session, match_id=match_id)
    if scorecard is None:
        raise HTTPException(status_code=404, detail=f"Match {match_id} was not found.")
    return scorecard


@router.post(
    "/matches/{match_id}/next-innings",
    response_model=MatchScorecard,
    summary="Start the chase after the first innings is complete",
)
def next_innings(
    match_id: int,
    session: Session = Depends(get_db),
) -> MatchScorecard:
    start_next_innings(session, match_id)
    scorecard = get_match_scorecard(session, match_id)
    if scorecard is None:
        raise HTTPException(status_code=404, detail=f"Match {match_id} was not found.")
    return scorecard


@router.post(
    "/innings/{innings_id}/start",
    response_model=ScoreStateRead,
    summary="Set opening batters and bowler",
)
def start_scoring(
    innings_id: int,
    payload: InningsStart,
    session: Session = Depends(get_db),
) -> ScoreStateRead:
    return start_innings(session, innings_id, payload)


@router.post(
    "/innings/{innings_id}/deliveries",
    response_model=DeliveryResult,
    status_code=status.HTTP_201_CREATED,
    summary="Record one delivery",
)
def score_delivery(
    innings_id: int,
    payload: DeliveryCreate,
    session: Session = Depends(get_db),
) -> DeliveryResult:
    return record_delivery(session, innings_id, payload)


@router.post(
    "/innings/{innings_id}/undo",
    response_model=UndoResult,
    summary="Undo the most recent delivery",
)
def undo_delivery(
    innings_id: int,
    payload: UndoRequest,
    session: Session = Depends(get_db),
) -> UndoResult:
    return undo_last_delivery(session, innings_id, str(payload.request_id))
