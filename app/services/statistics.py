from collections import defaultdict

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.models import (
    Innings,
    Match,
    MatchPlayer,
    MatchStatus,
    Player,
    PlayerMatchStatistics,
    Team,
)
from app.schemas.statistics import (
    MatchHistoryRead,
    MatchInningsSummary,
    PlayerMatchAppearance,
    PlayerProfileRead,
    PlayerStatisticsRead,
)


_PLAYED_MATCH_STATUSES = (MatchStatus.LIVE, MatchStatus.COMPLETED)


def get_match_history(
    session: Session,
    *,
    limit: int,
    offset: int,
) -> list[MatchHistoryRead]:
    matches = session.scalars(
        select(Match)
        .order_by(
            Match.completed_at.desc(),
            Match.started_at.desc(),
            Match.id.desc(),
        )
        .limit(limit)
        .offset(offset)
    ).all()
    if not matches:
        return []

    match_ids = [match.id for match in matches]
    team_ids = {
        team_id
        for match in matches
        for team_id in (match.home_team_id, match.away_team_id)
    }
    teams = {
        team.id: team
        for team in session.scalars(select(Team).where(Team.id.in_(team_ids))).all()
    }
    innings = session.scalars(
        select(Innings)
        .where(Innings.match_id.in_(match_ids))
        .order_by(Innings.match_id, Innings.innings_number)
    ).all()
    innings_by_match: dict[int, list[Innings]] = defaultdict(list)
    for row in innings:
        innings_by_match[row.match_id].append(row)

    return [
        MatchHistoryRead(
            id=match.id,
            name=match.name,
            venue=match.venue,
            started_at=match.started_at,
            completed_at=match.completed_at,
            status=match.status,
            home_team_id=match.home_team_id,
            home_team_name=teams[match.home_team_id].name,
            home_team_short_name=teams[match.home_team_id].short_name,
            away_team_id=match.away_team_id,
            away_team_name=teams[match.away_team_id].name,
            away_team_short_name=teams[match.away_team_id].short_name,
            winner_team_id=match.winner_team_id,
            result_summary=match.result_summary,
            innings=[
                MatchInningsSummary(
                    innings_number=innings_row.innings_number,
                    batting_team_id=innings_row.batting_team_id,
                    batting_team_name=teams[innings_row.batting_team_id].name,
                    total_runs=innings_row.total_runs,
                    wickets=innings_row.wickets_down,
                    legal_balls=innings_row.legal_balls,
                    overs_limit=innings_row.overs_limit,
                    status=innings_row.status.value,
                    target=innings_row.target,
                )
                for innings_row in innings_by_match[match.id]
            ],
        )
        for match in matches
    ]


