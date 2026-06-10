"""
Scraper registry — one entry per hygiene field group.

Each scraper declares the sheet columns it owns and an async `fetch` that pulls
those values for one property via a fast direct request. Add a new hygiene field
by adding one entry here (status 'soon' until its fetch is wired up).
"""

import asyncio
import json
import re
from datetime import date, timedelta
from scrape_core import SessionExpired, VerificationRequired

REVIEWS_URL = ("https://admin.booking.com/hotel/hoteladmin/extranet_ng/manage/"
               "reviews.html?hotel_id={hid}&lang=xu&ses={ses}")


async def _fetch_reviews(ctx, ses, hotel_id):
    r = await ctx.request.get(REVIEWS_URL.format(hid=hotel_id, ses=ses), timeout=20000)
    html = await r.text()
    low = html.lower()

    # Session check by final URL + page marker (NOT body keywords — words like
    # "verification" appear on valid pages too). A valid Guest Reviews page stays
    # on admin.booking.com and contains "guest reviews"; a dead/2FA session
    # bounces to account.booking.com/sign-in.
    if "admin.booking.com" not in r.url or "guest reviews" not in low:
        raise SessionExpired("Guest Reviews returned a sign-in/verification page")

    ms = re.search(r'bui-review-score__badge">\s*([\d.]+)\s*<', html)
    # "based on 1 review" (singular) or "based on 182 reviews" (plural)
    mc = re.search(r'based on\s*([\d,]+)\s*reviews?', html, re.IGNORECASE)
    return {
        # No score badge when the property has no reviews yet -> leave blank.
        "review_score": ms.group(1) if ms else "",
        # Valid page with no "based on N" -> the property has 0 reviews.
        "review_count": mc.group(1).replace(",", "") if mc else "0",
    }


GENIUS_URL = ("https://admin.booking.com/hotel/hoteladmin/extranet_ng/manage/"
              "genius.html?hotel_id={hid}&lang=xu&ses={ses}")

# Reads the embedded GraphQL state for the Genius base programme.
_GENIUS_RE = re.compile(
    r'"status":"(ACTIVE|INACTIVE)","productConfig":\{"__typename":'
    r'"GeniusBaseProgrammeConfig","isEligible":(?:true|false),'
    r'"eligibilityStatus":"(\w+)"')


async def _genius_raw(ctx, ses, hotel_id):
    """Fast: ('ACTIVE'|'INACTIVE'|None, eligibilityStatus, isPriceCompetitive)
    from the embedded GraphQL state in the raw page."""
    r = await ctx.request.get(GENIUS_URL.format(hid=hotel_id, ses=ses), timeout=20000)
    html = await r.text()
    if "admin.booking.com" not in r.url:
        raise SessionExpired("Genius page bounced to sign-in")
    m = _GENIUS_RE.search(html)
    mp = re.search(r'"isPriceCompetitive":(true|false)', html)
    return (m.group(1) if m else None,
            m.group(2) if m else None,
            mp.group(1) if mp else None)


async def _fetch_genius_status(ctx, ses, hotel_id):
    """Enrolled / Eligible / Not Eligible + External prices — instant, raw page."""
    status, elig, price = await _genius_raw(ctx, ses, hotel_id)
    if status == "ACTIVE":
        gs = "Enrolled"
    elif status == "INACTIVE":
        gs = "Eligible" if elig == "ELIGIBLE" else "Not Eligible"
    else:
        gs = ""   # couldn't read it; leave blank rather than guess
    if price is None:
        # External prices not present on the page, but we did read a Genius
        # status -> flag it as "Competitive-1" (per requirement).
        ext = "Competitive-1" if gs else ""
    else:
        ext = "Competitive" if price == "true" else "Not Competitive"
    return {"genius_status": gs, "external_prices": ext}


