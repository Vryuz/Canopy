# AO session prompts — paste-ready

> **STATUS: superseded.** These three features were built directly on `main` in a normal
> Claude Code session (commits `795c0e0` resume-scan UI, `4a9c0da` map tour, `77d5d54`
> attestation share), **not** in AO — the AO plan was dropped. This file is kept as a record
> and as ready briefs in case any of them is ever rebuilt/extended inside AO for provenance.
> See `ORCHESTRA_SUBMISSION.md` for the honest current state.

Three self-contained briefs for three parallel AO sessions (each = its own git worktree,
its own Claude Code instance, zero shared memory with this conversation). Written so a
cold-start agent has everything it needs without asking you anything.

## Before you open AO

1. Install AO, point it at `C:\Users\varun\Desktop\Mireye`.
2. Confirm `main` is clean and pushed (`git status`, `git log -1` should show `da71c34` or
   later).
3. Start three sessions off `main`, each on its own branch (AO creates the worktree/branch
   for you — suggested branch names below, use them so the evidence trail is legible).
4. Paste one full prompt block per session, verbatim, as the *first* message in that
   session. Do not summarize or paraphrase them — the file paths and exact signatures
   matter.

## Why three, and why these three

They're scoped to touch **disjoint files** wherever possible, and where they must share a
file (`api/server.py`, `web/style.css`) each is told to *append*, never edit existing code —
that keeps merge conflicts small and mechanical instead of semantic. Session A is the one
that matters most for the Orchestra story (it makes "stateful continuity for stateless MCP"
literal and clickable); do that one first if you can only run one.

---

## Session A — Resume-scan UI · branch `feat/resume-scan-ui`

