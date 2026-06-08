"""
BDC Hygiene local worker.

Runs on a team member's PC. It attaches to their ALREADY logged-in, trusted
Chrome over the DevTools protocol (Way 1 — no automated login), polls the
OTA Tracker's Apps Script backend for hygiene-scrape jobs they queued, scrapes
each property inside the trusted browser, and posts results back (Apps Script
writes the BDC Hygiene Sheet).

One-time setup per PC:
  1. Run launch-chrome.bat  (opens Chrome with a debug port + a dedicated
     'bdc-profile'); log into Booking.com once in that window.
  2. Fill .env (copy from .env.example): WORKER_NAME must equal the name you
     type on the Hygiene Scrape page (that's how jobs are routed to you).
  3. Run start-worker.bat.
"""

import asyncio
import os
import sys

import httpx
from dotenv import load_dotenv
from playwright.async_api import async_playwright

import scrape_lib
from scrape_lib import navigate_to_hotel, get_hygiene_data, is_login_page

# Force UTF-8 so emoji logs don't crash on Windows consoles.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

load_dotenv()

# The Google Apps Script web-app /exec URL (same one assets/api.js uses).
GAS_URL        = os.environ.get("GAS_URL", "").rstrip("/")
WORKER_TOKEN   = os.environ.get("WORKER_TOKEN", "")
WORKER_NAME    = os.environ.get("WORKER_NAME", "").strip()
CDP_PORT       = os.environ.get("CDP_PORT", "9222")
POLL_INTERVAL  = float(os.environ.get("POLL_INTERVAL", "4"))
JOB_TIMEOUT    = int(os.environ.get("JOB_TIMEOUT", "120"))
SEARCH_URL     = "https://admin.booking.com/hotel/hoteladmin/groups/home/index.html"


def banner(msg: str):
    print(msg, flush=True)


_http: httpx.AsyncClient | None = None

# Keep scrape_lib's chatty per-step logs local (console only) to avoid one HTTP
# request per log line. The worker sends a few explicit progress updates instead.
scrape_lib.log = lambda msg, *a, **k: print(msg, flush=True)


async def _call(action: str, body: dict) -> dict:
    """POST an action to the Apps Script web app and return its `data` payload.
    GAS POSTs 302-redirect to googleusercontent, so follow_redirects must be on."""
    assert _http is not None
    payload = dict(body or {})
    payload["token"] = WORKER_TOKEN
    r = await _http.post(f"{GAS_URL}?action={action}", json=payload, timeout=40)
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(data.get("error") or "Apps Script error")
    return data.get("data") or {}


async def heartbeat(chrome_ok: bool, note: str = ""):
    try:
        await _call("hyg_heartbeat", {"worker": WORKER_NAME, "chromeOk": chrome_ok, "note": note})
    except Exception as e:
        banner(f"  ⚠️ heartbeat failed: {e}")


async def claim() -> dict | None:
    try:
        res = await _call("hyg_claim", {"worker": WORKER_NAME, "chromeOk": True})
        return res.get("job")
    except Exception as e:
        banner(f"  ⚠️ claim failed: {e}")
        return None


async def report_result(job_id, result: dict):
    await _call("hyg_result", {"id": job_id, "result": result})


async def report_status(job_id, scrap_status: str, error: str = ""):
    await _call("hyg_result", {"id": job_id, "scrapStatus": scrap_status, "error": error})


async def progress(job_id, status: str, log: str = ""):
    try:
        await _call("hyg_progress", {"id": job_id, "status": status, "log": log})
    except Exception:
        pass


async def get_search_page(context):
    """Reuse a single tab on the BDC group-home for property searches."""
    page = None
    for p in context.pages:
        if "admin.booking.com" in p.url and "hotel_id=" not in p.url:
            page = p
            break
    if page is None:
        page = await context.new_page()
    try:
        if "groups/home" not in page.url:
            await page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(0.5)
    except Exception:
        pass
    return page


async def process_job(context, job: dict):
    job_id = job["id"]
    bdc_id = str(job["bdc_id"]).strip()
    name = job.get("prop_name") or bdc_id

    await progress(job_id, "running", f"Starting {name} ({bdc_id})")
    banner(f"▶ Job {job_id}: {name} ({bdc_id})")

    search_page = await get_search_page(context)

    if is_login_page(search_page.url):
        await progress(job_id, "pending", "Requeued — Booking.com login required")
        banner("  🔐 Login required — requeued; log in and it resumes")
        return False

    active_page, is_new_tab = await navigate_to_hotel(search_page, context, bdc_id)
    if active_page is None:
        banner(f"  ⏭ {name} — not found in BDC search")
        await report_status(job_id, "Not Found", "Property not found in BDC search")
        return True

    try:
        if is_login_page(active_page.url):
            await progress(job_id, "pending", "Requeued — Booking.com login required")
            return False
        try:
            result = await asyncio.wait_for(get_hygiene_data(active_page), timeout=JOB_TIMEOUT)
        except asyncio.TimeoutError:
            banner(f"  ⏱ {name} — {JOB_TIMEOUT}s timeout")
            await report_status(job_id, "Timeout", f"{JOB_TIMEOUT}s timeout")
            return True
        await report_result(job_id, result)
        banner(f"  ✅ {name} done")
        return True
    except Exception as e:
        banner(f"  ❌ {name} error: {e}")
        try:
            await report_status(job_id, "Error", str(e))
        except Exception:
            pass
        return True
    finally:
        if is_new_tab and active_page is not None:
            try:
                await active_page.close()
            except Exception:
                pass


async def run():
    global _http

    if not GAS_URL or not WORKER_TOKEN or not WORKER_NAME:
        banner("❌ Set GAS_URL, WORKER_TOKEN and WORKER_NAME in .env first.")
        return

    banner(f"🤖 BDC Hygiene worker '{WORKER_NAME}' → {GAS_URL}")
    banner(f"   Attaching to Chrome on CDP port {CDP_PORT} …")

    async with httpx.AsyncClient(follow_redirects=True) as http:
        _http = http
        async with async_playwright() as p:
            try:
                browser = await p.chromium.connect_over_cdp(f"http://localhost:{CDP_PORT}")
            except Exception as e:
                banner(f"❌ Could not attach to Chrome on port {CDP_PORT}: {e}")
                banner("   Run launch-chrome.bat first (and keep that window open).")
                await heartbeat(False, "Chrome not reachable on debug port")
                return

            context = browser.contexts[0] if browser.contexts else await browser.new_context()
            banner("✅ Attached to your trusted Chrome. Watching for jobs…")

            idle_logged = False
            while True:
                # Presence + login check
                search_page = await get_search_page(context)
                if is_login_page(search_page.url):
                    await heartbeat(False, "Please log into Booking.com in the worker's Chrome")
                    banner("🔐 Waiting for Booking.com login in the Chrome window…")
                    await asyncio.sleep(POLL_INTERVAL)
                    continue

                job = await claim()
                if job:
                    idle_logged = False
                    await process_job(context, job)
                    continue

                if not idle_logged:
                    banner("… idle (no queued jobs). Submit IDs on the Hygiene Scrape page.")
                    idle_logged = True
                await heartbeat(True, "")
                await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        banner("\n👋 Worker stopped.")
