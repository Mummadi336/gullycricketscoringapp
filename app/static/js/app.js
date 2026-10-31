const viewRoot = document.querySelector("#view-root");
const toast = document.querySelector("#toast");
const pageLabel = document.querySelector("#page-label");

const pageNames = {
  landing: "Welcome",
  dashboard: "Dashboard",
  teams: "Teams & players",
  "create-match": "Create match",
  "live-scoring": "Live scoring",
  history: "Match history",
  statistics: "Player statistics",
  "player-profile": "Player profile",
  "match-summary": "Match summary",
};

const recentMatches = [
  { date: "Oct 26, 2025", home: "Salt Lake Strikers", homeCode: "SS", away: "Lake Town Lions", awayCode: "LL", score: "142/6", opponentScore: "128/9", result: "Won by 14 runs", outcome: "win" },
  { date: "Oct 19, 2025", home: "Salt Lake Strikers", homeCode: "SS", away: "Ballygunge Blasters", awayCode: "BB", score: "96/8", opponentScore: "99/4", result: "Lost by 6 wickets", outcome: "loss" },
  { date: "Oct 12, 2025", home: "Salt Lake Strikers", homeCode: "SS", away: "New Town Knights", awayCode: "NK", score: "167/5", opponentScore: "151/8", result: "Won by 16 runs", outcome: "win" },
  { date: "Oct 05, 2025", home: "Salt Lake Strikers", homeCode: "SS", away: "Howrah Hurricanes", awayCode: "HH", score: "118/7", opponentScore: "114/9", result: "Won by 4 runs", outcome: "win" },
  { date: "Sep 28, 2025", home: "Salt Lake Strikers", homeCode: "SS", away: "Park Street Panthers", awayCode: "PP", score: "131/6", opponentScore: "132/5", result: "Lost by 5 wickets", outcome: "loss" },
  { date: "Sep 21, 2025", home: "Salt Lake Strikers", homeCode: "SS", away: "Dum Dum Daredevils", awayCode: "DD", score: "154/4", opponentScore: "146/8", result: "Won by 8 runs", outcome: "win" },
];

const liveMatch = {
  home: "Salt Lake Strikers",
  homeCode: "SS",
  away: "Park Street Panthers",
  awayCode: "PP",
  venue: "Central Park Ground",
  competition: "SUNDAY LEAGUE · WEEK 12",
  innings: 2,
  battingFirstTeam: "away",
  target: 148,
  oversLimit: 20,
  wicketsLimit: 10,
  battingFirstScore: 147,
  battingFirstWickets: 8,
  battingFirstOvers: "20.0",
  score: 86,
  wickets: 4,
  legalBalls: 75,
  extras: { wd: 3, nb: 1, b: 2, lb: 1 },
  batters: [
    { name: "Rohan Das", runs: 32, balls: 24, active: true },
    { name: "Kabir Sen", runs: 18, balls: 14, active: false },
  ],
  bowler: "Dev Kapoor",
  bowlerFigures: "2/24 (3.3)",
  ballHistory: ["0", "4", "1"],
  commentary: [
    { over: "12.3", text: "Kabir Sen tucks it into the leg side. Easy single, and that's 86 up for the Strikers." },
    { over: "12.2", text: "Just two! Well run between the wickets in the deep." },
    { over: "12.1", text: "Good length outside off. Rohan opens the face and finds the gap for four." },
  ],
  undoStack: [],
};

let activeHistoryFilter = "all";
let activeStatTab = "batting";
let matchHistory = [];
let matchHistoryLoading = false;
let matchHistoryError = "";
let matchHistoryLoadId = 0;
let playerStatistics = [];
let playerStatisticsLoading = false;
let playerStatisticsError = "";
let playerStatisticsLoadId = 0;
let playerProfile = null;
let playerProfileLoadId = 0;
let selectedMatchSummary = null;
let matchSummaryLoadId = 0;
let toastTimeout;
let selectedTeamId = null;
let cachedTeams = [];
let teamLoadId = 0;
let matchSetupLoadId = 0;
let matchRosterRequests = { a: 0, b: 0 };
let matchRosters = { a: [], b: [] };
let activeScorecard = null;
let scoringRequestPending = false;
let scorecardLoading = false;
let scorecardLoadId = 0;
let scoringErrorMessage = "";
const pendingDeliveryStorageKey = "gullyscore.pendingDelivery";
const pendingUndoStorageKey = "gullyscore.pendingUndo";

function readPendingRequest(storageKey) {
  const raw = sessionStorage.getItem(storageKey);
  if (!raw) return null;
  try {
    const request = JSON.parse(raw);
    return Number.isInteger(request.innings_id) && typeof request.request_id === "string"
      ? request
      : null;
  } catch {
    sessionStorage.removeItem(storageKey);
    return null;
  }
}

function requestIdForRetry(storageKey, inningsId, payload = null) {
  const fingerprint = JSON.stringify(payload);
  const pending = readPendingRequest(storageKey);
  if (pending?.innings_id === inningsId && pending.fingerprint === fingerprint) {
    return pending.request_id;
  }
  const request = {
    innings_id: inningsId,
    fingerprint,
    request_id: crypto.randomUUID(),
  };
  sessionStorage.setItem(storageKey, JSON.stringify(request));
  return request.request_id;
}

function clearPendingRequest(storageKey) {
  sessionStorage.removeItem(storageKey);
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[character]);
}

function currentRoute() {
  const route = window.location.hash.replace(/^#\/?/, "");
  if (/^players\/\d+$/.test(route)) return "player-profile";
  if (/^matches\/\d+$/.test(route)) return "match-summary";
  return pageNames[route] ? route : "dashboard";
}

function currentRouteId() {
  const route = window.location.hash.replace(/^#\/?/, "");
  const match = route.match(/^(?:players|matches)\/(\d+)$/);
  return match ? Number(match[1]) : null;
}

function goTo(route) {
  window.location.hash = route;
}

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("visible");
  window.clearTimeout(toastTimeout);
  toastTimeout = window.setTimeout(() => toast.classList.remove("visible"), 2800);
}

async function apiRequest(path, options = {}) {
  let response;
  try {
    response = await fetch(path, {
      ...options,
      headers: {
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...options.headers,
      },
    });
  } catch {
    throw new Error("Cannot reach GullyScore right now. Check that the local app is running.");
  }

  if (!response.ok) {
    let message = `Request failed (${response.status}).`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail)) message = body.detail.map((item) => item.msg).join(" ");
    } catch {
      message = `Request failed (${response.status}).`;
    }
    throw new Error(message);
  }

  if (response.status === 204) return null;
  return response.json();
}

function heading(eyebrow, title, description, action = "") {
  return `
    <div class="page-heading">
      <div class="page-heading-copy">
        <p class="eyebrow">${eyebrow}</p>
        <h1>${title}</h1>
        <p>${description}</p>
      </div>
      ${action}
    </div>`;
}

function actionButton(label, route, extraClass = "") {
  return `<a class="button button-primary ${extraClass}" href="#${route}"><span class="button-icon" aria-hidden="true">+</span>${label}</a>`;
}

function teamCrest(code, extraClass = "") {
  return `<span class="team-crest ${extraClass}" aria-hidden="true">${escapeHtml(code)}</span>`;
}

function statCard(label, value, change, icon) {
  return `
    <article class="panel panel-hover stat-card">
      <div class="stat-top"><span>${label}</span><span class="stat-icon" aria-hidden="true">${icon}</span></div>
      <div class="stat-value-row"><strong class="stat-value">${value}</strong><span class="stat-change">${change}</span></div>
    </article>`;
}

function landingPage() {
  return `
    <section class="landing-page">
      <div class="landing-hero">
        <div class="landing-copy">
          <p class="eyebrow"><span class="live-dot"></span> THE LOCAL GAME, LEVELLED UP</p>
          <h1>Every run has<br>a <span>story.</span></h1>
          <p>From the first toss to the last ball. Bring your crew together, keep every delivery on the board, and make your corner of the game count.</p>
          <div class="landing-actions">
            ${actionButton("Open your dashboard", "dashboard")}
            <a class="button button-secondary" href="#create-match">Start a match</a>
          </div>
          <div class="landing-proof">
            <span class="proof-avatars" aria-hidden="true"><span>AM</span><span>RD</span><span>KS</span></span>
            <span>Built for the players who make the game.</span>
          </div>
        </div>
        <div class="landing-art" aria-label="Illustration of a cricket ball">
          <div class="art-orbit"></div><div class="art-ball"></div>
          <div class="art-label">YOUR SEASON<strong>2025 / 26</strong></div>
          <div class="art-stat"><b>18</b><span>matches played</span></div>
        </div>
      </div>
      <div class="landing-feature-grid">
        <article class="panel feature-card"><span class="feature-icon" aria-hidden="true">◎</span><div><h3>Every ball, counted</h3><p>Keep the score moving with a fast, intuitive live scorer.</p></div></article>
        <article class="panel feature-card"><span class="feature-icon" aria-hidden="true">↗</span><div><h3>Your team, your story</h3><p>Follow match history and see your players find their form.</p></div></article>
        <article class="panel feature-card"><span class="feature-icon" aria-hidden="true">✳</span><div><h3>Made for match day</h3><p>A clean scorecard that feels right on the boundary or at home.</p></div></article>
      </div>
    </section>`;
}

function dashboardPage() {
  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
  const today = new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long" });

  return `
    ${heading(`SUNDAY STRIKERS · ${today}`, `${greeting}, <span class="text-lime">captain.</span>`, "Your season is heating up. Here's what's happening around the club.", actionButton("Create match", "create-match"))}
    <section class="stat-grid" aria-label="Season overview">
      ${statCard("Matches played", "18", "↗ 3 this month", "◷")}
      ${statCard("Win rate", "72%", "↗ 8% this season", "↗")}
      ${statCard("Runs scored", "2,486", "↗ 14.2 avg", "✳")}
      ${statCard("Wickets taken", "126", "↗ 7 this month", "⌁")}
    </section>

    <div class="dashboard-grid">
      <section>
        <div class="section-title-row"><div><h2>On the field</h2><p class="section-subtitle">The game is on. Follow it live.</p></div><a href="#live-scoring">Full scorecard ↗</a></div>
        <article class="panel panel-hover live-card">
          <div class="live-card-head"><span class="live-tag"><i></i> LIVE NOW</span><span class="match-meta">${liveMatch.venue} · 12:30 PM</span></div>
          <p class="league-label">${liveMatch.competition}</p>
          <div class="versus-row">
            <div class="team-block">${teamCrest(liveMatch.homeCode)}<span><strong class="team-name">${liveMatch.home}</strong><small class="team-sub">${currentBattingSide() === "home" ? `Batting · ${liveMatch.innings === 1 ? "1st" : "2nd"} innings` : "Bowling"}</small></span></div>
            <span class="versus">VS</span>
            <div class="team-block away"><span><strong class="team-name">${liveMatch.away}</strong><small class="team-sub">${currentBattingSide() === "away" ? `Batting · ${liveMatch.innings === 1 ? "1st" : "2nd"} innings` : liveMatch.innings === 1 ? "Up next" : "1st innings"}</small></span>${teamCrest(liveMatch.awayCode, "blue")}</div>
          </div>
          <div class="score-row">
            <div class="score-side"><strong class="score-number" data-live-score>${liveMatch.score}<small>/<span data-live-wickets>${liveMatch.wickets}</span></small></strong><span class="score-detail" data-live-overs>${formatOvers(liveMatch.legalBalls)} overs</span></div>
            <span class="overs-chip">${liveMatch.oversLimit} overs</span>
            <div class="score-side"><strong class="score-number">${liveMatch.innings === 1 ? "—" : `${liveMatch.battingFirstScore}<small>/${liveMatch.battingFirstWickets}</small>`}</strong><span class="score-detail">${liveMatch.innings === 1 ? "yet to bat" : `${liveMatch.battingFirstOvers} overs`}</span></div>
          </div>
          <div class="target-line">${liveMatch.innings === 1 ? "First innings · get your total on the board." : `Need <strong data-runs-needed>${liveMatch.target - liveMatch.score} runs</strong> from <strong data-balls-left>${liveMatch.oversLimit * 6 - liveMatch.legalBalls} balls</strong>`}</div>
          <div class="last-balls"><span class="last-balls-label">THIS OVER</span>${liveMatch.ballHistory.slice(-6).map((ball) => `<span class="ball-chip ${ball === "W" ? "wicket" : ball === "4" || ball === "6" ? "highlight" : ""}">${ball}</span>`).join("")}</div>
          <div class="live-card-foot"><span class="current-batters"><strong>Rohan Das*</strong> 32 (24) &nbsp;·&nbsp; <strong>Kabir Sen</strong> 18 (14)</span><a class="section-link" href="#live-scoring">Open scorer →</a></div>
        </article>
      </section>

      <section>
        <div class="section-title-row"><div><h2>Recent matches</h2><p class="section-subtitle">Your club, in good company.</p></div><a href="#history">See all →</a></div>
        <div class="panel recent-list">
          ${recentMatches.slice(0, 4).map((match, index) => `
            <article class="recent-match">
              <span class="recent-crest ${index === 1 ? "purple" : index === 3 ? "orange" : ""}">${match.awayCode}</span>
              <span class="recent-copy"><strong>vs ${match.away}</strong><small>${match.date} · ${match.score} — ${match.opponentScore}</small></span>
              <span class="recent-result"><strong>${match.outcome === "win" ? "W" : "L"}</strong><small class="${match.outcome === "loss" ? "loss" : ""}">${match.result.replace(/^(Won|Lost) /, "")}</small></span>
            </article>`).join("")}
        </div>
      </section>
    </div>

    <div class="dashboard-lower">
      <section class="panel form-guide"><div class="section-title-row"><div><h2>Last five</h2><p class="section-subtitle">A little momentum goes a long way.</p></div><span class="section-link">4 wins · 1 loss</span></div><div class="form-pills" aria-label="Last five match results"><span>W</span><span>W</span><span>L</span><span>W</span><span>W</span></div></section>
      <section class="panel club-record"><div><p>Top run scorer</p><strong>Arjun Mehta</strong><br><small>684 runs this season</small></div><span class="player-avatar">AM</span></section>
    </div>`;
}

