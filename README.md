# GullyScore

GullyScore is a local-first gully cricket scoring application built with FastAPI, SQLite, SQLAlchemy, and a responsive HTML/CSS/JavaScript frontend.

## Run on Windows

From the project directory in a PowerShell terminal:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
$credential = Get-Credential -Message "Set the GullyScore API username and password (16+ characters)"
$env:GULLYSCORE_USERNAME = $credential.UserName
$env:GULLYSCORE_PASSWORD = $credential.GetNetworkCredential().Password
python -m uvicorn app.main:app --reload
```

If PowerShell blocks virtual-environment activation, allow it for the current terminal process and activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Open <http://127.0.0.1:8000> for the dashboard. The frontend is built with plain HTML, CSS, and JavaScript. Team/player management, match setup, live scoring, match history, and player statistics use persisted API data. The landing/dashboard preview cards remain illustrative.

## Local deployment guide

GullyScore is currently suitable for a single-user local deployment only. API routes and the application page use one shared HTTP Basic username/password configured through environment variables. There are no individual accounts or role-based permissions. Keep Uvicorn bound to loopback (`127.0.0.1`); do not expose this service to a LAN, reverse proxy, or the public internet. Network deployment additionally requires HTTPS, stronger identity/authorization controls, and an operational database migration and backup strategy.

From PowerShell in the project directory:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
$credential = Get-Credential -Message "Set the GullyScore API username and password (16+ characters)"
$env:GULLYSCORE_USERNAME = $credential.UserName
$env:GULLYSCORE_PASSWORD = $credential.GetNetworkCredential().Password
python -m app.init_db
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The app refuses to start if either credential is missing or the password is shorter than 16 characters. The browser requests credentials when opening the app; Swagger UI can also use its **Authorize** control. Do not use `--reload` outside development. Keep the app to one Uvicorn process; SQLite and the startup schema updater are not configured for multi-worker deployment. Browse to <http://127.0.0.1:8000>. Stop the server with `Ctrl+C`, then clear the process environment:

```powershell
Remove-Item Env:GULLYSCORE_USERNAME, Env:GULLYSCORE_PASSWORD
```

The database is `gullyscore.db` in the project root and contains match and player data. Before upgrading or migrating an existing database, stop the server and make a backup outside the project folder:

```powershell
$backupDirectory = Join-Path $env:USERPROFILE "Documents\GullyScore-Backups"
New-Item -ItemType Directory -Force $backupDirectory | Out-Null
$backupName = "gullyscore-{0}.db" -f (Get-Date -Format "yyyyMMdd-HHmmss")
Copy-Item .\gullyscore.db (Join-Path $backupDirectory $backupName)
```

The current startup updater handles a limited set of earlier schemas; it is not a versioned migration system. Verify that a backup can be restored before upgrading valuable data. To validate a deployment from the project root, run `python -m unittest discover -s tests`, then check <http://127.0.0.1:8000/api/health> and <http://127.0.0.1:8000/docs>.

## Frontend preview

Use the sidebar, mobile navigation, and dashboard actions to explore these pages:

- `/#landing`: product landing page.
- `/#dashboard`: club dashboard with live-match preview and recent results.
- `/#teams`: API-backed team and player roster management.
- `/#create-match`: API-backed match setup with both playing XIs and toss selection.
- `/#live-scoring`: persistent live scorecard, delivery controls, and undo for the selected match.
- `/#history`: persisted match history with outcome filters and final score summaries.
- `/#statistics`: batting, bowling, and fielding leaderboards calculated from saved innings.
- `/#players/{player_id}`: persisted player career profile and match-by-match figures.
- `/#matches/{match_id}`: final match summary and innings scorecards.

To try match setup and live scoring, create two teams with at least 11 rostered players each, choose each playing XI, set the overs/wicket limits and toss result, then create the match. The match, lineups, toss, and innings are saved in SQLite. On the Live Scoring page, choose the opening batters and bowler, then use the delivery controls. Score changes persist across refreshes; undo asks for confirmation before restoring the complete prior delivery state.

For responsive checks, use the browser's device toolbar in VS Code or Chrome and test both a desktop viewport and a narrow mobile viewport (for example, 390 px wide). The navigation changes to a bottom bar on mobile.

The unauthenticated liveness check remains available at <http://127.0.0.1:8000/api/health>, and the interactive API docs are at <http://127.0.0.1:8000/docs>; protected API operations require Basic credentials. The SQLite database file, `gullyscore.db`, is created in the project root when the app first starts.

## Team and player management API

