from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Delivery,
    ExtraType,
    Innings,
    InningsStatus,
    MatchPlayer,
    Match,
    MatchStatus,
    PlayerMatchStatistics,
    Player,
    Team,
    WicketType,
)
from app.schemas.scoring import (
    DeliveryCreate,
    DeliveryResult,
    InningsStart,
    InningsScorecard,
    MatchScorecard,
    ScorecardDelivery,
    ScorecardPlayer,
    ScoreStateRead,
    UndoResult,
)


_BOWLER_CREDITED_DISMISSALS = {
    WicketType.BOWLED,
    WicketType.CAUGHT,
    WicketType.CAUGHT_AND_BOWLED,
    WicketType.LBW,
    WicketType.STUMPED,
    WicketType.HIT_WICKET,
}
_STAT_FIELDS = (
    "runs",
    "balls_faced",
    "fours",
    "sixes",
    "wickets",
    "maidens",
    "runs_conceded",
    "balls_bowled",
    "catches",
    "run_outs",
    "stumpings",
    "not_out",
    "dismissed",
)


def get_match_scorecard(
    session: Session,
    match_id: int | None,
) -> MatchScorecard | None:
    statement = select(Match).where(Match.status == MatchStatus.LIVE)
    if match_id is not None:
        statement = select(Match).where(Match.id == match_id)
    else:
        statement = statement.order_by(Match.started_at.desc(), Match.id.desc()).limit(1)
    match = session.scalar(statement)
    if match is None:
        return None

    teams = {
        team.id: team
        for team in session.scalars(
            select(Team).where(Team.id.in_([match.home_team_id, match.away_team_id]))
        ).all()
    }
    innings_rows = session.scalars(
        select(Innings)
        .where(Innings.match_id == match.id)
        .order_by(Innings.innings_number)
    ).all()
    scorecards: list[InningsScorecard] = []
    for innings in innings_rows:
        lineup_rows = session.execute(
            select(MatchPlayer, Player)
            .join(Player, Player.id == MatchPlayer.player_id)
            .where(
                MatchPlayer.match_id == match.id,
                MatchPlayer.team_id.in_(
                    [innings.batting_team_id, innings.bowling_team_id]
                ),
            )
            .order_by(MatchPlayer.team_id, MatchPlayer.batting_order)
        ).all()
        lineup_by_team: dict[int, list[ScorecardPlayer]] = {
            innings.batting_team_id: [],
            innings.bowling_team_id: [],
        }
        stats_rows = session.scalars(
            select(PlayerMatchStatistics).where(
                PlayerMatchStatistics.innings_id == innings.id
            )
        ).all()
        stats_by_player = {row.player_id: row for row in stats_rows}
        for membership, player in lineup_rows:
            stats = stats_by_player.get(player.id)
            lineup_by_team[membership.team_id].append(
                ScorecardPlayer(
                    id=player.id,
                    name=player.display_name,
                    runs=stats.runs if stats else 0,
                    balls=stats.balls_faced if stats else 0,
                    fours=stats.fours if stats else 0,
                    sixes=stats.sixes if stats else 0,
                    wickets=stats.wickets if stats else 0,
                    runs_conceded=stats.runs_conceded if stats else 0,
                    balls_bowled=stats.balls_bowled if stats else 0,
                    maidens=stats.maidens if stats else 0,
                    at_crease=player.id in {
                        innings.striker_id,
                        innings.non_striker_id,
                    },
                    dismissed=stats.dismissed if stats else False,
                )
            )
        batting_xi = lineup_by_team.get(innings.batting_team_id, [])
        bowling_xi = lineup_by_team.get(innings.bowling_team_id, [])
        active_deliveries = session.scalars(
            select(Delivery)
            .where(
                Delivery.innings_id == innings.id,
                Delivery.is_undone.is_(False),
            )
            .order_by(Delivery.delivery_number)
        ).all()
        legal_ball_number = 0
        delivery_rows: list[ScorecardDelivery] = []
        for delivery in active_deliveries:
            if delivery.is_legal_ball:
                legal_ball_number += 1
            ball_label = f"{legal_ball_number // 6}.{legal_ball_number % 6}"
            delivery_rows.append(
                ScorecardDelivery(
                    id=delivery.id,
                    delivery_number=delivery.delivery_number,
                    request_id=delivery.request_id,
                    over=ball_label,
                    batter_runs=delivery.batter_runs,
                    extras_type=delivery.extras_type,
                    extras_runs=delivery.extras_runs,
                    wicket_type=delivery.wicket_type,
                    dismissed_player_id=delivery.dismissed_player_id,
                )
            )
        extras = int(
            session.scalar(
                select(func.coalesce(func.sum(Delivery.extras_runs), 0)).where(
                    Delivery.innings_id == innings.id,
                    Delivery.is_undone.is_(False),
                )
            )
            or 0
        )
        scorecards.append(
            InningsScorecard(
                id=innings.id,
                innings_number=innings.innings_number,
                status=innings.status,
                batting_team_id=innings.batting_team_id,
                bowling_team_id=innings.bowling_team_id,
                total_runs=innings.total_runs,
                wickets=innings.wickets_down,
                legal_balls=innings.legal_balls,
                overs=f"{innings.legal_balls // 6}.{innings.legal_balls % 6}",
                overs_limit=innings.overs_limit,
                wickets_limit=innings.wickets_limit,
                target=innings.target,
                maiden_overs=innings.maiden_overs,
                extras=extras,
                striker_id=innings.striker_id,
                non_striker_id=innings.non_striker_id,
                current_bowler_id=innings.current_bowler_id,
                batting_xi=batting_xi,
                bowling_xi=bowling_xi,
                batters=batting_xi,
                bowlers=bowling_xi,
                deliveries=delivery_rows[-12:],
            )
        )
    home_team = teams[match.home_team_id]
    away_team = teams[match.away_team_id]
    return MatchScorecard(
        match_id=match.id,
        name=match.name,
        venue=match.venue,
        status=match.status.value,
        winner_team_id=match.winner_team_id,
        result_summary=match.result_summary,
        home_team_id=home_team.id,
        home_team_name=home_team.name,
        home_team_short_name=home_team.short_name,
        away_team_id=away_team.id,
        away_team_name=away_team.name,
        away_team_short_name=away_team.short_name,
        innings=scorecards,
    )


