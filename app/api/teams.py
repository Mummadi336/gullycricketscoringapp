from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import Match, Player, Team, TeamPlayer
from app.schemas.team import (
    PlayerCreate,
    PlayerUpdate,
    RosterDetailsUpdate,
    RosterPlayerRead,
    TeamCreate,
    TeamRead,
    TeamRosterRead,
    TeamUpdate,
)
from app.security import require_api_auth


router = APIRouter(tags=["teams and players"], dependencies=[Depends(require_api_auth)])


def get_team_or_404(session: Session, team_id: int) -> Team:
    team = session.scalar(
        select(Team)
        .options(selectinload(Team.players).selectinload(TeamPlayer.player))
        .where(Team.id == team_id)
    )
    if team is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Team {team_id} was not found.",
        )
    return team


def get_team_player_or_404(
    session: Session,
    team_id: int,
    player_id: int,
) -> TeamPlayer:
    team_player = session.scalar(
        select(TeamPlayer)
        .options(selectinload(TeamPlayer.player))
        .where(
            TeamPlayer.team_id == team_id,
            TeamPlayer.player_id == player_id,
        )
    )
    if team_player is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Player {player_id} is not on team {team_id}.",
        )
    return team_player


def roster_player_read(team_player: TeamPlayer) -> RosterPlayerRead:
    return RosterPlayerRead(
        id=team_player.player.id,
        display_name=team_player.player.display_name,
        jersey_number=team_player.jersey_number,
        role=team_player.role,
    )


def player_name_conflict(
    session: Session,
    player_id: int,
    display_name: str,
) -> bool:
    player_team_ids = select(TeamPlayer.team_id).where(
        TeamPlayer.player_id == player_id
    )
    return session.scalar(
        select(Player.id)
        .join(TeamPlayer, TeamPlayer.player_id == Player.id)
        .where(
            TeamPlayer.team_id.in_(player_team_ids),
            Player.id != player_id,
            func.lower(Player.display_name) == display_name.lower(),
        )
        .limit(1)
    ) is not None


@router.post(
    "/teams",
    response_model=TeamRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a team",
)
def create_team(payload: TeamCreate, session: Session = Depends(get_db)) -> TeamRead:
    duplicate = session.scalar(
        select(Team.id).where(func.lower(Team.name) == payload.name.lower())
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A team with this name already exists.",
        )

    team = Team(name=payload.name, short_name=payload.short_name)
    session.add(team)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A team with this name already exists.",
        ) from error
    session.refresh(team)
    return TeamRead(
        id=team.id,
        name=team.name,
        short_name=team.short_name,
        player_count=0,
    )


@router.get(
    "/teams",
    response_model=list[TeamRead],
    summary="List all teams",
)
def list_teams(session: Session = Depends(get_db)) -> list[TeamRead]:
    player_counts = (
        select(TeamPlayer.team_id, func.count(TeamPlayer.id).label("player_count"))
        .group_by(TeamPlayer.team_id)
        .subquery()
    )
    rows = session.execute(
        select(
            Team.id,
            Team.name,
            Team.short_name,
            func.coalesce(player_counts.c.player_count, 0).label("player_count"),
        )
        .outerjoin(player_counts, player_counts.c.team_id == Team.id)
        .order_by(func.lower(Team.name), Team.id)
    )
    return [
        TeamRead(
            id=row.id,
            name=row.name,
            short_name=row.short_name,
            player_count=row.player_count,
        )
        for row in rows
    ]


@router.get(
    "/teams/{team_id}",
    response_model=TeamRosterRead,
    summary="View a team's roster",
)
def get_team(team_id: int, session: Session = Depends(get_db)) -> TeamRosterRead:
    team = get_team_or_404(session, team_id)
    players = sorted(
        team.players,
        key=lambda item: (
            item.jersey_number is None,
            item.jersey_number if item.jersey_number is not None else 0,
            item.player.display_name.casefold(),
        ),
    )
    return TeamRosterRead(
        id=team.id,
        name=team.name,
        short_name=team.short_name,
        players=[roster_player_read(item) for item in players],
    )


