# BDC Hygiene App

A small **local** app that pulls Booking.com (BDC) hygiene data straight into the
shared **BDC Hygiene** Google Sheet — fast, from your own logged-in Chrome.

It runs on your PC (it needs your trusted Booking login). Everything writes to the
same sheet, so the whole team's results land in one place.

---

## ⬇️ Download

**[Download the Hygiene App (zip)](https://minhaskamal.github.io/DownGit/#/home?url=https://github.com/Praveen-svnit/OTA-Handler/tree/main/hygiene-app)**

That link downloads just this folder as a zip. Unzip it somewhere you'll remember
(e.g. your Desktop).

> The download does **not** include the Google key (`service_account.json`).
> Ask the admin (Praveen / Sujeet) for that file and drop it into the folder — see
> step 2 below. It's left out on purpose so the code can be public while the key
> stays private.

---

## First-time setup

1. Install **Python** (Anaconda is fine) and **Google Chrome** if you don't have them.
2. Double-click **`Start Hygiene App.bat`**. The first run installs dependencies
   (~1–2 min, includes the Chrome automation engine); after that it starts fast and
   opens the control panel in your browser (`http://localhost:8765`).
   - It also drops a **"BDC Hygiene" shortcut on your Desktop**, so from then on
     it's a single click — no hunting for the .bat.
3. **Add your Google key (one-time).** Get `service_account.json` from the admin,
   then in the control panel use the **"One-time setup — add your Google key"** box
   to locate it. It's saved locally and never leaves your PC.
   - (Or just drop `service_account.json` into this folder manually — same effect.)
   - Whichever service account is used (OTA-handler or Sujeet's), it must have
     **Editor** access to the BDC Hygiene sheet.

> Nothing here is public — the control panel only runs at `localhost` on your machine.
> Your Booking login lives in your own Chrome and is never shared.

---

## Daily use

1. Double-click **`Start Hygiene App.bat`** — the control panel opens.
2. Click **"Open Booking & log in"** → a Chrome window opens; log into Booking.com
   there. The panel shows **"Booking session ready ✓"**.
3. Scrapers are grouped into three categories:
   - **Fast — endpoint**: instant, no attention needed.
   - **Fast — needs verification**: may pause to open a tab so you can verify your
     identity, then resumes automatically.
   - **Page render**: opens a page per property (slower).
4. Click **Run** on any single scraper, or **Run all (N)** on a category to fetch
   every field in that category in one pass (property by property).
   - Use the **Test limit** box (e.g. `50`) to try a small batch first.
   - Use **Stop** to halt safely — it finishes the current property and saves.

---

## Notes

- If a scrape says the session needs re-verifying, complete Booking's verification
  in the Chrome window and it resumes / re-run to fill the rest.
- Each scraper only writes its own columns, so running one never disturbs the others.
- Columns are matched to the sheet by **header keywords**, so the sheet can be
  reordered freely.

## Files

| File | What it is |
|---|---|
| `Start Hygiene App.bat` | One-click launcher (installs deps on first run) |
| `app.py` | The local control-panel web server (Flask) |
| `index.html` | The control-panel UI |
| `scrape_core.py` | Engine: Chrome session, sheet read/write, run logic |
| `scrapers.py` | All the field scrapers + their categories |
| `requirements.txt` | Python dependencies |
| `service_account.json` | **(not in the download — get it from the admin)** |