```
You're working in an existing Python/FastAPI + vanilla-JS project called Canopy, at
C:\Users\varun\Desktop\Mireye. Canopy verifies claims about US locations (flood risk,
carbon-credit claims, data-center siting) against cited federal ground truth from Mireye
plus independent second sources, and produces shareable, tamper-evident attestations.

BACKGROUND YOU NEED

The project has a national scan (src/scan.py) that screens ~1,800 US data-center sites
against Mireye. It's long-running and credit-metered, so it's built to checkpoint: every
completed row is appended to a JSONL file as it finishes, and a killed/interrupted run
resumes from that file with zero re-billed work. This is the single most interesting piece
of engineering in the project and it is currently invisible — you can only see it by
tailing a log file. Your job is to make it visible and clickable in the web UI.

THE EXACT MECHANISM (read src/scan.py yourself to confirm, but here's the shape):

- `run_scan(*, limit=None, concurrency=6, mireye=None, attestation_dir=None,
  checkpoint=None, progress_every=25) -> ScanResult` is the entry point. It's an async
  function.
- If you pass `checkpoint=<Path>`, it loads already-done rows from that file first
  (`_load_checkpoint`), skips those sites, and appends each newly-completed row to the same
  file as `{"osm_id": ..., "row": {...ScanRow fields...}}\n` (one JSON object per line).
- `ScanRow` fields: name, lat, lng, verdict, physical_mean, permitting, stranded_viability,
  top_lever, nearest_moratorium.
- The real checkpoint file from the full national run lives at
  `findings/checkpoint.jsonl` — it has ~1,814 completed rows already. DO NOT delete or
  truncate this file; it's a committed-adjacent artifact (findings/ is gitignored but the
  user has real data there locally). Copy it or work with it read-only for state display.

WHAT TO BUILD

A new page, `web/scan-resume.html`, served at a new route `GET /scan/resume-ui`, that:

1. On load, calls a new `GET /scan/state` endpoint (you add this) that reads
   `findings/checkpoint.jsonl` and returns JSON: `{"total_target": 1824, "completed": N,
   "remaining": 1824-N, "last_updated": <ISO timestamp of file mtime>}`. If the file doesn't
   exist, return completed=0, remaining=1824.
2. Renders that as a stat strip (reuse the `.stat` / `.stat-n` / `.stat-l` CSS classes
   already defined in web/style.css — look at web/map.html for how they're used) plus a
   progress bar (reuse `.pmeter` / `.pmeter-fill` classes from web/style.css, defined for
   the portfolio batch tab).
3. Has a "Resume 5 sites" button that POSTs to a new `POST /scan/resume-demo` endpoint (you
   add this). That endpoint must be SAFE FOR A LIVE DEMO — it must NEVER kick off a full
   1,824-site scan. It should call `run_scan(limit=<completed_count + 5>, concurrency=2,
   checkpoint=Path("findings/checkpoint.jsonl"))` — i.e. resume exactly 5 more sites past
   whatever is already checkpointed, then return the 5 newly-added ScanRow objects as JSON.
   Because `run_scan` is async and takes a few seconds even for 5 sites, run it with
   `await` directly in the endpoint (FastAPI route can be `async def`) — no need for
   background tasks or polling for this small a slice.
4. After the POST resolves, the page appends the 5 new rows to a visible list (name,
   verdict badge, stranded_viability) using the same `.badge` CSS classes the rest of the
   site uses (`.badge.disputed`, `.badge.verified`, `.badge.flagged` — see web/index.html
   for the exact markup pattern in `verdictBadge()`), and re-fetches `/scan/state` to update
   the stat strip and progress bar.
5. Include the site's real branding: copy the `<header class="topbar">` block verbatim from
   web/map.html (it has the Canopy logo SVG and nav), and link back to `/` and `/map`.
   Use the same `<link>` tags for fonts/stylesheet as web/map.html (Inter Tight + JetBrains
   Mono from Google Fonts, `/static/style.css` — check the exact `?v=NN` cache-bust suffix
   currently in web/map.html and match it).

CONSTRAINTS — READ CAREFULLY

- You are one of three parallel agents working on this repo in separate git worktrees.
  Another session may also touch api/server.py and web/style.css. To keep merges clean:
  - In api/server.py: ONLY ADD new route functions. Add them right before the final
    `if WEB_DIR.exists(): app.mount(...)` line. Do not edit, reorder, or reformat any
    existing route.
  - In web/style.css: if you need new rules beyond what already exists (`.stat`, `.pmeter`,
    `.badge`, etc. should already cover most of this), append a new clearly-delimited
    section at the very end of the file behind a comment banner like
    `/* --- scan-resume page (Session A) --- */`. Never edit an existing rule.
  - Do not touch web/index.html, web/map.html (other than copying the header block once),
    or any file under src/verticals/, src/clients/, src/output/.
- Never write a scan with unbounded limit. The 5-site cap in step 3 is load-bearing — this
  runs against a live paid API.
- The endpoint should work whether or not a live Mireye token is configured. If
  MIREYE_API_TOKEN is missing/offline mode, run_scan will use offline fixtures — that's
  fine, don't special-case it, just let it run and don't crash if it screens fewer than 5
  (some fixture coordinates may not resolve).

VERIFICATION

- `MIREYE_OFFLINE=1 python -m pytest tests/ -q` must still pass (55 tests currently) —
  you're not expected to add new tests for this UI page, just don't break existing ones.
- Manually start the server (`python -m uvicorn api.server:app --port 8000`) and confirm:
  `GET /scan/resume-ui` renders, `GET /scan/state` returns real numbers from the checkpoint
  file, clicking "Resume 5 sites" completes within ~30s and the stat strip updates.

COMMIT

One commit when done, conventional format (`feat(web): resume-scan demo UI`), body
explaining what it does and why. No AI co-author trailer in the commit message.
```

---

## Session B — Map story tour · branch `feat/map-tour`