function createMatchPage() {
  return `
    ${heading("MATCH DAY STARTS HERE", "Set up your <span class=\"text-lime\">match.</span>", "Pick your sides, set the format, and get your scorecard ready.", '<a class="button button-secondary" href="#dashboard">Cancel</a>')}
    <div class="create-layout">
      <form class="panel form-panel" id="create-match-form">
        <section class="form-section">
          <div class="form-section-heading"><span class="step-number">01</span><h2>Who's playing?</h2></div>
          <div class="field-grid">
            <div class="field field-full"><label for="match-title">Match name <span class="muted">(optional)</span></label><input id="match-title" name="title" type="text" maxlength="60" placeholder="e.g. Sunday League · Week 13"><span class="field-hint">Give this fixture a name your team will remember.</span></div>
            <div class="field"><label for="home-team">Team A</label><select id="home-team" name="home" required><option value="">Loading teams…</option></select></div>
            <div class="field"><label for="away-team">Team B</label><select id="away-team" name="away" required><option value="">Select a team</option></select></div>
            <div class="field"><label for="match-venue">Ground <span class="muted">(optional)</span></label><input id="match-venue" name="venue" type="text" maxlength="120" placeholder="Enter ground name"></div>
            <div class="field"><label for="match-date">Date</label><input id="match-date" name="date" type="date" value="${new Date().toISOString().slice(0, 10)}" required></div>
          </div>
        </section>
        <section class="form-section">
          <div class="form-section-heading"><span class="step-number">02</span><h2>Select both playing XIs</h2></div>
          <p class="field-hint">Choose exactly 11 registered players for each side.</p>
          <div class="field-grid xi-grid">
            <section class="xi-picker"><div class="xi-picker-heading"><strong data-xi-team-name="a">Team A</strong><span data-xi-count="a">0 / 11</span></div><div class="xi-player-list" data-xi-list="a"><p class="field-hint">Choose Team A to load its roster.</p></div></section>
            <section class="xi-picker"><div class="xi-picker-heading"><strong data-xi-team-name="b">Team B</strong><span data-xi-count="b">0 / 11</span></div><div class="xi-player-list" data-xi-list="b"><p class="field-hint">Choose Team B to load its roster.</p></div></section>
          </div>
        </section>
        <section class="form-section">
          <div class="form-section-heading"><span class="step-number">03</span><h2>Choose your format &amp; toss</h2></div>
          <div class="field-grid">
            <div class="field"><label for="match-overs">Overs per innings</label><select id="match-overs" name="overs"><option value="5">5 overs</option><option value="8">8 overs</option><option value="10">10 overs</option><option value="12">12 overs</option><option value="15">15 overs</option><option value="20" selected>20 overs</option><option value="25">25 overs</option></select></div>
            <div class="field"><label for="match-wickets">Wickets per innings</label><select id="match-wickets" name="wickets"><option value="5">5 wickets</option><option value="7">7 wickets</option><option value="10" selected>10 wickets</option></select></div>
            <div class="field"><label for="toss-winner">Toss winner</label><select id="toss-winner" name="toss-winner" required><option value="">Select both teams first</option></select></div>
            <div class="field"><label for="toss-decision">Toss decision</label><select id="toss-decision" name="toss-decision" required><option value="BAT">Bat first</option><option value="BOWL">Bowl first</option></select></div>
          </div>
        </section>
        <p class="form-error" data-match-error role="alert" hidden></p>
        <div class="form-actions"><a class="button button-secondary" href="#dashboard">Cancel</a><button class="button button-primary" type="submit"><span class="button-icon" aria-hidden="true">+</span>Create match</button></div>
      </form>

      <aside class="panel setup-aside">
        <span class="preview-badge"><span class="live-dot"></span> MATCH PREVIEW</span>
        <h2 class="match-preview-title" data-preview-title>Sunday League · New fixture</h2>
        <div class="preview-teams">
          <div class="preview-team"><span class="team-crest" data-preview-home-code>SS</span><span><strong data-preview-home>Salt Lake Strikers</strong><small>Your team</small></span></div>
          <span class="preview-vs">VS</span>
          <div class="preview-team"><span class="team-crest blue" data-preview-away-code>PP</span><span><strong data-preview-away>Park Street Panthers</strong><small>Opposition</small></span></div>
        </div>
        <ul class="preview-detail-list"><li><span>Format</span><strong data-preview-format>20 overs · 10 wickets</strong></li><li><span>Ground</span><strong data-preview-venue>Central Park Ground</strong></li><li><span>First innings</span><strong data-preview-batting>Salt Lake Strikers</strong></li></ul>
        <p class="local-note">Your match setup and both playing XIs will be saved to GullyScore before scoring begins.</p>
      </aside>
    </div>`;
}

function formatOvers(balls) {
  return `${Math.floor(balls / 6)}.${balls % 6}`;
}

function totalExtras() {
  return Object.values(liveMatch.extras).reduce((total, runs) => total + runs, 0);
}

function currentStriker() {
  return liveMatch.batters.find((batter) => batter.active) || liveMatch.batters[0];
}

function currentBattingSide() {
  if (liveMatch.innings === 1) return liveMatch.battingFirstTeam;
  return liveMatch.battingFirstTeam === "home" ? "away" : "home";
}

function currentBattingTeam() {
  return liveMatch[currentBattingSide()];
}

function currentBowlingTeam() {
  return liveMatch[currentBattingSide() === "home" ? "away" : "home"];
}

function scoringPage() {
  if (activeScorecard) return persistentScoringPage();
  return `
    ${heading("MATCH DAY", "Live <span class=\"text-lime\">scoring.</span>", "Loading the saved match scorecard…")}
    <section class="panel scorecard-loading" role="status">Connecting to the GullyScore scoring engine…</section>`;
}

