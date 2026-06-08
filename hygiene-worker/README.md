# BDC Hygiene Worker

A tiny tool each team member runs on their own PC. It rides **your already
logged-in, trusted Chrome** to scrape Booking.com (BDC) hygiene data for the
properties you queue on the Hygiene Scrape page, and the results are written straight to
the **BDC Hygiene** Google Sheet.

You never type a password into a script — it uses the Chrome window you log into
yourself. If Booking ever asks you to log in, just log in in that window.

## How it fits together

```
OTA Tracker page (Hygiene Scrape)  ──queue BDC IDs──►  Apps Script (Code.gs) + Sheet queue
        ▲                                                │
        │ live status                       your worker claims YOUR jobs
        │                                                ▼
   you watch progress            worker.py ──► your trusted Chrome ──► Booking.com
                                                         │
                                  posts results ─┘ ──► Apps Script writes the BDC Hygiene Sheet
```

Everything lives in **ota-handler**: the page is part of the OTA Tracker static
site, the backend is its Google Apps Script (`Code.gs`), and results land in the
**BDC Hygiene** sheet. No separate server or database.

Jobs are routed by name: the page sends jobs to the worker whose `WORKER_NAME`
matches the name you type on the page.

## One-time setup

1. **Install Python 3.11+** (tick "Add Python to PATH" during install).
2. Get this folder onto your PC (zip or `git clone`).
3. Copy `.env.example` to `.env` and fill it in:
   - `GAS_URL` = the Apps Script web-app URL (ends in `/exec`; ask your admin).
   - `WORKER_TOKEN` = the shared token (ask your admin).
   - `WORKER_NAME` = the **exact** name you'll type on the Hygiene Scrape page.
4. Double-click **`start-worker.bat`** once — the first run creates a virtual
   environment, installs dependencies, and downloads the browser engine. (Later
   runs start instantly.)

## Daily use

1. Double-click **`launch-chrome.bat`**. A Chrome window opens on the BDC admin.
   Log into Booking.com if it asks. **Leave this window open.**
2. Double-click **`start-worker.bat`**. It attaches to that Chrome and waits for
   jobs. You should see `Attached to your trusted Chrome. Watching for jobs…`.
3. Open the OTA Tracker site → **Hygiene Scrape**, type your name, paste BDC IDs, click **Start Scrape**,
   and watch the rows turn **Done**. The Sheet updates as each finishes.

To stop, close the worker window (Ctrl+C). You can leave it running all day.

## Troubleshooting

- **"Worker not connected" on the page** → start `start-worker.bat` (and make
  sure `WORKER_NAME` matches the name you typed on the page exactly).
- **"Could not attach to Chrome on port 9222"** → run `launch-chrome.bat` first
  and keep that window open. Don't use your normal Chrome — it must be the one
  launched with the debug port.
- **A job shows "Needs Login"** → log into Booking.com in the worker's Chrome
  window; it resumes on its own.
- **Port 9222 already in use** → change `CDP_PORT` in `.env` and the
  `--remote-debugging-port` value in `launch-chrome.bat` to match.

## Notes

- Nothing secret lives here: no Booking password, no Google key. The worker only
  drives your browser and talks to Apps Script with the shared `WORKER_TOKEN`.
- The scraping logic is the same proven code from the original local scraper.