def start_next_innings(session: Session, match_id: int) -> Innings:
    match = session.scalar(
        select(Match).where(Match.id == match_id).with_for_update()
    )
    if match is None:
        raise HTTPException(status_code=404, detail=f"Match {match_id} was not found.")
    if match.status != MatchStatus.LIVE:
        raise HTTPException(status_code=409, detail="This match is not live.")
    innings_rows = session.scalars(
        select(Innings)
        .where(Innings.match_id == match_id)
        .order_by(Innings.innings_number)
        .with_for_update()
    ).all()
    if len(innings_rows) != 1 or innings_rows[0].status != InningsStatus.COMPLETED:
        raise HTTPException(
            status_code=409,
            detail="The first innings must be complete before the chase can start.",
        )
    first_innings = innings_rows[0]
    chase = Innings(
        match_id=match.id,
        home_team_id=match.home_team_id,
        away_team_id=match.away_team_id,
        innings_number=2,
        batting_team_id=first_innings.bowling_team_id,
        bowling_team_id=first_innings.batting_team_id,
        overs_limit=first_innings.overs_limit,
        wickets_limit=first_innings.wickets_limit,
        target=first_innings.total_runs + 1,
        status=InningsStatus.LIVE,
    )
    session.add(chase)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail="The chase could not be started because the match state changed. Reload and retry.",
        ) from error
    session.refresh(chase)
    return chase


def _innings_or_404(session: Session, innings_id: int) -> Innings:
    innings = session.scalar(
        select(Innings)
        .where(Innings.id == innings_id)
        .with_for_update()
    )
    if innings is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Innings {innings_id} was not found.",
        )
    return innings


def _lineup_ids(session: Session, innings: Innings, team_id: int) -> set[int]:
    return set(
        session.scalars(
            select(MatchPlayer.player_id).where(
                MatchPlayer.match_id == innings.match_id,
                MatchPlayer.team_id == team_id,
            )
        ).all()
    )


def _get_or_create_statistics(
    session: Session,
    innings_id: int,
    player_id: int,
) -> PlayerMatchStatistics:
    statistics = session.scalar(
        select(PlayerMatchStatistics).where(
            PlayerMatchStatistics.innings_id == innings_id,
            PlayerMatchStatistics.player_id == player_id,
        )
    )
    if statistics is None:
        statistics = PlayerMatchStatistics(
            innings_id=innings_id,
            player_id=player_id,
        )
        session.add(statistics)
        session.flush()
    return statistics


