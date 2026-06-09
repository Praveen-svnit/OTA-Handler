"""
BDC Hygiene local worker.

Runs on a team member's PC. It attaches to their ALREADY logged-in, trusted
Chrome over the DevTools protocol (Way 1 — no automated login), polls the
OTA Tracker's Apps Script backend for hygiene-scrape jobs they queued, scrapes
each property inside the trusted browser, and posts results back (Apps Script
writes the BDC Hygiene Sheet).

Shared pool: the whole team uses one Booking.com account, so any worker can run
any queued job. There's no per-person name — every PC uses the SAME .env
(GAS_URL + WORKER_TOKEN). This machine labels itself by PC name in the log only.

One-time setup per PC:
  1. Run launch-chrome.bat  (opens Chrome with a debug port + a dedicated
     'bdc-profile'); log into Booking.com once in that window.
  2. Drop in the shared .env (copy from .env.example): GAS_URL + WORKER_TOKEN.
  3. Run start-worker.bat.
"""

import asyncio
import os
import socket
import sys

import httpx
from dotenv import load_dotenv
from playwright.async_api import async_playwright

import scrape_lib
from scrape_lib import find_ses, fetch_reviews_fast, SessionExpired

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
# Shared pool: a name isn't needed for routing. We only use an id to label this
# machine in the activity log — default to the PC name so .env needs no name.
WORKER_NAME    = os.environ.get("WORKER_NAME", "").strip() or os.environ.get("COMPUTERNAME", "") or socket.gethostname()
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


async def process_job(context, job: dict):
    """Endpoint-only: no browser navigation (so no 2FA, no wrong-property bug).
    Each phase fetches its fields via direct requests and reports them; the
    sheet does a partial update (only the columns we send)."""
    job_id = job["id"]
    bdc_id = str(job["bdc_id"]).strip()
    name = job.get("prop_name") or bdc_id

    await progress(job_id, "running", f"Starting {name} ({bdc_id})")
    banner(f"▶ Job {job_id}: {name} ({bdc_id})")

    ses = find_ses(context)
    if not ses:
        await progress(job_id, "pending", "Requeued — no Booking session (log in)")
        banner("  🔐 No session token found — requeued; log into Booking.com")
        return False

    try:
        result = {}
        # ── Phase 1: Review Score + Count ──────────────────────────────────
        rev_score, rev_count = await fetch_reviews_fast(context, ses, bdc_id)
        result["review_score"] = rev_score
        result["review_count"] = rev_count
        banner(f"  ⭐ reviews: score={rev_score} count={rev_count}")

        await report_result(job_id, result)
        banner(f"  ✅ {name} done")
        return True
    except SessionExpired:
        await progress(job_id, "pending", "Requeued — Booking login/verification required")
        banner("  🔐 Session needs re-verify in Chrome — requeued; pausing 20s")
        await heartbeat(False, "Booking session needs re-verifying (open admin & complete 2FA)")
        await asyncio.sleep(20)   # back off so we don't hammer a bad session
        return False
    except Exception as e:
        banner(f"  ❌ {name} error: {e}")
        try:
            await report_status(job_id, "Error", str(e))
        except Exception:
            pass
        return True


async def run():
    global _http

    if not GAS_URL or not WORKER_TOKEN:
        banner("❌ Set GAS_URL and WORKER_TOKEN in .env first.")
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
                # Presence check: need a logged-in admin tab carrying a session
                # token. (We never navigate, to avoid tripping Booking's 2FA.)
                if not find_ses(context):
                    await heartbeat(False, "Open/refresh a Booking.com admin tab so the worker has a session")
                    banner("🔐 No Booking session tab found — log into Booking.com in the Chrome window…")
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
