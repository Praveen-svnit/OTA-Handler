import streamlit as st
import pandas as pd
import json
import ast
import re
import io

from sheets import fetch_crs, fetch_dashboard

st.set_page_config(page_title="SU Mapping Checker", layout="wide", page_icon="🔍")

# ── Constants ──────────────────────────────────────────────────────────────────

YATRA = '97'

CH_MAP = [
    {'col': 11, 'code': '19',  'name': 'Booking.com'},
    {'col': 18, 'code': '105', 'name': 'MakeMyTrip'},
    {'col': 22, 'code': '189', 'name': 'Agoda'},
    {'col': 29, 'code': '217', 'name': 'EMT'},
    {'col': 31, 'code': '351', 'name': 'CT'},
    {'col': 34, 'code': '9',   'name': 'Expedia'},
    {'col': 37, 'code': '97',  'name': 'Yatra'},
]
CH_NAME = {c['code']: c['name'] for c in CH_MAP}

# ── Utilities ──────────────────────────────────────────────────────────────────

def norm_id(v):
    """Strip whitespace and trailing .0 from an ID value."""
    return re.sub(r'\.0+$', '', str(v if v is not None else '').strip())


def parse_room(val):
    """Parse PMS Room ID: 24873-1-RANDOM → propId, roomType."""
    p = str(val or '').split('-')
    return {
        'propId':   norm_id(p[0]) if len(p) > 0 else '',
        'roomType': norm_id(p[1]) if len(p) > 1 else '',
        'raw':      str(val or ''),
    }


def parse_rate(val):
    """Parse PMS Rate ID: 24873-1-CP-RANDOM → propId, roomType, rateCode, suffix."""
    p = str(val or '').split('-')
    return {
        'propId':   norm_id(p[0]) if len(p) > 0 else '',
        'roomType': norm_id(p[1]) if len(p) > 1 else '',
        'rateCode': norm_id(p[2]) if len(p) > 2 else '',
        'suffix':   '-'.join(p[3:]) if len(p) > 3 else '',
        'raw':      str(val or ''),
    }


def parse_obp(val):
    """
    Parse OBP multiplier JSON: {"1": 1, "2": 1} → {"1": 1, "2": 1}
    Handles both standard JSON (double quotes) and Python dict literals (single quotes).
    Returns {} if unparseable.
    """
    if val is None:
        return {}
    s = str(val).strip()
    if s in ('', 'nan', 'None', 'NaN', '{}'):
        return {}

    # Standard JSON — handles {"1": 1, "2": 1}
    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return {str(k): v for k, v in obj.items()}
    except Exception:
        pass

    # Python literal fallback — handles {'1': 1, '2': 1} with single quotes
    try:
        obj = ast.literal_eval(s)
        if isinstance(obj, dict):
            return {str(k): v for k, v in obj.items()}
    except Exception:
        pass

    return {}


def obp_int_keys(obp):
    """Return sorted list of integer occupancy keys from OBP dict."""
    result = []
    for k in obp:
        try:
            n = float(str(k).strip())
            if n == n:          # exclude NaN
                result.append(int(n))
        except (ValueError, TypeError):
            pass
    return sorted(set(result))


def not_one(v):
    try:
        return float(v) != 1.0
    except (ValueError, TypeError):
        return True


def auto_detect(cols, *hint_groups):
    """Return first column whose name (lowercased) contains ALL words in any hint group."""
    for hints in hint_groups:
        hl = [h.lower() for h in hints]
        for col in cols:
            if all(h in col.lower() for h in hl):
                return col
    return None


def pick(cols, *hints):
    """Required selectbox: return index of auto-detected column (default 0)."""
    v = auto_detect(cols, *hints)
    return cols.index(v) if v and v in cols else 0


def pick_opt(cols, *hints):
    """Optional selectbox ([None]+cols): return index of auto-detected column (default 0 = None)."""
    v = auto_detect(cols, *hints)
    lst = [None] + cols
    return lst.index(v) if v and v in lst else 0


# ── File reader ────────────────────────────────────────────────────────────────