def _statistics_snapshot(
    session: Session,
    innings_id: int,
) -> list[dict[str, Any]]:
    rows = session.scalars(
        select(PlayerMatchStatistics).where(
            PlayerMatchStatistics.innings_id == innings_id
        )
    ).all()
    return [
        {
            "id": row.id,
            "player_id": row.player_id,
            **{field: getattr(row, field) for field in _STAT_FIELDS},
        }
        for row in rows
    ]


def _score_state(session: Session, innings: Innings) -> ScoreStateRead:
    extras = session.scalar(
        select(func.coalesce(func.sum(Delivery.extras_runs), 0)).where(
            Delivery.innings_id == innings.id,
            Delivery.is_undone.is_(False),
        )
    )
    return ScoreStateRead(
        innings_id=innings.id,
        status=innings.status,
        total_runs=innings.total_runs,
        wickets=innings.wickets_down,
        legal_balls=innings.legal_balls,
        overs=f"{innings.legal_balls // 6}.{innings.legal_balls % 6}",
        extras=int(extras or 0),
        maiden_overs=innings.maiden_overs,
        striker_id=innings.striker_id,
        non_striker_id=innings.non_striker_id,
        current_bowler_id=innings.current_bowler_id,
    )


def start_innings(
    session: Session,
    innings_id: int,
    payload: InningsStart,
) -> ScoreStateRead:
    innings = _innings_or_404(session, innings_id)
    if innings.status != InningsStatus.LIVE:
        raise HTTPException(status_code=409, detail="Only a live innings can be started.")
    if innings.striker_id is not None or innings.legal_balls or innings.total_runs:
        raise HTTPException(status_code=409, detail="This innings has already started.")

    batters = _lineup_ids(session, innings, innings.batting_team_id)
    bowlers = _lineup_ids(session, innings, innings.bowling_team_id)
    if payload.striker_id not in batters or payload.non_striker_id not in batters:
        raise HTTPException(
            status_code=422,
            detail="Both opening batters must be in the batting team's playing XI.",
        )
    if payload.bowler_id not in bowlers:
        raise HTTPException(
            status_code=422,
            detail="The opening bowler must be in the bowling team's playing XI.",
        )

    innings.striker_id = payload.striker_id
    innings.non_striker_id = payload.non_striker_id
    innings.current_bowler_id = payload.bowler_id
    innings.over_bowler_id = payload.bowler_id
    for player_id in batters | bowlers:
        _get_or_create_statistics(session, innings.id, player_id)
    for player_id in (payload.striker_id, payload.non_striker_id):
        _get_or_create_statistics(session, innings.id, player_id).not_out = True
    _get_or_create_statistics(session, innings.id, payload.bowler_id)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail="The innings could not be started because its state changed. Reload and retry.",
        ) from error
    return _score_state(session, innings)


def _request_fingerprint(payload: DeliveryCreate) -> str:
    data = payload.model_dump(mode="json", exclude={"request_id"})
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _delivery_result(
    session: Session,
    delivery: Delivery,
    *,
    replayed: bool,
) -> DeliveryResult:
    innings = session.get(Innings, delivery.innings_id)
    return DeliveryResult(
        delivery_id=delivery.id,
        replayed=replayed,
        state=_score_state(session, innings),
    )


def _swap_strike(innings: Innings) -> None:
    innings.striker_id, innings.non_striker_id = (
        innings.non_striker_id,
        innings.striker_id,
    )


def _is_innings_complete(innings: Innings) -> bool:
    return (
        innings.wickets_down >= innings.wickets_limit
        or innings.legal_balls >= innings.overs_limit * 6
        or (innings.target is not None and innings.total_runs >= innings.target)
    )


def _save_snapshot(session: Session, innings: Innings) -> str:
    match = session.get(Match, innings.match_id)
    snapshot = {
        "innings": {
            "total_runs": innings.total_runs,
            "wickets_down": innings.wickets_down,
            "legal_balls": innings.legal_balls,
            "maiden_overs": innings.maiden_overs,
            "striker_id": innings.striker_id,
            "non_striker_id": innings.non_striker_id,
            "current_bowler_id": innings.current_bowler_id,
            "over_bowler_id": innings.over_bowler_id,
            "current_over_runs": innings.current_over_runs,
            "status": innings.status.value,
        },
        "statistics": _statistics_snapshot(session, innings.id),
        "match": {
            "status": match.status.value,
            "winner_team_id": match.winner_team_id,
            "result_summary": match.result_summary,
            "completed_at": match.completed_at.isoformat()
            if match.completed_at
            else None,
        },
    }
    return json.dumps(snapshot, separators=(",", ":"))


