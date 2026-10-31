from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import Innings, InningsStatus, Match, MatchPlayer, MatchStatus, Team, TossDecision
from app.schemas.match import InningsRead, MatchCreate, MatchRead, MatchTeamRead
from app.schemas.statistics import MatchHistoryRead
from app.security import require_api_auth
from app.services.statistics import get_match_history


router = APIRouter(tags=["matches"], dependencies=[Depends(require_api_auth)])


@router.get(
    "/matches",
    response_model=list[MatchHistoryRead],
    summary="List saved match history",
)
def list_matches(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db),
) -> list[MatchHistoryRead]:
    return get_match_history(session, limit=limit, offset=offset)


@router.post(
    "/matches",
    response_model=MatchRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a match and initialize its first innings",
)
def create_match(payload: MatchCreate, session: Session = Depends(get_db)) -> MatchRead:
    teams = session.scalars(
        select(Team)
        .options(selectinload(Team.players))
        .where(Team.id.in_([payload.team_a_id, payload.team_b_id]))
    ).all()
    teams_by_id = {team.id: team for team in teams}
    missing_team_ids = {payload.team_a_id, payload.team_b_id} - teams_by_id.keys()
    if missing_team_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Team(s) not found: {', '.join(map(str, sorted(missing_team_ids)))}.",
        )

    player_ids_by_team = {
        payload.team_a_id: payload.team_a_player_ids,
        payload.team_b_id: payload.team_b_player_ids,
    }
    for team_id, selected_ids in player_ids_by_team.items():
        roster_ids = {membership.player_id for membership in teams_by_id[team_id].players}
        invalid_ids = set(selected_ids) - roster_ids
        if invalid_ids:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Every selected player for {teams_by_id[team_id].name} must "
                    "belong to that team's roster. Invalid player ID(s): "
                    f"{', '.join(map(str, sorted(invalid_ids)))}."
                ),
            )

    toss_winner_id = payload.toss_winner_team_id
    if payload.toss_decision == TossDecision.BAT:
        batting_team_id = toss_winner_id
    else:
        batting_team_id = (
            payload.team_b_id if toss_winner_id == payload.team_a_id else payload.team_a_id
        )
    bowling_team_id = (
        payload.team_b_id if batting_team_id == payload.team_a_id else payload.team_a_id
    )
    match = Match(
        name=payload.name,
        home_team_id=payload.team_a_id,
        away_team_id=payload.team_b_id,
        venue=payload.venue,
        scheduled_at=payload.scheduled_at,
        overs_limit=payload.overs_limit,
        wickets_limit=payload.wickets_limit,
        status=MatchStatus.LIVE,
        toss_winner_team_id=toss_winner_id,
        toss_decision=payload.toss_decision,
        started_at=datetime.now(timezone.utc),
    )
    session.add(match)
    try:
        session.flush()
        innings = Innings(
            match_id=match.id,
            home_team_id=payload.team_a_id,
            away_team_id=payload.team_b_id,
            innings_number=1,
            batting_team_id=batting_team_id,
            bowling_team_id=bowling_team_id,
            overs_limit=payload.overs_limit,
            wickets_limit=payload.wickets_limit,
            target=None,
            status=InningsStatus.LIVE,
        )
        session.add(innings)
        for team_id, selected_ids in player_ids_by_team.items():
            for batting_order, player_id in enumerate(selected_ids, start=1):
                session.add(
                    MatchPlayer(
                        match_id=match.id,
                        home_team_id=payload.team_a_id,
                        away_team_id=payload.team_b_id,
                        team_id=team_id,
                        player_id=player_id,
                        batting_order=batting_order,
                    )
                )
        session.flush()
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The match could not be saved because its data conflicts with existing records.",
        ) from error

    return MatchRead(
        id=match.id,
        name=match.name,
        venue=match.venue,
        scheduled_at=match.scheduled_at,
        status=match.status,
        overs_limit=match.overs_limit,
        wickets_limit=match.wickets_limit,
        toss_winner_team_id=toss_winner_id,
        toss_decision=payload.toss_decision,
        home_team=MatchTeamRead(
            id=teams_by_id[payload.team_a_id].id,
            name=teams_by_id[payload.team_a_id].name,
            short_name=teams_by_id[payload.team_a_id].short_name,
            playing_xi=payload.team_a_player_ids,
        ),
        away_team=MatchTeamRead(
            id=teams_by_id[payload.team_b_id].id,
            name=teams_by_id[payload.team_b_id].name,
            short_name=teams_by_id[payload.team_b_id].short_name,
            playing_xi=payload.team_b_player_ids,
        ),
        innings=[
            InningsRead(
                id=innings.id,
                innings_number=innings.innings_number,
                batting_team_id=innings.batting_team_id,
                bowling_team_id=innings.bowling_team_id,
                overs_limit=innings.overs_limit,
                wickets_limit=innings.wickets_limit,
                target=innings.target,
                status=innings.status.value,
            )
        ],
    )