def read_su_file(uploaded):
    """Read uploaded SU Excel/CSV file, combining all sheets into one DataFrame."""
    data = uploaded.read()

    # Try openpyxl (.xlsx)
    try:
        xl = pd.ExcelFile(io.BytesIO(data))
        sheets = xl.sheet_names
        dfs = [pd.read_excel(xl, sheet_name=s, dtype=str).fillna('') for s in sheets]
        return pd.concat(dfs, ignore_index=True), sheets
    except Exception:
        pass

    # Try xlrd (.xls legacy)
    try:
        import xlrd
        book = xlrd.open_workbook(file_contents=data, ignore_workbook_corruption=True)
        sheets = book.sheet_names()
        dfs = []
        for sn in sheets:
            ws = book.sheet_by_name(sn)
            if ws.nrows == 0:
                continue
            headers = [str(ws.cell_value(0, c)) for c in range(ws.ncols)]
            body    = [[str(ws.cell_value(r, c)) for c in range(ws.ncols)] for r in range(1, ws.nrows)]
            dfs.append(pd.DataFrame(body, columns=headers))
        if dfs:
            return pd.concat(dfs, ignore_index=True), sheets
    except Exception:
        pass

    # CSV fallback
    for enc in ('utf-8', 'latin-1', 'cp1252'):
        try:
            df = pd.read_csv(io.BytesIO(data), dtype=str, encoding=enc).fillna('')
            return df, ['Sheet1']
        except Exception:
            continue

    raise Exception("Could not read file — try saving as .xlsx in Excel and re-uploading.")


# ── Check engine ───────────────────────────────────────────────────────────────

def build_dash_map(raw_rows):
    """Parse Prop Level Dashboard rows → {propId: {chCode: is_live}}."""
    m = {}
    for row in raw_rows[1:]:
        pid = norm_id(row[0]) if row else ''
        if not pid:
            continue
        m[pid] = {
            ch['code']: (str(row[ch['col']]).strip() == 'Live' if ch['col'] < len(row) else False)
            for ch in CH_MAP
        }
    return m