@router.put(
    "/teams/{team_id}",
    response_model=TeamRead,
    summary="Update a team's details",
)
def update_team(
    team_id: int,
    payload: TeamUpdate,
    session: Session = Depends(get_db),
) -> TeamRead:
    team = session.get(Team, team_id)
    if team is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Team {team_id} was not found.",
        )

    duplicate = session.scalar(
        select(Team.id).where(
            func.lower(Team.name) == payload.name.lower(),
            Team.id != team_id,
        )
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A team with this name already exists.",
        )

    team.name = payload.name
    team.short_name = payload.short_name
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The team details conflict with an existing team.",
        ) from error
    session.refresh(team)
    player_count = session.scalar(
        select(func.count(TeamPlayer.id)).where(TeamPlayer.team_id == team.id)
    )
    return TeamRead(
        id=team.id,
        name=team.name,
        short_name=team.short_name,
        player_count=player_count or 0,
    )


@router.delete(
    "/teams/{team_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a team that has no match history",
)
def delete_team(team_id: int, session: Session = Depends(get_db)) -> Response:
    team = session.get(Team, team_id)
    if team is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Team {team_id} was not found.",
        )

    match_exists = session.scalar(
        select(Match.id)
        .where(
            (Match.home_team_id == team_id)
            | (Match.away_team_id == team_id)
            | (Match.winner_team_id == team_id)
        )
        .limit(1)
    )
    if match_exists is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This team cannot be deleted because it appears in match history. "
            "Remove its players or keep it for historical records.",
        )

    session.delete(team)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This team is still referenced by existing records and cannot be deleted.",
        ) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/teams/{team_id}/players",
    response_model=RosterPlayerRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a player to a team",
)
def add_player(
    team_id: int,
    payload: PlayerCreate,
    session: Session = Depends(get_db),
) -> RosterPlayerRead:
    get_team_or_404(session, team_id)
    duplicate_name = session.scalar(
        select(Player.id)
        .join(TeamPlayer, TeamPlayer.player_id == Player.id)
        .where(
            TeamPlayer.team_id == team_id,
            func.lower(Player.display_name) == payload.display_name.lower(),
        )
        .limit(1)
    )
    if duplicate_name is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A player with this name is already on this team's roster.",
        )
    if payload.jersey_number is not None:
        jersey_in_use = session.scalar(
            select(TeamPlayer.id).where(
                TeamPlayer.team_id == team_id,
                TeamPlayer.jersey_number == payload.jersey_number,
            )
        )
        if jersey_in_use is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Jersey number {payload.jersey_number} is already in use by this team.",
            )

    player = Player(display_name=payload.display_name)
    membership = TeamPlayer(
        team_id=team_id,
        player=player,
        jersey_number=payload.jersey_number,
        role=payload.role,
    )
    session.add(membership)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The player could not be added because their jersey number or roster entry conflicts.",
        ) from error
    session.refresh(player)
    return roster_player_read(membership)


@router.put(
    "/teams/{team_id}/players/{player_id}",
    response_model=RosterPlayerRead,
    summary="Edit a player's name",
)
def update_player(
    team_id: int,
    player_id: int,
    payload: PlayerUpdate,
    session: Session = Depends(get_db),
) -> RosterPlayerRead:
    membership = get_team_player_or_404(session, team_id, player_id)
    if player_name_conflict(session, player_id, payload.display_name):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A player with this name is already on this team's roster.",
        )
    membership.player.display_name = payload.display_name
    session.commit()
    session.refresh(membership.player)
    return roster_player_read(membership)


@router.patch(
    "/teams/{team_id}/players/{player_id}",
    response_model=RosterPlayerRead,
    summary="Update a player's details on a team roster",
)
def update_roster_details(
    team_id: int,
    player_id: int,
    payload: RosterDetailsUpdate,
    session: Session = Depends(get_db),
) -> RosterPlayerRead:
    membership = get_team_player_or_404(session, team_id, player_id)
    if player_name_conflict(session, player_id, payload.display_name):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A player with this name is already on this team's roster.",
        )
    if payload.jersey_number is not None:
        jersey_in_use = session.scalar(
            select(TeamPlayer.id).where(
                TeamPlayer.team_id == team_id,
                TeamPlayer.player_id != player_id,
                TeamPlayer.jersey_number == payload.jersey_number,
            )
        )
        if jersey_in_use is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Jersey number {payload.jersey_number} is already in use by this team.",
            )

    membership.player.display_name = payload.display_name
    membership.jersey_number = payload.jersey_number
    membership.role = payload.role
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The jersey number is already in use by this team.",
        ) from error
    session.refresh(membership)
    return roster_player_read(membership)


@router.delete(
    "/teams/{team_id}/players/{player_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a player from a team",
)
def remove_player(
    team_id: int,
    player_id: int,
    session: Session = Depends(get_db),
) -> Response:
    membership = get_team_player_or_404(session, team_id, player_id)
    session.delete(membership)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