```
You're working in an existing Python/FastAPI + vanilla-JS project called Canopy, at
C:\Users\varun\Desktop\Mireye. Canopy ran a national scan of ~1,800 US data centers,
screened each against Mireye ground truth plus a moratorium database, and found that 500 of
1,154 campuses (43%) are "stranded" — physically excellent sites now inside an active local
permitting moratorium. That finding is visualized at web/map.html, served at GET /map: an
Albers-projection SVG scatter of every campus over real US Census state outlines, colored
by verdict (red=disputed, amber=flagged, grey=verified), with a hover tooltip per dot.

READ web/map.html FIRST, in full. It's ~200 lines, self-contained (no external JS
dependencies besides the fonts). Understand:
- The `project(lat, lng)` function (Albers conic → SVG coords) and the `FIT` object it
  depends on (computed once from the state-outline bounds).
- The `CITIES` array and `drawCityAnchors()` — a sparse set of 12 muted metro labels
  already on the map for orientation (Seattle, Bay Area, LA, Phoenix, Dallas, Chicago,
  Ashburn VA, New York, Atlanta, Miami, Denver, Omaha).
- `showTip(e, c)` / `hideTip()` — the hover tooltip pattern.
- The data source: `GET /scan/campuses` returns the full array of campus objects (name,
  operator, lat, lng, verdict, physical_mean, permitting, stranded_viability, top_lever,
  building_count).

THE FINDING'S FOUR STANDOUT SITES (from docs/SCAN_RUNLOG.md — read that file too for exact
numbers) are Ashburn VA (Google/AWS cluster, DISPUTED, stranded ~0.95, in PJM),
Columbus OH (DISPUTED, worst permitting score in the sample, the market Mireye's own blog
recommends fleeing TO), Phoenix AZ (VERIFIED — clean on moratoria but weak on
water/externalities), and Council Bluffs IA (FLAGGED). These four are already used as the
canned examples in the main demo (web/index.html, the "dc" tab's example buttons) — use the
SAME coordinates so the tour is consistent with the rest of the site: Ashburn
39.0438,-77.4874 · Columbus 39.9612,-82.9988 · Phoenix 33.4484,-112.074 · Council Bluffs
41.2619,-95.8608.

WHAT TO BUILD

A guided tour overlay on the existing /map page (edit web/map.html directly — do not create
a new file):

1. Four numbered pin markers (a small square or diamond marker, distinct from the round
   campus dots already on the map — e.g. a `<rect>` or a `<path>` star, stroked in
   `var(--ink)`, NOT filled with a verdict color, so it reads as "narrator", not "data") at
   those four coordinates, each labeled 1–4 in reading order (Ashburn, Columbus, Phoenix,
   Council Bluffs).
2. A small fixed panel (bottom-left or bottom-right of the map figure — pick whichever
   doesn't collide with the existing `.map-legend` bar) with: current stop's title, one
   sentence from SCAN_RUNLOG's narrative for that site, and Prev/Next buttons. Also support
   pressing keys "1"–"4" to jump directly to a stop, and Escape to dismiss the tour panel.
3. Clicking a numbered pin, or navigating to it via the panel, should: pan/zoom is NOT
   required (keep the SVG viewBox fixed — this is a small scatter map, not a slippy map),
   but DO visually emphasize the pin's dot (e.g. toggle a CSS class that adds a pulsing
   outline ring — compositor-friendly, animate `transform: scale()` and `opacity` only, not
   width/height/top/left) and dim the rest of the campus dots slightly (e.g. drop their
   opacity to ~0.15) while a stop is focused, restoring full opacity when the tour is
   dismissed or on stop 0/none.
4. A "Start tour" button near the map heading (in `.map-head`) that opens the tour at stop
   1. The tour is off by default — the base map experience must be unchanged when a visitor
   hasn't clicked anything.

CONSTRAINTS — READ CAREFULLY

- You are one of three parallel agents working on this repo in separate git worktrees.
  Another session may also touch api/server.py and web/style.css.
  - Do not touch api/server.py at all — this task needs no new backend route, everything
    reads from the existing `GET /scan/campuses`.
  - In web/style.css: append new rules for the tour panel/pins at the very end of the file
    behind a comment banner `/* --- map story tour (Session B) --- */`. Do not edit any
    existing rule, including the existing `.map-*` rules — if you need to adjust existing
    map layout, do it via new classes added in the new section instead.
  - Do not touch web/index.html or anything under src/, api/ (other than reading for
    context).
- Respect `prefers-reduced-motion: reduce` — no pulsing/scaling animation if that media
  query matches; just show a static highlighted state instead. The existing style.css has
  a `@media (prefers-reduced-motion: reduce)` block near the bottom you can pattern-match.
- Keep it keyboard accessible: Tab should reach the tour controls, Enter/Space should
  activate them.

VERIFICATION

- `MIREYE_OFFLINE=1 python -m pytest tests/ -q` must still pass unchanged (this task adds
  no Python, so it should be a no-op check — just confirm you haven't broken anything).
- Manually start the server, open /map, confirm: page looks identical to before with the
  tour untouched, "Start tour" opens stop 1 (Ashburn), Next/Prev/1-4 keys all work, Escape
  closes it and dots return to normal opacity.

COMMIT

One commit when done, conventional format (`feat(web): guided story tour on the national
map`), body explaining what it does and why. No AI co-author trailer in the commit message.
```