def _complete_match_if_needed(
    session: Session,
    innings: Innings,
) -> None:
    if innings.innings_number != 2 or innings.status != InningsStatus.COMPLETED:
        return
    match = session.get(Match, innings.match_id)
    if match is None or match.status == MatchStatus.COMPLETED:
        return
    first_innings = session.scalar(
        select(Innings).where(
            Innings.match_id == match.id,
            Innings.innings_number == 1,
        )
    )
    if first_innings is None or first_innings.status != InningsStatus.COMPLETED:
        return

    match.status = MatchStatus.COMPLETED
    match.completed_at = datetime.now(UTC)
    if innings.total_runs == first_innings.total_runs:
        match.winner_team_id = None
        run_label = "run" if innings.total_runs == 1 else "runs"
        match.result_summary = f"Match tied at {innings.total_runs} {run_label}."
    elif innings.total_runs > first_innings.total_runs:
        wickets_remaining = max(innings.wickets_limit - innings.wickets_down, 0)
        match.winner_team_id = innings.batting_team_id
        match.result_summary = (
            f"{innings.batting_team.name} won by {wickets_remaining} "
            f"{'wicket' if wickets_remaining == 1 else 'wickets'}."
        )
    else:
        run_margin = first_innings.total_runs - innings.total_runs
        match.winner_team_id = first_innings.batting_team_id
        match.result_summary = (
            f"{first_innings.batting_team.name} won by {run_margin} "
            f"{'run' if run_margin == 1 else 'runs'}."
        )