def _statistics_by_player(
    session: Session,
) -> dict[int, dict[str, int | list[tuple[int, int]]]]:
    participation = or_(
        PlayerMatchStatistics.balls_faced > 0,
        PlayerMatchStatistics.runs > 0,
        PlayerMatchStatistics.dismissed.is_(True),
        PlayerMatchStatistics.not_out.is_(True),
    )
    batting_rows = session.execute(
        select(
            PlayerMatchStatistics.player_id,
            func.sum(PlayerMatchStatistics.runs).label("runs"),
            func.sum(PlayerMatchStatistics.balls_faced).label("balls_faced"),
            func.sum(case((PlayerMatchStatistics.dismissed.is_(True), 1), else_=0)).label(
                "dismissals"
            ),
            func.max(PlayerMatchStatistics.runs).label("highest_score"),
            func.sum(case((participation, 1), else_=0)).label("innings_played"),
            func.sum(PlayerMatchStatistics.catches).label("catches"),
            func.sum(PlayerMatchStatistics.run_outs).label("run_outs"),
            func.sum(PlayerMatchStatistics.stumpings).label("stumpings"),
        )
        .join(Innings, Innings.id == PlayerMatchStatistics.innings_id)
        .join(
            MatchPlayer,
            (MatchPlayer.match_id == Innings.match_id)
            & (MatchPlayer.player_id == PlayerMatchStatistics.player_id)
            & (MatchPlayer.team_id == Innings.batting_team_id),
        )
        .join(Match, Match.id == Innings.match_id)
        .where(Match.status.in_(_PLAYED_MATCH_STATUSES))
        .group_by(PlayerMatchStatistics.player_id)
    ).all()
    bowling_rows = session.execute(
        select(
            PlayerMatchStatistics.player_id,
            func.sum(PlayerMatchStatistics.wickets).label("wickets"),
            func.sum(PlayerMatchStatistics.runs_conceded).label("runs_conceded"),
            func.sum(PlayerMatchStatistics.balls_bowled).label("balls_bowled"),
        )
        .join(Innings, Innings.id == PlayerMatchStatistics.innings_id)
        .join(
            MatchPlayer,
            (MatchPlayer.match_id == Innings.match_id)
            & (MatchPlayer.player_id == PlayerMatchStatistics.player_id)
            & (MatchPlayer.team_id == Innings.bowling_team_id),
        )
        .join(Match, Match.id == Innings.match_id)
        .where(Match.status.in_(_PLAYED_MATCH_STATUSES))
        .group_by(PlayerMatchStatistics.player_id)
    ).all()
    membership_rows = session.execute(
        select(
            MatchPlayer.player_id,
            func.count(func.distinct(MatchPlayer.match_id)).label("matches_played"),
        )
        .join(Match, Match.id == MatchPlayer.match_id)
        .where(Match.status.in_(_PLAYED_MATCH_STATUSES))
        .group_by(MatchPlayer.player_id)
    ).all()
    aggregates: dict[int, dict[str, int | list[tuple[int, int]]]] = {
        row.player_id: {
            "matches_played": row.matches_played,
            "innings_played": 0,
            "runs": 0,
            "balls_faced": 0,
            "dismissals": 0,
            "highest_score": 0,
            "wickets": 0,
            "runs_conceded": 0,
            "balls_bowled": 0,
            "catches": 0,
            "run_outs": 0,
            "stumpings": 0,
            "bowling_figures": [],
        }
        for row in membership_rows
    }

    for row in batting_rows:
        aggregate = aggregates[row.player_id]
        aggregate["innings_played"] = row.innings_played
        aggregate["runs"] = row.runs
        aggregate["balls_faced"] = row.balls_faced
        aggregate["dismissals"] = row.dismissals
        aggregate["highest_score"] = row.highest_score
        aggregate["catches"] = row.catches
        aggregate["run_outs"] = row.run_outs
        aggregate["stumpings"] = row.stumpings

    for row in bowling_rows:
        aggregate = aggregates[row.player_id]
        aggregate["wickets"] = row.wickets
        aggregate["runs_conceded"] = row.runs_conceded
        aggregate["balls_bowled"] = row.balls_bowled

    bowling_figures = session.execute(
        select(
            PlayerMatchStatistics.player_id,
            PlayerMatchStatistics.wickets,
            PlayerMatchStatistics.runs_conceded,
        )
        .join(Innings, Innings.id == PlayerMatchStatistics.innings_id)
        .join(
            MatchPlayer,
            (MatchPlayer.match_id == Innings.match_id)
            & (MatchPlayer.player_id == PlayerMatchStatistics.player_id)
            & (MatchPlayer.team_id == Innings.bowling_team_id),
        )
        .join(Match, Match.id == Innings.match_id)
        .where(Match.status.in_(_PLAYED_MATCH_STATUSES))
    ).all()
    for player_id, wickets, runs_conceded in bowling_figures:
        aggregates[player_id]["bowling_figures"].append((wickets, runs_conceded))

    return aggregates


def _player_statistics(player: Player, data: dict) -> PlayerStatisticsRead:
    wickets = data["wickets"]
    runs_conceded = data["runs_conceded"]
    balls_bowled = data["balls_bowled"]
    figures = data["bowling_figures"]
    best_wickets, best_runs = min(
        figures,
        key=lambda figure: (-figure[0], figure[1]),
        default=(0, 0),
    )
    return PlayerStatisticsRead(
        id=player.id,
        name=player.display_name,
        matches_played=data["matches_played"],
        innings_played=data["innings_played"],
        total_runs=data["runs"],
        highest_score=data["highest_score"],
        batting_average=(
            round(data["runs"] / data["dismissals"], 2)
            if data["dismissals"]
            else None
        ),
        strike_rate=(
            round(data["runs"] * 100 / data["balls_faced"], 2)
            if data["balls_faced"]
            else None
        ),
        wickets_taken=wickets,
        bowling_economy=(
            round(runs_conceded * 6 / balls_bowled, 2)
            if balls_bowled
            else None
        ),
        best_bowling_wickets=best_wickets,
        best_bowling_runs=best_runs,
        catches=data["catches"],
        run_outs=data["run_outs"],
        stumpings=data["stumpings"],
    )


