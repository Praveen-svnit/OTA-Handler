# OTA Tracker (Static HTML + Google Apps Script)

A static site with a Google Apps Script backend. Goals: instant page navigation,
presentation-ready UI, free hosting, team needs zero Google Sheet permissions.

## Architecture at a glance

```
                   ┌─── (your Google account) ────┐
   GitHub Pages    │                              │
   (free, static)  │  Google Apps Script Web App  │ ──► Reads Sheets
   ──────────────► │  Code.gs (this folder)       │
   index.html      │                              │
   assets/*        └──────────────────────────────┘
        │                          ▲
        └──── JSON over fetch() ───┘
```

* **Frontend** — `index.html` + `assets/` files in this folder. Hosted free on
  GitHub Pages. Single URL with hash-based internal routing (`#/booking`,
  `#/gommt`, etc.). All interactivity is in-browser JS — clicks feel instant.

* **Backend** — `Code.gs` deployed as a Google Apps Script Web App. Holds the
  credentials (runs as YOU), reads the sheets, returns JSON. 1-hour cache via
  `CacheService`.

## One-time setup

### 1. Deploy the Apps Script backend

1. Go to <https://script.google.com>, click **New project**.
2. Replace the default `Code.gs` with the contents of `Code.gs` from this folder.
3. **Run → Run function: `_smokeTest`** once. It will prompt you to grant
   permission to read your sheets — accept.
4. **Deploy → New deployment → Web app**:
   - Description: `OTA Tracker backend v1`
   - **Execute as**: `Me (<your fabhotels.com email>)`
   - **Who has access**: `Anyone`
5. Click **Deploy**, copy the deployment URL (it ends in `/exec`).
6. Test the URL in a browser: append `?action=ping`. You should see
   `{"ok":true,"data":{"time":"..."}}`.

### 2. Configure the frontend

Edit `assets/api.js` line ~15:

```js
const GAS_URL = 'PASTE_YOUR_DEPLOYMENT_URL_HERE';
```

### 3. Test locally

You can preview the site locally without any web server — but `fetch()` to
the GAS URL needs HTTPS (which GAS always uses), so it works fine from
`file://` for testing.

```bash
# Just open index.html in Chrome / Edge directly:
start index.html       # Windows
open index.html        # macOS
```

### 4. Deploy to GitHub Pages

1. Push this folder to a GitHub repo.
2. Repo **Settings → Pages**:
   - Source: `Deploy from a branch`
   - Branch: `main`, folder: `/v2` (or move these files to repo root if you prefer)
3. Wait ~1 min. Visit `https://<your-org>.github.io/<repo>/v2/` — done.

### 5. Share the URL with your team

Bookmark it. That's it. They don't need Google Sheet access — your Apps Script
reads on their behalf.

## What's included in Phase 1

| Page | Status |
|---|---|
| Booking.com | ✅ Full — Status & Tracker, Hygiene Checks, Value Summaries, E-F-L-M Matrix |
| GoMMT | ✅ Full — same as Booking.com, driven by config |
| Listing Tracker | ✅ Full — searchable + filterable table |
| Last Checked | ✅ Full — run history + last-run details viewer |
| Mapping Checker | ⏳ Placeholder (Phase 2) — see notes below |

## Phase 2 — Mapping Checker port

The existing `C:\Users\cs03778\su-mapping-checker.html` already contains the
full 12-check validation engine in vanilla JS. To port it into this app:

1. Copy the `runAnalysis()` function (and its helpers `parsePMSRoom`,
   `parsePMSRate`, `parseOBP`, `normId`) from `su-mapping-checker.html`
   into `assets/pages/mapping.js`.
2. Replace the inline gviz JSONP fetches (`fetchGviz`) with `API.crs()` and
   `API.dashboard()` from `api.js`.
3. Wire the upload UI to a single `<input type="file">` and use `SheetJS`
   (via CDN, like the old HTML did) to parse the SU file.

Estimated effort: 1 day.

## Updating data

* **End users**: click the **Refresh** button in any page header. It bypasses
  both the in-browser cache and the Apps Script cache, fetching fresh.
* **Default cache**: 1 hour. Configurable in `Code.gs` (`CACHE_TTL_S`).

## Adding a new page

1. Create `assets/pages/foo.js`:
   ```js
   (function () {
     async function render(target) { /* ... */ }
     window.PAGE_FOO = { id: 'foo', label: 'Foo', render };
   })();
   ```
2. Add `<script src="assets/pages/foo.js"></script>` to `index.html` (before
   `app.js`).
3. Add `Router.register(window.PAGE_FOO);` to `assets/app.js`.

## Why not pure static HTML?

The Google Sheets must stay restricted to a service account — they can't be
made publicly readable. A pure-static frontend would have to embed credentials
in JS, which is unsafe. The Apps Script backend solves this: it runs server-side
in Google's free infrastructure as you, returns JSON to anyone, exposes no
credentials.

## Updating sheet IDs

Edit the constants at the top of `Code.gs`.