def record_delivery(
    session: Session,
    innings_id: int,
    payload: DeliveryCreate,
) -> DeliveryResult:
    fingerprint = _request_fingerprint(payload)
    request_id = str(payload.request_id)
    existing = session.scalar(
        select(Delivery).where(
            Delivery.innings_id == innings_id,
            Delivery.request_id == request_id,
        )
    )
    if existing is not None:
        if existing.request_fingerprint != fingerprint:
            raise HTTPException(
                status_code=409,
                detail="This request ID was already used for a different delivery.",
            )
        return _delivery_result(session, existing, replayed=True)

    innings = _innings_or_404(session, innings_id)
    if innings.status != InningsStatus.LIVE:
        raise HTTPException(status_code=409, detail="This innings is not live.")
    if innings.striker_id is None or innings.non_striker_id is None:
        raise HTTPException(
            status_code=409,
            detail="Set the opening batters and bowler before recording deliveries.",
        )
    if _is_innings_complete(innings):
        raise HTTPException(status_code=409, detail="This innings is complete.")
    if payload.batter_id != innings.striker_id:
        raise HTTPException(status_code=409, detail="The supplied batter is not on strike.")
    if payload.bowler_id not in _lineup_ids(session, innings, innings.bowling_team_id):
        raise HTTPException(status_code=422, detail="The bowler is not in the playing XI.")
    at_over_start = innings.legal_balls > 0 and innings.legal_balls % 6 == 0
    if not at_over_start and payload.bowler_id != innings.current_bowler_id:
        raise HTTPException(status_code=409, detail="The bowler cannot change mid-over.")
    if not at_over_start and innings.over_bowler_id != payload.bowler_id:
        raise HTTPException(status_code=409, detail="The same bowler must complete the over.")

    if payload.wicket_type is not None:
        if payload.dismissed_player_id not in {
            innings.striker_id,
            innings.non_striker_id,
        }:
            raise HTTPException(
                status_code=422,
                detail="The dismissed player must be the striker or non-striker.",
            )
        legal_delivery = payload.extras_type not in {
            ExtraType.WIDE,
            ExtraType.NO_BALL,
        }
        innings_ends_with_wicket = (
            innings.wickets_down + 1 >= innings.wickets_limit
            or (
                legal_delivery
                and innings.legal_balls + 1 >= innings.overs_limit * 6
            )
            or (
                innings.target is not None
                and innings.total_runs
                + payload.batter_runs
                + payload.extras_runs
                >= innings.target
            )
        )
        if not innings_ends_with_wicket and payload.incoming_batter_id is None:
            raise HTTPException(
                status_code=422,
                detail="Select the incoming batter to continue after a wicket.",
            )
        if innings_ends_with_wicket and payload.incoming_batter_id is not None:
            raise HTTPException(
                status_code=422,
                detail="No incoming batter is needed because this delivery ends the innings.",
            )
        if payload.incoming_batter_id is not None:
            batting_xi = _lineup_ids(session, innings, innings.batting_team_id)
            if payload.incoming_batter_id not in batting_xi:
                raise HTTPException(
                    status_code=422,
                    detail="The incoming batter must be in the batting team's playing XI.",
                )
            if payload.incoming_batter_id in {
                innings.striker_id,
                innings.non_striker_id,
            }:
                raise HTTPException(
                    status_code=422,
                    detail="The incoming batter is already at the crease.",
                )
            incoming_stats = session.scalar(
                select(PlayerMatchStatistics).where(
                    PlayerMatchStatistics.innings_id == innings_id,
                    PlayerMatchStatistics.player_id == payload.incoming_batter_id,
                )
            )
            if incoming_stats is not None and incoming_stats.dismissed:
                raise HTTPException(
                    status_code=422,
                    detail="A dismissed batter cannot return to the crease.",
                )

    snapshot = _save_snapshot(session, innings)
    if at_over_start:
        innings.current_bowler_id = payload.bowler_id
        innings.over_bowler_id = payload.bowler_id
        innings.current_over_runs = 0

    batter_stats = _get_or_create_statistics(
        session, innings_id, payload.batter_id
    )
    bowler_stats = _get_or_create_statistics(
        session, innings_id, payload.bowler_id
    )
    is_legal = payload.extras_type not in {ExtraType.WIDE, ExtraType.NO_BALL}
    team_runs = payload.batter_runs + payload.extras_runs
    if payload.extras_type in {ExtraType.BYE, ExtraType.LEG_BYE}:
        bowler_runs = 0
    elif payload.extras_type == ExtraType.NO_BALL:
        bowler_runs = team_runs - payload.completed_runs
    else:
        bowler_runs = team_runs
    delivery_number = int(
        session.scalar(
            select(func.coalesce(func.max(Delivery.delivery_number), 0)).where(
                Delivery.innings_id == innings_id
            )
        )
        or 0
    ) + 1
    delivery = Delivery(
        innings_id=innings_id,
        delivery_number=delivery_number,
        request_id=request_id,
        request_fingerprint=fingerprint,
        state_before=snapshot,
        batter_id=payload.batter_id,
        bowler_id=payload.bowler_id,
        batter_runs=payload.batter_runs,
        extras_type=payload.extras_type,
        extras_runs=payload.extras_runs,
        completed_runs=payload.completed_runs,
        is_legal_ball=is_legal,
        wicket_type=payload.wicket_type,
        dismissed_player_id=payload.dismissed_player_id,
    )

    innings.total_runs += team_runs
    innings.current_over_runs += bowler_runs
    batter_stats.runs += payload.batter_runs
    if payload.batter_runs == 4:
        batter_stats.fours += 1
    elif payload.batter_runs == 6:
        batter_stats.sixes += 1
    if payload.extras_type not in {ExtraType.WIDE, ExtraType.NO_BALL}:
        batter_stats.balls_faced += 1
    bowler_stats.runs_conceded += bowler_runs
    if is_legal:
        innings.legal_balls += 1
        bowler_stats.balls_bowled += 1

    if (payload.batter_runs + payload.completed_runs) % 2:
        _swap_strike(innings)

    if payload.wicket_type is not None:
        dismissed_id = payload.dismissed_player_id
        dismissed_stats = _get_or_create_statistics(
            session, innings_id, dismissed_id
        )
        dismissed_stats.dismissed = True
        dismissed_stats.not_out = False
        innings.wickets_down += 1
        if payload.wicket_type in _BOWLER_CREDITED_DISMISSALS:
            bowler_stats.wickets += 1
        slot = "striker_id" if innings.striker_id == dismissed_id else "non_striker_id"
        if payload.incoming_batter_id is not None:
            setattr(innings, slot, payload.incoming_batter_id)
            _get_or_create_statistics(
                session, innings_id, payload.incoming_batter_id
            ).not_out = True
        else:
            setattr(innings, slot, None)

    completed_over = is_legal and innings.legal_balls % 6 == 0
    if completed_over:
        if innings.current_over_runs == 0:
            innings.maiden_overs += 1
            bowler_stats.maidens += 1
        innings.current_over_runs = 0
        innings.over_bowler_id = None
        if innings.striker_id is not None and innings.non_striker_id is not None:
            _swap_strike(innings)

    if _is_innings_complete(innings):
        innings.status = InningsStatus.COMPLETED
        for player_id in (innings.striker_id, innings.non_striker_id):
            if player_id is not None:
                _get_or_create_statistics(
                    session, innings_id, player_id
                ).not_out = True
        _complete_match_if_needed(session, innings)

    session.add(delivery)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        duplicate = session.scalar(
            select(Delivery).where(
                Delivery.innings_id == innings_id,
                Delivery.request_id == request_id,
            )
        )
        if duplicate is not None:
            if duplicate.request_fingerprint != fingerprint:
                raise HTTPException(
                    status_code=409,
                    detail="This request ID was already used for a different delivery.",
                ) from error
            return _delivery_result(session, duplicate, replayed=True)
        raise HTTPException(
            status_code=409,
            detail="The delivery conflicts with the latest innings state. Reload and retry.",
        ) from error
    return _delivery_result(session, delivery, replayed=False)


