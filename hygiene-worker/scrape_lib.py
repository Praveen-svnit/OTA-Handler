"""
BDC hygiene extraction logic — lifted almost verbatim from hygiene_scraper.py.

The only change vs. the original is that the module-level `log` is a plug-in
callable (default: print). worker.py overrides it with a function that also
streams progress to Apps Script. All the page-navigation and regex parsing is
unchanged, so behaviour matches the proven local scraper.
"""

import asyncio
import random
import re

# Overridable logger. worker.py sets scrape_lib.log = <its logger>.
def log(msg: str, *args, **kwargs):
    print(msg, flush=True)


# ── small utils ──────────────────────────────────────────────────────────────
def normId(v) -> str:
    return re.sub(r'\.0+$', '', str(v if v is not None else "").strip())


def is_login_page(url: str) -> bool:
    return any(x in url for x in ["signin", "login", "auth", "account.booking.com"])


def get_property_page_score(text: str) -> str:
    m = re.search(r'Property page score[^%]{0,300}?(\d+)\s*%', text, re.IGNORECASE | re.DOTALL)
    if m:
        return m.group(1) + "%"
    return ""


# ── Performance dashboard ────────────────────────────────────────────────────
async def get_performance_dashboard(page) -> dict:
    result = {
        "review_score": "", "review_count": "", "genius_eligibility": "",
        "genius_status": "", "preferred_status": "", "preferred_eligibility": "",
        "perf_score": "",
    }
    try:
        analytics_loc = page.locator("a, button, li").filter(has_text="Analytics").first
        await analytics_loc.wait_for(state="visible", timeout=5000)
        await analytics_loc.click()
        await asyncio.sleep(1)

        for label in ["Performance dashboard", "Performance Dashboard"]:
            try:
                loc = page.locator("a").filter(has_text=label).first
                await loc.wait_for(state="visible", timeout=3000)
                await loc.click()
                try:
                    await page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    await page.wait_for_load_state("domcontentloaded", timeout=15000)
                await asyncio.sleep(2)
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(1.5)
                await page.evaluate("window.scrollTo(0, 0)")
                await asyncio.sleep(0.5)
                break
            except Exception:
                continue

        text = await page.inner_text("body")

        nor_pos = text.lower().find("number of reviews")
        genius_pre = text[max(0, nor_pos - 500):nor_pos] if nor_pos >= 0 else ""
        _genius_raw = text[nor_pos:nor_pos + 500] if nor_pos >= 0 else ""
        _pref_boundary = _genius_raw.find("Preferred")
        genius_post = _genius_raw[:_pref_boundary] if _pref_boundary > 0 else _genius_raw

        pref_search_start = nor_pos + 100 if nor_pos >= 0 else 0
        p_pos = text.find("Preferred", pref_search_start)
        preferred_section = text[p_pos:p_pos + 700] if p_pos >= 0 else ""

        m = re.search(r'Review Score[\s\S]{0,20}?(\d+\.\d+)', genius_pre, re.IGNORECASE)
        if m:
            result["review_score"] = m.group(1)
        m = re.search(r'Number of Reviews[\s\S]{0,20}?(\d+)', genius_post, re.IGNORECASE)
        if m:
            result["review_count"] = m.group(1)

        m = re.search(r"You're a member|You're still in the Genius programme", genius_post, re.IGNORECASE)
        result["genius_status"] = m.group(0) if m else "Not Enrolled"
        m = re.search(r"You're not eligible", genius_post, re.IGNORECASE)
        result["genius_eligibility"] = m.group(0) if m else "Eligible"

        m = re.search(r"You're a member", preferred_section, re.IGNORECASE)
        result["preferred_status"] = m.group(0) if m else "Not Enrolled"
        m = re.search(r"You're not eligible", preferred_section, re.IGNORECASE)
        result["preferred_eligibility"] = m.group(0) if m else "Eligible"

        m = re.search(r'Performance score[\s\S]{0,60}?(\d+(?:\.\d+)?)\s*%', text)
        if m:
            result["perf_score"] = m.group(1) + "%"
    except Exception as e:
        log(f"  ⚠️ Performance Dashboard error: {e}")
    return result


async def get_genius_level(page) -> str:
    try:
        boost_loc = page.locator("a, button, li").filter(has_text="Boost performance").first
        await boost_loc.wait_for(state="visible", timeout=5000)
        await boost_loc.click()
        await asyncio.sleep(1)

        for label in ["Genius partner programme", "Genius programme", "Genius partner"]:
            try:
                loc = page.locator("a").filter(has_text=label).first
                await loc.wait_for(state="visible", timeout=3000)
                await loc.click()
                await page.wait_for_load_state("domcontentloaded", timeout=15000)
                await asyncio.sleep(1.5)
                break
            except Exception:
                continue

        text = await page.inner_text("body")
        if "Manage your setup" in text or "Genius Level" in text:
            header = next((line for line in text.splitlines() if "Your discount" in line), "")
            if "20%" in header: return "G3"
            if "15%" in header: return "G2"
            return "G1"
        if "Grow your business with Genius" in text:
            return "Eligible - Not Enrolled"
        if "not eligible" in text.lower():
            return "Not Eligible"
        return "Unknown"
    except Exception as e:
        log(f"  ⚠️ Genius level error: {e}")
        return ""


