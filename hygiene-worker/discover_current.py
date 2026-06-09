"""
Capture JSON endpoints from the tab you ALREADY have open.

Avoids the buggy auto-search: you manually navigate the worker's Chrome to the
correct property's Guest Reviews page (the one showing 'Your review score N
based on M reviews'), then run this. It finds that tab, reloads it, and records
the JSON calls so we can see which endpoint returns the score + count.

Usage:
    "%LOCALAPPDATA%\\anaconda3\\python.exe" discover_current.py
"""

import asyncio
import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv()
CDP_PORT = os.environ.get("CDP_PORT", "9222")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "discover_output.json")
HINTS = ("reviewscore", "review_score", "averagescore", "average_score", "review", "rating", "score")
captured = []


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(f"http://localhost:{CDP_PORT}")
        ctx = browser.contexts[0]

        # Pick the open tab that looks like the reviews page (fall back to last tab).
        target = None
        for pg in ctx.pages:
            u = pg.url.lower()
            if "review" in u or "reviews.html" in u:
                target = pg
                break
        if target is None and ctx.pages:
            target = ctx.pages[-1]
        if target is None:
            print("No open tabs found. Open the Guest Reviews page first.")
            return
        print(f"Using tab: {target.url[:130]}")

        async def on_response(resp):
            try:
                ct = (resp.headers or {}).get("content-type", "")
                if "json" not in ct:
                    return
                url, body = resp.url, await resp.text()
            except Exception:
                return
            low = body.lower()
            hit = next((h for h in HINTS if h in low), None)
            if hit or "graphql" in url.lower() or "/review" in url.lower():
                snip = ""
                if hit:
                    i = low.find(hit)
                    snip = body[max(0, i - 90):i + 140].replace("\n", " ")
                captured.append({"url": url, "method": resp.request.method, "status": resp.status,
                                 "len": len(body), "hint": hit or "", "snippet": snip,
                                 "post_data": resp.request.post_data, "body_head": body[:3000]})

        target.on("response", on_response)
        print("Reloading the tab to capture its data calls…")
        try:
            await target.reload(wait_until="networkidle", timeout=25000)
        except Exception:
            await asyncio.sleep(5)
        await asyncio.sleep(3)

        # Rendered score text (fallback / sanity check)
        try:
            text = await target.inner_text("body")
            low = text.lower()
            i = low.find("review score")
            if i < 0:
                i = low.find("based on")
            print("\n=== Rendered text around score ===")
            print("   ", (text[max(0, i-90):i+170].replace("\n", " ") if i >= 0 else "(not found on this tab)"))
        except Exception:
            pass

        json.dump(captured, open(OUT, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
        print(f"\n=== {len(captured)} candidate JSON calls (saved {OUT}) ===")
        for c in captured:
            print(f"- [{c['method']}] {c['url'][:120]}")
            if c["snippet"]:
                print(f"      …{c['snippet']}")


asyncio.run(main())