function persistentScoringPage() {
  const innings = activeScorecard.innings.find((item) => item.status === "LIVE")
    || activeScorecard.innings[activeScorecard.innings.length - 1];
  if (!innings) {
    return `${heading("MATCH DAY", "Live <span class=\"text-lime\">scoring.</span>", "This match has no innings yet.")}`;
  }
  const battingTeam = innings.batting_team_id === activeScorecard.home_team_id
    ? activeScorecard.home_team_name
    : activeScorecard.away_team_name;
  const bowlingTeam = innings.bowling_team_id === activeScorecard.home_team_id
    ? activeScorecard.home_team_name
    : activeScorecard.away_team_name;
  const target = innings.target;
  const ballsRemaining = Math.max(innings.overs_limit * 6 - innings.legal_balls, 0);
  const runsNeeded = target === null ? null : Math.max(target - innings.total_runs, 0);
  const runRate = innings.legal_balls
    ? (innings.total_runs / (innings.legal_balls / 6)).toFixed(2)
    : "0.00";
  const requiredRate = target !== null && ballsRemaining > 0
    ? (runsNeeded / (ballsRemaining / 6)).toFixed(2)
    : "—";
  const striker = innings.batting_xi.find((player) => player.id === innings.striker_id);
  const nonStriker = innings.batting_xi.find((player) => player.id === innings.non_striker_id);
  const bowler = innings.bowling_xi.find((player) => player.id === innings.current_bowler_id);
  const complete = innings.status !== "LIVE";
  const atOverStart = innings.legal_balls > 0 && innings.legal_balls % 6 === 0;
  const nextBowlerId = innings.bowling_xi.find((player) => player.id !== innings.current_bowler_id)?.id
    ?? innings.current_bowler_id;
  const deliveryLabel = (delivery) => {
    const label = delivery.wicket_type ? "W"
      : delivery.extras_type === "WIDE" ? `Wd${delivery.extras_runs}`
        : delivery.extras_type === "NO_BALL" ? `Nb${delivery.batter_runs + delivery.extras_runs}`
          : delivery.extras_type === "BYE" ? `B${delivery.extras_runs}`
            : delivery.extras_type === "LEG_BYE" ? `Lb${delivery.extras_runs}`
              : String(delivery.batter_runs);
    const highlight = label === "4" || label === "6" ? "highlight" : "";
    return `<span class="ball-chip ${delivery.wicket_type ? "wicket" : highlight}" title="${escapeHtml(delivery.wicket_type || delivery.extras_type || "Runs")}">${escapeHtml(label)}</span>`;
  };
  const recentBalls = innings.deliveries.slice(-8).map(deliveryLabel).join("");
  const currentOverNumber = innings.legal_balls > 0 && innings.legal_balls % 6 === 0
    ? innings.legal_balls / 6 - 1
    : Math.floor(innings.legal_balls / 6);
  const currentOverDeliveries = innings.deliveries
    .filter((delivery) => Number(delivery.over.split(".")[0]) === currentOverNumber)
    .slice(-8).map(deliveryLabel).join("");
  const currentBowlerBalls = bowler?.balls_bowled || 0;
  const bowlerEconomy = currentBowlerBalls
    ? ((bowler.runs_conceded / currentBowlerBalls) * 6).toFixed(2)
    : "0.00";
  const canScore = !complete && striker && nonStriker && bowler && !scoringRequestPending;
  const firstInnings = innings.innings_number === 1;
  const firstInningsSummary = activeScorecard.innings.find((item) => item.innings_number === 1);
  const errorBlock = scoringErrorMessage
    ? `<p class="form-error scoring-error" role="alert">${escapeHtml(scoringErrorMessage)}</p>`
    : "";
  const finalResult = activeScorecard.status === "COMPLETED"
    ? `<section class="panel final-result-panel"><span class="live-tag">FINAL RESULT</span><h2>${escapeHtml(activeScorecard.result_summary || "Match completed.")}</h2></section>`
    : "";
  const playerRow = (player, isStriker) => player
    ? `<div class="batter-row ${isStriker ? "on-strike" : ""}"><span class="batter-name">${escapeHtml(player.name)}${isStriker ? '<em>*</em>' : ""}</span><span class="batter-stats">${player.runs} <small>(${player.balls})</small></span><span class="batter-stats"><small>${player.balls ? (player.runs * 100 / player.balls).toFixed(1) : "—"} SR</small></span></div>`
    : `<div class="batter-row"><span class="batter-name muted">Awaiting batter</span><span class="batter-stats">—</span><span class="batter-stats">—</span></div>`;

  return `
    ${heading(escapeHtml(activeScorecard.name || "GULLYSCORE · LIVE MATCH"), "Live <span class=\"text-lime\">scoring.</span>", `${escapeHtml(battingTeam)} batting · ${escapeHtml(activeScorecard.venue || "Ground to be confirmed")} · ${innings.overs_limit} overs`, '<a class="button button-secondary button-small" href="#dashboard">← Dashboard</a>')}
    ${finalResult}
    ${errorBlock}
    <div class="scoring-grid">
      <section>
        <article class="panel scoreboard-panel">
          <div class="scoreboard-topline"><span class="live-tag"><i></i> ${complete ? "INNINGS COMPLETE" : `LIVE · ${firstInnings ? "FIRST" : "SECOND"} INNINGS`}</span><span>${escapeHtml(activeScorecard.venue || "Ground to be confirmed")}</span></div>
          <div class="scoreboard-teams">
            <div class="scoreboard-team">${teamCrest(activeScorecard.home_team_short_name || initialsFor(activeScorecard.home_team_name))}<span><strong class="scoreboard-team-name">${escapeHtml(activeScorecard.home_team_name)}</strong><small class="scoreboard-team-label">${innings.batting_team_id === activeScorecard.home_team_id ? "Batting now" : firstInnings ? "Up next" : `1st innings · ${firstInningsSummary?.total_runs ?? 0}/${firstInningsSummary?.wickets ?? 0}`}</small></span></div>
            <div class="scoreboard-team"><span><strong class="scoreboard-team-name">${escapeHtml(activeScorecard.away_team_name)}</strong><small class="scoreboard-team-label">${innings.batting_team_id === activeScorecard.away_team_id ? "Batting now" : firstInnings ? "Up next" : `1st innings · ${firstInningsSummary?.total_runs ?? 0}/${firstInningsSummary?.wickets ?? 0}`}</small></span>${teamCrest(activeScorecard.away_team_short_name || initialsFor(activeScorecard.away_team_name), "blue")}</div>
          </div>
          <div class="big-score"><span data-live-score>${innings.total_runs}</span><small>/<span data-live-wickets>${innings.wickets}</span></small></div>
          <p class="score-context">${escapeHtml(battingTeam)} · ${innings.overs} overs <span aria-hidden="true">·</span> ${innings.legal_balls % 6} balls in this over ${target === null ? "" : `<span aria-hidden="true">·</span> Target <strong>${target}</strong> <span aria-hidden="true">·</span> Need <strong>${runsNeeded} runs</strong> from <strong>${ballsRemaining} balls</strong>`}</p>
          <div class="score-details-grid">
            <div class="score-detail-card"><span>Run rate</span><strong>${runRate}</strong></div>
            <div class="score-detail-card"><span>Required rate</span><strong>${requiredRate}</strong></div>
            <div class="score-detail-card"><span>Extras</span><strong>${innings.extras}</strong></div>
            <div class="score-detail-card"><span>Overs left</span><strong>${formatOvers(ballsRemaining)}</strong></div>
          </div>
        </article>
        <article class="panel current-batters-panel">
          <p class="mini-panel-heading">At the crease · ${escapeHtml(battingTeam)}</p>
          ${playerRow(striker, true)}
          ${playerRow(nonStriker, false)}
          <div class="bowler-line"><span>Bowling · <strong>${escapeHtml(bowlingTeam)}</strong></span><span>${escapeHtml(bowler?.name || "Select bowler")} · ${bowler?.wickets || 0}/${bowler?.runs_conceded || 0} (${formatOvers(currentBowlerBalls)}) · Eco ${bowlerEconomy} · ${bowler?.maidens || 0} M</span></div>
        </article>
        <article class="panel current-batters-panel recent-deliveries-panel">
          <p class="mini-panel-heading">Recent deliveries</p>
          <div class="last-balls">${recentBalls || '<span class="trail-empty">No deliveries recorded yet.</span>'}</div>
        </article>
      </section>
      <aside class="panel scoring-controls">
        <div class="controls-header"><h2>${complete ? "Innings complete" : innings.striker_id ? "Record delivery" : "Start scoring"}</h2><button class="undo-button" type="button" data-score-action="undo" ${!innings.deliveries.length || scoringRequestPending ? "disabled" : ""}>↶ Undo</button></div>
        ${complete ? `<p class="control-label">${target !== null && innings.total_runs >= target ? `${escapeHtml(battingTeam)} reached the target.` : `${escapeHtml(battingTeam)} finished on ${innings.total_runs}/${innings.wickets}.`}</p>` : ""}
        ${complete && firstInnings ? `<button class="button button-primary scoring-start-button" type="button" data-score-action="start-next-innings" ${scoringRequestPending ? "disabled" : ""}>Start the chase →</button>` : ""}
        ${!innings.striker_id && !complete ? `<button class="button button-primary scoring-start-button" type="button" data-score-action="set-openers">Set batters &amp; bowler</button>` : ""}
        ${atOverStart && !complete ? `<label class="field next-bowler-field"><span>Next over bowler</span><select data-next-bowler ${scoringRequestPending ? "disabled" : ""}>${innings.bowling_xi.map((player) => `<option value="${player.id}" ${player.id === nextBowlerId ? "selected" : ""}>${escapeHtml(player.name)}</option>`).join("")}</select></label>` : ""}
        <p class="control-label">BATTER RUNS</p>
        <div class="run-grid">
          ${[0, 1, 2, 3, 4, 6].map((runs) => `<button class="run-button ${runs === 4 || runs === 6 ? "boundary" : ""}" type="button" data-score-action="runs" data-runs="${runs}" ${canScore ? "" : "disabled"}>${runs}</button>`).join("")}
          <button class="run-button wicket-run-button" type="button" data-score-action="wicket" ${canScore ? "" : "disabled"}>Wicket</button>
        </div>
        <p class="control-label">EXTRAS</p>
        <div class="scoring-extra-options">
          <label>Wide total<select data-wide-runs>${[1, 2, 3, 4, 5, 6, 7].map((runs) => `<option value="${runs}">${runs}</option>`).join("")}</select></label>
          <label>No-ball batter runs<select data-no-ball-runs>${[0, 1, 2, 3, 4, 5, 6].map((runs) => `<option value="${runs}">${runs}</option>`).join("")}</select></label>
          <label>No-ball other completed runs<select data-no-ball-completed-runs>${[0, 1, 2, 3, 4, 5].map((runs) => `<option value="${runs}">${runs}</option>`).join("")}</select></label>
          <label>Bye / leg-bye runs<select data-bye-runs>${[1, 2, 3, 4, 5, 6].map((runs) => `<option value="${runs}">${runs}</option>`).join("")}</select></label>
        </div>
        <div class="run-grid extra-run-grid">
          <button class="run-button extra" type="button" data-score-action="extra" data-type="WIDE" ${canScore ? "" : "disabled"}>Wide</button>
          <button class="run-button extra" type="button" data-score-action="extra" data-type="NO_BALL" ${canScore ? "" : "disabled"}>No ball</button>
          <button class="run-button extra" type="button" data-score-action="extra" data-type="BYE" ${canScore ? "" : "disabled"}>Bye</button>
          <button class="run-button extra" type="button" data-score-action="extra" data-type="LEG_BYE" ${canScore ? "" : "disabled"}>Leg bye</button>
        </div>
        <p class="control-label">THIS OVER · ${formatOvers(innings.legal_balls)}</p>
        <div class="ball-trail">${currentOverDeliveries || '<span class="trail-empty">No deliveries recorded this over.</span>'}</div>
        <p class="scoring-disclaimer">Every delivery is saved to GullyScore. Duplicate requests are safely ignored.</p>
      </aside>
    </div>
    <dialog class="scoring-dialog" id="scoring-dialog"></dialog>`;
}

async function loadLiveScorecard() {
  if (scorecardLoading) return;
  const requestId = ++scorecardLoadId;
  scorecardLoading = true;
  try {
    const storedMatchId = sessionStorage.getItem("gullyscore.currentMatchId");
    const endpoint = storedMatchId
      ? `/api/matches/${encodeURIComponent(storedMatchId)}/scorecard`
      : "/api/matches/live/scorecard";
    const scorecard = await apiRequest(endpoint);
    if (requestId !== scorecardLoadId || currentRoute() !== "live-scoring") return;
    const pendingDelivery = readPendingRequest(pendingDeliveryStorageKey);
    if (
      pendingDelivery
      && scorecard.innings.some((innings) =>
        innings.id === pendingDelivery.innings_id
        && innings.deliveries.some((delivery) => delivery.request_id === pendingDelivery.request_id))
    ) {
      clearPendingRequest(pendingDeliveryStorageKey);
    }
    activeScorecard = scorecard;
    sessionStorage.setItem("gullyscore.currentMatchId", String(scorecard.match_id));
    scoringErrorMessage = "";
    renderApp();
    const innings = activeScorecard.innings.find((item) => item.status === "LIVE");
    if (innings && !innings.striker_id) openInningsSetupDialog(innings);
  } catch (error) {
    if (requestId !== scorecardLoadId || currentRoute() !== "live-scoring") return;
    activeScorecard = null;
    viewRoot.innerHTML = `
      ${heading("MATCH DAY", "Live <span class=\"text-lime\">scoring.</span>", "Your match scorecard will appear here.")}
      <section class="panel scoring-empty-state"><strong>${escapeHtml(error.message)}</strong><p>Create a match to start scoring, or check that the server is running.</p><a class="button button-primary" href="#create-match">Create match</a><button class="button button-secondary" type="button" data-score-action="reload">Refresh scorecard</button></section>`;
  } finally {
    scorecardLoading = false;
  }
}

function openInningsSetupDialog(innings) {
  const dialog = document.querySelector("#scoring-dialog");
  if (!dialog) return;
  const battingPlayers = innings.batting_xi;
  const bowlingPlayers = innings.bowling_xi;
  dialog.innerHTML = `
    <form class="scoring-dialog-form" id="innings-start-form" data-innings-id="${innings.id}">
      <div class="team-dialog-heading"><span><h2>Start the innings</h2><p>Choose the opening batters and first bowler.</p></span><button class="dialog-close" type="button" data-scoring-dialog-close aria-label="Close dialog">×</button></div>
      <label class="field"><span>Striker</span><select name="striker" required>${battingPlayers.map((player) => `<option value="${player.id}">${escapeHtml(player.name)}</option>`).join("")}</select></label>
      <label class="field"><span>Non-striker</span><select name="non-striker" required>${battingPlayers.map((player, index) => `<option value="${player.id}" ${index === 1 ? "selected" : ""}>${escapeHtml(player.name)}</option>`).join("")}</select></label>
      <label class="field"><span>Opening bowler</span><select name="bowler" required>${bowlingPlayers.map((player) => `<option value="${player.id}">${escapeHtml(player.name)}</option>`).join("")}</select></label>
      <p class="form-error" data-dialog-error hidden></p>
      <div class="dialog-actions"><button class="button button-primary" type="submit">Start innings</button></div>
    </form>`;
  dialog.showModal();
}