async def _fetch_genius_level(ctx, ses, hotel_id):
    """G1 / G2 / G3. Only enrolled properties have a level, so we render the page
    only for ACTIVE ones (cheap for the not-enrolled majority)."""
    status, _, _ = await _genius_raw(ctx, ses, hotel_id)
    if status != "ACTIVE":
        return {"genius_level": ""}   # no level unless enrolled
    url = GENIUS_URL.format(hid=hotel_id, ses=ses)
    page = await ctx.new_page()
    txt = ""
    try:
        # Booking sometimes serves a transient "Sorry, this page isn't working —
        # try refreshing it" error, especially under load. Reload a few times
        # until the discount header renders.
        for attempt in range(4):
            try:
                if attempt == 0:
                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                else:
                    await page.reload(wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_function(
                    "() => /Your discounts?:/i.test(document.body.innerText)", timeout=12000)
                txt = await page.inner_text("body")
                break   # header rendered
            except Exception:
                try:
                    txt = await page.inner_text("body")
                except Exception:
                    break   # page/context gone — stop
                low = txt.lower()
                if "isn't working" in low or "try refreshing" in low or "page does not exist" in low:
                    await page.wait_for_timeout(1500)
                    continue   # transient error — retry
                break          # genuinely no header (e.g. unusual page) — give up
    finally:
        await page.close()

    # Read ONLY the "Your discount(s):" header line — it lists the enrolled
    # discounts. Unenrolled tier cards also show "Discount: 15%/20%" as upsell
    # text, so scanning the whole body would over-count. (Logic from the original
    # genius_scraper.py.)
    #   G1: "Your discount: 10% to Genius Level 1, 2, and 3"   (no 15%/20%)
    #   G2: "Your discounts: 10% … and 15% to Level 2 and 3"
    #   G3: "Your discounts: … and 20% to Level 3"
    header = next((ln for ln in txt.splitlines()
                   if re.search(r'your discounts?:', ln, re.IGNORECASE) and '%' in ln), "")
    if "20%" in header:
        level = "G3"
    elif "15%" in header:
        level = "G2"
    elif header:
        level = "G1"
    else:
        level = ""   # enrolled but the discount header didn't render — leave blank
    return {"genius_level": level}


PREFERRED_URL = ("https://admin.booking.com/fresa/extranet/preferred/{ep}"
                 "?hotel_id={hid}&lang=xu&ses={ses}")


def _num(body, key):
    m = re.search(r'"' + key + r'":\s*(\d+)', body)
    return int(m.group(1)) if m else None


async def _fetch_preferred(ctx, ses, hotel_id):
    """Preferred membership (col L) + de-preferring risk (col M), from one fast
    fresa GET endpoint (no rendering)."""
    r1 = await ctx.request.get(PREFERRED_URL.format(ep="get_page_data", hid=hotel_id, ses=ses), timeout=20000)
    b1 = await r1.text()
    if "admin.booking.com" not in r1.url or not b1.lstrip().startswith("{"):
        raise SessionExpired("Preferred endpoint bounced to sign-in")
    is_pref = _num(b1, "isPreferred")
    is_plus = _num(b1, "isPreferredPlus")
    if is_pref == 1:
        status = "You're a member" + (" (Plus)" if is_plus == 1 else "")
    elif is_pref == 0:
        status = "Not Enrolled"
    else:
        status = ""

    # Eligibility = de-preferring risk (Booking removes you at the quarterly
    # review if criteria aren't met). Only meaningful for members.
    if is_pref == 1:
        if _num(b1, "isInDepreferring") == 1:
            days = _num(b1, "daysToImprove")
            elig = f"At risk - {days} days" if days is not None else "At risk"
        else:
            elig = "OK"
    else:
        elig = ""
    return {"preferred_status": status, "preferred_eligibility": elig}


PERF_URL = ("https://admin.booking.com/hotel/hoteladmin/extranet_ng/manage/"
            "performance_dashboard.html?hotel_id={hid}&lang=xu&ses={ses}")


async def _fetch_performance(ctx, ses, hotel_id):
    """Performance score % (col N) from the Performance Dashboard's embedded data."""
    r = await ctx.request.get(PERF_URL.format(hid=hotel_id, ses=ses), timeout=20000)
    html = await r.text()
    if "admin.booking.com" not in r.url:
        raise SessionExpired("Performance dashboard bounced to sign-in")
    m = re.search(r'"performanceScore":\s*\{"formattedScore":"([\d.]+%?)"', html)
    return {"perf_score": m.group(1) if m else ""}


CANCEL_URL = ("https://admin.booking.com/fresa/extranet/policy_page/get_groups"
              "?hotel_id={hid}&lang=xu&ses={ses}")


async def _fetch_cancellation(ctx, ses, hotel_id):
    """Cancellation policy name (e.g. 'Flexible - 1 day') from the policy endpoint."""
    r = await ctx.request.get(CANCEL_URL.format(hid=hotel_id, ses=ses), timeout=20000)
    body = await r.text()
    if "admin.booking.com" not in r.url or '"name":"Cancellation"' not in body:
        raise SessionExpired("Policy endpoint bounced to sign-in")
    m = re.search(
        r'"(?:title|policy_name|label)":"((?:Flexible|Non-refundable|Moderate|Strict|Fully flexible)[^"]{0,30})"',
        body)
    return {"cancellation": m.group(1).strip() if m else ""}


CONTACTS_URL = ("https://admin.booking.com/hotel/hoteladmin/extranet_ng/manage/"
                "contacts.html?hotel_id={hid}&lang=xu&ses={ses}")

# A phone as Booking renders it on the Contacts page: '+<country><number>'.
_PHONE_RE = re.compile(r'\+?\d[\d\-\s().]{6,}\d')


def _clean_phone(raw):
    """Normalise a captured phone to '+<digits>' / '<digits>', dropping noise."""
    if not raw:
        return ""
    s = re.sub(r'[^\d+]', '', raw)
    plus = s.startswith("+")
    digits = s.lstrip("+")
    if len(digits) < 7 or len(digits) > 15:   # not a real phone
        return ""
    return ("+" + digits) if plus else digits


async def _fetch_contact(ctx, ses, hotel_id):
    """Main (Primary) contact person's phone number — col 'Contact No.'.

    Fast path (like the other endpoint scrapers): a direct request to the
    Contacts page. Booking server-renders the phone into the HTML, so no tab /
    rendering is needed — but only while the session is identity-verified. If it
    isn't, the request bounces to account.booking.com and we raise
    VerificationRequired; the engine then opens this property's Contacts tab so
    the user can verify, and switches straight back to this fast path.
    """
    r = await ctx.request.get(CONTACTS_URL.format(hid=hotel_id, ses=ses), timeout=25000)
    html = await r.text()
    if "account.booking.com" in r.url or "Verify your identity" in html:
        raise VerificationRequired("Contacts page needs identity verification")

    # The primary contact's phone sits inside a 'contact-phones-cell' container.
    m = re.search(r'contact-phones-cell.*?(\+?\d[\d\s\-()]{6,}\d)', html, re.S)
    return {"contact_no": _clean_phone(m.group(1)) if m else ""}


def contact_verify_url(ses, hotel_id):
    """URL the engine opens in a tab when this property needs verification."""
    return CONTACTS_URL.format(hid=hotel_id, ses=ses)


ACCOUNTS_URL = ("https://admin.booking.com/hotel/hoteladmin/extranet_ng/manage/"
                "accounts_and_permissions.html?hotel_id={hid}&lang=xu&ses={ses}")


async def _fetch_extranet_access(ctx, ses, hotel_id):
    """Non-FabHotels emails that have extranet access (col 'Extranet Access').

    Lists the extranet account emails and flags any that aren't @fabhotels.com.
    Like Contacts, this page sits behind Booking's identity check, so on a bounce
    we raise VerificationRequired and the engine opens this property's page in a
    tab to verify, then goes back to the fast endpoint."""
    r = await ctx.request.get(ACCOUNTS_URL.format(hid=hotel_id, ses=ses), timeout=25000)
    html = await r.text()
    if "account.booking.com" in r.url or "Verify your identity" in html:
        raise VerificationRequired("Accounts & permissions page needs identity verification")
    emails = sorted({e.lower() for e in re.findall(r'"email"\s*:\s*"([^"]+@[^"]+)"', html)})
    # Allowed domains: FabHotels + the channel manager (SU). Anything else is flagged.
    allowed = ("@fabhotels.com", "@suissu.com")
    external = [e for e in emails if not e.endswith(allowed)]
    return {"extranet_external": ", ".join(external) if external else "None"}


def extranet_verify_url(ses, hotel_id):
    """URL the engine opens in a tab when this property needs verification."""
    return ACCOUNTS_URL.format(hid=hotel_id, ses=ses)


HOME_URL = ("https://admin.booking.com/hotel/hoteladmin/extranet_ng/manage/"
            "home.html?hotel_id={hid}&lang=xu&ses={ses}")

# The guest-facing property page link, e.g. www.booking.com/hotel/in/<slug>.html
_FRONTEND_RE = re.compile(r'https?://www\.booking\.com/hotel/[a-z]{2}/[a-z0-9\-]+\.html',
                          re.IGNORECASE)


PHOTOS_URL = ("https://admin.booking.com/hotel/hoteladmin/extranet_ng/manage/"
              "photos.html?hotel_id={hid}&lang=xu&ses={ses}")

# Each uploaded photo appears as bstatic image URLs ending /<photoId>.jpg at
# several sizes; the unique id count == number of photos on the property.
_PHOTO_ID_RE = re.compile(r'/images/hotel/[^"\\]*?/(\d+)\.(?:jpe?g|png)', re.IGNORECASE)


async def _fetch_photos(ctx, ses, hotel_id):
    """Number of photos currently on the property (col 'Photos').

    Fast endpoint: the Photos page embeds the uploaded image URLs. 0 means no
    photos added. No identity verification needed."""
    r = await ctx.request.get(PHOTOS_URL.format(hid=hotel_id, ses=ses), timeout=25000)
    if "admin.booking.com" not in r.url:
        raise SessionExpired("Photos page bounced to sign-in")
    html = await r.text()
    count = len(set(_PHOTO_ID_RE.findall(html)))
    return {"photos": count}


def _pdp_params():
    """Availability params that force the property's own landing page (PDP),
    not a search-results page. Dates are relative to the run so they stay valid:
    check-in 14 days out, 1-night stay, 2 adults, 1 room."""
    ci = date.today() + timedelta(days=14)
    co = ci + timedelta(days=1)
    return (f"checkin={ci.isoformat()}&checkout={co.isoformat()}"
            f"&group_adults=2&group_children=0&no_rooms=1")


async def _fetch_frontend(ctx, ses, hotel_id):
    """Public Booking.com property page URL (col 'Frontend Link').

    Fast endpoint: the property Home page embeds the guest-facing link. We append
    availability params so it opens the specific property page (PDP) rather than
    bouncing to search results. No identity verification needed."""
    r = await ctx.request.get(HOME_URL.format(hid=hotel_id, ses=ses), timeout=25000)
    if "admin.booking.com" not in r.url:
        raise SessionExpired("Home page bounced to sign-in")
    html = await r.text()
    m = _FRONTEND_RE.search(html)
    if not m:
        return {"frontend_link": ""}
    base = m.group(0).replace("http://", "https://")
    return {"frontend_link": f"{base}?{_pdp_params()}"}


PROMO_URL = ("https://admin.booking.com/hotel/hoteladmin/extranet_ng/manage/"
             "promotions/list.html?hotel_id={hid}&lang=xu&ses={ses}")
MARKETPLACE_URL = ("https://admin.booking.com/hotel/hoteladmin/extranet_ng/manage/"
                   "promotions/marketplace.html?hotel_id={hid}&lang=xu&ses={ses}")


async def _fetch_dod(ctx, ses, hotel_id):
    """Deal-of-the-Day (Deep deal / Limited-time deal) eligibility. Only eligible
    properties render the deep-deal card on the 'Choose new promotion' page, so
    we render and check for it. (Raw HTML shows it for everyone, so we must render.)"""
    page = await ctx.new_page()
    url = MARKETPLACE_URL.format(hid=hotel_id, ses=ses)
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(1500)
        txt = (await page.inner_text("body")).lower()
        cur = page.url
    finally:
        await page.close()
    if "account.booking.com" in cur or ("promotion" not in txt and "deep deals" not in txt):
        raise SessionExpired("Marketplace page bounced to sign-in")
    eligible = "limited-time deal" in txt   # the deep-deal card only renders if eligible
    return {"dod_eligible": "Eligible" if eligible else "Not Eligible"}


async def _fetch_promotions(ctx, ses, hotel_id):
    """Highest ACTIVE discount per category: Portfolio / Campaign / Deep Deal,
    plus Targeting split into Mobile and Country-rate. All from the embedded
    promotion list in the raw page (fast, every row, no rendering)."""
    r = await ctx.request.get(PROMO_URL.format(hid=hotel_id, ses=ses), timeout=20000)
    html = await r.text()
    if "admin.booking.com" not in r.url:
        raise SessionExpired("Promotions page bounced to sign-in")

    promos = []   # (productType, categoryId, discount)
    for m in re.finditer(r'"productType":"([A-Z_]+)"', html):
        start = m.start()
        nxt = html.find('"productType":', start + 12)
        w = html[start:(nxt if nxt > 0 else start + 4000)]
        cat = re.search(r'"categoryId":"([A-Z_]+)"', w)
        st = re.search(r'"status":"(\w+)"', w)
        d = re.search(r'"discount":(\d+)', w)
        if cat and d and st and st.group(1) == "ACTIVE":
            promos.append((m.group(1), cat.group(1), int(d.group(1))))

    def mx(pred):
        vals = [d for (pt, cat, d) in promos if pred(pt, cat)]
        return f"{max(vals)}%" if vals else "None"

    return {
        "promo_portfolio": mx(lambda pt, cat: cat == "PORTFOLIO"),
        "promo_campaign":  mx(lambda pt, cat: cat == "CAMPAIGN"),
        "promo_deep":      mx(lambda pt, cat: cat == "BOOSTER"),   # "Deep deals" category
        "promo_mobile":    mx(lambda pt, cat: pt == "MOBILE_RATE"),
        "promo_country":   mx(lambda pt, cat: pt == "COUNTRY_RATE"),
    }


PBB_URL = ("https://admin.booking.com/fresa/extranet/payments/finance_settings/"
           "{ep}?lang=xu&hotel_id={hid}&ses={ses}")
CO_ADD_URL = ("https://admin.booking.com/hotel/hoteladmin/extranet_ng/manage/"
              "co_add.html?hotel_id={hid}&lang=xu&ses={ses}")
VAT_URL = ("https://admin.booking.com/hotel/hoteladmin/extranet_ng/manage/"
           "vat_tax_charges.html?hotel_id={hid}&lang=xu&ses={ses}")
FINANCE_SETTINGS_URL = ("https://admin.booking.com/hotel/hoteladmin/extranet_ng/manage/"
                        "finance_settings.html?hotel_id={hid}&lang=xu&ses={ses}")


async def _fetch_bank_account(ctx, ses, hotel_id):
    """Bank account number. The number is gated behind each property's sub-account
    and only appears after the finance page loads, so we render — but only for
    properties that actually have valid bank details (fast pre-check)."""
    r = await ctx.request.get(PBB_URL.format(ep="pbb_status", hid=hotel_id, ses=ses), timeout=20000)
    body = await r.text()
    if "admin.booking.com" not in r.url or '"success"' not in body:
        raise SessionExpired("Finance endpoint bounced to sign-in")
    if not re.search(r'"hasValidBankDetails":\s*true', body):
        return {"bank_account": "Not Set"}

    page = await ctx.new_page()
    try:
        await page.goto(FINANCE_SETTINGS_URL.format(hid=hotel_id, ses=ses),
                        wait_until="networkidle", timeout=30000)
        try:
            await page.wait_for_function(
                "() => /Account number/i.test(document.body.innerText)", timeout=8000)
        except Exception:
            await page.wait_for_timeout(2000)
        txt = await page.inner_text("body")
    finally:
        await page.close()
    m = re.search(r'Account number\s*([0-9]{5,})', txt)
    return {"bank_account": m.group(1) if m else ""}


PAGESCORE_URL = ("https://admin.booking.com/hotel/hoteladmin/extranet_ng/manage/"
                 "content_score.html?hotel_id={hid}&lang=xu&ses={ses}")


async def _fetch_pagescore(ctx, ses, hotel_id):
    """Property Page Score % (col 'Property Page Score').

    The dedicated page renders the score client-side, so we render it and read
    the percentage shown under the 'Property page score' card. Retries on
    Booking's transient 'page isn't working' error (same as Genius)."""
    url = PAGESCORE_URL.format(hid=hotel_id, ses=ses)
    page = await ctx.new_page()
    txt = ""
    cur = ""
    try:
        for attempt in range(4):
            try:
                if attempt == 0:
                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                else:
                    await page.reload(wait_until="domcontentloaded", timeout=30000)
                cur = page.url
                if "account.booking.com" in cur:
                    break
                await page.wait_for_function(
                    "() => /property page score/i.test(document.body.innerText)"
                    " && /\\d+\\s*%/.test(document.body.innerText)", timeout=12000)
                txt = await page.inner_text("body")
                break
            except Exception:
                try:
                    txt = await page.inner_text("body")
                    cur = page.url
                except Exception:
                    break
                low = txt.lower()
                if "isn't working" in low or "try refreshing" in low or "does not exist" in low:
                    await page.wait_for_timeout(1500)
                    continue
                break
    finally:
        await page.close()

    if "account.booking.com" in cur:
        raise SessionExpired("Property Page Score page bounced to sign-in")
    # First "NN%" after the 'Property page score' heading is the score.
    m = re.search(r'property page score(.*?)(\d{1,3})\s*%', txt, re.S | re.I)
    return {"pagescore": f"{m.group(2)}%" if m else ""}


async def _fetch_visibility_booster(ctx, ses, hotel_id):
    """Visibility Booster status + boosted commission % (cols 'Visibility Booster'
    [/ 'Booster Commission']).

    Fast endpoint: the co_add page embeds a 'commission_override_list' mapping
    boosted check-in dates -> commission. Any entry means the booster is active
    on at least one day. Empty means inactive."""
    r = await ctx.request.get(CO_ADD_URL.format(hid=hotel_id, ses=ses), timeout=25000)
    if "admin.booking.com" not in r.url:
        raise SessionExpired("co_add page bounced to sign-in")
    html = await r.text()
    # e.g. "2026-06-10":{"commission":"23.0000"} — only present inside the override list
    pairs = re.findall(r'"(\d{4}-\d{2}-\d{2})":\{"commission":"(\d+(?:\.\d+)?)"\}', html)
    if not pairs:
        return {"vb_status": "Inactive", "vb_commission": ""}
    days = len({d for d, _ in pairs})
    pcts = sorted({float(v) for _, v in pairs})
    pct = ", ".join(f"{p:g}%" for p in pcts)
    status = f"Active ({pct})" if days == 1 else f"Active - {days} days ({pct})"
    return {"vb_status": status, "vb_commission": pct}


POLICIES_URL = ("https://admin.booking.com/hotel/hoteladmin/extranet_ng/manage/"
                "property_policies.html?hotel_id={hid}&lang=xu&ses={ses}")


def _line_after(lines, header_kw, value_kw=None, max_ahead=4):
    """First non-empty line after a header line (optionally containing value_kw)."""
    for i, ln in enumerate(lines):
        if header_kw.lower() in ln.lower():
            for nxt in lines[i + 1:i + 1 + max_ahead]:
                s = nxt.strip()
                if s and (value_kw is None or value_kw.lower() in s.lower()):
                    return s
    return ""


def _first_match(txt, *patterns):
    for p in patterns:
        m = re.search(p, txt, re.I)
        if m:
            return (m.group(1) if m.groups() else m.group(0)).strip()
    return ""


def _parse_policies(txt):
    lines = [l.strip() for l in txt.splitlines() if l.strip()]
    checkin  = _first_match(txt, r'Check-?in\s+from\s+([0-9:]+\s*[AaPp][Mm])', r'Check-?in[^\n]*?from\s+([^\n]+)')
    checkout = _first_match(txt, r'Check-?out\s+until\s+([0-9:]+\s*[AaPp][Mm])', r'Check-?out[^\n]*?until\s+([^\n]+)')
    children = _first_match(txt, r'(Children of all ages are allowed[^\n]*)',
                            r'(Children are not allowed[^\n]*)',
                            r'(Children from[^\n]*)')
    # Extra bed: the sentence(s) under "Extra beds"
    extrabed = _line_after(lines, "Extra beds", "extra bed") or \
               _first_match(txt, r'([^\n]*extra bed[^\n]*)')
    payment  = (_first_match(txt, r'You accept the following credit cards:\s*([^\n]+)',
                             r'(You.?re [Uu]sing Payments by Booking[^\n]*)',
                             r'(You don.?t accept[^\n]*card[^\n]*)',
                             r'(No credit cards[^\n]*)')
                or _line_after(lines, "Guest Payment Options"))
    pet      = _first_match(txt, r'(Pets are [^\n.]+)')
    internet = _first_match(txt, r'(WiFi[^\n.]+)', r'(No internet[^\n.]+)', r'(Internet is[^\n.]+)')
    # Parking moved to the facilities page; capture the real sentence, not the
    # "Internet, Parking & Pets" section heading.
    parking  = _first_match(txt, r'(No parking[^\n.]+)', r'(Free[^\n]*parking[^\n.]+)',
                            r'(Parking is available[^\n.]+)', r'(Parking info can now[^\n.]+)')
    pip = " | ".join(f"{k}: {v}" for k, v in
                     (("Pets", pet), ("Internet", internet), ("Parking", parking)) if v)
    longstay = _first_match(txt, r'(You accept reservations for stays longer than[^\n]*)',
                            r'(You don.?t accept reservations for stays longer than[^\n]*)',
                            r'(stays longer than \d+ nights[^\n]*)')
    # Smart Flex: "Join today" pitch = not enrolled; otherwise enrolled/active.
    sf = re.search(r'Smart Flex Reservations(.*?)(?:Looking for|30\+? night|$)', txt, re.S | re.I)
    sf_seg = sf.group(1) if sf else ""
    if re.search(r'Join (today|now)', sf_seg, re.I):
        smart_flex = "Not enrolled"
    elif re.search(r'enrolled|participating|you.?re in|active|opted in', sf_seg, re.I):
        smart_flex = "Enrolled"
    else:
        smart_flex = next((l.strip() for l in sf_seg.splitlines() if l.strip()), "") if sf_seg else ""
    return {
        "checkin_time":  checkin,
        "checkout_time": checkout,
        "children_policy": children,
        "extrabed_policy": extrabed,
        "guest_payment": payment,
        "pet_internet_parking": pip,
        "long_stay_30": longstay,
        "smart_flex": smart_flex,
    }


async def _fetch_policies_fast(ctx, ses, hotel_id):
    """Fast endpoint (policy groups): Check-in time, Check-out time, and
    Pet/Internet/Parking. No rendering."""
    r = await ctx.request.get(CANCEL_URL.format(hid=hotel_id, ses=ses), timeout=25000)
    body = (await r.text()).replace('&nbsp;', ' ')
    if "admin.booking.com" not in r.url or '"name":"Cancellation"' not in body:
        raise SessionExpired("Policy endpoint bounced to sign-in")

    ci  = re.search(r'Check-?in from\s*([0-9:]+\s*[AP]M)', body, re.I)
    co  = re.search(r'Check-?out until\s*([0-9:]+\s*[AP]M)', body, re.I)
    pet = re.search(r'(Pets are[^"<.]*)', body)
    net = re.search(r'((?:Wi-?Fi|WiFi)[^"<.]*)', body)
    pa  = re.search(r'"parking_available"\s*:\s*"?([^",}]*)', body)
    pav = (pa.group(1) if pa else "").strip()
    parking = "Not available" if pav in ("none", "") else pav.replace("_", " ").title()
    pip = " | ".join(f"{k}: {v}" for k, v in (
        ("Pets", pet.group(1).strip() if pet else ""),
        ("Internet", net.group(1).strip() if net else ""),
        ("Parking", parking)) if v)
    return {
        "checkin_time":  ci.group(1).strip() if ci else "",
        "checkout_time": co.group(1).strip() if co else "",
        "pet_internet_parking": pip,
    }


async def _fetch_policies(ctx, ses, hotel_id):
    """Renders the Property Policies page for the fields without a clean endpoint:
    children, extra bed, payment options, and 30+ night stays."""
    url = POLICIES_URL.format(hid=hotel_id, ses=ses)
    page = await ctx.new_page()
    txt = ""
    cur = ""
    try:
        for attempt in range(4):
            try:
                if attempt == 0:
                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                else:
                    await page.reload(wait_until="domcontentloaded", timeout=30000)
                cur = page.url
                if "account.booking.com" in cur:
                    break
                await page.wait_for_function(
                    "() => /Check-?in/i.test(document.body.innerText)"
                    " && /Children|Pets/i.test(document.body.innerText)", timeout=12000)
                txt = await page.inner_text("body")
                break
            except Exception:
                try:
                    txt = await page.inner_text("body")
                    cur = page.url
                except Exception:
                    break
                low = txt.lower()
                if "isn't working" in low or "try refreshing" in low or "does not exist" in low:
                    await page.wait_for_timeout(1500)
                    continue
                break
    finally:
        await page.close()
    if "account.booking.com" in cur:
        raise SessionExpired("Property Policies page bounced to sign-in")
    return _parse_policies(txt)


RES_POLICIES_URL = ("https://admin.booking.com/hotel/hoteladmin/extranet_ng/manage/"
                    "policies.html?hotel_id={hid}&lang=xu&ses={ses}")


async def _fetch_reservation_policies(ctx, ses, hotel_id):
    """Credit Card Exceptions + Date-change for non-refundable bookings, from the
    Policies page (rendered). Retries on Booking's transient error."""
    url = RES_POLICIES_URL.format(hid=hotel_id, ses=ses)
    page = await ctx.new_page()
    txt = ""
    cur = ""
    try:
        for attempt in range(4):
            try:
                if attempt == 0:
                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                else:
                    await page.reload(wait_until="domcontentloaded", timeout=30000)
                cur = page.url
                if "account.booking.com" in cur:
                    break
                await page.wait_for_function(
                    "() => /credit card exception/i.test(document.body.innerText)", timeout=12000)
                txt = await page.inner_text("body")
                break
            except Exception:
                try:
                    txt = await page.inner_text("body")
                    cur = page.url
                except Exception:
                    break
                low = txt.lower()
                if "isn't working" in low or "try refreshing" in low or "does not exist" in low \
                        or "credit card exception" not in low:
                    await page.wait_for_timeout(1500)
                    continue
                break
    finally:
        await page.close()
    if "account.booking.com" in cur:
        raise SessionExpired("Policies page bounced to sign-in")

    cc = re.search(r'You have\s+(\d+)\s+of\s+(\d+)\s+credit card exceptions selected', txt, re.I)
    dc = re.search(r'You added exceptions to\s+(\d+)\s*/\s*(\d+)\s+dates', txt, re.I)
    return {
        "cc_exceptions": f"{cc.group(1)}/{cc.group(2)}" if cc else "",
        "date_change_nonref": f"{dc.group(1)}/{dc.group(2)}" if dc else "",
    }


MSG_TEMPLATES_URL = ("https://admin.booking.com/fresa/messaging/quickReplies/partners/list"
                     "?hotel_id={hid}&lang=xu&ses={ses}")


async def _fetch_messaging(ctx, ses, hotel_id):
    """Message templates count + scheduler (col 'Messaging Template').

    Fast endpoint: the quick-replies list returns each template and its
    scheduler_info (scheduled templates have it). No rendering."""
    r = await ctx.request.get(MSG_TEMPLATES_URL.format(hid=hotel_id, ses=ses), timeout=25000)
    body = await r.text()
    if "admin.booking.com" not in r.url:
        raise SessionExpired("Messaging endpoint bounced to sign-in")
    try:
        data = json.loads(body).get("data") or []
    except Exception:
        data = []
    count = len(data)
    scheduled = sum(1 for t in data if isinstance(t, dict) and t.get("scheduler_info"))
    if count == 0:
        summary, names = "No templates", ""
    else:
        summary = f"{count} template{'s' if count != 1 else ''}, " + \
                  (f"{scheduled} scheduled" if scheduled else "none scheduled")
        # Each name, marked (scheduled) where it has a scheduler.
        names = " | ".join(
            f"{str(t.get('title', '')).strip()}" + (" (scheduled)" if t.get("scheduler_info") else "")
            for t in data if isinstance(t, dict) and t.get("title"))
    return {"messaging_templates": summary, "template_names": names}


RANKING_URL = ("https://admin.booking.com/fresa/extranet/homePage/get_ranking_details"
               "?hotel_id={hid}&lang=xu&ses={ses}")


async def _fetch_analytics(ctx, ses, hotel_id):
    """Search Result Views, Property Page Views, Conversion %, Bookings — fast
    endpoint (ranking details JSON, page-default period). No rendering."""
    r = await ctx.request.get(RANKING_URL.format(hid=hotel_id, ses=ses), timeout=25000)
    body = await r.text()
    if "admin.booking.com" not in r.url or '"success"' not in body:
        raise SessionExpired("Ranking endpoint bounced to sign-in")
    try:
        data = json.loads(body).get("data", {})
    except Exception:
        return {"search_result_views": "", "page_views": "", "conversion_pct": "", "bookings": ""}
    sp = data.get("searchPerformanceData", {}) or {}
    pp = data.get("propertyPageData", {}) or {}
    bk = data.get("bookingsData", {}) or {}

    def pct(d):
        v = str(d.get("conversionFormatted", "")).strip()
        return "" if v == "" else (v if v.endswith("%") else v + "%")

    return {
        # Order as shown on the dashboard:
        # Search Result Views → Search % → Property Page Views → Property % → Bookings
        "search_result_views": sp.get("totalViewsFormatted", ""),
        "search_pct":          pct(sp),
        "page_views":          pp.get("totalViewsFormatted", ""),
        "property_pct":        pct(pp),
        "bookings":            bk.get("totalFormatted", ""),
    }


async def _fetch_tax_details(ctx, ses, hotel_id):
    """GST, PAN and Legal Company Name (cols 'GST' / 'PAN' / 'Legal Company Name').

    Fast endpoint: the finance-settings VAT endpoint returns a rendered HTML
    fragment with Trade name / GSTIN / PAN. The endpoint is occasionally flaky
    (returns no fragment), so we retry a few times. No identity verification."""
    plain = ""
    registered = False
    for attempt in range(4):
        r = await ctx.request.get(PBB_URL.format(ep="VAT", hid=hotel_id, ses=ses), timeout=25000)
        body = await r.text()
        if "admin.booking.com" not in r.url or '"success"' not in body:
            raise SessionExpired("VAT endpoint bounced to sign-in")
        m = re.search(r'"vatDetailsRendered"\s*:\s*"(.*?)"\s*,\s*"isVatEligible"', body, re.S)
        if m:
            frag = (m.group(1).replace('\\u003c', '<').replace('\\u003e', '>')
                    .replace('\\/', '/').replace('\\"', '"')
                    .replace('\\n', ' ').replace('\\t', ' '))
            plain = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', frag)).strip()
            # Stop only on a DEFINITE result: a real GSTIN, or an explicit "No".
            # A flaky/partial fragment (neither) gets retried.
            if re.search(r'GSTIN\s+[0-9A-Z]{15}', plain) or \
               re.search(r'registered for GST purposes\?\s*No\b', plain, re.I):
                break
        await asyncio.sleep(0.6)

    gst  = re.search(r'GSTIN\s+([0-9A-Z]{15})', plain)
    pan  = re.search(r'\bPAN\s+([A-Z]{5}[0-9]{4}[A-Z])\b', plain)
    name = re.search(r'Trade name\s+(.+?)\s+GSTIN', plain)
    return {
        "gst":        gst.group(1) if gst else "",
        "pan":        pan.group(1) if pan else "",
        "legal_name": name.group(1).strip() if name else "",
    }


async def _fetch_finance(ctx, ses, hotel_id):
    """Commission %, Bank details, Prepaid (Payments-by-Booking) status,
    payout timing — all from fast endpoints/pages (no rendering)."""
    r = await ctx.request.get(PBB_URL.format(ep="pbb_status", hid=hotel_id, ses=ses), timeout=20000)
    body = await r.text()
    if "admin.booking.com" not in r.url or '"success"' not in body:
        raise SessionExpired("Finance endpoint bounced to sign-in")

    bank = ("Valid" if re.search(r'"hasValidBankDetails":\s*true', body)
            else ("Not Set" if re.search(r'"hasValidBankDetails":\s*false', body) else ""))
    m = re.search(r'"canOptOut":\s*(true|false)', body)
    prepaid = ("Active" if (m and m.group(1) == "true") else "Inactive") if m else ""

    rt = await ctx.request.get(PBB_URL.format(ep="payout_timing", hid=hotel_id, ses=ses), timeout=20000)
    bt = await rt.text()
    fr = re.search(r'"payoutFrequency":\s*"([a-zA-Z]+)"', bt)
    payout = fr.group(1).capitalize() if fr else ""

    # Commission % from the co_add (visibility booster) page's embedded text.
    rc = await ctx.request.get(CO_ADD_URL.format(hid=hotel_id, ses=ses), timeout=20000)
    bc = await rc.text()
    mc = re.search(r'current commission[^0-9]{0,15}(\d+(?:\.\d+)?)\s*%', bc, re.IGNORECASE)
    commission = (mc.group(1) + "%") if mc else ""

    # Service fee from VAT/Tax — the configured service charge (chargeTypeId 0/1),
    # only present when active. Blank otherwise.
    rv = await ctx.request.get(VAT_URL.format(hid=hotel_id, ses=ses), timeout=20000)
    bv = await rv.text()
    ms = re.search(r'"chargeTypeId":\s*[01],[^}]*?"currencyCode":"([A-Z]+)","amount":([\d.]+)', bv)
    service_fee = f"{ms.group(1)} {ms.group(2)}" if ms else "Not Active"

    return {"commission_pct": commission, "service_fee": service_fee,
            "bank_details": bank, "prepaid_status": prepaid, "payout_timing": payout}


SCRAPERS = [
    # Columns are matched to the sheet by HEADER keywords (not fixed letters),
    # so the sheet can be reordered freely.
    {
        "id": "reviews",
        "label": "Review & Rating",
        "desc": "Review score + number of reviews",
        "status": "live",
        "columns": [(("review", "score"), "review_score"),
                    (("review", "count"), "review_count")],
        "fetch": _fetch_reviews,
    },
    {
        "id": "genius_status",
        "label": "Genius Status",
        "desc": "Enrolled / Eligible / Not Eligible + External prices — instant",
        "status": "live",
        "columns": [(("genius", "status"), "genius_status"),
                    (("external", "price"), "external_prices")],
        "fetch": _fetch_genius_status,
    },
    {
        "id": "genius_level",
        "label": "Genius Level",
        "desc": "G1 / G2 / G3 for enrolled properties — opens enrolled pages",
        "status": "live",
        "columns": [(("genius", "level"), "genius_level")],
        "fetch": _fetch_genius_level,
    },
    # ── Coming next (wire up fetch + columns, then flip status to 'live') ──────
    {
        "id": "preferred",
        "label": "Preferred Status",
        "desc": "Member / Not Enrolled (col L) + Plus eligibility (col M)",
        "status": "live",
        "columns": [(("preferred", "status"), "preferred_status"),
                    (("preferred", "eligib"), "preferred_eligibility")],
        "fetch": _fetch_preferred,
    },
    {
        "id": "performance",
        "label": "Performance Score",
        "desc": "Performance score % (col N)",
        "status": "live",
        "columns": [(("performance", "score"), "perf_score")],
        "fetch": _fetch_performance,
    },
    {
        "id": "promotion",
        "label": "Promotions",
        "desc": "Max active discount: Portfolio / Campaign / Deep Deal / Mobile / Country rate",
        "status": "live",
        "columns": [(("portfolio",), "promo_portfolio"),
                    (("campaign",), "promo_campaign"),
                    (("deep",), "promo_deep"),
                    (("mobile", "rate"), "promo_mobile"),
                    (("country", "rate"), "promo_country")],
        "fetch": _fetch_promotions,
    },
    {
        "id": "dod",
        "label": "DOD Eligibility",
        "desc": "Deal-of-the-Day (deep deal) eligibility — opens each property's page (slower)",
        "status": "live",
        "columns": [(("dod",), "dod_eligible")],
        "fetch": _fetch_dod,
    },
    {
        "id": "finance",
        "label": "Finance",
        "desc": "Commission %, Bank Details, Prepaid status, Payout timing",
        "status": "live",
        "columns": [(("commission",), "commission_pct"),
                    (("service", "fee"), "service_fee"),
                    (("bank", "detail"), "bank_details"),
                    (("prepaid", "status"), "prepaid_status"),
                    (("payout", "timing"), "payout_timing")],
        "fetch": _fetch_finance,
    },
    {
        "id": "bank_account",
        "label": "Bank Account No.",
        "desc": "Account number — opens each bank-having property's page (slower)",
        "status": "live",
        "columns": [(("account", "number"), "bank_account")],
        "fetch": _fetch_bank_account,
    },
    {
        "id": "cancellation",
        "label": "Cancellation Policy",
        "desc": "Cancellation policy name (e.g. 'Flexible - 1 day')",
        "status": "live",
        "columns": [(("cancellation",), "cancellation")],
        "fetch": _fetch_cancellation,
    },
    {
        "id": "contact",
        "label": "Contact No.",
        "desc": "Main (Primary) contact person's phone number — fast; opens a tab only to verify",
        "status": "live",
        "columns": [(("contact",), "contact_no")],
        "fetch": _fetch_contact,
        "verify_url": contact_verify_url,   # opened in a tab on a verification bounce
    },
    {
        "id": "frontend",
        "label": "Frontend Link",
        "desc": "Public Booking.com property page URL — fast",
        "status": "live",
        "columns": [(("front",), "frontend_link")],
        "fetch": _fetch_frontend,
    },
    {
        "id": "photos",
        "label": "Photos",
        "desc": "Number of photos on the property (0 = none added) — fast",
        "status": "live",
        "columns": [(("photo",), "photos")],
        "fetch": _fetch_photos,
    },
    {
        "id": "visibility_booster",
        "label": "Visibility Booster",
        "desc": "Active on any date? + boosted commission % — fast",
        "status": "live",
        "columns": [(("visibility",), "vb_status"),
                    (("booster", "comm"), "vb_commission")],
        "fetch": _fetch_visibility_booster,
    },
    {
        "id": "extranet_access",
        "label": "Extranet Access",
        "desc": "Non-FabHotels emails with extranet access — fast; opens a tab only to verify",
        "status": "live",
        "columns": [(("extranet",), "extranet_external")],
        "fetch": _fetch_extranet_access,
        "verify_url": extranet_verify_url,
    },
    {
        "id": "tax_details",
        "label": "GST / PAN / Legal Name",
        "desc": "GST, PAN and Legal Company Name — fast",
        "status": "live",
        "columns": [(("gst",), "gst"),
                    (("pan",), "pan"),
                    (("legal",), "legal_name")],
        "fetch": _fetch_tax_details,
    },
    {
        "id": "policies_fast",
        "label": "Policies — Check-in / Pet (fast)",
        "desc": "Check-in time, Check-out time, Pet/Internet/Parking — fast endpoint",
        "status": "live",
        "columns": [(("checkin",), "checkin_time"),
                    (("checkout",), "checkout_time"),
                    (("pet",), "pet_internet_parking")],
        "fetch": _fetch_policies_fast,
    },
    {
        "id": "policies",
        "label": "Policies — Children / Bed / Pay (renders)",
        "desc": "Children, extra bed, guest payment, 30+ nights — renders the page (no endpoint)",
        "status": "live",
        "columns": [(("children",), "children_policy"),
                    (("extrabed",), "extrabed_policy"),
                    (("payment",), "guest_payment"),
                    (("night",), "long_stay_30"),
                    (("smart", "flex"), "smart_flex")],
        "fetch": _fetch_policies,
    },
    {
        "id": "reservation_policies",
        "label": "CC Exceptions / Date Change",
        "desc": "Credit card exceptions + date-change for non-refundable bookings — renders the page",
        "status": "live",
        "columns": [(("card", "exception"), "cc_exceptions"),
                    (("date", "change"), "date_change_nonref")],
        "fetch": _fetch_reservation_policies,
    },
    {
        "id": "analytics",
        "label": "Search Perf (Views / Conversion)",
        "desc": "Search result views, property page views, conversion %, bookings — fast",
        "status": "live",
        "columns": [(("search", "view"), "search_result_views"),
                    (("search", "%"), "search_pct"),
                    (("page", "view"), "page_views"),
                    (("property", "%"), "property_pct"),
                    (("booking",), "bookings")],
        "fetch": _fetch_analytics,
    },
    {
        "id": "messaging",
        "label": "Messaging Template",
        "desc": "Message templates count + scheduled + names — fast",
        "status": "live",
        "columns": [(("messag",), "messaging_templates"),
                    (("template", "name"), "template_names")],
        "fetch": _fetch_messaging,
    },
    {
        "id": "pagescore",
        "label": "Property Page Score",
        "desc": "Property page score % — renders the score page (slower)",
        "status": "live",
        "columns": [(("page", "score"), "pagescore")],
        "fetch": _fetch_pagescore,
    },
]

# ── Categorise each scraper by HOW it runs (drives the UI grouping) ───────────
#   fast   — pure endpoint, instant, no user attention needed
#   verify — endpoint, but may pause to open a tab for identity verification
#   render — opens/renders a page per property (slower)
_RENDER_IDS = {"genius_level", "dod", "bank_account", "policies",
               "reservation_policies", "pagescore"}
for _s in SCRAPERS:
    if _s.get("fetch") is None:
        _s["cat"] = "soon"
    elif _s.get("verify_url"):
        _s["cat"] = "verify"
    elif _s["id"] in _RENDER_IDS:
        _s["cat"] = "render"
    else:
        _s["cat"] = "fast"

# Display metadata for each category (order matters for the UI).
CATEGORIES = [
    {"key": "fast",   "label": "Fast — endpoint",         "hint": "Instant, no attention needed"},
    {"key": "verify", "label": "Fast — needs verification","hint": "May pause to verify in Chrome"},
    {"key": "render", "label": "Page render",             "hint": "Opens a page per property — slower"},
]

BY_ID = {s["id"]: s for s in SCRAPERS}
