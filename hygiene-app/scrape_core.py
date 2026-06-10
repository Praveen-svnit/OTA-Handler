"""
Core engine for the BDC Hygiene app.

- Attaches to the user's already-logged-in Chrome (DevTools/CDP) — the trusted
  Booking session lives there.
- Reads the property list from the BDC Hygiene Google Sheet.
- Each "scraper" (reviews, genius, …) fetches its fields fast via direct
  requests and the engine writes ONLY that scraper's columns back in one batch.
"""

import asyncio
import os
import re
import time

import gspread
from google.oauth2.service_account import Credentials
from playwright.async_api import async_playwright

HERE = os.path.dirname(os.path.abspath(__file__))

# ── Config (a .env or environment can override) ───────────────────────────────
SERVICE_ACCOUNT_FILE = os.environ.get("SERVICE_ACCOUNT_FILE", os.path.join(HERE, "service_account.json"))
SHEET_ID    = os.environ.get("HYG_SHEET_ID", "1VkFA4keBAT3tG5NkZwmSNRbLZJgx2neOhZ7Zuj2z_98")
TAB_NAME    = os.environ.get("HYG_TAB", "BDC Hygiene")
CDP_PORT    = os.environ.get("CDP_PORT", "9222")
CONCURRENCY = int(os.environ.get("CONCURRENCY", "16"))


class SessionExpired(Exception):
    """A direct request came back as a sign-in / 2FA page."""


class VerificationRequired(SessionExpired):
    """The page bounced to Booking's identity-verification (auth-assurance) step.

    Unlike a plain expired session, this is recoverable in place: the user just
    completes the verification in Chrome and the run resumes. The engine pauses
    the whole run when it sees this, rather than marking rows as expired.
    """


# ── Google Sheet ──────────────────────────────────────────────────────────────
def _retry(fn, tries=6, base_delay=2.0):
    """Run a gspread call, retrying transient Google errors (429/5xx/HTML 502)."""
    last = None
    for i in range(tries):
        try:
            return fn()
        except gspread.exceptions.APIError as e:
            status = None
            try:
                status = e.response.status_code
            except Exception:
                pass
            transient = (status is None) or (status in (429, 500, 502, 503, 504))
            if not transient:
                raise
            last = e
            time.sleep(base_delay * (i + 1))
    raise last