function openWicketDialog(innings) {
  const dialog = document.querySelector("#scoring-dialog");
  if (!dialog) return;
  const currentBatters = innings.batting_xi.filter((player) =>
    [innings.striker_id, innings.non_striker_id].includes(player.id));
  const unavailableIds = new Set([
    ...currentBatters.map((player) => player.id),
    ...innings.batting_xi.filter((player) => player.dismissed).map((player) => player.id),
  ]);
  const incomingPlayers = innings.batting_xi.filter((player) => !unavailableIds.has(player.id));
  const endsInnings = innings.wickets + 1 >= innings.wickets_limit
    || innings.legal_balls + 1 >= innings.overs_limit * 6
    || (innings.target !== null && innings.total_runs >= innings.target);
  const dismissals = ["BOWLED", "CAUGHT", "CAUGHT_AND_BOWLED", "LBW", "RUN_OUT", "STUMPED", "HIT_WICKET", "RETIRED_OUT", "OBSTRUCTING_THE_FIELD", "HIT_THE_BALL_TWICE", "TIMED_OUT"];
  dialog.innerHTML = `
    <form class="scoring-dialog-form" id="wicket-form" data-innings-id="${innings.id}">
      <div class="team-dialog-heading"><span><h2>Record a wicket</h2><p>Select the dismissal and batter.</p></span><button class="dialog-close" type="button" data-scoring-dialog-close aria-label="Close dialog">×</button></div>
      <label class="field"><span>Dismissal</span><select name="wicket-type" required>${dismissals.map((type) => `<option value="${type}">${type.replaceAll("_", " ")}</option>`).join("")}</select></label>
      <label class="field"><span>Dismissed batter</span><select name="dismissed-player" required>${currentBatters.map((player) => `<option value="${player.id}">${escapeHtml(player.name)}${player.id === innings.striker_id ? " (on strike)" : ""}</option>`).join("")}</select></label>
      ${endsInnings ? '<p class="field-hint">This wicket will complete the innings.</p>' : `<label class="field"><span>Incoming batter</span><select name="incoming-batter" required>${incomingPlayers.map((player) => `<option value="${player.id}">${escapeHtml(player.name)}</option>`).join("")}</select></label>`}
      <p class="form-error" data-dialog-error hidden></p>
      <div class="dialog-actions"><button class="button button-secondary" type="button" data-scoring-dialog-close>Cancel</button><button class="button button-primary" type="submit">Confirm wicket</button></div>
    </form>`;
  dialog.showModal();
}

function currentPersistentInnings() {
  return activeScorecard?.innings.find((innings) => innings.status === "LIVE")
    || activeScorecard?.innings[activeScorecard.innings.length - 1]
    || null;
}

async function submitPersistentDelivery(payload) {
  if (scoringRequestPending) return;
  const innings = currentPersistentInnings();
  if (!innings) return;
  const requestId = requestIdForRetry(
    pendingDeliveryStorageKey,
    innings.id,
    payload,
  );
  scoringRequestPending = true;
  scoringErrorMessage = "";
  renderApp();
  try {
    await apiRequest(`/api/innings/${innings.id}/deliveries`, {
      method: "POST",
      body: JSON.stringify({ request_id: requestId, ...payload }),
    });
    clearPendingRequest(pendingDeliveryStorageKey);
    clearPendingRequest(pendingUndoStorageKey);
    await loadLiveScorecard();
  } catch (error) {
    scoringErrorMessage = error.message;
    renderApp();
  } finally {
    scoringRequestPending = false;
    if (currentRoute() === "live-scoring") renderApp();
  }
}

async function undoPersistentDelivery() {
  const innings = currentPersistentInnings();
  if (!innings?.deliveries.length || scoringRequestPending) return;
  if (!window.confirm("Undo the last delivery? This will restore the score, batter and bowler figures, strike, and over state.")) return;
  const requestId = requestIdForRetry(pendingUndoStorageKey, innings.id);
  scoringRequestPending = true;
  scoringErrorMessage = "";
  renderApp();
  try {
    await apiRequest(`/api/innings/${innings.id}/undo`, {
      method: "POST",
      body: JSON.stringify({ request_id: requestId }),
    });
    clearPendingRequest(pendingUndoStorageKey);
    clearPendingRequest(pendingDeliveryStorageKey);
    await loadLiveScorecard();
    showToast("Last delivery undone.");
  } catch (error) {
    scoringErrorMessage = error.message;
    renderApp();
  } finally {
    scoringRequestPending = false;
    if (currentRoute() === "live-scoring") renderApp();
  }
}

function handlePersistentScoringClick(actionButton) {
  const action = actionButton.dataset.scoreAction;
  const innings = currentPersistentInnings();
  if (action === "reload") {
    loadLiveScorecard();
    return;
  }
  if (!innings) return;
  if (action === "set-openers") {
    openInningsSetupDialog(innings);
    return;
  }
  if (action === "start-next-innings") {
    startNextInnings();
    return;
  }
  if (action === "undo") {
    undoPersistentDelivery();
    return;
  }
  if (action === "wicket") {
    openWicketDialog(innings);
    return;
  }
  const bowlerId = Number(document.querySelector("[data-next-bowler]")?.value || innings.current_bowler_id);
  if (action === "runs") {
    submitPersistentDelivery({
      batter_id: innings.striker_id,
      bowler_id: bowlerId,
      batter_runs: Number(actionButton.dataset.runs),
    });
    return;
  }
  if (action !== "extra") return;
  const type = actionButton.dataset.type;
  const control = (selector) => Number(document.querySelector(selector)?.value || 1);
  if (type === "WIDE") {
    const extras = control("[data-wide-runs]");
    submitPersistentDelivery({
      batter_id: innings.striker_id,
      bowler_id: bowlerId,
      extras_type: type,
      extras_runs: extras,
      completed_runs: extras - 1,
    });
  } else if (type === "NO_BALL") {
    const batterRuns = control("[data-no-ball-runs]");
    const completedRuns = Number(document.querySelector("[data-no-ball-completed-runs]")?.value || 0);
    submitPersistentDelivery({
      batter_id: innings.striker_id,
      bowler_id: bowlerId,
      batter_runs: batterRuns,
      extras_type: type,
      extras_runs: 1 + completedRuns,
      completed_runs: completedRuns,
    });
  } else {
    const runs = control("[data-bye-runs]");
    submitPersistentDelivery({
      batter_id: innings.striker_id,
      bowler_id: bowlerId,
      extras_type: type,
      extras_runs: runs,
      completed_runs: runs,
    });
  }
}

function submitInningsStart(form) {
  const dialog = form.closest("dialog");
  const formData = new FormData(form);
  const submitButton = form.querySelector('[type="submit"]');
  if (submitButton) submitButton.disabled = true;
  apiRequest(`/api/innings/${form.dataset.inningsId}/start`, {
    method: "POST",
    body: JSON.stringify({
      striker_id: Number(formData.get("striker")),
      non_striker_id: Number(formData.get("non-striker")),
      bowler_id: Number(formData.get("bowler")),
    }),
  }).then(() => {
    dialog?.close();
    loadLiveScorecard();
  }).catch((error) => {
    const errorElement = form.querySelector("[data-dialog-error]");
    if (errorElement) {
      errorElement.textContent = error.message;
      errorElement.hidden = false;
    }
    if (submitButton) submitButton.disabled = false;
  });
}

async function submitWicket(form) {
  const innings = currentPersistentInnings();
  if (!innings) return;
  const values = new FormData(form);
  const bowlerId = Number(document.querySelector("[data-next-bowler]")?.value || innings.current_bowler_id);
  form.closest("dialog")?.close();
  await submitPersistentDelivery({
    batter_id: innings.striker_id,
    bowler_id: bowlerId,
    wicket_type: String(values.get("wicket-type")),
    dismissed_player_id: Number(values.get("dismissed-player")),
    incoming_batter_id: values.get("incoming-batter")
      ? Number(values.get("incoming-batter"))
      : null,
  });
}

async function startNextInnings() {
  if (scoringRequestPending || !activeScorecard) return;
  scoringRequestPending = true;
  renderApp();
  let shouldSetOpeners = false;
  try {
    const updated = await apiRequest(
      `/api/matches/${activeScorecard.match_id}/next-innings`,
      { method: "POST" },
    );
    activeScorecard = updated;
    scoringErrorMessage = "";
    shouldSetOpeners = true;
  } catch (error) {
    scoringErrorMessage = error.message;
  } finally {
    scoringRequestPending = false;
    if (currentRoute() === "live-scoring") {
      renderApp();
      const innings = currentPersistentInnings();
      if (shouldSetOpeners && innings && !innings.striker_id) {
        openInningsSetupDialog(innings);
      }
    }
  }
}

function showScoringError(message) {
  scoringErrorMessage = message;
  const error = document.querySelector(".scoring-error");
  if (error) {
    error.textContent = message;
    error.hidden = false;
  } else {
    showToast(message);
  }
}
function historyRows() {
  return matchHistory;
}

function historyPage() {
  return `
    ${heading("THE SCOREBOOK", "Match <span class=\"text-lime\">history.</span>", "Every result, every rivalry, all in one place.", actionButton("New match", "create-match", "button-small"))}
    <div class="toolbar">
      <div class="filter-tabs" role="group" aria-label="Filter match results">
        ${[["all", "All matches"], ["win", "Wins"], ["loss", "Losses"], ["tied", "Tied"], ["live", "Live"]].map(([value, label]) => `<button class="filter-tab ${activeHistoryFilter === value ? "active" : ""}" type="button" data-filter="${value}">${label}</button>`).join("")}
      </div>
      <label class="search-wrap"><span class="sr-only"></span><input id="history-search" class="search-input" type="search" placeholder="Search opponent…" aria-label="Search opponents"></label>
    </div>
    <section class="panel">
      <div class="data-table-wrap"><table class="data-table">
        <thead><tr><th>Match</th><th>Date</th><th>Score</th><th>Result</th><th>Status</th><th></th></tr></thead>
        <tbody id="history-rows">${matchHistoryLoading ? '<tr><td colspan="6">Loading saved matches…</td></tr>' : matchHistoryError ? `<tr><td colspan="6">${escapeHtml(matchHistoryError)} <button type="button" class="table-link" data-history-reload>Try again</button></td></tr>` : renderHistoryRows()}</tbody>
      </table></div>
      <div class="table-footer"><span id="history-count">Showing ${historyRows().length} matches</span><button class="button button-secondary button-small" type="button" data-history-reload>Refresh</button></div>
    </section>`;
}