def run_checks(su_df, crs_df, dash_raw, col):
    su = col['su']
    ci = col['int']

    # ── CRS lookups ────────────────────────────────────────────────────────────
    prop_set = set()        # valid property IDs
    rp_set   = set()        # "propId|roomType|rateCode" for active entries
    occ_map  = {}           # "propId|roomType" → max occupancy (int)

    for _, r in crs_df.iterrows():
        if ci.get('is_active'):
            if str(r.get(ci['is_active'], '')).strip().upper() != 'TRUE':
                continue
        pid = norm_id(r.get(ci['prop_id'], ''))
        rt  = norm_id(r.get(ci['room_type'], ''))
        rc  = norm_id(r.get(ci['rate_code'], ''))
        if not pid:
            continue
        prop_set.add(pid)
        if rt and rc:
            rp_set.add(f"{pid}|{rt}|{rc}")
        if ci.get('max_occ'):
            try:
                mo = int(float(str(r.get(ci['max_occ'], '') or '0')))
            except (ValueError, TypeError):
                mo = 0
            k = f"{pid}|{rt}"
            if mo > 0 and occ_map.get(k, 0) < mo:
                occ_map[k] = mo

    dash = build_dash_map(dash_raw) if dash_raw else {}

    # ── Result buckets ─────────────────────────────────────────────────────────
    res = {k: [] for k in [
        'rr',       # Check 1 : Room type mismatch (Room ID vs Rate ID)
        'apg',      # Check 2 : Applicable Guests on non-Yatra channel
        'obpv',     # Check 3 : OBP multiplier ≠ 1
        'obpoe',    # Check 4a: OBP extra occupancy (exceeds CRS max_occ)
        'obpom',    # Check 4b: OBP missing occupancy (below CRS max_occ)
        'rpmicp',   # Check 5 : Rate plan missing in SU — EP / CP
        'rpmimap',  # Check 5 : Rate plan missing in SU — MAP / AP
        'rpmi',     # Check 5 : Rate plan missing in SU — other
        'rpex',     # Check 5 : Rate plan extra in SU (not in CRS)
        'chlive',   # Check 6 : OTA Live in dashboard but no SU mapping
        'chdead',   # Check 6 : SU mapping exists but OTA not Live
        'ncrs',     # Info    : Excluded — property not found in CRS
    ]}

    # SU tracking (built during main loop, consumed in post-loop checks)
    su_rp  = set()   # "ch|propId|roomType|rateCode"
    su_raw = {}      # su_rp key → {raw, ch_name, pname}
    su_ch  = set()   # "propId|ch"
    names  = {}      # propId → property name
    sfxs   = {}      # "propId|roomType" → rate ID suffix

    su_excluded = su_analyzed = 0

    # ── Main SU loop ───────────────────────────────────────────────────────────
    for _, row in su_df.iterrows():
        rm    = parse_room(row.get(su['room_id'], ''))
        rt    = parse_rate(row.get(su['rate_id'], ''))
        obp   = parse_obp(row.get(su['obp'], ''))
        pname = str(row.get(su.get('prop_name') or '', '') or '').strip()
        ch    = norm_id(str(row.get(su.get('channel') or '', '') or ''))
        ag    = str(row.get(su.get('app_guests') or '', '') or '').strip()
        chn   = CH_NAME.get(ch, ch)
        pid   = rt['propId']

        # Exclude rows whose property is not in CRS
        if not pid or pid not in prop_set:
            su_excluded += 1
            res['ncrs'].append({
                'Property ID':   pid or '(empty)',
                'Property Name': pname,
                'Channel':       ch,
                'PMS Room ID':   rm['raw'],
                'PMS Rate ID':   rt['raw'],
                'Reason':        'Property ID not found in CRS',
            })
            continue

        is_yatra = (ch == YATRA)
        if ch and pid:  su_ch.add(f"{pid}|{ch}")
        if pname and pid not in names:  names[pid] = pname

        # ── Check 2: Applicable Guests ─────────────────────────────────────────
        # Only channel 97 (Yatra) should have a value here. Flag all others.
        if su.get('app_guests') and not is_yatra and ag:
            res['apg'].append({
                'Property ID': pid, 'Property Name': pname,
                'OTA': chn, 'Ch Code': ch,
                'PMS Rate ID': rt['raw'], 'Rate Plan': rt['rateCode'],
                'Applicable Guests Value': ag,
                'Issue': f'Ch {ch} has "{ag}" in Applicable Guests — only ch {YATRA} (Yatra) should use this',
            })

        if is_yatra:
            continue
        su_analyzed += 1

        # ── Check 1: Room type mismatch ────────────────────────────────────────
        # Segment 2 of PMS Room ID and PMS Rate ID must be the same room category.
        if rm['roomType'] != rt['roomType']:
            res['rr'].append({
                'Property ID': pid, 'Property Name': pname,
                'OTA': chn, 'Ch Code': ch,
                'PMS Room ID': rm['raw'], 'Room Type (Room)': rm['roomType'],
                'PMS Rate ID': rt['raw'], 'Room Type (Rate)': rt['roomType'],
                'Rate Plan': rt['rateCode'],
                'Issue': f'Room type "{rm["roomType"]}" ≠ "{rt["roomType"]}"',
            })

        # ── Check 3: OBP multiplier ≠ 1 ───────────────────────────────────────
        # {"1": 1, "2": 1} — every occupancy value must equal 1.
        bad = [(k, v) for k, v in obp.items() if not_one(v)]
        if bad:
            res['obpv'].append({
                'Property ID': pid, 'Property Name': pname,
                'OTA': chn, 'Ch Code': ch,
                'PMS Rate ID': rt['raw'], 'Room Type': rt['roomType'],
                'Rate Plan': rt['rateCode'],
                'OBP (raw)': str(obp),
                'Bad Values': ', '.join(f'Occ {k}: {v}' for k, v in bad),
            })

        # ── Check 4: OBP occupancy keys vs CRS max_occupancy ──────────────────
        occ_key = f"{pid}|{rt['roomType']}"
        if ci.get('max_occ') and occ_key in occ_map:
            max_occ  = occ_map[occ_key]
            occ_keys = obp_int_keys(obp)
            extra    = [o for o in occ_keys if o > max_occ]
            missing  = [o for o in range(1, max_occ + 1) if o not in occ_keys]
            base = {
                'Property ID': pid, 'Property Name': pname,
                'OTA': chn, 'Ch Code': ch,
                'PMS Rate ID': rt['raw'], 'Room Type': rt['roomType'],
                'Rate Plan': rt['rateCode'],
                'Internal Max Occ': max_occ,
                'OBP Occupancies in SU': ', '.join(str(o) for o in occ_keys),
            }
            if extra:
                res['obpoe'].append({**base,
                    'Should Be Removed': ', '.join(str(o) for o in extra),
                    'Issue': f'Extra in SU: Occ {", ".join(str(o) for o in extra)} — CRS max occ is {max_occ}',
                })
            if missing:
                res['obpom'].append({**base,
                    'Needs to be Added': ', '.join(str(o) for o in missing),
                    'Issue': f'Missing in SU: Occ {", ".join(str(o) for o in missing)} — CRS max occ is {max_occ}',
                })

        # ── Check 6 (row-level): Mapped in SU but OTA not Live ─────────────────
        if dash:
            cs = dash.get(pid)
            if cs and not cs.get(ch):
                res['chdead'].append({
                    'Property ID': pid, 'Property Name': pname,
                    'OTA': chn, 'Ch Code': ch,
                    'PMS Rate ID': rt['raw'], 'Room Type': rt['roomType'],
                    'Rate Plan': rt['rateCode'],
                    'Internal Max Occ': occ_map.get(occ_key, ''),
                    'Issue': f'Mapped in SU but {chn} (ch {ch}) is not Live in dashboard',
                })

        # Track SU rate plans for Check 5
        rp_key = f"{pid}|{rt['roomType']}|{rt['rateCode']}"
        ck = f"{ch}|{rp_key}"
        su_rp.add(ck)
        su_raw[ck] = {'raw': rt['raw'], 'ch_name': chn, 'pname': pname}
        sk = f"{pid}|{rt['roomType']}"
        if rt['suffix'] and sk not in sfxs:
            sfxs[sk] = rt['suffix']

    # ── Check 5a: Rate plan in CRS but missing in SU ──────────────────────────
    for k in rp_set:
        pid, rt_id, rc = k.split('|')
        for ch_obj in CH_MAP:
            if ch_obj['code'] == YATRA:
                continue
            if dash:
                cs = dash.get(pid)
                if cs and not cs.get(ch_obj['code']):
                    continue    # OTA not live for this property — skip
            if f"{ch_obj['code']}|{pid}|{rt_id}|{rc}" not in su_rp:
                sfx = sfxs.get(f"{pid}|{rt_id}", '')
                entry = {
                    'Property ID':      pid,
                    'Property Name':    names.get(pid, ''),
                    'OTA':              ch_obj['name'],
                    'Ch Code':          ch_obj['code'],
                    'Room Type ID':     rt_id,
                    'Rate Plan Code':   rc,
                    'PMS Rate ID':      f"{pid}-{rt_id}-{rc}-{sfx}" if sfx else f"{pid}-{rt_id}-{rc}",
                    'Internal Max Occ': occ_map.get(f"{pid}|{rt_id}", ''),
                    'Issue':            'In CRS but not pushed to SU for this channel',
                }
                rcu = rc.upper()
                if rcu in ('EP', 'CP'):    res['rpmicp'].append(entry)
                elif rcu in ('MAP', 'AP'): res['rpmimap'].append(entry)
                else:                       res['rpmi'].append(entry)

    # ── Check 5b: Rate plan in SU but not in CRS ──────────────────────────────
    for ck in su_rp:
        ch, pid, rt_id, rc = ck.split('|', 3)
        if pid not in prop_set:
            continue
        if f"{pid}|{rt_id}|{rc}" not in rp_set:
            d = su_raw.get(ck, {})
            res['rpex'].append({
                'Property ID':      pid,
                'Property Name':    d.get('pname', names.get(pid, '')),
                'OTA':              d.get('ch_name', ch),
                'Ch Code':          ch,
                'PMS Rate ID':      d.get('raw', f"{pid}-{rt_id}-{rc}"),
                'Room Type ID':     rt_id,
                'Rate Plan Code':   rc,
                'Internal Max Occ': occ_map.get(f"{pid}|{rt_id}", ''),
                'Issue':            'In SU but not found in CRS',
            })

    # ── Check 6: OTA Live but no SU mapping at all ─────────────────────────────
    for prop_id, cs in dash.items():
        if prop_id not in prop_set:
            continue
        for ch_obj in CH_MAP:
            if cs.get(ch_obj['code']) and f"{prop_id}|{ch_obj['code']}" not in su_ch:
                res['chlive'].append({
                    'Property ID':   prop_id,
                    'Property Name': names.get(prop_id, ''),
                    'OTA':           ch_obj['name'],
                    'Ch Code':       ch_obj['code'],
                    'Issue': f'{ch_obj["name"]} (ch {ch_obj["code"]}) is Live but no mapping in SU',
                })

    res['_meta'] = {
        'crs_props':      len(prop_set),
        'su_excluded':    su_excluded,
        'total_analyzed': su_analyzed,
        'occ_map_size':   len(occ_map),     # diagnostic
        'max_occ_col':    ci.get('max_occ'), # diagnostic
    }
    return res


