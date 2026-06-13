# OTA-Handler — Project Notes / Handoff

_Last updated: 2026-06-13. Working state snapshot so work can resume after a restart._

## TL;DR — what this is
Two related projects:

1. **`C:\Users\cs03778\ota-handler`** — a **static HTML site** (GitHub Pages) + a **Google Apps Script** backend. Internal OTA tracking dashboard for FabHotels. Repo: `https://github.com/Praveen-svnit/OTA-Handler`, live at **https://praveen-svnit.github.io/OTA-Handler/**.
2. **`C:\Users\cs03778\bdc-hygiene-app`** — the **open (un-licensed) Booking.com hygiene scraper** (Flask + Playwright, runs locally on the user's Chrome). Distributed as a password-gated zip download from the site's **Scraper** page.

(An earlier licensed EXE version, `BDC-ExtraGOD`, was **deleted** to the Recycle Bin — abandoned approach.)

## Architecture (ota-handler)
- **Frontend:** `docs/` is the GitHub Pages root. SPA shell `docs/index.html` loads `assets/*.js` modules. Hash router (`assets/router.js`), pages register `window.PAGE_*` and are wired in `assets/app.js`.
- **Backend:** `docs/Code.gs` deployed as a **Google Apps Script Web App** (runs as the owner's Google account; "Anyone" access). Frontend calls it via `GAS_URL` in `docs/assets/api.js`. 1-hour `CacheService` cache; append `&refresh=1` to bypass.
- **Deploying changes:**
  - **Frontend (`docs/`)** — just `git push`; GitHub Pages auto-rebuilds (~1 min). CSS is cache-busted via `styles.css?v=2` in index.html.
  - **Backend (`Code.gs`)** — **MANUAL**: paste latest `docs/Code.gs` into the Apps Script editor → **Deploy → Manage deployments → ✏️ edit → Version: New version → Deploy**. The deployment URL stays the same. **Cache survives redeploys** — click the page **Refresh** button (or `?action=...&refresh=1`) to see new data.

## Sidebar pages
- **Listing Overview** (top) — see below.
- **Booking.com / GoMMT / GMB** — original channel pages (`assets/pages/booking.js`, config-driven; tabs: Matrix, Hygiene Checks, Value Summaries).
- **Agoda, Expedia, Cleartrip, Yatra, EaseMyTrip, Ixigo, Indigo** — new OTA channel pages (`assets/pages/ota-channel.js` + `ota-channel-config.js`), same tabs as Booking. Matrix is the full ported one (Rows/Columns/Filters multiselects, hide-zero, save defaults, drill-down).
- **Photoshoot, OTA DSS** — simple table pages (`assets/pages/ota-pages.js`); OTA DSS has DoD/WoW/MoM sub-tabs.
- **— OTA Tools —** group → **Mapping Checker** (`mapping.js`, iframe of `su-mapping-checker.html`), **Scraper** (`scraper.js`).
- **Listing Tracker** — REMOVED.

## Listing Overview (`docs/assets/pages/listing-overview.js` + `Code.gs` → `listingOverview`)
- **Base** = BDC Hygiene **`Inv`** tab (sheet `1VkFA4keBAT3tG5NkZwmSNRbLZJgx2neOhZ7Zuj2z_98`), non-churned rows = **1610**.
- **`Inv` is a master**: cols A=id, E=STATUS, **F=`Pre/Post` (Prop Set)**, **G=`Prop Cat`**, plus per-OTA status cols (but GMB/Indigo cols there are empty — DON'T use Inv for live status).
- **Live status** for each channel comes from its **own sheet's status column** (`statusHeader` in `OVERVIEW_OTAS`), value `Live`. Channels (Booking/GoMMT) use `Sub Status`; GMB uses `GMB Sub Status`; the 7 OTAs use `<OTA> Status` (e.g. `Agoda Status`).
- **Live Month** = Booking sheet's `FH Live Month` joined by id (only canonical source; ~25 props disagree with other sheets — known limitation).
- Backend aggregates **(Prop Set × Prop Cat × Live Month)** groups, each with per-OTA `l` (live), `p` (pending), `e` (exception) counts. Page filters + sums instantly. Filters: **Prop Set, Prop Cat, Live Month**.
- **Pending = base − Live** (includes blank/no-status props — DECIDED CORRECT: 70 not 69; a blank-status property is genuinely not-listed).
- **Exception** = status containing "exception", read from `excHeader` (default `Sub Status`; GMB `GMB Sub Status`). A subset of Pending. Live values: Booking 5, GoMMT 24, GMB 4, Agoda 1, Expedia 5, Cleartrip 2, EaseMyTrip 5, Yatra/Ixigo/Indigo 0.
- Verified totals (base 1610): Agoda 1567/97.3%, Expedia 1498/93%, Cleartrip 1476/91.7%, GoMMT 1464/90.9%, GMB 1336/83%, Booking 1174/72.9%, Yatra 899/55.8%, EaseMyTrip 690/42.9%, Ixigo 237/14.7%, Indigo 108/6.7%.
- Below the table: **Deep dive** — pick any channel → full Rows/Columns/Filters pivot (reuses `window.OTA_renderMatrix`).

## Scraper (`bdc-hygiene-app`, distributed via site Scraper page)
- Site **Scraper** page (`assets/pages/scraper.js`): password gate (SHA-256, default password **`fabhotels2026`** — change `PW_HASH`). Re-locks on every browser refresh.
- Downloads `docs/downloads/bdc-hygiene-app.zip` (CODE ONLY — **no `service_account.json`**; key shared privately).
- Local app self-registers a `bdchygiene://` URL protocol on first run, so the site's **▶ Start engine** button can launch it. Has **CORS** so the hosted https page can drive `http://localhost:8765`. Controls: Open Booking & log in, Run / Run all / Stop, **⏻ Shut down engine** (kills engine + console window). No auto-opened localhost tab.
- **Service account:** `sujeet@nifty-seat-268909.iam.gserviceaccount.com` (project `nifty-seat-268909`) — used by the scraper AND for local data inspection. All OTA sheets are shared with it (Viewer).

## Key IDs
- Inv / BDC Hygiene sheet: `1VkFA4keBAT3tG5NkZwmSNRbLZJgx2neOhZ7Zuj2z_98`
- Booking BCOM: `1vjm8BX1QZKMqXiLjbokCD0R91JvlscXcg5812p_IolI` (live tab `Live`)
- GoMMT: `1Pr2iEC7UvI7sWgwx4qQGQcO9Iw3dyzBqLpAr2mrQvKc` (`Live`)
- GMB: `16awDYKs1jdR0x5VDJTo8CokB_fqqjr7JRpmRY0tv4Fk` (`New Tracker`)
- OTA sheet IDs + tabs: see `OTA_SHEETS` in `docs/Code.gs`.
- GAS deployment URL: in `docs/assets/api.js` (`GAS_URL`).

## Open / pending items
- **Redeploy `Code.gs`** whenever it changes (last changes: exception-from-Sub-Status, month restore, pending=base−live). Exceptions confirmed working in backend; refresh page to see.
- **Photoshoot** page tab is large (17.6k rows) — slow (~50s), can't cache (>100KB). Could point at a smaller tab or cap rows.
- Optional: per-OTA check-column tweaks for the channel pages' Hygiene/Value tabs (`ota-channel-config.js`).
- UI was refreshed (indigo accent, depth) via `docs/assets/styles.css`.

## Working method
- Edits are committed + pushed to `main` after each change (commits co-authored). Git identity is auto-detected (Praveen Kumar Yadav).
- Syntax-check JS with `node --check`; `.gs` via a temp `.js` copy.
- To inspect sheets locally: Python + gspread with `bdc-hygiene-app/service_account.json`.