def _restore_snapshot(
    session: Session,
    innings: Innings,
    snapshot_text: str,
) -> None:
    snapshot = json.loads(snapshot_text)
    for field, value in snapshot["innings"].items():
        if field == "status":
            value = InningsStatus(value)
        setattr(innings, field, value)

    match_state = snapshot.get("match")
    if match_state is not None:
        match = session.get(Match, innings.match_id)
        if match is not None:
            match.status = MatchStatus(match_state["status"])
            match.winner_team_id = match_state["winner_team_id"]
            match.result_summary = match_state["result_summary"]
            match.completed_at = (
                datetime.fromisoformat(match_state["completed_at"])
                if match_state["completed_at"]
                else None
            )

    old_stats = {
        item["player_id"]: item for item in snapshot["statistics"]
    }
    existing_stats = session.scalars(
        select(PlayerMatchStatistics).where(
            PlayerMatchStatistics.innings_id == innings.id
        )
    ).all()
    for row in existing_stats:
        if row.player_id not in old_stats:
            session.delete(row)
    session.flush()

    for player_id, values in old_stats.items():
        row = session.scalar(
            select(PlayerMatchStatistics).where(
                PlayerMatchStatistics.innings_id == innings.id,
                PlayerMatchStatistics.player_id == player_id,
            )
        )
        if row is None:
            row = PlayerMatchStatistics(
                innings_id=innings.id,
                player_id=player_id,
            )
            session.add(row)
        for field in _STAT_FIELDS:
            setattr(row, field, values[field])


def undo_last_delivery(
    session: Session,
    innings_id: int,
    request_id: str,
) -> UndoResult:
    innings = _innings_or_404(session, innings_id)
    already_undone = session.scalar(
        select(Delivery).where(
            Delivery.innings_id == innings_id,
            Delivery.undo_request_id == request_id,
        )
    )
    if already_undone is not None:
        return UndoResult(
            undone_delivery_id=already_undone.id,
            state=_score_state(session, innings),
        )
    if innings.innings_number == 1 and session.scalar(
        select(Innings.id).where(
            Innings.match_id == innings.match_id,
            Innings.innings_number == 2,
        )
    ) is not None:
        raise HTTPException(
            status_code=409,
            detail="The first innings cannot be changed after the chase has started.",
        )
    delivery = session.scalar(
        select(Delivery)
        .where(
            Delivery.innings_id == innings_id,
            Delivery.is_undone.is_(False),
        )
        .order_by(Delivery.delivery_number.desc())
        .limit(1)
        .with_for_update()
    )
    if delivery is None:
        raise HTTPException(status_code=409, detail="There is no delivery to undo.")
    if delivery.state_before is None:
        raise HTTPException(
            status_code=409,
            detail="This legacy delivery does not have a reversible score snapshot.",
        )

    delivery.is_undone = True
    delivery.undo_request_id = request_id
    _restore_snapshot(session, innings, delivery.state_before)
    session.commit()
    return UndoResult(
        undone_delivery_id=delivery.id,
        state=_score_state(session, innings),
    )