async def get_commission(page) -> str:
    try:
        boost_loc = page.locator("a, button, li").filter(has_text="Boost performance").first
        await boost_loc.wait_for(state="visible", timeout=8000)
        await boost_loc.click()
        await asyncio.sleep(1)

        for label in ["Visibility booster", "Visibility Booster", "Boost Your Visibility", "Boost visibility"]:
            try:
                loc = page.locator("a").filter(has_text=label).first
                await loc.wait_for(state="visible", timeout=3000)
                await loc.click()
                await page.wait_for_load_state("domcontentloaded", timeout=15000)
                await asyncio.sleep(2)
                break
            except Exception:
                continue

        if page.is_closed():
            return ""
        text = await page.inner_text("body")
        if "Boost Your Visibility" not in text and "Current commission" not in text and "Visibility" not in text:
            log("  ⚠️ Commission: did not reach Visibility Booster page")
            return ""
        m = re.search(r'Current commission:\s*(\d+(?:\.\d+)?)\s*%', text, re.IGNORECASE)
        if m:
            return m.group(1) + "%"
        m = re.search(r'(\d+(?:\.\d+)?)\s*%\s*commission', text, re.IGNORECASE)
        if m:
            return m.group(1) + "%"
    except Exception as e:
        log(f"  ⚠️ Commission (Visibility Booster) error: {e}")
    return ""


def extract_search_performance(text: str):
    search_views = ""
    views = ""
    conversion = ""

    m = re.search(r'Search result views[\s\S]{0,20}?([\d,]+)', text, re.IGNORECASE)
    if m:
        val = m.group(1).replace(",", "")
        if val.isdigit():
            search_views = val

    for pat in [
        r'Property page views[\s\S]{0,30}?([\d,]+)',
        r'([\d,]+)[\s\S]{0,20}?Property page views',
    ]:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = m.group(1).replace(",", "")
            if val.isdigit():
                views = val
                break

    m_bookings = re.search(r'Bookings received[\s\S]{0,20}?([\d,]+)', text, re.IGNORECASE)
    if m_bookings and views:
        b = int(m_bookings.group(1).replace(",", ""))
        v = int(views)
        if v > 0:
            conversion = f"{(b / v * 100):.2f}%"

    return search_views, views, conversion


async def get_top_promotion(page) -> str:
    try:
        try:
            home_loc = page.locator("nav a, [role='navigation'] a").filter(has_text="Home").first
            await home_loc.wait_for(state="visible", timeout=3000)
            await home_loc.click()
            await page.wait_for_load_state("domcontentloaded", timeout=10000)
            await asyncio.sleep(1)
        except Exception:
            pass

        try:
            promo_loc = page.locator("a, button, li").filter(has_text="Promotions").first
            await promo_loc.wait_for(state="visible", timeout=5000)
            await promo_loc.click()
            await asyncio.sleep(1.5)
        except Exception as e:
            log(f"  ⚠️ Promotions: could not click nav: {e}")
            return ""

        try:
            active_loc = page.locator("a, button").filter(has_text="Your active promotions").first
            await active_loc.wait_for(state="visible", timeout=4000)
            await active_loc.click()
            await page.wait_for_load_state("domcontentloaded", timeout=15000)
            await asyncio.sleep(1.5)
        except Exception:
            pass

        async def dismiss_popup():
            for selector in [
                "[aria-label='Close']", "[aria-label='close']",
                "[aria-label='Dismiss']", "[aria-label='dismiss']",
                "[data-testid*='close']", "[data-testid*='dismiss']",
            ]:
                try:
                    btn = page.locator(selector).first
                    await btn.wait_for(state="visible", timeout=800)
                    await btn.click()
                    await asyncio.sleep(0.5)
                    return
                except Exception:
                    continue
            for label in ["Close", "Dismiss", "Got it", "OK", "I understand", "Understood", "Accept", "×", "✕"]:
                try:
                    btn = page.locator("button, [role='button']").filter(has_text=label).first
                    await btn.wait_for(state="visible", timeout=800)
                    await btn.click()
                    await asyncio.sleep(0.5)
                    return
                except Exception:
                    continue

        await dismiss_popup()

        text = await page.inner_text("body")
        if re.search(r"no active promotions|you don.t have any active", text, re.IGNORECASE):
            return "None"

        try:
            discount_header = page.locator("th, [role='columnheader'], thead td, button").filter(has_text="Discount").first
            await discount_header.wait_for(state="visible", timeout=3000)
            await discount_header.dblclick()
            await asyncio.sleep(1.5)
            text = await page.inner_text("body")
        except Exception:
            pass

        discount_pos = text.find("Discount")
        if discount_pos >= 0:
            after_header = text[discount_pos:]
            m = re.search(r'\b(\d{1,2})\s*%', after_header)
            if m:
                val = int(m.group(1))
                if 5 <= val <= 95:
                    return str(val) + "%"
        return "None"
    except Exception as e:
        log(f"  ⚠️ Promotions error: {e}")
    return ""