---

## Session C — Shareable attestation polish · branch `feat/attestation-share`

```
You're working in an existing Python/FastAPI + vanilla-JS project called Canopy, at
C:\Users\varun\Desktop\Mireye. Canopy verifies claims about US locations and produces
content-hashed, tamper-evident "attestations" — each one gets a shareable URL at
GET /a/{attestation_id} (HTML, self-verifying: the page recomputes the sha256 in-browser
and shows Intact/Tampered) and GET /a/{attestation_id}.json (the raw record).

READ THESE FILES FIRST, in full:
- src/output/attestation.py — the `Attestation` pydantic model. Key fields: `version`,
  `issuer`, `kind` ("flood_verification" | "carbon_verification" | "datacenter_screen"),
  `subject` (human label — the address or coordinate), `issued_at`, `content_hash`, `body`
  (dict — the full verdict/discrepancies/evidence/etc.).
- src/output/store.py — `save(att) -> str` (returns the id), `load(att_id) -> Attestation |
  None`. The id is the first 12 hex chars of content_hash. Storage is flat JSON files under
  data/attestations/{id}.json.
- src/output/attestation_page.py — `render_page(att, att_id) -> str`, the function that
  builds the HTML body for the attestation page. This is where you'll add UI, NOT by
  creating a new file.
- api/server.py — the two existing routes, `GET /a/{att_id}.json` and
  `GET /a/{att_id}` (around lines 119–147). Note the `_PAGE_SHELL` string template right
  after them, which wraps `render_page()`'s output in `<html><head>...` with the site's
  fonts/stylesheet — that's where `<meta property="og:...">` tags need to go, since Open
  Graph tags must be in `<head>`, not inside the rendered body.

WHAT TO BUILD

1. Open Graph + Twitter Card meta tags in the attestation page's `<head>`, so pasting an
   `/a/{id}` link into Slack, iMessage, or X shows a rich preview instead of a bare link.
   Add these to the `_PAGE_SHELL` template in api/server.py (it currently takes one
   `{body}` format placeholder — extend it to also take `{title}` and `{description}`
   placeholders, and update the one call site, `attestation_html()`, to pass real values
   derived from the loaded `Attestation`: title = f"Canopy — {kind label} — {verdict}"
   (e.g. "Canopy — Flood verification — DISPUTED"), description = the verdict's
   `reasoning` string truncated to ~160 chars). Include at minimum: `og:title`,
   `og:description`, `og:type=website`, `twitter:card=summary`. Skip `og:image` — no image
   asset exists for this and generating one is out of scope.

2. A "Copy link" button on the attestation page itself (edit render_page() in
   src/output/attestation_page.py to add it, near the top of the page, next to or below the
   verdict badge). Clicking it copies `window.location.href` to the clipboard via
   `navigator.clipboard.writeText(...)` and shows a brief "Copied" confirmation (toggle a
   CSS class or swap the button's text for ~1.5s, then revert — no external toast library).

3. A "Share to X" link/button next to it: a plain `<a>` tag to
   `https://twitter.com/intent/tweet?text=<url-encoded text>&url=<url-encoded attestation
   URL>`, `target="_blank" rel="noopener"`. The tweet text should be dynamic based on the
   verdict — e.g. for a DISPUTED verdict: "Canopy flagged a discrepancy: {subject} — {one-
   line reasoning, truncated}". Build this string in Python (in render_page(), you already
   have all the data) and URL-encode it with `urllib.parse.quote` — don't try to build the
   encoded URL in JS.

4. Match existing visual style: buttons should use the same visual language as the `.cta`
   button class already defined in web/style.css (dark pill button) — reuse that class
   rather than inventing a new button style. Look at how web/index.html uses `.cta` for the
   pattern.

CONSTRAINTS — READ CAREFULLY

- You are one of three parallel agents working on this repo in separate git worktrees.
  Another session may also touch api/server.py and web/style.css.
  - In api/server.py: you MUST touch the `_PAGE_SHELL` string and the `attestation_html()`
    function body (that's the whole point of this task) — that's expected and fine, keep
    the diff to exactly those two things, don't refactor anything else nearby, and don't
    touch any other route in the file.
  - In web/style.css: if the existing `.cta`, `.share`, `.integrity` classes (search for
    them — they already exist, built for the attestation page) don't cover what you need,
    append new rules at the very end of the file behind a comment banner
    `/* --- attestation share UI (Session C) --- */`. Do not edit any existing rule.
  - Do not touch web/index.html or web/map.html at all.
  - Do not touch src/output/store.py, src/output/attestation.py, or anything under
    src/verticals/, src/clients/.
- The clipboard API requires a secure context; `localhost` counts as secure, so this will
  work in local testing without extra configuration.
- Never invent a claim about the attestation that isn't in its actual data — the tweet-text
  builder must only use fields that exist on the Attestation/verdict objects; if a field is
  missing/None, degrade gracefully (omit that clause) rather than printing "None" or
  "undefined".

VERIFICATION

- `MIREYE_OFFLINE=1 python -m pytest tests/ -q` must still pass (55 tests currently) — if
  you add Python logic (the tweet-text builder, the meta-tag values), add 2-3 focused
  pytest cases in tests/test_agent.py following the existing style for
  src/output/attestation_page.py tests (search that file for
  "test_attestation_page_renders" to find the pattern) — e.g. assert the og:title contains
  the verdict kind, assert the tweet URL is properly encoded, assert a missing field
  degrades without crashing.
- Manually start the server, run any existing verify call to mint a fresh attestation (or
  reuse one already in data/attestations/ if present), open its /a/{id} page, confirm: og
  tags are present in page source (view-source or curl the page and grep), Copy Link works
  and shows the confirmation state, Share to X opens the correct intent URL with sensible
  pre-filled text.

COMMIT

One commit when done, conventional format (`feat(web): shareable attestation links with OG
previews`), body explaining what it does and why. No AI co-author trailer in the commit
message.
```

---

## After all three land

1. In AO's dashboard, check each session's status — merge each worktree branch back to
   `main` one at a time (AO surfaces PR/merge state per session; use its merge action, or
   fall back to `git merge feat/resume-scan-ui` etc. from a terminal on `main` if AO's merge
   UI is unavailable). Resolve any conflicts in `api/server.py` / `web/style.css` by keeping
   both additions — they were told to append, so conflicts should be mechanical (both sides
   added new content near the same anchor line), not semantic.
2. Re-run the full test suite once on `main` after all three are merged:
   `MIREYE_OFFLINE=1 PYTHONIOENCODING=utf-8 python -m pytest tests/ -q`
3. Screenshot AO's dashboard while all three sessions are visibly running/active — that's
   your primary piece of Orchestra evidence. Also run `git log --oneline --graph -10` and
   `git worktree list` after merging and screenshot those too.
4. Update docs/ORCHESTRA_SUBMISSION.md: replace the "Honest notes" section's timeline
   caveat with the real one — these three features were built in AO on [date], name the
   three branches/commits.
5. Push `main`.