def connect_sheet():
    scope = ["https://www.googleapis.com/auth/spreadsheets",
             "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scope)
    gc = gspread.authorize(creds)
    return _retry(lambda: gc.open_by_key(SHEET_ID).worksheet(TAB_NAME))


def _find_col(headers, *keywords):
    """Index of the header matching all keywords.

    Among matches, prefer an exact match of the joined keywords, then the
    SHORTEST header — so e.g. keyword 'booking' picks 'Bookings' rather than
    'Date change for non refundable bookings'."""
    kws = [str(k).strip().lower() for k in keywords]
    joined = " ".join(kws)
    best, best_len = -1, None
    for i, h in enumerate(headers):
        low = str(h).strip().lower()
        if all(k in low for k in kws):
            if low == joined:
                return i
            if best_len is None or len(low) < best_len:
                best, best_len = i, len(low)
    return best


def _col_letter(idx0):
    """0-based column index -> spreadsheet letter (A, B, …, Z, AA, …)."""
    s, n = "", idx0 + 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _bdc_col(headers):
    return _find_col(headers, "bdc", "id")


# ── Chrome session ────────────────────────────────────────────────────────────
def find_ses(ctx) -> str:
    """Session token from any open, authenticated admin tab (no navigation)."""
    for pg in ctx.pages:
        m = re.search(r'[?&]ses=([a-f0-9]{16,})', pg.url)
        if m:
            return m.group(1)
    return ""


async def attach(p):
    browser = await p.chromium.connect_over_cdp(f"http://localhost:{CDP_PORT}")
    ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
    return browser, ctx


# Last known-good session token — lets a run recover if every open tab has been
# navigated away from admin.booking.com (e.g. to a public property page).
_LAST_SES = {"ses": ""}


async def get_ses(ctx) -> str:
    """Robustly obtain the admin session token.

    1) Read it from any open admin tab (fast, no navigation).
    2) Else reuse the last known-good token from this process.
    3) Else open admin home in a throwaway tab; if still logged in (via cookies)
       Booking redirects to a URL carrying a fresh ses, which we capture.
    Returns '' only if the user is genuinely not logged in.
    """
    ses = find_ses(ctx)
    if ses:
        _LAST_SES["ses"] = ses
        return ses
    if _LAST_SES["ses"]:
        return _LAST_SES["ses"]
    try:
        page = await ctx.new_page()
    except Exception:
        return ""
    try:
        await page.goto("https://admin.booking.com/hotel/hoteladmin/home.html",
                        wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(1200)
        m = re.search(r'[?&]ses=([a-f0-9]{16,})', page.url)
        if not m:
            try:
                m = re.search(r'[?&]ses=([a-f0-9]{16,})', await page.content())
            except Exception:
                m = None
        if m:
            _LAST_SES["ses"] = m.group(1)
            return m.group(1)
    except Exception:
        pass
    finally:
        try:
            await page.close()
        except Exception:
            pass
    return ""


async def session_status():
    """Quick check used by the control panel: is Chrome reachable + logged in?"""
    try:
        async with async_playwright() as p:
            try:
                _, ctx = await attach(p)
            except Exception:
                return {"chrome": False, "logged_in": False}
            ses = find_ses(ctx) or _LAST_SES["ses"]
            return {"chrome": True, "logged_in": bool(ses)}
    except Exception:
        return {"chrome": False, "logged_in": False}


# ── Generic runner ────────────────────────────────────────────────────────────
# A "scraper" provides:
#   id, label, status ("live"/"soon")
#   columns: list of (sheet_col_letter, result_key)
#   async fetch(ctx, ses, hotel_id) -> { result_key: value, ... }
async def run_scraper(scraper, progress=None, ids=None, limit=0):
    def report(**kw):
        if progress is not None:
            progress.update(kw)

    report(stage="reading", message="Reading the BDC Hygiene sheet…")
    ws = connect_sheet()
    values = _retry(lambda: ws.get_all_values())
    headers = values[0]
    bcol = _bdc_col(headers)
    if bcol < 0:
        raise RuntimeError("Could not find a 'BDC ID' column in the sheet.")

    only = set(ids or [])
    targets = []
    for i in range(1, len(values)):
        bdc = str(values[i][bcol]).strip().replace(".0", "") if bcol < len(values[i]) else ""
        if not bdc or bdc.lower() == "nan":
            continue
        if only and bdc not in only:
            continue
        targets.append((i + 1, bdc))
    if limit:
        targets = targets[:limit]

    # Resolve every column by header name (robust to the sheet being reordered).
    status_idx = _find_col(headers, "scrap", "status")
    ts_idx = _find_col(headers, "last", "checked")
    status_col = _col_letter(status_idx) if status_idx >= 0 else None
    ts_col = _col_letter(ts_idx) if ts_idx >= 0 else None
    resolved_cols = []   # (letter, result_key)
    missing = []
    for header_kws, key in scraper["columns"]:
        idx = _find_col(headers, *header_kws)
        if idx >= 0:
            resolved_cols.append((_col_letter(idx), key))
        else:
            missing.append(" ".join(header_kws))
    if not resolved_cols:
        raise RuntimeError("None of this scraper's columns exist in the sheet: " + ", ".join(missing))
    # Missing columns are skipped (e.g. a header not added yet) — not fatal.

    total = len(targets)
    report(stage="running", total=total, done=0,
           message=f"Fetching {scraper['label']} for {total} properties…")
    if total == 0:
        report(stage="done", message="Nothing to do.")
        return {"total": 0, "filled": 0}

    async with async_playwright() as p:
        try:
            _, ctx = await attach(p)
        except Exception as e:
            raise RuntimeError(f"Could not attach to Chrome on port {CDP_PORT}. "
                               f"Click 'Open Booking & log in' first. ({e})")
        ses = await get_ses(ctx)
        if not ses:
            raise SessionExpired("No Booking session — log into Booking.com in the app's Chrome window.")

        conc = max(1, int(scraper.get("concurrency", CONCURRENCY)))

        async def _call(bdc):
            return await scraper["fetch"](ctx, ses, bdc)

        # When a scraper sits behind Booking's identity check (e.g. 'contact'), it
        # provides verify_url(ses, bdc). On a verification bounce we open THAT
        # property's page in a new Chrome tab so the user can verify, then close it
        # and go back to the fast concurrent endpoint.
        verify_page = [None]

        async def _open_verify(bdc):
            vu = scraper.get("verify_url")
            if not vu:
                return
            try:
                await _close_verify()
                vp = await ctx.new_page()
                verify_page[0] = vp
                await vp.goto(vu(ses, bdc), wait_until="domcontentloaded", timeout=30000)
                await vp.bring_to_front()
            except Exception:
                pass

        async def _close_verify():
            vp = verify_page[0]
            verify_page[0] = None
            if vp is not None:
                try:
                    await vp.close()
                except Exception:
                    pass

        sem = asyncio.Semaphore(conc)
        results = {}
        state = {"done": 0, "expired": 0, "paused": 0}
        t0 = time.time()

        # ── Auto-pause on identity-verification bounce ────────────────────────
        # Normally set (run proceeds). When a worker hits VerificationRequired we
        # clear it (everyone waits), prompt the user to re-verify in Chrome, and
        # a single monitor re-probes until verification succeeds, then re-sets it.
        can_run = asyncio.Event(); can_run.set()
        verify_lock = asyncio.Lock()

        def _progress_msg():
            return f"{state['done']}/{total} fetched…"

        async def _wait_until_reverified(sample_bdc):
            # Only one monitor runs at a time; later callers no-op once resumed.
            async with verify_lock:
                if can_run.is_set():
                    return
                waited = 0
                while True:
                    if progress and progress.get("stop"):
                        can_run.set()   # release workers so they see the stop
                        return
                    await asyncio.sleep(5)
                    waited += 5
                    try:
                        # A successful fetch (no VerificationRequired) means the
                        # user has re-verified in Chrome.
                        await _call(sample_bdc)
                        await _close_verify()   # verification done — close the tab
                        can_run.set()
                        report(stage="running",
                               message=f"Re-verified — resuming… ({_progress_msg()})")
                        return
                    except VerificationRequired:
                        report(stage="paused",
                               message=("Identity check needed: a Contacts tab is open in Chrome — "
                                        "complete the verification there and the run resumes "
                                        f"automatically. (waited {waited}s)"))
                    except Exception:
                        # Transient error during probe — keep waiting.
                        report(stage="paused",
                               message=("Waiting for you to verify in the open Chrome Contacts tab… "
                                        f"({waited}s)"))

        def _stopping():
            return bool(progress and progress.get("stop"))

        async def work(row, bdc):
            async with sem:
                while True:
                    # User asked to stop — leave this row untouched (not written).
                    if _stopping():
                        return
                    await can_run.wait()
                    if _stopping():
                        return
                    try:
                        results[row] = await _call(bdc)
                        break
                    except VerificationRequired:
                        # First worker to notice trips the pause + starts monitor.
                        if can_run.is_set():
                            can_run.clear()
                            state["paused"] += 1
                            await _open_verify(bdc)
                            report(stage="paused",
                                   message=("Identity check needed: I opened this property's "
                                            "Contacts tab in Chrome — complete the verification "
                                            "there and the run resumes automatically."))
                            asyncio.create_task(_wait_until_reverified(bdc))
                        # Loop back, wait for resume, then retry THIS row.
                        continue
                    except SessionExpired:
                        state["expired"] += 1
                        results[row] = {}
                        break
                    except Exception:
                        results[row] = {}
                        break
            state["done"] += 1
            if state["done"] % 20 == 0 or state["done"] == total:
                report(done=state["done"], message=_progress_msg())

        try:
            await asyncio.gather(*(work(r, b) for r, b in targets))
        finally:
            await _close_verify()

        # ── Batch write only this scraper's columns (+ Scrap Status, Last Checked) ──
        report(stage="writing", message="Writing results to the sheet…")
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        updates, filled = [], 0
        for row, data in results.items():
            got_any = False
            for col, key in resolved_cols:
                val = data.get(key, "")
                if val != "":
                    got_any = True
                updates.append({"range": f"{col}{row}", "values": [[val]]})
            if status_col:
                updates.append({"range": f"{status_col}{row}",
                                "values": [["Successful" if got_any else "Session Expired"]]})
            if ts_col:
                updates.append({"range": f"{ts_col}{row}", "values": [[ts]]})
            if got_any:
                filled += 1
        if updates:
            _retry(lambda: ws.batch_update(updates, value_input_option="USER_ENTERED"))

        secs = time.time() - t0
        expired = state["expired"]
        stopped = bool(progress and progress.get("stop"))
        processed = len(results)
        if stopped:
            msg = (f"Stopped by user — saved {filled} filled of {processed} processed "
                   f"(of {total}) in {secs:.0f}s. Re-run to fill the rest.")
        else:
            msg = f"Done — {filled}/{total} filled in {secs:.0f}s."
            if expired:
                msg += f" {expired} skipped (session expired)."
        report(stage="done", done=total, message=msg)
        return {"total": total, "filled": filled, "expired": expired,
                "secs": round(secs), "stopped": stopped}


async def run_combined(members, progress=None, ids=None, limit=0, label="batch"):
    """Run several scrapers as ONE pass: for each property, fetch every member's
    fields, then move to the next property. One sheet read, one batch write.

    More efficient than running each scraper end-to-end. Identity-verification
    pauses (for 'verify' scrapers) and Stop work the same as a single run.
    """
    def report(**kw):
        if progress is not None:
            progress.update(kw)

    members = [m for m in members if m.get("fetch")]
    if not members:
        report(stage="done", message="Nothing to run.")
        return {"total": 0, "filled": 0}

    report(stage="reading", message=f"Reading the BDC Hygiene sheet… ({label})")
    ws = connect_sheet()
    values = _retry(lambda: ws.get_all_values())
    headers = values[0]
    bcol = _bdc_col(headers)
    if bcol < 0:
        raise RuntimeError("Could not find a 'BDC ID' column in the sheet.")

    only = set(ids or [])
    targets = []
    for i in range(1, len(values)):
        bdc = str(values[i][bcol]).strip().replace(".0", "") if bcol < len(values[i]) else ""
        if not bdc or bdc.lower() == "nan":
            continue
        if only and bdc not in only:
            continue
        targets.append((i + 1, bdc))
    if limit:
        targets = targets[:limit]

    status_idx = _find_col(headers, "scrap", "status")
    ts_idx = _find_col(headers, "last", "checked")
    status_col = _col_letter(status_idx) if status_idx >= 0 else None
    ts_col = _col_letter(ts_idx) if ts_idx >= 0 else None

    # Union of all members' columns that actually exist in the sheet.
    resolved = []
    for sc in members:
        for header_kws, key in sc["columns"]:
            idx = _find_col(headers, *header_kws)
            if idx >= 0:
                resolved.append((_col_letter(idx), key))
    if not resolved:
        raise RuntimeError("None of these scrapers' columns exist in the sheet.")

    total = len(targets)
    report(stage="running", total=total, done=0,
           message=f"Fetching {len(members)} field group(s) for {total} properties…")
    if total == 0:
        report(stage="done", message="Nothing to do.")
        return {"total": 0, "filled": 0}

    async with async_playwright() as p:
        try:
            _, ctx = await attach(p)
        except Exception as e:
            raise RuntimeError(f"Could not attach to Chrome on port {CDP_PORT}. "
                               f"Click 'Open Booking & log in' first. ({e})")
        ses = await get_ses(ctx)
        if not ses:
            raise SessionExpired("No Booking session — log into Booking.com in the app's Chrome window.")

        sem = asyncio.Semaphore(CONCURRENCY)
        results = {}
        state = {"done": 0, "expired": 0, "paused": 0}
        t0 = time.time()
        can_run = asyncio.Event(); can_run.set()
        verify_lock = asyncio.Lock()
        verify_page = [None]

        async def _close_verify():
            vp = verify_page[0]
            verify_page[0] = None
            if vp is not None:
                try:
                    await vp.close()
                except Exception:
                    pass

        async def _open_verify(sc, bdc):
            vu = sc.get("verify_url")
            if not vu:
                return
            try:
                await _close_verify()
                vp = await ctx.new_page()
                verify_page[0] = vp
                await vp.goto(vu(ses, bdc), wait_until="domcontentloaded", timeout=30000)
                await vp.bring_to_front()
            except Exception:
                pass

        def _stopping():
            return bool(progress and progress.get("stop"))

        async def _wait_reverified(sc, bdc):
            async with verify_lock:
                if can_run.is_set():
                    return
                waited = 0
                while True:
                    if _stopping():
                        can_run.set()
                        return
                    await asyncio.sleep(5)
                    waited += 5
                    try:
                        await sc["fetch"](ctx, ses, bdc)
                        await _close_verify()
                        can_run.set()
                        report(stage="running",
                               message=f"Re-verified — resuming… ({state['done']}/{total})")
                        return
                    except VerificationRequired:
                        report(stage="paused",
                               message=f"Verify in the open Chrome tab; resumes automatically. ({waited}s)")
                    except Exception:
                        report(stage="paused",
                               message=f"Waiting for you to verify in Chrome… ({waited}s)")

        async def work(row, bdc):
            async with sem:
                merged = {}
                for sc in members:
                    if _stopping():
                        break
                    while True:
                        await can_run.wait()
                        if _stopping():
                            break
                        try:
                            out = await sc["fetch"](ctx, ses, bdc)
                            if isinstance(out, dict):
                                merged.update(out)
                            break
                        except VerificationRequired:
                            if can_run.is_set():
                                can_run.clear()
                                state["paused"] += 1
                                await _open_verify(sc, bdc)
                                report(stage="paused",
                                       message=("Identity check needed: I opened this property's page "
                                                "in Chrome — verify there and it resumes automatically."))
                                asyncio.create_task(_wait_reverified(sc, bdc))
                            continue
                        except SessionExpired:
                            state["expired"] += 1
                            break
                        except Exception:
                            break
                results[row] = merged
            state["done"] += 1
            if state["done"] % 10 == 0 or state["done"] == total:
                report(done=state["done"], message=f"{state['done']}/{total} properties…")

        try:
            await asyncio.gather(*(work(r, b) for r, b in targets))
        finally:
            await _close_verify()

        report(stage="writing", message="Writing results to the sheet…")
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        updates, filled = [], 0
        for row, data in results.items():
            got_any = False
            for col, key in resolved:
                val = data.get(key, "")
                if val != "":
                    got_any = True
                updates.append({"range": f"{col}{row}", "values": [[val]]})
            if status_col:
                updates.append({"range": f"{status_col}{row}",
                                "values": [["Successful" if got_any else "Session Expired"]]})
            if ts_col:
                updates.append({"range": f"{ts_col}{row}", "values": [[ts]]})
            if got_any:
                filled += 1
        if updates:
            _retry(lambda: ws.batch_update(updates, value_input_option="USER_ENTERED"))

        secs = time.time() - t0
        stopped = _stopping()
        msg = (f"Stopped — {filled}/{total} filled in {secs:.0f}s."
               if stopped else
               f"Done — {filled}/{total} filled in {secs:.0f}s "
               f"({len(members)} field groups in one pass).")
        report(stage="done", done=total, message=msg)
        return {"total": total, "filled": filled, "secs": round(secs), "stopped": stopped}