Team names are unique without regard to letter case. Roster names and jersey numbers are unique within each team. Removing a player removes only that roster membership and preserves their match history. A team with match history cannot be deleted.

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/teams` | Create a team |
| `GET` | `/api/teams` | List teams and roster counts |
| `GET` | `/api/teams/{team_id}` | Get a team and its roster |
| `PUT` | `/api/teams/{team_id}` | Update team name and short name |
| `DELETE` | `/api/teams/{team_id}` | Safely delete a team without match history |
| `POST` | `/api/teams/{team_id}/players` | Add a player to a roster |
| `PUT` | `/api/teams/{team_id}/players/{player_id}` | Rename a player on a roster |
| `PATCH` | `/api/teams/{team_id}/players/{player_id}` | Update player name, role, or jersey number |
| `DELETE` | `/api/teams/{team_id}/players/{player_id}` | Remove a player from a roster |

### Try the API in Swagger UI

Start the app and open <http://127.0.0.1:8000/docs>. Expand **teams and players** and try:

1. `POST /api/teams`:

   ```json
   {
     "name": "Salt Lake Strikers",
     "short_name": "SS"
   }
   ```

   Note the returned team `id`.

2. `POST /api/teams/{team_id}/players`, using that team ID:

   ```json
   {
     "display_name": "Arjun Mehta",
     "jersey_number": 7,
     "role": "Opener"
   }
   ```

   Note the returned player `id`.

3. Use `GET /api/teams/{team_id}` to check the roster, and `GET /api/teams` to see the player count.
4. Try `PATCH /api/teams/{team_id}/players/{player_id}`:

   ```json
   {
     "display_name": "Arjun Mehta",
     "jersey_number": 18,
     "role": "Captain"
   }
   ```

5. Use `PUT /api/teams/{team_id}` to rename the team. Remove the player with `DELETE /api/teams/{team_id}/players/{player_id}`, then delete the now-empty team with `DELETE /api/teams/{team_id}`.

Request validation failures return `422`, missing teams or roster memberships return `404`, and duplicate names/numbers or unsafe deletes return `409` with a readable `detail` message.

## Match creation API

`POST /api/matches` creates a live match, saves each team's selected XI, and initializes innings 1 in the same database transaction. Each XI must contain 11 distinct player IDs that are rostered to the corresponding team. The teams must be different, and the toss winner must be one of them. `toss_decision` is `BAT` or `BOWL`; the toss winner bats first for `BAT`, and the other team bats first for `BOWL`. Overs must be from 1 to 100 and wickets from 1 to 10.

Example request (replace IDs with the IDs returned by the team and roster APIs):

```json
{
  "team_a_id": 1,
  "team_b_id": 2,
  "team_a_player_ids": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
  "team_b_player_ids": [12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22],
  "overs_limit": 8,
  "wickets_limit": 7,
  "toss_winner_team_id": 1,
  "toss_decision": "BOWL",
  "name": "Sunday League · Week 13",
  "venue": "Central Park Ground",
  "scheduled_at": "2026-03-16T12:00:00Z"
}
```

The `201` response includes the stored team lineups, toss details, `LIVE` match status, and the initialized `LIVE` first innings with its batting and bowling team IDs. Open `/docs`, expand **matches**, and use `POST /api/matches` to try it interactively. Invalid XI size/duplicates, non-roster players, an unrelated toss winner, and invalid limits return `422`; missing teams return `404`.

## Cricket scoring and match results

The scoring engine exposes transactional API operations and is connected to the live scoring UI. Start an innings with `POST /api/innings/{innings_id}/start`, choosing two different batters from the batting XI and a bowler from the bowling XI:

```json
{
  "striker_id": 1,
  "non_striker_id": 2,
  "bowler_id": 12
}
```

Record a delivery with `POST /api/innings/{innings_id}/deliveries`. Each command needs a unique UUID `request_id`; retrying the same ID and payload returns the original delivery result without scoring it twice. Reusing an ID for a different payload returns `409`.

```json
{
  "request_id": "bd2cc23c-0c1a-47b6-a956-95e20a15eb14",
  "batter_id": 1,
  "bowler_id": 12,
  "batter_runs": 4
}
```

`batter_runs` accepts 0–6. For an extra, set `extras_type` to `WIDE`, `NO_BALL`, `BYE`, or `LEG_BYE` and provide `extras_runs`. Wide and no-ball extras include their required one-run penalty; no-ball batter runs are added separately. For additional no-ball byes/leg-byes, include those runs in `extras_runs` and `completed_runs`; they count for the team but are excluded from the bowler's conceded runs. Byes and leg-byes are extras and legal deliveries. Wides and no-balls are not legal deliveries. Use `completed_runs` for additional runs that physically rotate the batters on wides/no-balls; for byes and leg-byes it must equal `extras_runs`.

For a dismissal, send `wicket_type` and `dismissed_player_id`; to continue, also provide `incoming_batter_id`. The engine credits the bowler only for bowled, caught, caught-and-bowled, LBW, stumped, and hit-wicket dismissals. A run out is not charged to the bowler. Invalid dismissal/extra combinations are rejected. The engine tracks innings totals, batter and bowler statistics, strike, legal balls, and maidens. No-balls and wides do not count as balls faced; byes and leg-byes do. Dismissals such as bowled, caught, LBW, stumped, and hit wicket cannot be submitted with batter or completed runs. A bowler may change at an over boundary, not mid-over. Once the second innings exists, the first innings can no longer be changed through undo.

Undo the latest delivery with `POST /api/innings/{innings_id}/undo`, supplying a unique request ID:

```json
{
  "request_id": "73077eef-cb0f-48f6-8c8a-5d7e4f0e03d1"
}
```

The undo restores the innings state and affected player statistics from the saved pre-delivery snapshot. Retrying the same undo request ID will not undo a second delivery. Completed innings reject further scoring; completion occurs at the wicket limit, over limit, or a configured chase target.

After the first innings ends, `POST /api/matches/{match_id}/next-innings` initializes the chase with a target one run above the first-innings total. The match is automatically completed when the chase is successful or the second innings ends by all-out or the overs limit. The result is calculated transactionally: a successful chase is a win by wickets remaining; a lower second-innings total is a win by runs; equal scores are recorded as a tie. The result summary, winner, and completion time are saved on the match. Undoing the last delivery also restores the match from completed to live when that delivery decided the result.

## Match history and player statistics

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/matches?limit=50&offset=0` | List saved matches, innings totals, status, and result |
| `GET` | `/api/matches/{match_id}/scorecard` | Retrieve a saved match scorecard, including completed results |
| `GET` | `/api/statistics/players?category=batting` | List saved player career statistics; category may be `batting`, `bowling`, or `fielding` |
| `GET` | `/api/players/{player_id}/statistics` | Retrieve a player profile and match appearances |