function renderHistoryRows() {
  return historyRows().map((match) => {
    const outcome = match.status === "LIVE"
      ? "live"
      : match.status === "UPCOMING" ? "upcoming"
      : match.result_summary?.toLowerCase().includes("tied")
        ? "tied"
        : match.winner_team_id === match.home_team_id ? "win" : "loss";
    const result = match.result_summary
      ? `<span class="result-pill ${outcome === "loss" ? "loss" : ""}">${escapeHtml(match.result_summary)}</span>`
      : `<span class="status-pill">${match.status === "UPCOMING" ? "Scheduled" : "In progress"}</span>`;
    const scores = match.innings.map((innings) =>
      `${escapeHtml(innings.batting_team_name)} ${innings.total_runs}/${innings.wickets} (${formatOvers(innings.legal_balls)})`,
    ).join(" · ") || "No innings started";
    const started = match.started_at ? new Date(match.started_at).toLocaleDateString() : "—";
    return `<tr data-match-outcome="${outcome}" data-search="${escapeHtml(`${match.home_team_name} ${match.away_team_name}`.toLowerCase())}">
      <td><span class="table-teams"><span class="recent-crest">${escapeHtml(match.home_team_short_name || initialsFor(match.home_team_name))}</span>${escapeHtml(match.home_team_name)} <span class="table-vs">vs</span> ${escapeHtml(match.away_team_name)}</span></td>
      <td>${escapeHtml(started)}</td><td><span class="table-score">${scores}</span></td><td>${result}</td>
      <td>${match.status === "LIVE" ? '<span class="status-pill">● Live</span>' : match.status === "COMPLETED" ? '<span class="status-pill complete">Complete</span>' : '<span class="status-pill complete">Upcoming</span>'}</td>
      <td><a class="table-link" ${match.status === "LIVE" ? `data-open-live-match="${match.id}"` : ""} href="${match.status === "LIVE" ? "#live-scoring" : `#matches/${match.id}`}">${match.status === "LIVE" ? "Score →" : "Summary →"}</a></td>
    </tr>`;
  }).join("");
}

function statRows(type) {
  return playerStatistics.map((player, index) => {
    const metrics = type === "bowling"
      ? `<td>${player.matches_played}</td><td class="metric-cell">${player.wickets_taken}<small> wkts</small></td><td>${player.bowling_economy ?? "—"}</td><td>${player.best_bowling_wickets}/${player.best_bowling_runs}</td>`
      : type === "fielding"
        ? `<td>${player.catches}</td><td>${player.run_outs}</td><td>${player.stumpings}</td><td>${player.matches_played}</td>`
        : `<td>${player.matches_played}</td><td class="metric-cell">${player.total_runs}<small> runs</small></td><td>${player.highest_score}</td><td>${player.batting_average ?? "—"}</td><td>${player.strike_rate ?? "—"}</td>`;
    return `<tr><td class="rank-cell">${String(index + 1).padStart(2, "0")}</td><td><a class="player-cell player-profile-link" href="#players/${player.id}"><span class="player-avatar">${escapeHtml(initialsFor(player.name))}</span><span><strong>${escapeHtml(player.name)}</strong><small>${player.innings_played} innings</small></span></a></td>${metrics}</tr>`;
  }).join("");
}

function statHeaders(type) {
  if (type === "bowling") return "<th>Matches</th><th>Wickets</th><th>Economy</th><th>Best</th>";
  if (type === "fielding") return "<th>Catches</th><th>Run outs</th><th>Stumpings</th><th>Matches</th>";
  return "<th>Matches</th><th>Runs</th><th>Highest</th><th>Average</th><th>Strike rate</th>";
}

function statisticsPage() {
  const top = playerStatistics[0];
  const fieldingTracked = playerStatistics.some((player) => player.catches || player.run_outs || player.stumpings);
  const topValue = !top || (activeStatTab === "fielding" && !fieldingTracked) ? "—" : activeStatTab === "bowling"
    ? `${top.wickets_taken}<small> wkts</small>`
    : activeStatTab === "fielding"
      ? `${top.catches}<small> catches</small>`
      : `${top.total_runs}<small> runs</small>`;
  const topTitle = activeStatTab === "bowling"
    ? "Leading wicket taker"
    : activeStatTab === "fielding" ? "Most catches" : "Top run scorer";
  const tableBody = playerStatisticsLoading
    ? '<tr><td colspan="7">Loading persisted player statistics…</td></tr>'
    : playerStatisticsError
      ? `<tr><td colspan="7">${escapeHtml(playerStatisticsError)} <button class="table-link" type="button" data-statistics-reload>Try again</button></td></tr>`
    : activeStatTab === "fielding" && !fieldingTracked
    ? '<tr><td colspan="7">Fielding events are not recorded by the current scoring flow.</td></tr>'
    : playerStatistics.length
    ? statRows(activeStatTab)
    : '<tr><td colspan="7">No saved player statistics yet. Complete a match to build the leaderboard.</td></tr>';

  return `
    ${heading("YOUR SCOREBOOK", "Player <span class=\"text-lime\">statistics.</span>", "Career figures calculated from saved match innings.", '<a class="button button-secondary button-small" href="#history">Match history →</a>')}
    <div class="stats-main-grid">
      <section class="panel leaderboard-panel">
        <div class="leaderboard-top">
          <div class="section-title-row"><div><h2>Player leaderboard</h2><p class="section-subtitle">Persisted career records · ${activeStatTab}</p></div></div>
          <div class="stat-tabs" role="tablist" aria-label="Statistics category">
            ${[["batting", "Batting"], ["bowling", "Bowling"], ["fielding", "Fielding"]].map(([value, label]) => `<button class="stat-tab ${activeStatTab === value ? "active" : ""}" type="button" role="tab" aria-selected="${activeStatTab === value}" data-stat-tab="${value}">${label}</button>`).join("")}
          </div>
        </div>
        <div class="data-table-wrap"><table class="data-table"><thead><tr><th>#</th><th>Player</th>${statHeaders(activeStatTab)}</tr></thead><tbody>${tableBody}</tbody></table></div>
        <p class="leaderboard-note">${activeStatTab === "fielding" ? "Fielding event tracking is not yet available." : "Batting average is runs per dismissal; strike rate is runs per 100 balls. Bowling economy uses legal balls."}</p>
      </section>
      <aside class="stats-side">
        <article class="panel leader-card"><div class="leader-card-heading"><h3>${topTitle}</h3><span class="leader-card-icon">✳</span></div>${activeStatTab === "fielding" && !fieldingTracked ? '<p class="field-hint">Fielding events are not recorded yet.</p>' : top ? `<a class="leader-person player-profile-link" href="#players/${top.id}"><span class="player-avatar">${escapeHtml(initialsFor(top.name))}</span><span><strong>${escapeHtml(top.name)}</strong><small>${top.matches_played} matches · Avg ${top.batting_average ?? "—"}</small></span><span class="leader-value">${topValue}</span></a>` : '<p class="field-hint">Player figures will appear after scoring is saved.</p>'}</article>
        <article class="panel leader-card"><div class="leader-card-heading"><h3>Match archive</h3><span class="leader-card-icon">◷</span></div><a class="button button-secondary button-small" href="#history">Browse saved matches →</a></article>
      </aside>
    </div>`;
}

function playerProfilePage() {
  if (!playerProfile) {
    return `${heading("PLAYER RECORD", "Player <span class=\"text-lime\">profile.</span>", "Loading this player's saved career record…")}<section class="panel scorecard-loading" role="status">Loading player statistics and match appearances…</section>`;
  }
  const profile = playerProfile;
  const best = `${profile.best_bowling_wickets}/${profile.best_bowling_runs}`;
  const appearances = profile.matches.length
    ? profile.matches.map((match) => `<tr><td>${escapeHtml(match.name || `${match.home_team_name} vs ${match.away_team_name}`)}</td><td>${match.date ? new Date(match.date).toLocaleDateString() : "—"}</td><td>${match.runs} (${match.balls_faced})</td><td>${match.wickets}/${match.runs_conceded} (${formatOvers(match.balls_bowled)})</td><td>${escapeHtml(match.result_summary || match.status)}</td></tr>`).join("")
    : '<tr><td colspan="5">No match appearances saved yet.</td></tr>';
  return `
    ${heading("PLAYER RECORD", `${escapeHtml(profile.name)} <span class="text-lime">.</span>`, `${profile.matches_played} matches · ${profile.innings_played} batting innings`, '<a class="button button-secondary button-small" href="#statistics">← Leaderboard</a>')}
    <section class="stats-overview">
      ${statCard("Matches played", profile.matches_played, "saved appearances", "◷")}
      ${statCard("Total runs", profile.total_runs, `highest ${profile.highest_score}`, "✳")}
      ${statCard("Batting average", profile.batting_average ?? "—", "runs / dismissal", "↗")}
      ${statCard("Strike rate", profile.strike_rate ?? "—", "runs / 100 balls", "⌁")}
    </section>
    <section class="stats-overview">
      ${statCard("Wickets", profile.wickets_taken, "bowler credited", "⌁")}
      ${statCard("Economy", profile.bowling_economy ?? "—", "runs / 6 legal balls", "↗")}
      ${statCard("Best bowling", best, "wickets / runs", "✳")}
      ${statCard("Fielding", profile.catches + profile.run_outs + profile.stumpings, `${profile.catches} catches · ${profile.run_outs} run outs`, "◷")}
    </section>
    <section class="panel leaderboard-panel"><div class="leaderboard-top"><div class="section-title-row"><div><h2>Match-by-match</h2><p class="section-subtitle">Batting and bowling record from saved innings</p></div></div></div>
      <div class="data-table-wrap"><table class="data-table"><thead><tr><th>Match</th><th>Date</th><th>Batting</th><th>Bowling</th><th>Result</th></tr></thead><tbody>${appearances}</tbody></table></div>
    </section>`;
}

function matchSummaryPage() {
  if (!selectedMatchSummary) {
    return `${heading("THE SCOREBOOK", "Match <span class=\"text-lime\">summary.</span>", "Loading the saved match result…")}<section class="panel scorecard-loading" role="status">Loading final scorecard…</section>`;
  }
  const match = selectedMatchSummary;
  const inningsCards = match.innings.map((innings) => {
    const batting = innings.batting_xi
      .filter((player) => player.balls || player.runs || player.dismissed || player.at_crease)
      .map((player) => `<tr><td>${escapeHtml(player.name)}${player.at_crease ? "*" : ""}</td><td>${player.runs}</td><td>${player.balls}</td><td>${player.fours}</td><td>${player.sixes}</td></tr>`).join("")
      || '<tr><td colspan="5">No batting figures recorded.</td></tr>';
    const bowling = innings.bowling_xi
      .filter((player) => player.balls_bowled || player.wickets)
      .map((player) => `<tr><td>${escapeHtml(player.name)}</td><td>${player.wickets}/${player.runs_conceded}</td><td>${formatOvers(player.balls_bowled)}</td><td>${player.maidens}</td></tr>`).join("")
      || '<tr><td colspan="4">No bowling figures recorded.</td></tr>';
    const teamName = innings.batting_team_id === match.home_team_id ? match.home_team_name : match.away_team_name;
    return `<article class="panel match-innings-summary"><div class="section-title-row"><div><h2>${escapeHtml(teamName)} · ${innings.total_runs}/${innings.wickets}</h2><p class="section-subtitle">Innings ${innings.innings_number} · ${innings.overs} overs · ${innings.extras} extras${innings.target ? ` · target ${innings.target}` : ""}</p></div></div>
      <div class="data-table-wrap"><table class="data-table"><thead><tr><th>Batter</th><th>Runs</th><th>Balls</th><th>4s</th><th>6s</th></tr></thead><tbody>${batting}</tbody></table></div>
      <div class="data-table-wrap summary-bowling"><table class="data-table"><thead><tr><th>Bowler</th><th>Wickets / runs</th><th>Overs</th><th>M</th></tr></thead><tbody>${bowling}</tbody></table></div>
    </article>`;
  }).join("");
  return `${heading("THE SCOREBOOK", "Match <span class=\"text-lime\">summary.</span>", `${escapeHtml(match.home_team_name)} vs ${escapeHtml(match.away_team_name)}`, '<a class="button button-secondary button-small" href="#history">← Match history</a>')}
    <section class="panel final-result-panel"><span class="live-tag">${match.status === "COMPLETED" ? "FINAL RESULT" : "MATCH IN PROGRESS"}</span><h2>${escapeHtml(match.result_summary || "Match has not been decided yet.")}</h2><p>${escapeHtml(match.name || "GullyScore match")} · ${escapeHtml(match.venue || "Venue not set")}</p></section>
    <div class="match-innings-list">${inningsCards || '<section class="panel empty-state">No innings are available for this match.</section>'}</div>`;
}

async function loadMatchHistory() {
  const requestId = ++matchHistoryLoadId;
  matchHistoryLoading = true;
  matchHistoryError = "";
  try {
    matchHistory = await apiRequest("/api/matches?limit=100");
  } catch (error) {
    matchHistory = [];
    matchHistoryError = `Couldn't load match history: ${error.message}`;
  } finally {
    matchHistoryLoading = false;
    if (requestId === matchHistoryLoadId && currentRoute() === "history") {
      viewRoot.innerHTML = historyPage();
      applyHistoryFilters();
    }
  }
}

async function loadPlayerStatistics() {
  const requestId = ++playerStatisticsLoadId;
  playerStatisticsLoading = true;
  playerStatisticsError = "";
  try {
    playerStatistics = await apiRequest(`/api/statistics/players?category=${activeStatTab}&limit=100`);
  } catch (error) {
    playerStatistics = [];
    playerStatisticsError = `Couldn't load player statistics: ${error.message}`;
  } finally {
    playerStatisticsLoading = false;
    if (requestId === playerStatisticsLoadId && currentRoute() === "statistics") {
      viewRoot.innerHTML = statisticsPage();
    }
  }
}

async function loadPlayerProfile(playerId) {
  const requestId = ++playerProfileLoadId;
  playerProfile = null;
  try {
    playerProfile = await apiRequest(`/api/players/${playerId}/statistics`);
  } catch (error) {
    playerProfile = null;
    if (requestId === playerProfileLoadId && currentRoute() === "player-profile") {
      viewRoot.innerHTML = `${heading("PLAYER RECORD", "Player <span class=\"text-lime\">profile.</span>", "This saved player record could not be loaded.")}<section class="panel teams-error"><p>${escapeHtml(error.message)}</p><a class="button button-secondary button-small" href="#statistics">Back to statistics</a></section>`;
    }
    return;
  }
  if (requestId === playerProfileLoadId && currentRoute() === "player-profile") {
    viewRoot.innerHTML = playerProfilePage();
  }
}

async function loadMatchSummary(matchId) {
  const requestId = ++matchSummaryLoadId;
  selectedMatchSummary = null;
  try {
    selectedMatchSummary = await apiRequest(`/api/matches/${matchId}/scorecard`);
  } catch (error) {
    selectedMatchSummary = null;
    if (requestId === matchSummaryLoadId && currentRoute() === "match-summary") {
      viewRoot.innerHTML = `${heading("THE SCOREBOOK", "Match <span class=\"text-lime\">summary.</span>", "This saved match could not be loaded.")}<section class="panel teams-error"><p>${escapeHtml(error.message)}</p><a class="button button-secondary button-small" href="#history">Back to match history</a></section>`;
    }
    return;
  }
  if (requestId === matchSummaryLoadId && currentRoute() === "match-summary") {
    viewRoot.innerHTML = matchSummaryPage();
  }
}

function teamManagementPage(teams, selectedTeam) {
  const teamList = teams.length
    ? teams.map((team) => `
      <button class="team-list-item ${selectedTeam?.id === team.id ? "active" : ""}" type="button" data-team-select="${team.id}">
        <span class="team-crest">${escapeHtml(team.short_name || initialsFor(team.name))}</span>
        <span class="team-list-copy"><strong>${escapeHtml(team.name)}</strong><small>${team.player_count} ${team.player_count === 1 ? "player" : "players"}</small></span>
        <span class="team-list-chevron">›</span>
      </button>`).join("")
    : '<div class="teams-empty-list">Your club is ready for its first team.</div>';

  const roster = selectedTeam
    ? selectedTeam.players.length
      ? selectedTeam.players.map((player) => `
        <article class="roster-row">
          <span class="player-avatar">${escapeHtml(initialsFor(player.display_name))}</span>
          <span class="roster-player-name"><strong>${escapeHtml(player.display_name)}</strong><small>${escapeHtml(player.role || "Player")}</small></span>
          <span class="roster-jersey">${player.jersey_number === null ? "—" : `#${player.jersey_number}`}</span>
          <span class="roster-actions">
            <button type="button" class="roster-action" aria-label="Edit ${escapeHtml(player.display_name)}" data-player-edit="${player.id}">Edit</button>
            <button type="button" class="roster-action remove" aria-label="Remove ${escapeHtml(player.display_name)}" data-player-remove="${player.id}">Remove</button>
          </span>
        </article>`).join("")
      : '<div class="team-roster-empty"><span class="empty-ball">+</span><strong>No players yet</strong><span>Add the first player to this roster.</span></div>'
    : '<div class="team-roster-empty"><span class="empty-ball">♟</span><strong>Select a team</strong><span>Choose a team to view and manage its roster.</span></div>';

  return `
    ${heading("YOUR CLUB · SQUAD MANAGEMENT", "Teams &amp; <span class=\"text-lime\">players.</span>", "Build your squads, keep the roster tidy, and get ready for match day.", '<button class="button button-primary" type="button" data-team-create><span class="button-icon" aria-hidden="true">+</span>Create team</button>')}
    <div class="teams-layout">
      <section class="panel teams-list-panel">
        <div class="teams-panel-heading"><span><strong>Your teams</strong><small>${teams.length} ${teams.length === 1 ? "team" : "teams"} in your club</small></span><span class="teams-heading-icon">♟</span></div>
        <div class="team-list">${teamList}</div>
      </section>
      <section class="panel team-roster-panel">
        ${selectedTeam ? `
          <div class="roster-heading">
            <div class="roster-team-identity"><span class="team-crest large">${escapeHtml(selectedTeam.short_name || initialsFor(selectedTeam.name))}</span><span><h2>${escapeHtml(selectedTeam.name)}</h2><small>${selectedTeam.player_count} ${selectedTeam.player_count === 1 ? "player" : "players"} · Team roster</small></span></div>
            <div class="roster-heading-actions"><button class="button button-secondary button-small" type="button" data-team-edit="${selectedTeam.id}">Edit team</button><button class="roster-action remove" type="button" data-team-delete="${selectedTeam.id}">Delete</button></div>
          </div>
          <form class="add-player-form" id="add-player-form" data-team-id="${selectedTeam.id}">
            <label class="sr-only" for="player-name">Player name</label><input id="player-name" name="display_name" maxlength="80" placeholder="Add a player to the squad…" required>
            <label class="sr-only" for="player-number">Jersey number</label><input id="player-number" class="jersey-input" name="jersey_number" type="number" min="0" max="999" placeholder="#" aria-label="Jersey number">
            <label class="sr-only" for="player-role">Player role</label><input id="player-role" class="role-input" name="role" maxlength="40" placeholder="Role" aria-label="Player role">
            <button class="button button-primary button-small" type="submit"><span class="button-icon" aria-hidden="true">+</span>Add player</button>
          </form>
          <div class="roster-column-label"><span>PLAYER</span><span>NO.</span><span>ROSTER ACTIONS</span></div>
          <div class="roster-list">${roster}</div>
        ` : `
          <div class="roster-placeholder"><span class="empty-ball">♟</span><h2>Your squad starts here.</h2><p>Create a team, then add players and jersey details to build its roster.</p><button class="button button-primary" type="button" data-team-create><span class="button-icon" aria-hidden="true">+</span>Create your first team</button></div>
        `}
      </section>
    </div>
    <div class="teams-modal-root"></div>`;
}

function openTeamDialog({ mode, team = null, player = null }) {
  const root = document.querySelector(".teams-modal-root");
  if (!root) return;

  const teamForm = mode === "create-team" || mode === "edit-team";
  const editing = mode === "edit-team" || mode === "edit-player";
  const title = mode === "create-team"
    ? "Create a team"
    : mode === "edit-team"
      ? "Edit team details"
      : "Edit player";
  const description = mode === "create-team"
    ? "Give your squad a name and a short match-day badge."
    : mode === "edit-team"
      ? "Update how this team appears across GullyScore."
      : "Update this player's name, number, and squad role.";
  const fields = teamForm
    ? `
      <div class="field"><label for="dialog-team-name">Team name</label><input id="dialog-team-name" name="name" maxlength="80" required value="${escapeHtml(team?.name || "")}" placeholder="e.g. Salt Lake Strikers"></div>
      <div class="field"><label for="dialog-team-short">Short name <span class="muted">(optional)</span></label><input id="dialog-team-short" name="short_name" maxlength="12" value="${escapeHtml(team?.short_name || "")}" placeholder="e.g. SS"></div>`
    : `
      <div class="field"><label for="dialog-player-name">Player name</label><input id="dialog-player-name" name="display_name" maxlength="80" required value="${escapeHtml(player?.display_name || "")}"></div>
      <div class="field"><label for="dialog-player-number">Jersey number <span class="muted">(optional)</span></label><input id="dialog-player-number" name="jersey_number" type="number" min="0" max="999" value="${player?.jersey_number ?? ""}" placeholder="e.g. 7"></div>
      <div class="field"><label for="dialog-player-role">Role <span class="muted">(optional)</span></label><input id="dialog-player-role" name="role" maxlength="40" value="${escapeHtml(player?.role || "")}" placeholder="e.g. All-rounder"></div>`;

  root.innerHTML = `
    <dialog id="team-dialog">
      <form class="team-dialog-form" id="team-dialog-form" data-mode="${mode}" data-team-id="${team?.id ?? selectedTeamId ?? ""}" data-player-id="${player?.id ?? ""}">
        <div class="team-dialog-heading"><span><h2>${title}</h2><p>${description}</p></span><button class="dialog-close" type="button" aria-label="Close dialog" data-dialog-close>×</button></div>
        ${fields}
        <div class="dialog-actions"><button class="button button-secondary" type="button" data-dialog-close>Cancel</button><button class="button button-primary" type="submit">${editing ? "Save changes" : "Create team"}</button></div>
      </form>
    </dialog>`;
  const dialog = root.querySelector("#team-dialog");
  dialog.showModal();
  dialog.querySelector("input")?.focus();
}

async function loadTeamManagementPage() {
  const requestId = ++teamLoadId;
  try {
    const teams = await apiRequest("/api/teams");
    if (requestId !== teamLoadId || currentRoute() !== "teams") return;
    cachedTeams = teams;
    let selectedTeam = teams.find((team) => team.id === selectedTeamId) || teams[0] || null;
    selectedTeamId = selectedTeam?.id ?? null;
    if (selectedTeam) selectedTeam = await apiRequest(`/api/teams/${selectedTeam.id}`);
    if (requestId === teamLoadId && currentRoute() === "teams") {
      viewRoot.innerHTML = teamManagementPage(teams, selectedTeam);
    }
  } catch (error) {
    if (requestId !== teamLoadId || currentRoute() !== "teams") return;
    viewRoot.innerHTML = `
      ${heading("YOUR CLUB · SQUAD MANAGEMENT", "Teams &amp; <span class=\"text-lime\">players.</span>", "Build your squads and get ready for match day.")}
      <section class="panel teams-error"><strong>Couldn't load your teams.</strong><p>${escapeHtml(error.message)}</p><button class="button button-secondary button-small" type="button" data-team-retry>Try again</button></section>`;
  }
}

function renderApp() {
  const route = currentRoute();
  if (route === "history") matchHistoryLoading = true;
  if (route === "statistics") playerStatisticsLoading = true;
  if (route === "player-profile") playerProfile = null;
  if (route === "match-summary") selectedMatchSummary = null;
  pageLabel.textContent = pageNames[route];
  document.title = `${pageNames[route]} · GullyScore`;
  document.querySelectorAll("[data-nav]").forEach((link) => {
    const isActive = link.dataset.nav === route;
    link.classList.toggle("active", isActive);
    if (isActive) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });

  const pages = {
    landing: landingPage,
    dashboard: dashboardPage,
    teams: () => '<div class="teams-loading panel" role="status">Loading your teams…</div>',
    "create-match": createMatchPage,
    "live-scoring": scoringPage,
    history: historyPage,
    statistics: statisticsPage,
    "player-profile": playerProfilePage,
    "match-summary": matchSummaryPage,
  };
  viewRoot.innerHTML = pages[route]();
  if (route === "teams") loadTeamManagementPage();
  if (route === "create-match") loadCreateMatchPage();
  if (route === "live-scoring" && !activeScorecard && !scorecardLoading) loadLiveScorecard();
  if (route === "history") {
    applyHistoryFilters();
    loadMatchHistory();
  }
  if (route === "statistics") loadPlayerStatistics();
  if (route === "player-profile") loadPlayerProfile(currentRouteId());
  if (route === "match-summary") loadMatchSummary(currentRouteId());
  viewRoot.scrollTop = 0;
  window.scrollTo(0, 0);
}

function applyHistoryFilters() {
  const search = (document.querySelector("#history-search")?.value || "").trim().toLowerCase();
  const rows = [...document.querySelectorAll("#history-rows tr")];
  let visibleCount = 0;
  rows.forEach((row) => {
    if (!row.dataset.matchOutcome) {
      row.hidden = false;
      return;
    }
    const filterMatches = activeHistoryFilter === "all" || row.dataset.matchOutcome === activeHistoryFilter;
    const searchMatches = (row.dataset.search || "").includes(search);
    const visible = filterMatches && searchMatches;
    row.hidden = !visible;
    if (visible) visibleCount += 1;
  });
  const count = document.querySelector("#history-count");
  if (count) count.textContent = `Showing ${visibleCount} ${visibleCount === 1 ? "match" : "matches"}`;
}

function initialsFor(name) {
  return name.split(/\s+/).slice(0, 2).map((part) => part.charAt(0).toUpperCase()).join("");
}

function updateMatchPreview() {
  const form = document.querySelector("#create-match-form");
  if (!form) return;
  const values = new FormData(form);
  const homeSelect = form.querySelector("#home-team");
  const awaySelect = form.querySelector("#away-team");
  const home = homeSelect?.selectedOptions[0]?.textContent || "Choose Team A";
  const away = awaySelect?.selectedOptions[0]?.textContent || "Choose Team B";
  const venue = String(values.get("venue") || "");
  const title = String(values.get("title") || "").trim();
  const overs = String(values.get("overs") || "20");
  const wickets = String(values.get("wickets") || "10");
  const tossWinner = String(values.get("toss-winner") || "");
  const decision = String(values.get("toss-decision") || "BAT");
  const homeName = document.querySelector("[data-preview-home]");
  const awayName = document.querySelector("[data-preview-away]");
  const previewTitle = document.querySelector("[data-preview-title]");
  if (homeName) homeName.textContent = home;
  if (awayName) awayName.textContent = away;
  if (previewTitle) previewTitle.textContent = title || "Sunday League · New fixture";
  const homeCode = document.querySelector("[data-preview-home-code]");
  const awayCode = document.querySelector("[data-preview-away-code]");
  if (homeCode) homeCode.textContent = initialsFor(home);
  if (awayCode) awayCode.textContent = initialsFor(away);
  const format = document.querySelector("[data-preview-format]");
  const previewVenue = document.querySelector("[data-preview-venue]");
  const batting = document.querySelector("[data-preview-batting]");
  if (format) format.textContent = `${overs} overs · ${wickets} wickets`;
  if (previewVenue) previewVenue.textContent = venue || "Ground to be confirmed";
  const tossSelect = form.querySelector("#toss-winner");
  const tossTeam = tossSelect?.selectedOptions[0]?.textContent || "";
  if (batting) batting.textContent = tossTeam
    ? decision === "BAT" ? tossTeam : tossWinner === String(homeSelect?.value) ? away : home
    : "Select toss outcome";
  ["a", "b"].forEach((side) => {
    const count = form.querySelector(`[data-xi-count="${side}"]`);
    const selected = form.querySelectorAll(`[name="team-${side}-player"]:checked`).length;
    if (count) count.textContent = `${selected} / 11`;
  });
}

function setMatchError(message) {
  const error = document.querySelector("[data-match-error]");
  if (!error) return;
  error.textContent = message;
  error.hidden = !message;
}

async function loadCreateMatchPage() {
  const requestId = ++matchSetupLoadId;
  matchRosters = { a: [], b: [] };
  matchRosterRequests = { a: 0, b: 0 };
  try {
    const teams = await apiRequest("/api/teams");
    if (requestId !== matchSetupLoadId || currentRoute() !== "create-match") return;
    const homeSelect = document.querySelector("#home-team");
    const awaySelect = document.querySelector("#away-team");
    if (!homeSelect || !awaySelect) return;
    if (teams.length < 2) {
      homeSelect.innerHTML = '<option value="">Create at least two teams first</option>';
      awaySelect.innerHTML = '<option value="">Create at least two teams first</option>';
      setMatchError("Create at least two teams and add 11 players to each roster before setting up a match.");
      return;
    }

    const options = teams.map((team) => `<option value="${team.id}">${escapeHtml(team.name)}</option>`).join("");
    homeSelect.innerHTML = options;
    awaySelect.innerHTML = options;
    homeSelect.value = String(teams[0].id);
    awaySelect.value = String(teams.find((team) => team.id !== teams[0].id).id);
    refreshTossTeams();
    await Promise.all([loadMatchRoster("a"), loadMatchRoster("b")]);
    updateMatchPreview();
  } catch (error) {
    if (requestId !== matchSetupLoadId || currentRoute() !== "create-match") return;
    setMatchError(`Couldn't load teams. ${error.message}`);
  }
}

function refreshTossTeams() {
  const form = document.querySelector("#create-match-form");
  const tossSelect = form?.querySelector("#toss-winner");
  const homeSelect = form?.querySelector("#home-team");
  const awaySelect = form?.querySelector("#away-team");
  if (!tossSelect || !homeSelect || !awaySelect) return;
  const previous = tossSelect.value;
  const teamOptions = [homeSelect.selectedOptions[0], awaySelect.selectedOptions[0]]
    .filter((option) => option && option.value)
    .map((option) => `<option value="${option.value}">${escapeHtml(option.textContent)}</option>`)
    .join("");
  tossSelect.innerHTML = teamOptions || '<option value="">Select both teams first</option>';
  tossSelect.value = [...tossSelect.options].some((option) => option.value === previous)
    ? previous
    : homeSelect.value;
  if (homeSelect.value && homeSelect.value === awaySelect.value) {
    setMatchError("Team A and Team B must be different teams.");
  } else {
    setMatchError("");
  }
}

async function loadMatchRoster(side) {
  const form = document.querySelector("#create-match-form");
  const teamId = form?.querySelector(side === "a" ? "#home-team" : "#away-team")?.value;
  const list = form?.querySelector(`[data-xi-list="${side}"]`);
  const teamName = form?.querySelector(`[data-xi-team-name="${side}"]`);
  const requestId = ++matchRosterRequests[side];
  if (!teamId || !list) return;
  list.innerHTML = '<p class="field-hint">Loading roster…</p>';
  try {
    const team = await apiRequest(`/api/teams/${teamId}`);
    if (requestId !== matchRosterRequests[side] || currentRoute() !== "create-match") return;
    matchRosters[side] = team.players;
    if (teamName) teamName.textContent = team.name;
    list.innerHTML = team.players.length
      ? team.players.map((player) => `
        <label class="xi-player">
          <input type="checkbox" name="team-${side}-player" value="${player.id}">
          <span>${escapeHtml(player.display_name)}</span>
          <small>${player.jersey_number === null ? "" : `#${player.jersey_number}`}</small>
        </label>`).join("")
      : '<p class="field-hint">This team has no players yet. Add players under Teams &amp; players.</p>';
    updateMatchPreview();
  } catch (error) {
    if (requestId !== matchRosterRequests[side] || currentRoute() !== "create-match") return;
    list.innerHTML = `<p class="field-hint">${escapeHtml(error.message)}</p>`;
  }
}

function saveUndoState() {
  liveMatch.undoStack.push({
    score: liveMatch.score,
    wickets: liveMatch.wickets,
    legalBalls: liveMatch.legalBalls,
    extras: { ...liveMatch.extras },
    batters: liveMatch.batters.map((batter) => ({ ...batter })),
    ballHistory: [...liveMatch.ballHistory],
    commentary: [...liveMatch.commentary],
  });
  if (liveMatch.undoStack.length > 30) liveMatch.undoStack.shift();
}

function addCommentary(text, legalBall = true) {
  const currentOver = formatOvers(liveMatch.legalBalls);
  const label = legalBall && liveMatch.legalBalls % 6 === 0 ? `${Math.max(1, liveMatch.legalBalls / 6)}.0` : currentOver;
  liveMatch.commentary.unshift({ over: label, text });
  liveMatch.commentary = liveMatch.commentary.slice(0, 12);
}

function isInningsComplete() {
  return (liveMatch.innings === 2 && liveMatch.score >= liveMatch.target)
    || liveMatch.wickets >= liveMatch.wicketsLimit
    || liveMatch.legalBalls >= liveMatch.oversLimit * 6;
}

function recordDelivery(action, value) {
  if (isInningsComplete()) {
    showToast("This innings is complete.");
    return;
  }
  saveUndoState();

  if (action === "score") {
    const runs = Number(value);
    liveMatch.score += runs;
    liveMatch.legalBalls += 1;
    const striker = currentStriker();
    striker.runs += runs;
    striker.balls += 1;
    liveMatch.ballHistory.push(String(runs));
    if (runs % 2 === 1) liveMatch.batters.forEach((batter) => { batter.active = !batter.active; });
    addCommentary(runs === 0 ? "A dot ball. Well bowled, and the pressure stays on." : `${striker.name} works ${runs} ${runs === 1 ? "run" : "runs"} into the score.`);
  } else if (action === "wicket") {
    liveMatch.wickets += 1;
    liveMatch.legalBalls += 1;
    const dismissed = currentStriker();
    dismissed.active = false;
    dismissed.balls += 1;
    if (liveMatch.wickets < liveMatch.wicketsLimit) {
      const nextBatter = { name: ["Ishaan Roy", "Dev Kapoor", "Nikhil Bose", "Ayaan Ghosh", "Samar Dey"][Math.max(0, liveMatch.wickets - 5) % 5], runs: 0, balls: 0, active: true };
      liveMatch.batters.push(nextBatter);
    }
    liveMatch.ballHistory.push("W");
    addCommentary(`${dismissed.name} is out! The Panthers find a breakthrough.`);
  } else if (action === "extra") {
    const type = value;
    liveMatch.extras[type] += 1;
    liveMatch.score += 1;
    const legalBall = type === "b" || type === "lb";
    if (legalBall) {
      liveMatch.legalBalls += 1;
      currentStriker().balls += 1;
      liveMatch.batters.forEach((batter) => { batter.active = !batter.active; });
    }
    liveMatch.ballHistory.push(type === "wd" ? "Wd" : type === "nb" ? "Nb" : type.toUpperCase());
    const extraName = { wd: "Wide", nb: "No ball", b: "Bye", lb: "Leg bye" }[type];
    addCommentary(`${extraName}. One extra run added.`, legalBall);
  }

  if (liveMatch.legalBalls % 6 === 0 && liveMatch.legalBalls > 0) {
    liveMatch.batters.forEach((batter) => { batter.active = !batter.active; });
  }

  if (isInningsComplete()) {
    addCommentary(liveMatch.innings === 2 && liveMatch.score >= liveMatch.target
      ? `${liveMatch.home} win! Target chased down.`
      : liveMatch.innings === 1
        ? "First innings complete."
        : "Innings complete. That's the end of the chase.");
  }
  renderApp();
}

function undoDelivery() {
  const previous = liveMatch.undoStack.pop();
  if (!previous) return;
  Object.assign(liveMatch, previous);
  renderApp();
  showToast("Last delivery undone.");
}

function startSecondInnings() {
  if (liveMatch.innings !== 1 || !isInningsComplete()) return;
  liveMatch.battingFirstScore = liveMatch.score;
  liveMatch.battingFirstWickets = liveMatch.wickets;
  liveMatch.battingFirstOvers = formatOvers(liveMatch.legalBalls);
  liveMatch.target = liveMatch.score + 1;
  liveMatch.innings = 2;
  liveMatch.score = 0;
  liveMatch.wickets = 0;
  liveMatch.legalBalls = 0;
  liveMatch.extras = { wd: 0, nb: 0, b: 0, lb: 0 };
  const secondBattingSide = liveMatch.battingFirstTeam === "home" ? "away" : "home";
  const secondInningsPlayers = liveMatch.lineups?.[secondBattingSide] || ["Arjun Mehta", "Rohan Das"];
  liveMatch.batters = secondInningsPlayers.slice(0, 2).map((name, index) => ({
    name, runs: 0, balls: 0, active: index === 0,
  }));
  liveMatch.bowler = liveMatch.lineups?.[liveMatch.battingFirstTeam]?.[0] || liveMatch.bowler;
  liveMatch.ballHistory = [];
  liveMatch.commentary = [{ over: "0.0", text: `${currentBattingTeam()} begin the chase. Target: ${liveMatch.target}.` }];
  liveMatch.undoStack = [];
  renderApp();
  showToast(`${currentBattingTeam()} need ${liveMatch.target} to win.`);
}

async function createMatch(form) {
  const values = new FormData(form);
  const teamAId = Number(values.get("home"));
  const teamBId = Number(values.get("away"));
  const teamAPlayerIds = values.getAll("team-a-player").map(Number);
  const teamBPlayerIds = values.getAll("team-b-player").map(Number);
  if (!teamAId || !teamBId || teamAId === teamBId) {
    setMatchError("Choose two different teams to start a match.");
    return;
  }
  if (teamAPlayerIds.length !== 11 || teamBPlayerIds.length !== 11) {
    setMatchError("Select exactly 11 players for each team's playing XI.");
    return;
  }

  const date = String(values.get("date") || "");
  const payload = {
    team_a_id: teamAId,
    team_b_id: teamBId,
    team_a_player_ids: teamAPlayerIds,
    team_b_player_ids: teamBPlayerIds,
    overs_limit: Number(values.get("overs")),
    wickets_limit: Number(values.get("wickets")),
    toss_winner_team_id: Number(values.get("toss-winner")),
    toss_decision: String(values.get("toss-decision")),
    name: String(values.get("title") || "").trim() || null,
    venue: String(values.get("venue") || "").trim() || null,
    scheduled_at: date ? `${date}T12:00:00Z` : null,
  };
  const submitButton = form.querySelector('[type="submit"]');
  if (submitButton) submitButton.disabled = true;
  setMatchError("");
  try {
    const match = await apiRequest("/api/matches", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    sessionStorage.setItem("gullyscore.currentMatchId", String(match.id));
    activeScorecard = null;
    scoringErrorMessage = "";
    showToast("Match created. Set the opening batters and bowler to start scoring.");
    goTo("live-scoring");
  } catch (error) {
    setMatchError(error.message);
    if (submitButton) submitButton.disabled = false;
  }
}

document.addEventListener("click", (event) => {
  const target = event.target instanceof Element ? event.target : null;
  if (!target) return;

  if (target.closest("[data-dialog-close]")) {
    target.closest("dialog")?.close();
    return;
  }

  if (target.closest("[data-scoring-dialog-close]")) {
    target.closest("dialog")?.close();
    return;
  }

  const scoringAction = target.closest("[data-score-action]");
  if (scoringAction) {
    handlePersistentScoringClick(scoringAction);
    return;
  }

  const liveMatchLink = target.closest("[data-open-live-match]");
  if (liveMatchLink) {
    sessionStorage.setItem("gullyscore.currentMatchId", liveMatchLink.dataset.openLiveMatch);
    activeScorecard = null;
    scoringErrorMessage = "";
    return;
  }

  if (target.closest("[data-team-create]")) {
    openTeamDialog({ mode: "create-team" });
    return;
  }

  const teamSelect = target.closest("[data-team-select]");
  if (teamSelect) {
    selectedTeamId = Number(teamSelect.dataset.teamSelect);
    loadTeamManagementPage();
    return;
  }

  if (target.closest("[data-team-retry]")) {
    loadTeamManagementPage();
    return;
  }

  const editTeamButton = target.closest("[data-team-edit]");
  if (editTeamButton) {
    const team = cachedTeams.find((item) => item.id === Number(editTeamButton.dataset.teamEdit));
    if (team) openTeamDialog({ mode: "edit-team", team });
    return;
  }

  const editPlayerButton = target.closest("[data-player-edit]");
  if (editPlayerButton) {
    const row = editPlayerButton.closest(".roster-row");
    const team = cachedTeams.find((item) => item.id === selectedTeamId);
    const playerId = Number(editPlayerButton.dataset.playerEdit);
    const playerName = row?.querySelector(".roster-player-name strong")?.textContent || "";
    const playerRole = row?.querySelector(".roster-player-name small")?.textContent || "";
    const jersey = row?.querySelector(".roster-jersey")?.textContent || "";
    openTeamDialog({
      mode: "edit-player",
      team,
      player: {
        id: playerId,
        display_name: playerName,
        role: playerRole === "Player" ? "" : playerRole,
        jersey_number: jersey.startsWith("#") ? Number(jersey.slice(1)) : null,
      },
    });
    return;
  }

  const removePlayerButton = target.closest("[data-player-remove]");
  if (removePlayerButton) {
    const playerId = Number(removePlayerButton.dataset.playerRemove);
    const playerName = removePlayerButton.closest(".roster-row")?.querySelector(".roster-player-name strong")?.textContent || "this player";
    if (!window.confirm(`Remove ${playerName} from this team? Their match history will be kept.`)) return;
    apiRequest(`/api/teams/${selectedTeamId}/players/${playerId}`, { method: "DELETE" })
      .then(() => loadTeamManagementPage())
      .then(() => showToast(`${playerName} removed from the roster.`))
      .catch((error) => showToast(error.message));
    return;
  }

  const deleteTeamButton = target.closest("[data-team-delete]");
  if (deleteTeamButton) {
    const teamId = Number(deleteTeamButton.dataset.teamDelete);
    const teamName = cachedTeams.find((item) => item.id === teamId)?.name || "this team";
    if (!window.confirm(`Delete ${teamName}? Teams with match history cannot be deleted.`)) return;
    apiRequest(`/api/teams/${teamId}`, { method: "DELETE" })
      .then(() => {
        selectedTeamId = null;
        return loadTeamManagementPage();
      })
      .then(() => showToast(`${teamName} deleted.`))
      .catch((error) => showToast(error.message));
    return;
  }

  const actionButtonElement = target.closest("[data-action]");
  if (actionButtonElement) {
    const { action, runs, type } = actionButtonElement.dataset;
    if (action === "score" || action === "wicket" || action === "extra") recordDelivery(action, runs ?? type);
    if (action === "undo") undoDelivery();
    if (action === "start-chase") startSecondInnings();
    return;
  }

  const historyFilter = target.closest("[data-filter]");
  if (historyFilter) {
    activeHistoryFilter = historyFilter.dataset.filter;
    document.querySelectorAll("[data-filter]").forEach((button) => button.classList.toggle("active", button === historyFilter));
    applyHistoryFilters();
    return;
  }

  const statsTab = target.closest("[data-stat-tab]");
  if (statsTab) {
    activeStatTab = statsTab.dataset.statTab;
    playerStatisticsLoading = true;
    renderApp();
    return;
  }

  if (target.closest("[data-history-reload]")) {
    loadMatchHistory();
    return;
  }

  if (target.closest("[data-statistics-reload]")) {
    loadPlayerStatistics();
    return;
  }

  if (target.closest(".notification-button")) showToast("You're all caught up. Match day awaits.");
  if (target.closest(".profile-button")) showToast("Profile settings are coming soon.");
});

document.addEventListener("input", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLInputElement)) return;
  if (target.id === "history-search") applyHistoryFilters();
  if (target.form?.id === "create-match-form") updateMatchPreview();
});

document.addEventListener("change", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLInputElement || target instanceof HTMLSelectElement)) return;
  if (target.form?.id === "create-match-form") {
    if (target.id === "home-team" || target.id === "away-team") {
      refreshTossTeams();
      loadMatchRoster(target.id === "home-team" ? "a" : "b");
    }
    if (target instanceof HTMLInputElement && target.type === "checkbox" && target.checked) {
      const selectedCount = target.form.querySelectorAll(`[name="${target.name}"]:checked`).length;
      if (selectedCount > 11) {
        target.checked = false;
        showToast("A playing XI can contain exactly 11 players.");
      }
    }
    updateMatchPreview();
  }
});

document.addEventListener("submit", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLFormElement)) return;
  if (target.id === "innings-start-form") {
    event.preventDefault();
    if (target.reportValidity()) submitInningsStart(target);
    return;
  }
  if (target.id === "wicket-form") {
    event.preventDefault();
    if (target.reportValidity()) submitWicket(target);
    return;
  }
  if (target.id === "add-player-form") {
    event.preventDefault();
    if (!target.reportValidity()) return;
    const values = new FormData(target);
    const jerseyText = String(values.get("jersey_number") || "").trim();
    const payload = {
      display_name: String(values.get("display_name") || ""),
      jersey_number: jerseyText ? Number(jerseyText) : null,
      role: String(values.get("role") || "").trim() || null,
    };
    const submitButton = target.querySelector('[type="submit"]');
    if (submitButton) submitButton.disabled = true;
    apiRequest(`/api/teams/${target.dataset.teamId}/players`, {
      method: "POST",
      body: JSON.stringify(payload),
    })
      .then((player) => {
        selectedTeamId = Number(target.dataset.teamId);
        return loadTeamManagementPage().then(() => showToast(`${player.display_name} added to the roster.`));
      })
      .catch((error) => {
        if (submitButton) submitButton.disabled = false;
        showToast(error.message);
      });
    return;
  }

  if (target.id === "team-dialog-form") {
    event.preventDefault();
    if (!target.reportValidity()) return;
    const values = new FormData(target);
    const mode = target.dataset.mode;
    const teamId = Number(target.dataset.teamId);
    const playerId = Number(target.dataset.playerId);
    let path;
    let method;
    let payload;
    if (mode === "create-team") {
      path = "/api/teams";
      method = "POST";
      payload = {
        name: String(values.get("name") || ""),
        short_name: String(values.get("short_name") || "").trim() || null,
      };
    } else if (mode === "edit-team") {
      path = `/api/teams/${teamId}`;
      method = "PUT";
      payload = {
        name: String(values.get("name") || ""),
        short_name: String(values.get("short_name") || "").trim() || null,
      };
    } else {
      path = `/api/teams/${teamId}/players/${playerId}`;
      method = "PATCH";
      const jerseyText = String(values.get("jersey_number") || "").trim();
      payload = {
        display_name: String(values.get("display_name") || ""),
        jersey_number: jerseyText ? Number(jerseyText) : null,
        role: String(values.get("role") || "").trim() || null,
      };
    }

    const submitButton = target.querySelector('[type="submit"]');
    if (submitButton) submitButton.disabled = true;
    const dialog = target.closest("dialog");
    apiRequest(path, { method, body: JSON.stringify(payload) })
      .then((result) => {
        dialog?.close();
        if (mode === "create-team") selectedTeamId = result.id;
        if (mode === "edit-team" || mode === "edit-player") selectedTeamId = teamId;
        return loadTeamManagementPage().then(() => {
          showToast(mode === "create-team" ? "Team created." : mode === "edit-team" ? "Team details updated." : "Player details updated.");
        });
      })
      .catch((error) => {
        showToast(error.message);
        if (submitButton) submitButton.disabled = false;
      });
    return;
  }

  if (target.id !== "create-match-form") return;
  event.preventDefault();
  if (!target.reportValidity()) return;
  createMatch(target);
});

window.addEventListener("hashchange", renderApp);
if (!window.location.hash) window.location.hash = "#dashboard";
else renderApp();