def get_player_statistics(
    session: Session,
    *,
    order_by: str,
    search: str | None,
    limit: int,
    offset: int,
) -> list[PlayerStatisticsRead]:
    players_statement = select(Player).order_by(func.lower(Player.display_name))
    if search:
        players_statement = players_statement.where(
            Player.display_name.ilike(f"%{search.strip()}%")
        )
    players = session.scalars(players_statement).all()
    aggregates = _statistics_by_player(session)
    results = [
        _player_statistics(
            player,
            aggregates.get(
                player.id,
                {
                    "matches_played": 0,
                    "innings_played": 0,
                    "runs": 0,
                    "balls_faced": 0,
                    "dismissals": 0,
                    "highest_score": 0,
                    "wickets": 0,
                    "runs_conceded": 0,
                    "balls_bowled": 0,
                    "catches": 0,
                    "run_outs": 0,
                    "stumpings": 0,
                    "bowling_figures": [],
                },
            ),
        )
        for player in players
    ]
    sort_key = {
        "batting": lambda row: (-row.total_runs, -(row.batting_average or 0), row.name.lower()),
        "bowling": lambda row: (-row.wickets_taken, row.bowling_economy or float("inf"), row.name.lower()),
        "fielding": lambda row: (
            -(row.catches + row.run_outs + row.stumpings),
            row.name.lower(),
        ),
    }[order_by]
    results.sort(key=sort_key)
    return results[offset : offset + limit]


def get_player_profile(session: Session, player_id: int) -> PlayerProfileRead | None:
    player = session.get(Player, player_id)
    if player is None:
        return None
    stats = _player_statistics(
        player,
        _statistics_by_player(session).get(
            player.id,
            {
                "matches_played": 0,
                "innings_played": 0,
                "runs": 0,
                "balls_faced": 0,
                "dismissals": 0,
                "highest_score": 0,
                "wickets": 0,
                "runs_conceded": 0,
                "balls_bowled": 0,
                "catches": 0,
                "run_outs": 0,
                "stumpings": 0,
                "bowling_figures": [],
            },
        ),
    )
    home_team = aliased(Team)
    away_team = aliased(Team)
    appearances = session.execute(
        select(Match, home_team, away_team, PlayerMatchStatistics, Innings)
        .join(MatchPlayer, MatchPlayer.match_id == Match.id)
        .join(home_team, home_team.id == Match.home_team_id)
        .join(away_team, away_team.id == Match.away_team_id)
        .outerjoin(
            Innings,
            Innings.match_id == Match.id,
        )
        .outerjoin(
            PlayerMatchStatistics,
            (PlayerMatchStatistics.innings_id == Innings.id)
            & (PlayerMatchStatistics.player_id == player.id),
        )
        .where(
            MatchPlayer.player_id == player.id,
            Match.status.in_(_PLAYED_MATCH_STATUSES),
        )
        .order_by(Match.completed_at.desc(), Match.started_at.desc(), Match.id.desc())
    ).all()
    appearances_by_match: dict[int, dict] = {}
    for match, home, away, player_stats, _innings in appearances:
        appearance = appearances_by_match.setdefault(
            match.id,
            {
                "match": match,
                "home": home,
                "away": away,
                "runs": 0,
                "balls_faced": 0,
                "wickets": 0,
                "runs_conceded": 0,
                "balls_bowled": 0,
            },
        )
        if player_stats is not None:
            appearance["runs"] += player_stats.runs
            appearance["balls_faced"] += player_stats.balls_faced
            appearance["wickets"] += player_stats.wickets
            appearance["runs_conceded"] += player_stats.runs_conceded
            appearance["balls_bowled"] += player_stats.balls_bowled
    return PlayerProfileRead(
        **stats.model_dump(),
        matches=[
            PlayerMatchAppearance(
                match_id=appearance["match"].id,
                name=appearance["match"].name,
                date=appearance["match"].completed_at or appearance["match"].started_at,
                home_team_name=appearance["home"].name,
                away_team_name=appearance["away"].name,
                status=appearance["match"].status,
                result_summary=appearance["match"].result_summary,
                runs=appearance["runs"],
                balls_faced=appearance["balls_faced"],
                wickets=appearance["wickets"],
                runs_conceded=appearance["runs_conceded"],
                balls_bowled=appearance["balls_bowled"],
            )
            for appearance in appearances_by_match.values()
        ],
    )