Career summaries are derived from persisted `PlayerMatchStatistics`, match lineups, and innings for live and completed matches. Batting average is total runs divided by dismissals (null if not dismissed), strike rate is runs per 100 balls, bowling economy is conceded runs per six legal balls (null if no legal balls were bowled), and best bowling figures are the most wickets for the fewest runs in one innings. Highest score is the player's highest single-innings total. Matches played are distinct saved live/completed match lineups; innings played counts innings in which the player batted or was at the crease.

The fielding statistics tab is retained in the interface, but fielding events are not yet recorded by the current scoring flow, so it displays a clear tracking-unavailable message rather than sample figures.

Open `/#history` to filter and review match outcomes, then select **Summary** for the saved result and innings scorecards. Open `/#statistics` and select a player to view their profile, career totals, best figures, and match-by-match stats. The UI presents saved scorecards and career statistics rather than the earlier static sample leaderboard.

The Live Scoring UI uses `GET /api/matches/{match_id}/scorecard` to load and refresh the scorecard. It saves the selected match ID in browser session storage so reloads return to that match. If no match is selected, it loads the most recently active match from `GET /api/matches/live/scorecard`. After the first innings is complete, use **Start the chase**; `POST /api/matches/{match_id}/next-innings` creates the second innings with the correct target and teams. The UI displays the score, wickets, overs, run and required rates, batter and bowler figures, extras, and recent deliveries. At an over boundary, select the next bowler before recording the next delivery.

For an interactive API check, open <http://127.0.0.1:8000/docs>. Scorecard routes are grouped under **cricket scoring**. The UI workflow is available at `/#live-scoring`; when creating a match through the UI, it navigates directly to the new scorecard and prompts for opening players before the first delivery.

## Database initialization

The application creates missing tables during FastAPI startup, adds missing toss columns to existing matches, and upgrades an earlier lineup-table design without dropping saved lineup data. To initialize the schema explicitly from the project root, activate the virtual environment and run:

```powershell
python -m app.init_db
```

This command is safe to repeat: SQLAlchemy `create_all` creates missing tables without deleting existing data, and the schema migrations run only when the corresponding columns or old lineup constraint are detected.

The models live in `app/models/`. A `Team` owns roster entries through `TeamPlayer`, while `Player` is the reusable player identity. A `Match` references its home and away teams and has one or two `Innings`. Each innings records its batting/bowling teams and limits; a database constraint ensures those teams are the two teams registered for that match. Each `Delivery` is a separate, ordered record, so ball-by-ball details remain available for scorecards, undo/audit workflows, and derived totals. `PlayerMatchStatistics` stores one player's summary per innings; delivery history remains the source of truth for scoring.

`Match.status` is constrained to `UPCOMING`, `LIVE`, or `COMPLETED`. `MatchPlayer` preserves the selected player order for each side and uses a composite foreign key to restrict a lineup entry to a match participant. The API validates roster membership when the lineup is saved; lineup rows then act as match-history snapshots, so a later roster removal does not erase the match lineup. Foreign keys prevent references to missing teams and players; additional database checks reject invalid team pairings, match limits, innings targets, extras, dismissals, and negative statistics.

Run the model, API, and scoring-engine tests from the project root with Python's built-in test runner:

```powershell
python -m unittest discover -s tests
```

## Project layout

- `app/api/`: FastAPI route modules.
- `app/models/`: SQLAlchemy database models.
- `app/schemas/`: request and response validation schemas.
- `app/services/`: application and cricket-scoring rules.
- `app/static/`: browser HTML, CSS, and JavaScript.
- `tests/`: automated tests.