# ── UI helpers ─────────────────────────────────────────────────────────────────

def show_table(data, dl_name):
    if not data:
        st.success("✅ No issues found.")
        return
    df = pd.DataFrame(data)
    q = st.text_input("Search / filter rows", key=f"q_{dl_name}", placeholder="Type to filter…")
    if q:
        mask = df.apply(lambda r: r.astype(str).str.contains(q, case=False, regex=False).any(), axis=1)
        df = df[mask]
    st.caption(f"{len(df):,} row(s)")
    st.dataframe(df, use_container_width=True, height=420)
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    st.download_button("⬇️ Download Excel", buf.getvalue(),
                       file_name=f"{dl_name}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       key=f"dl_{dl_name}")


# ── Page layout ────────────────────────────────────────────────────────────────

st.title("🔍 SU Mapping Checker")
st.caption("Validates SU channel manager data against CRS & Prop Level Dashboard · FabHotels Internal")

# ── Step 1: Upload SU file ─────────────────────────────────────────────────────
st.markdown("### Step 1 — Upload SU Export")
uploaded = st.file_uploader("SU Excel file (all sheets will be combined)", type=["xlsx", "xls", "csv"])

if uploaded:
    try:
        with st.spinner("Reading file…"):
            su_df, sheets = read_su_file(uploaded)
        st.success(f"{len(su_df):,} rows loaded from {len(sheets)} sheet(s): {', '.join(str(s) for s in sheets)}")
        st.session_state['su_df'] = su_df
    except Exception as e:
        st.error(str(e))

su_df = st.session_state.get('su_df')

# ── Step 2: Fetch CRS & Dashboard ─────────────────────────────────────────────
st.markdown("### Step 2 — Fetch Data Sources")
c1, c2 = st.columns(2)

with c1:
    if st.button("🔄 Fetch CRS Data", use_container_width=True):
        fetch_crs.clear()
        try:
            with st.spinner("Fetching CRS data…"):
                crs_df = fetch_crs()
            st.session_state['crs_df'] = crs_df
            st.session_state.pop('crs_err', None)
        except Exception as e:
            st.session_state['crs_err'] = str(e)
    if 'crs_df' in st.session_state:
        d = st.session_state['crs_df']
        st.success(f"CRS loaded: {len(d):,} rows · {len(d.columns)} columns")
    elif 'crs_err' in st.session_state:
        st.error(f"CRS fetch failed: {st.session_state['crs_err']}")
    else:
        st.info("Click to fetch CRS data")

with c2:
    if st.button("🔄 Fetch Dashboard (optional)", use_container_width=True):
        fetch_dashboard.clear()
        try:
            with st.spinner("Fetching dashboard…"):
                dash_raw = fetch_dashboard()
            st.session_state['dash_raw'] = dash_raw
            st.session_state.pop('dash_err', None)
        except Exception as e:
            st.session_state['dash_err'] = str(e)
    if 'dash_raw' in st.session_state:
        st.success(f"Dashboard loaded: {len(st.session_state['dash_raw']) - 1:,} properties")
    elif 'dash_err' in st.session_state:
        st.warning(f"Dashboard failed: {st.session_state['dash_err']}")
    else:
        st.info("Click to fetch Prop Level Dashboard (for OTA live checks)")

crs_df   = st.session_state.get('crs_df')
dash_raw = st.session_state.get('dash_raw')

# ── Step 3: Column mapping ─────────────────────────────────────────────────────
st.markdown("### Step 3 — Column Mapping")

if su_df is None or crs_df is None:
    st.info("Upload the SU file and fetch CRS data first.")
    st.stop()

su_cols  = list(su_df.columns)
crs_cols = list(crs_df.columns)

with st.expander("SU File Columns", expanded=True):
    a, b, c = st.columns(3)
    with a:
        su_room_id = st.selectbox("PMS Room ID",     su_cols, index=pick(su_cols, ['pms room'], ['room id'], ['roomid']))
        su_rate_id = st.selectbox("PMS Rate ID",     su_cols, index=pick(su_cols, ['pms rate'], ['rate id'], ['rateid']))
    with b:
        su_obp     = st.selectbox("OBP Multiplier",  su_cols, index=pick(su_cols, ['obp'], ['multiplier'], ['occ']))
        su_channel = st.selectbox("Channel Code",    [None] + su_cols, index=pick_opt(su_cols, ['channel'], ['ota']))
    with c:
        su_prop_name  = st.selectbox("Property Name (optional)",     [None] + su_cols, index=pick_opt(su_cols, ['property name'], ['hotel name'], ['name']))
        su_app_guests = st.selectbox("Applicable Guests (optional)", [None] + su_cols, index=pick_opt(su_cols, ['applicable guests'], ['applicable_guests'], ['appguests']))

with st.expander("CRS Columns", expanded=True):
    a, b, c = st.columns(3)
    with a:
        crs_prop_id   = st.selectbox("Property ID",    crs_cols, index=pick(crs_cols, ['property id'], ['prop id'], ['hotel id'], ['property_id']))
        crs_room_type = st.selectbox("Room Type ID",   crs_cols, index=pick(crs_cols, ['room type'], ['room_type'], ['roomtype']))
    with b:
        crs_rate_code = st.selectbox("Rate Plan Code", crs_cols, index=pick(crs_cols, ['rate plan'], ['rate code'], ['rate_plan'], ['ratecode'], ['rate']))
        crs_max_occ   = st.selectbox("Max Occupancy (optional)", [None] + crs_cols,
                                     index=pick_opt(crs_cols, ['max occ'], ['max_occ'], ['max occupancy'],
                                                    ['maximum occupancy'], ['maxocc'], ['occupancy'], ['pax'], ['max pax']))
    with c:
        crs_is_active = st.selectbox("Active filter (optional)", [None] + crs_cols,
                                     index=pick_opt(crs_cols, ['is_active'], ['is active'], ['active'], ['status']))

col_cfg = {
    'su': {
        'room_id':    su_room_id,
        'rate_id':    su_rate_id,
        'obp':        su_obp,
        'prop_name':  su_prop_name,
        'channel':    su_channel,
        'app_guests': su_app_guests,
    },
    'int': {
        'prop_id':   crs_prop_id,
        'room_type': crs_room_type,
        'rate_code': crs_rate_code,
        'max_occ':   crs_max_occ,
        'is_active': crs_is_active,
    },
}

# ── OBP parse debug ────────────────────────────────────────────────────────────
with st.expander("🔬 OBP Parse Debug (check before running)", expanded=False):
    st.caption("Shows how the OBP column values are being read and parsed. If 'Parsed Keys' is always empty, the format is not being recognised.")
    sample = su_df.head(10)
    debug_rows = []
    for _, r in sample.iterrows():
        raw_val = r.get(su_obp, '')
        parsed  = parse_obp(raw_val)
        debug_rows.append({
            'OBP Raw Value':  str(raw_val)[:80],
            'Parsed (dict)':  str(parsed)[:80],
            'Parsed Keys':    str(list(parsed.keys())),
            'Key count':      len(parsed),
        })
    st.dataframe(pd.DataFrame(debug_rows), use_container_width=True)
    st.caption(f"Max Occ column selected: **{crs_max_occ}**  |  Is Active column selected: **{crs_is_active}**")

# ── Step 4: Run checks ─────────────────────────────────────────────────────────
st.markdown("### Step 4 — Run Checks")
if st.button("🚀 Run All Checks", type="primary", use_container_width=True):
    with st.spinner("Running checks…"):
        results = run_checks(su_df, crs_df, dash_raw, col_cfg)
    st.session_state['results'] = results
    m = results['_meta']
    st.success(
        f"Done · CRS properties: {m['crs_props']:,} · "
        f"SU rows analyzed: {m['total_analyzed']:,} · "
        f"Excluded (not in CRS): {m['su_excluded']:,}"
    )
    if m['max_occ_col']:
        st.info(f"Max Occ column used: **{m['max_occ_col']}** · entries in occ_map: **{m['occ_map_size']:,}**")
    else:
        st.warning("⚠️ No Max Occupancy column selected — OBP Extra/Missing checks will not run.")
    st.rerun()

# ── Results ────────────────────────────────────────────────────────────────────
if 'results' not in st.session_state:
    st.stop()

res  = st.session_state['results']
meta = res['_meta']

st.divider()
m1, m2, m3, m4 = st.columns(4)
m1.metric("CRS Properties",   f"{meta['crs_props']:,}")
m2.metric("SU Rows Analyzed", f"{meta['total_analyzed']:,}")
m3.metric("Excluded (not in CRS)", f"{meta['su_excluded']:,}")
m4.metric("OCC Map entries",  f"{meta['occ_map_size']:,}")

CHECKS = [
    ('rr',      "Room-Rate Mismatch",      "Room type in PMS Room ID ≠ PMS Rate ID"),
    ('apg',     "Applicable Guests",        "Non-ch 97 channel has value in Applicable Guests"),
    ('obpv',    "OBP Multiplier ≠ 1",       "Multiplier value is not 1"),
    ('obpoe',   "OBP Extra Occ (remove)",   "OBP occupancy > CRS max occ — needs removal"),
    ('obpom',   "OBP Missing Occ (add)",    "OBP occupancy < CRS max occ — needs to be added"),
    ('rpmicp',  "Missing in SU — EP/CP",    "EP or CP in CRS not pushed to SU"),
    ('rpmimap', "Missing in SU — MAP/AP",   "MAP or AP in CRS not pushed to SU"),
    ('rpmi',    "Missing in SU — Other",    "Other rate plans in CRS not pushed to SU"),
    ('rpex',    "Extra in SU",              "Rate plan in SU not found in CRS"),
    ('chlive',  "OTA Live, No Mapping",     "OTA is Live but no SU mapping exists"),
    ('chdead',  "Mapped, OTA Not Live",     "SU mapping exists but OTA is not Live"),
    ('ncrs',    "Not in CRS (excluded)",    "SU rows excluded — property not in CRS"),
]

tab_labels = [f"{'🔴' if len(res.get(k,[])) > 0 and k != 'ncrs' else '⚫' if k == 'ncrs' else '🟢'} {lbl} ({len(res.get(k,[]))})"
              for k, lbl, _ in CHECKS]
tabs = st.tabs(tab_labels)

for i, (k, lbl, desc) in enumerate(CHECKS):
    with tabs[i]:
        st.caption(desc)
        show_table(res.get(k, []), k)

# ── Full export ────────────────────────────────────────────────────────────────
st.divider()
if st.button("📥 Export All Results to Excel"):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for k, lbl, _ in CHECKS:
            rows = res.get(k, [])
            if rows:
                pd.DataFrame(rows).to_excel(writer, sheet_name=lbl[:31], index=False)
    st.download_button(
        "⬇️ Download Full Report",
        buf.getvalue(),
        file_name="su_mapping_report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
