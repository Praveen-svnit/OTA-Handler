"""
BDC Hygiene — run-and-go scraper.

One simple script: reads the property list from the BDC Hygiene sheet, fetches
the data fast through your already-logged-in Chrome (no page, no queue, no
Apps Script), and writes results straight back to the sheet in one batch.

Phase 1 fills: Review Score (F) + Review Count (G), Scrap Status (E),
Last Checked (T). More fields get added phase by phase.

Run:
    1. launch-chrome.bat  (logged into Booking.com), keep it open
    2. run-hygiene.bat     (or: <python> run_hygiene.py [--limit N] [--ids 123,456])
"""

import argparse
import asyncio
import os
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv
from playwright.async_api import async_playwright

import scrape_lib
from scrape_lib import find_ses, fetch_reviews_fast, SessionExpired

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
SERVICE_ACCOUNT_FILE = os.environ.get(
    "SERVICE_ACCOUNT_FILE", r"C:\Users\cs03778\Documents\sujeet_key.json")
SHEET_ID    = os.environ.get("HYG_SHEET_ID", "1VkFA4keBAT3tG5NkZwmSNRbLZJgx2neOhZ7Zuj2z_98")
TAB_NAME    = os.environ.get("HYG_TAB", "BDC Hygiene")
CDP_PORT    = os.environ.get("CDP_PORT", "9222")
CONCURRENCY = int(os.environ.get("CONCURRENCY", "16"))

scrape_lib.log = lambda m, *a, **k: None   # keep per-fetch logs quiet


def connect_sheet():
    scope = ["https://www.googleapis.com/auth/spreadsheets",
             "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scope)
    return gspread.authorize(creds).open_by_key(SHEET_ID).worksheet(TAB_NAME)


def col_index(headers, *keywords):
    for i, h in enumerate(headers):
        low = str(h).strip().lower()
        if all(k in low for k in keywords):
            return i
    return -1


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="only process the first N properties")
    ap.add_argument("--ids", default="", help="comma-separated BDC IDs to process (default: all)")
    args = ap.parse_args()

    print("📋 Reading the BDC Hygiene sheet…")
    ws = connect_sheet()
    values = ws.get_all_values()
    headers = values[0]
    bdc_col = col_index(headers, "bdc", "id")
    if bdc_col < 0:
        print("❌ Could not find a 'BDC ID' column."); return

    only = {x.strip() for x in args.ids.split(",") if x.strip()}
    targets = []  # (sheet_row, bdc_id)
    for i in range(1, len(values)):
        bdc = str(values[i][bdc_col]).strip().replace(".0", "") if bdc_col < len(values[i]) else ""
        if not bdc or bdc.lower() == "nan":
            continue
        if only and bdc not in only:
            continue
        targets.append((i + 1, bdc))   # sheet row is 1-based
    if args.limit:
        targets = targets[:args.limit]
    print(f"   {len(targets)} properties to check.")
    if not targets:
        return

    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(f"http://localhost:{CDP_PORT}")
        except Exception as e:
            print(f"❌ Could not attach to Chrome on port {CDP_PORT}: {e}")
            print("   Run launch-chrome.bat first and keep it open.")
            return
        ctx = browser.contexts[0] if browser.contexts else None
        if ctx is None:
            print("❌ No browser context."); return
        ses = find_ses(ctx)
        if not ses:
            print("❌ No Booking session found — log into Booking.com in the Chrome window first.")
            return

        print(f"🚀 Fetching reviews ({CONCURRENCY} at a time)…")
        sem = asyncio.Semaphore(CONCURRENCY)
        results = {}        # sheet_row -> (score, count)
        done = {"n": 0}
        session_dead = {"flag": False}
        t0 = time.time()

        async def work(row, bdc):
            if session_dead["flag"]:
                return
            async with sem:
                try:
                    score, count = await fetch_reviews_fast(ctx, ses, bdc)
                    results[row] = (score, count)
                except SessionExpired:
                    session_dead["flag"] = True
                except Exception:
                    results[row] = ("", "")
            done["n"] += 1
            if done["n"] % 25 == 0 or done["n"] == len(targets):
                print(f"   …{done['n']}/{len(targets)}")

        await asyncio.gather(*(work(r, b) for r, b in targets))

        if session_dead["flag"]:
            print("\n🔐 Booking session needs re-verifying (2FA). Re-open Booking in Chrome,")
            print("   complete any verification, then run this again.")
            if not results:
                return

        # ── Write back in one batch ───────────────────────────────────────────
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        updates = []
        for row, (score, count) in results.items():
            # E=Scrap Status, F=Review Score, G=Review Count  (contiguous E:G)
            updates.append({"range": f"E{row}:G{row}", "values": [["Successful", score, count]]})
            updates.append({"range": f"T{row}",        "values": [[ts]]})
        if updates:
            print(f"📝 Writing {len(results)} rows to the sheet…")
            ws.batch_update(updates, value_input_option="USER_ENTERED")

        secs = time.time() - t0
        print(f"✅ Done — {len(results)} properties in {secs:.0f}s "
              f"({len(results)/secs:.1f}/sec).")


if __name__ == "__main__":
    asyncio.run(main())
