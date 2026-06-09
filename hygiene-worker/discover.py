"""
Endpoint discovery helper (Phase 1: Review Score + Review Count).

Attaches to your trusted Chrome (same as the worker), opens ONE property's
Performance Dashboard, and records the internal JSON/XHR calls the page makes.
It flags the ones that look like they carry review data so we can call that
endpoint directly (fast, no page scraping).

Usage (stop the worker first so they don't fight over the page):
    1. launch-chrome.bat  (logged into Booking.com)
    2. start-worker.bat is NOT running
    3. run:  <python> discover.py <BDC_ID>
       e.g.  "%LOCALAPPDATA%\\anaconda3\\python.exe" discover.py 1518627

It prints candidate endpoints and saves full details to discover_output.json.
Paste the printed candidates (or send the json) back for wiring up.
"""

import asyncio
import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from dotenv import load_dotenv
from playwright.async_api import async_playwright

import scrape_lib
from scrape_lib import navigate_to_hotel, is_login_page


async def nav_guest_reviews(page):
    """Home -> Reviews -> Guest reviews (the page showing 'Your review score N
    based on M reviews'). Click-based, with fallbacks."""
    # Open the Reviews menu in the top nav.
    for label in ["Reviews", "Guest reviews", "Guest Reviews"]:
        try:
            loc = page.locator("a, button, li, [role='menuitem']").filter(has_text=label).first
            await loc.wait_for(state="visible", timeout=4000)
            await loc.click()
            await asyncio.sleep(1)
            break
        except Exception:
            continue
    # Then the "Guest reviews" sub-item if a dropdown opened.
    for label in ["Guest reviews", "Guest Reviews", "Review score", "Scores"]:
        try:
            loc = page.locator("a").filter(has_text=label).first
            await loc.wait_for(state="visible", timeout=2500)
            await loc.click()
            break
        except Exception:
            continue
    try:
        await page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        await page.wait_for_load_state("domcontentloaded", timeout=10000)
    await asyncio.sleep(2)

load_dotenv()
CDP_PORT = os.environ.get("CDP_PORT", "9222")
BDC = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("DISCOVER_BDC_ID", "")).strip()
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "discover_output.json")

scrape_lib.log = lambda m, *a, **k: print(m, flush=True)

# Words that hint a response carries review/rating data.
HINTS = ("review", "rating", "guestreview", "score")
captured = []


async def main():
    if not BDC:
        print("Usage: python discover.py <BDC_ID>")
        return

    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(f"http://localhost:{CDP_PORT}")
        except Exception as e:
            print(f"❌ Could not attach to Chrome on port {CDP_PORT}: {e}")
            print("   Run launch-chrome.bat first and keep it open.")
            return
        ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = await ctx.new_page()
        await page.goto("https://admin.booking.com/hotel/hoteladmin/groups/home/index.html",
                        wait_until="domcontentloaded")
        if is_login_page(page.url):
            print("❌ Not logged in — log into Booking.com in the Chrome window first.")
            return

        print(f"🔎 Opening property {BDC} …")
        active, is_new_tab = await navigate_to_hotel(page, ctx, BDC)
        if active is None:
            print("❌ Could not open the property in BDC search.")
            return

        async def on_response(resp):
            try:
                ct = (resp.headers or {}).get("content-type", "")
                if "json" not in ct:
                    return
                url = resp.url
                body = await resp.text()
            except Exception:
                return
            low = body.lower()
            hit = next((h for h in HINTS if h in low), None)
            if hit or "graphql" in url.lower() or "fresa" in url.lower():
                snippet = ""
                if hit:
                    i = low.find(hit)
                    snippet = body[max(0, i - 80):i + 120].replace("\n", " ")
                captured.append({
                    "url": url,
                    "method": resp.request.method,
                    "status": resp.status,
                    "len": len(body),
                    "hint": hit or "",
                    "snippet": snippet,
                    "post_data": resp.request.post_data,
                    "body_head": body[:2000],
                })

        active.on("response", on_response)

        # Navigate DIRECTLY to the Guest Reviews page, reusing the session params
        # (hotel_id, ses, etc.) already present in the open tab's URL.
        from urllib.parse import urlsplit, urlunsplit
        parts = urlsplit(active.url)
        reviews_url = urlunsplit((parts.scheme, parts.netloc,
                                  "/hotel/hoteladmin/extranet_ng/manage/reviews.html",
                                  parts.query, ""))
        print(f"📝 Opening Guest Reviews:\n    {reviews_url}")
        try:
            await active.goto(reviews_url, wait_until="networkidle", timeout=20000)
        except Exception:
            await active.goto(reviews_url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(4)

        # Fallback: dump the rendered text around the review score so we can
        # text-scrape if there's no clean JSON endpoint.
        try:
            text = await active.inner_text("body")
            low = text.lower()
            i = low.find("review score")
            if i < 0:
                i = low.find("based on")
            region = text[max(0, i - 80):i + 160].replace("\n", " ") if i >= 0 else "(‘review score’ text not found — wrong page?)"
            print("\n=== Rendered text around review score ===")
            print("   ", region)
        except Exception as e:
            print("   (could not read page text:", e, ")")

        json.dump(captured, open(OUT, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
        review_hits = [c for c in captured if c["hint"] in ("review", "rating", "guestreview")]
        print(f"\n=== Captured {len(captured)} JSON calls; {len(review_hits)} mention review/rating ===")
        print(f"(full detail saved to {OUT})\n")
        for c in (review_hits or captured):
            print(f"- [{c['method']}] {c['url'][:120]}")
            if c["snippet"]:
                print(f"      …{c['snippet']}")

        if is_new_tab:
            try:
                await active.close()
            except Exception:
                pass


asyncio.run(main())