async def get_hygiene_data(active_page) -> dict:
    """Extract all hygiene metrics from the property pages."""
    try:
        await active_page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        await asyncio.sleep(3)
    await active_page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    await asyncio.sleep(2)
    await active_page.evaluate("window.scrollTo(0, 0)")
    try:
        await active_page.wait_for_function(
            "() => document.body.innerText.includes('Search result views')",
            timeout=8000,
        )
    except Exception:
        await asyncio.sleep(2)
    home_text = await active_page.inner_text("body")
    page_score = get_property_page_score(home_text)
    search_views, views, conversion = extract_search_performance(home_text)

    perf = await get_performance_dashboard(active_page)
    genius_level = await get_genius_level(active_page)
    top_promo = await get_top_promotion(active_page)
    commission = await get_commission(active_page)

    log(
        f"  → score={perf['review_score']} count={perf['review_count']} "
        f"genius={genius_level} perf={perf['perf_score']} page={page_score} "
        f"promo={top_promo} comm={commission} views={views} conv={conversion}"
    )

    return {
        "review_score":          perf["review_score"],
        "review_count":          perf["review_count"],
        "genius_eligibility":    perf["genius_eligibility"],
        "genius_status":         perf["genius_status"],
        "genius_level":          genius_level,
        "preferred_status":      perf["preferred_status"],
        "preferred_eligibility": perf["preferred_eligibility"],
        "perf_score":            perf["perf_score"],
        "top_promotion":         top_promo,
        "commission_pct":        commission,
        "search_result_views":   search_views,
        "views":                 views,
        "conversion_pct":        conversion,
        "page_score":            page_score,
    }


async def navigate_to_hotel(page, context, bdc_id: str):
    """Navigate to a hotel via the BDC admin property list search.
    Returns (active_page, is_new_tab) or (None, False) on failure."""
    if "groups/home" not in page.url or "hotel_id=" in page.url or is_login_page(page.url):
        await page.goto(
            "https://admin.booking.com/hotel/hoteladmin/groups/home/index.html",
            wait_until="domcontentloaded", timeout=15000
        )
        await asyncio.sleep(0.5)

    search_input = await page.evaluate_handle("""() => {
        const inputs = Array.from(document.querySelectorAll(
            'input:not([type="hidden"]):not([type="checkbox"]):not([type="radio"]):not([type="password"])'
        ));
        const visible = inputs.filter(el => {
            const r = el.getBoundingClientRect();
            return r.width > 0 && r.height > 0 && !el.disabled;
        });
        return visible.length > 0 ? visible[visible.length - 1] : null;
    }""")

    try:
        is_elem = await page.evaluate("el => el !== null && el.tagName === 'INPUT'", search_input)
    except Exception:
        is_elem = False
    if not is_elem:
        return None, False

    try:
        await search_input.click()
        await asyncio.sleep(0.2)
        await page.keyboard.press("Control+a")
        await page.keyboard.press("Delete")
        for ch in str(bdc_id):
            await page.keyboard.type(ch)
            await asyncio.sleep(random.uniform(0.05, 0.08))

        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            await asyncio.sleep(2.5)

        result_selectors = [
            f'a[href*="hotel_id={bdc_id}"]',
            f'a[href*="{bdc_id}"]',
            'table tbody tr:first-child td:nth-child(2) a',
            'table tbody tr:first-child a',
            'table tbody tr:first-child',
            'tbody tr:first-child td:nth-child(2)',
        ]
        for rsel in result_selectors:
            try:
                r = await page.wait_for_selector(rsel, timeout=500, state="visible")
                if not r:
                    continue
                text = await r.inner_text()
                if not text.strip():
                    continue
                try:
                    async with context.expect_page(timeout=5000) as new_page_info:
                        await r.click()
                    new_tab = await new_page_info.value
                    await new_tab.wait_for_load_state("domcontentloaded", timeout=15000)
                    return new_tab, True
                except Exception:
                    await page.wait_for_load_state("domcontentloaded", timeout=10000)
                    if "hotel_id=" in page.url:
                        return page, False
            except Exception:
                continue
    except Exception:
        pass

    return None, False
