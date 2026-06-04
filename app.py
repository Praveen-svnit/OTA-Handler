import streamlit as st
import pandas as pd
import json
import ast
import re
import io

from sheets import fetch_crs, fetch_dashboard, save_run_log, fetch_run_log

st.set_page_config(
    page_title="SU Mapping Checker",
    layout="wide",
    page_icon="🔍",
    initial_sidebar_state="expanded",
)

# ── Styling ────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── Font & base ── */
* { font-family: -apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', sans-serif !important; }
body, .stApp { background: #f8fafc; }

/* ── Hide Streamlit chrome ── */
#MainMenu, footer, header { visibility: hidden; }
[data-testid="stDecoration"] { display: none; }
[data-testid="stSidebarNav"] { display: none; }

/* ── Main container ── */
.block-container { padding: 1.25rem 2rem 2rem !important; max-width: 1400px !important; }

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: #0f172a !important;
    border-right: 1px solid #1e293b !important;
}
[data-testid="stSidebar"] > div:first-child { padding-top: 0 !important; }

/* ── Section divider ── */
.sb-divider { height: 1px; background: #1e293b; margin: 8px 0 12px; }
.sb-label { font-size: 10px; font-weight: 600; text-transform: uppercase;
            letter-spacing: 1px; color: #475569; padding: 0 0 6px; }
.sb-nav-item {
    display: flex; align-items: center; gap: 9px;
    padding: 8px 10px; border-radius: 6px; cursor: pointer;
    color: #cbd5e1; font-size: 13px; font-weight: 500;
    transition: background .15s;
}
.sb-nav-item.active { background: #1e293b; color: #f1f5f9; }
.sb-nav-item:hover { background: #1e293b; }

/* ── Page header ── */
.pg-title { font-size: 17px; font-weight: 700; color: #0f172a; margin: 0; }
.pg-sub   { font-size: 12px; color: #64748b; margin-top: 2px; }
.pg-badge { background: #eff6ff; color: #2563eb; font-size: 10px; font-weight: 600;
            padding: 2px 8px; border-radius: 10px; }

/* ── Step label ── */
.step-pill {
    display: inline-flex; align-items: center; gap: 6px;
    font-size: 11px; font-weight: 600; text-transform: uppercase;
    letter-spacing: .5px; color: #64748b; margin: 14px 0 6px;
}
.step-num {
    width: 18px; height: 18px; border-radius: 50%; background: #e2e8f0;
    color: #475569; font-size: 10px; font-weight: 700;
    display: inline-flex; align-items: center; justify-content: center;
}

/* ── Status badges inside buttons / info ── */
.inf-row {
    display: flex; gap: 10px; flex-wrap: wrap; align-items: center;
    padding: 7px 12px; background: white; border: 1px solid #e2e8f0;
    border-radius: 7px; margin-top: 6px; font-size: 12px; color: #374151;
}
.inf-row b { color: #0f172a; }

/* ── Compact metrics ── */
[data-testid="stMetric"] {
    background: white !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 7px !important;
    padding: 10px 14px !important;
}
[data-testid="stMetricLabel"] p { font-size: 11px !important; color: #64748b !important; }
[data-testid="stMetricValue"]   { font-size: 22px !important; font-weight: 700 !important; }

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] {
    gap: 0; border-bottom: 1px solid #e2e8f0;
    overflow-x: auto; flex-wrap: nowrap;
}
.stTabs [data-baseweb="tab"] {
    font-size: 11px !important; padding: 6px 11px !important;
    white-space: nowrap; font-weight: 500;
}

/* ── Expanders ── */
[data-testid="stExpander"] {
    border: 1px solid #e2e8f0 !important;
    border-radius: 8px !important;
    margin-bottom: 6px !important;
    background: white !important;
}
details > summary {
    font-size: 13px !important; font-weight: 600 !important;
    color: #374151 !important; padding: 10px 14px !important;
}

/* ── Select / input ── */
[data-testid="stSelectbox"] label p,
[data-testid="stFileUploader"] label p { font-size: 12px !important; color: #374151 !important; }

/* ── Alerts compact ── */
[data-testid="stAlert"] { padding: 7px 12px !important; border-radius: 6px !important; }
[data-testid="stAlert"] p { font-size: 12px !important; margin: 0 !important; }

/* ── Dataframe ── */
[data-testid="stDataFrame"] { border: 1px solid #e2e8f0; border-radius: 6px; }

/* ── Caption ── */
.stCaption p { font-size: 11px !important; color: #94a3b8 !important; }

/* ── Divider ── */
hr { margin: 14px 0 !important; border-color: #e2e8f0 !important; }
</style>
""", unsafe_allow_html=True)

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
    return re.sub(r'\.0+$', '', str(v if v is not None else '').strip())

def parse_room(val):
    p = str(val or '').split('-')
    return {'propId': norm_id(p[0]) if p else '', 'roomType': norm_id(p[1]) if len(p) > 1 else '', 'raw': str(val or '')}

def parse_rate(val):
    p = str(val or '').split('-')
    return {
        'propId':   norm_id(p[0]) if p else '',
        'roomType': norm_id(p[1]) if len(p) > 1 else '',
        'rateCode': norm_id(p[2]) if len(p) > 2 else '',
        'suffix':   '-'.join(p[3:]) if len(p) > 3 else '',
        'raw':      str(val or ''),
    }

def parse_obp(val):
    if val is None: return {}
    s = str(val).strip()
    if s in ('', 'nan', 'None', 'NaN', '{}'): return {}
    try:
        obj = json.loads(s)
        if isinstance(obj, dict): return {str(k): v for k, v in obj.items()}
    except Exception: pass
    try:
        obj = ast.literal_eval(s)
        if isinstance(obj, dict): return {str(k): v for k, v in obj.items()}
    except Exception: pass
    return {}

def obp_int_keys(obp):
    out = []
    for k in obp:
        try:
            n = float(str(k).strip())
            if n == n: out.append(int(n))
        except (ValueError, TypeError): pass
    return sorted(set(out))

def not_one(v):
    try: return float(v) != 1.0
    except (ValueError, TypeError): return True

def auto_detect(cols, *hint_groups):
    for hints in hint_groups:
        hl = [h.lower() for h in hints]
        for col in cols:
            if all(h in col.lower() for h in hl): return col
    return None

def pick(cols, *hints):
    v = auto_detect(cols, *hints)
    return cols.index(v) if v and v in cols else 0

def pick_opt(cols, *hints):
    v = auto_detect(cols, *hints)
    lst = [None] + cols
    return lst.index(v) if v and v in lst else 0

# ── File reader ────────────────────────────────────────────────────────────────

def read_su_file(uploaded):
    data = uploaded.read()
    try:
        xl = pd.ExcelFile(io.BytesIO(data))
        sheets = xl.sheet_names
        dfs = [pd.read_excel(xl, sheet_name=s, dtype=str).fillna('') for s in sheets]
        return pd.concat(dfs, ignore_index=True), sheets
    except Exception: pass
    try:
        import xlrd
        book = xlrd.open_workbook(file_contents=data, ignore_workbook_corruption=True)
        sheets = book.sheet_names()
        dfs = []
        for sn in sheets:
            ws = book.sheet_by_name(sn)
            if ws.nrows == 0: continue
            h = [str(ws.cell_value(0, c)) for c in range(ws.ncols)]
            b = [[str(ws.cell_value(r, c)) for c in range(ws.ncols)] for r in range(1, ws.nrows)]
            dfs.append(pd.DataFrame(b, columns=h))
        if dfs: return pd.concat(dfs, ignore_index=True), sheets
    except Exception: pass
    for enc in ('utf-8', 'latin-1', 'cp1252'):
        try:
            df = pd.read_csv(io.BytesIO(data), dtype=str, encoding=enc).fillna('')
            return df, ['Sheet1']
        except Exception: continue
    raise Exception("Could not read file — try saving as .xlsx in Excel and re-uploading.")

# ── Check engine ───────────────────────────────────────────────────────────────

def build_dash_map(raw):
    m = {}
    for row in raw[1:]:
        pid = norm_id(row[0]) if row else ''
        if not pid: continue
        m[pid] = {ch['code']: (str(row[ch['col']]).strip() == 'Live' if ch['col'] < len(row) else False) for ch in CH_MAP}
    return m

def run_checks(su_df, crs_df, dash_raw, col):
    su, ci = col['su'], col['int']

    prop_set = set()
    rp_set   = set()
    occ_map  = {}

    for _, r in crs_df.iterrows():
        if ci.get('is_active'):
            if str(r.get(ci['is_active'], '')).strip().upper() != 'TRUE': continue
        pid = norm_id(r.get(ci['prop_id'], ''))
        rt  = norm_id(r.get(ci['room_type'], ''))
        rc  = norm_id(r.get(ci['rate_code'], ''))
        if not pid: continue
        prop_set.add(pid)
        if rt and rc: rp_set.add(f"{pid}|{rt}|{rc}")
        if ci.get('max_occ'):
            try: mo = int(float(str(r.get(ci['max_occ'], '') or '0')))
            except (ValueError, TypeError): mo = 0
            k = f"{pid}|{rt}"
            if mo > 0 and occ_map.get(k, 0) < mo: occ_map[k] = mo

    dash = build_dash_map(dash_raw) if dash_raw else {}

    res = {k: [] for k in ['rr','apg','obpv','obpoe','obpom','rpmicp','rpmimap','rpmi','rpex','chlive','chdead','ncrs']}

    su_rp = set(); su_raw = {}; su_ch = set(); names = {}; sfxs = {}
    excl = analyzed = 0

    for _, row in su_df.iterrows():
        rm    = parse_room(row.get(su['room_id'], ''))
        rt    = parse_rate(row.get(su['rate_id'], ''))
        obp   = parse_obp(row.get(su['obp'], ''))
        pname = str(row.get(su.get('prop_name') or '', '') or '').strip()
        ch    = norm_id(str(row.get(su.get('channel') or '', '') or ''))
        ag    = str(row.get(su.get('app_guests') or '', '') or '').strip()
        chn   = CH_NAME.get(ch, ch)
        pid   = rt['propId']

        if not pid or pid not in prop_set:
            excl += 1
            res['ncrs'].append({'Property ID': pid or '(empty)', 'Property Name': pname, 'Channel': ch,
                                'PMS Room ID': rm['raw'], 'PMS Rate ID': rt['raw'], 'Reason': 'Not found in CRS'})
            continue

        is_yatra = (ch == YATRA)
        if ch and pid: su_ch.add(f"{pid}|{ch}")
        if pname and pid not in names: names[pid] = pname

        if su.get('app_guests') and not is_yatra and ag:
            res['apg'].append({'Property ID': pid, 'Property Name': pname, 'OTA': chn, 'Ch Code': ch,
                               'PMS Rate ID': rt['raw'], 'Rate Plan': rt['rateCode'], 'Applicable Guests Value': ag,
                               'Issue': f'Ch {ch} has "{ag}" in Applicable Guests — only ch {YATRA} (Yatra) should use this'})

        if is_yatra: continue
        analyzed += 1

        if rm['roomType'] != rt['roomType']:
            res['rr'].append({'Property ID': pid, 'Property Name': pname, 'OTA': chn, 'Ch Code': ch,
                              'PMS Room ID': rm['raw'], 'Room Type (Room)': rm['roomType'],
                              'PMS Rate ID': rt['raw'], 'Room Type (Rate)': rt['roomType'], 'Rate Plan': rt['rateCode'],
                              'Issue': f'Room type "{rm["roomType"]}" ≠ "{rt["roomType"]}"'})

        bad = [(k, v) for k, v in obp.items() if not_one(v)]
        if bad:
            res['obpv'].append({'Property ID': pid, 'Property Name': pname, 'OTA': chn, 'Ch Code': ch,
                                'PMS Rate ID': rt['raw'], 'Room Type': rt['roomType'], 'Rate Plan': rt['rateCode'],
                                'OBP (raw)': str(obp), 'Bad Values': ', '.join(f'Occ {k}: {v}' for k, v in bad)})

        ok = f"{pid}|{rt['roomType']}"
        if ci.get('max_occ') and ok in occ_map:
            mx   = occ_map[ok]
            kys  = obp_int_keys(obp)
            ext  = [o for o in kys if o > mx]
            mis  = [o for o in range(1, mx + 1) if o not in kys]
            base = {'Property ID': pid, 'Property Name': pname, 'OTA': chn, 'Ch Code': ch,
                    'PMS Rate ID': rt['raw'], 'Room Type': rt['roomType'], 'Rate Plan': rt['rateCode'],
                    'Internal Max Occ': mx, 'OBP Occupancies in SU': ', '.join(str(o) for o in kys)}
            if ext: res['obpoe'].append({**base, 'Should Be Removed': ', '.join(str(o) for o in ext),
                                         'Issue': f'Extra in SU: Occ {", ".join(str(o) for o in ext)} — max occ is {mx}'})
            if mis: res['obpom'].append({**base, 'Needs to be Added': ', '.join(str(o) for o in mis),
                                         'Issue': f'Missing in SU: Occ {", ".join(str(o) for o in mis)} — max occ is {mx}'})

        if dash:
            cs = dash.get(pid)
            if cs and not cs.get(ch):
                res['chdead'].append({'Property ID': pid, 'Property Name': pname, 'OTA': chn, 'Ch Code': ch,
                                      'PMS Rate ID': rt['raw'], 'Room Type': rt['roomType'], 'Rate Plan': rt['rateCode'],
                                      'Internal Max Occ': occ_map.get(ok, ''),
                                      'Issue': f'Mapped in SU but {chn} (ch {ch}) is not Live'})

        rk = f"{pid}|{rt['roomType']}|{rt['rateCode']}"
        ck = f"{ch}|{rk}"
        su_rp.add(ck); su_raw[ck] = {'raw': rt['raw'], 'ch_name': chn, 'pname': pname}
        sk = f"{pid}|{rt['roomType']}"
        if rt['suffix'] and sk not in sfxs: sfxs[sk] = rt['suffix']

    for k in rp_set:
        pid, rt_id, rc = k.split('|')
        for ch_obj in CH_MAP:
            if ch_obj['code'] == YATRA: continue
            if dash:
                cs = dash.get(pid)
                if cs and not cs.get(ch_obj['code']): continue
            if f"{ch_obj['code']}|{pid}|{rt_id}|{rc}" not in su_rp:
                sfx = sfxs.get(f"{pid}|{rt_id}", '')
                e = {'Property ID': pid, 'Property Name': names.get(pid, ''), 'OTA': ch_obj['name'],
                     'Ch Code': ch_obj['code'], 'Room Type ID': rt_id, 'Rate Plan Code': rc,
                     'PMS Rate ID': f"{pid}-{rt_id}-{rc}-{sfx}" if sfx else f"{pid}-{rt_id}-{rc}",
                     'Internal Max Occ': occ_map.get(f"{pid}|{rt_id}", ''), 'Issue': 'In CRS but not pushed to SU'}
                rcu = rc.upper()
                if rcu in ('EP', 'CP'): res['rpmicp'].append(e)
                elif rcu in ('MAP', 'AP'): res['rpmimap'].append(e)
                else: res['rpmi'].append(e)

    for ck in su_rp:
        ch, pid, rt_id, rc = ck.split('|', 3)
        if pid not in prop_set: continue
        if f"{pid}|{rt_id}|{rc}" not in rp_set:
            d = su_raw.get(ck, {})
            res['rpex'].append({'Property ID': pid, 'Property Name': d.get('pname', names.get(pid, '')),
                                'OTA': d.get('ch_name', ch), 'Ch Code': ch,
                                'PMS Rate ID': d.get('raw', f"{pid}-{rt_id}-{rc}"),
                                'Room Type ID': rt_id, 'Rate Plan Code': rc,
                                'Internal Max Occ': occ_map.get(f"{pid}|{rt_id}", ''),
                                'Issue': 'In SU but not in CRS'})

    for prop_id, cs in dash.items():
        if prop_id not in prop_set: continue
        for ch_obj in CH_MAP:
            if cs.get(ch_obj['code']) and f"{prop_id}|{ch_obj['code']}" not in su_ch:
                res['chlive'].append({'Property ID': prop_id, 'Property Name': names.get(prop_id, ''),
                                      'OTA': ch_obj['name'], 'Ch Code': ch_obj['code'],
                                      'Issue': f'{ch_obj["name"]} is Live but no SU mapping'})

    res['_meta'] = {'crs_props': len(prop_set), 'su_excluded': excl,
                    'total_analyzed': analyzed, 'occ_map_size': len(occ_map), 'max_occ_col': ci.get('max_occ')}
    return res

# ── UI helper ──────────────────────────────────────────────────────────────────

def show_table(data, key):
    if not data:
        st.success("✅ No issues found.")
        return
    df = pd.DataFrame(data)
    q = st.text_input("Search", key=f"q_{key}", placeholder="Filter rows…", label_visibility="collapsed")
    if q:
        mask = df.apply(lambda r: r.astype(str).str.contains(q, case=False, regex=False).any(), axis=1)
        df = df[mask]
    st.caption(f"{len(df):,} row(s)")
    st.dataframe(df, use_container_width=True, height=400)
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    st.download_button("⬇️ Download", buf.getvalue(), file_name=f"{key}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key=f"dl_{key}")

# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("""
    <div style="padding:20px 16px 8px;">
      <div style="font-size:11px;font-weight:700;text-transform:uppercase;
                  letter-spacing:1.2px;color:#3b82f6;margin-bottom:4px;">FabHotels</div>
      <div style="font-size:15px;font-weight:700;color:#f1f5f9;line-height:1.2;">Revenue Tools</div>
    </div>
    <div class="sb-divider"></div>
    <div style="padding:0 8px 6px;">
      <div class="sb-label" style="padding:0 8px 8px;">Tools</div>
    </div>
    """, unsafe_allow_html=True)

    page = st.radio(
        "page",
        options=["📊 Mapping Checker", "🕐 Last Checked"],
        label_visibility="collapsed",
        key="page_nav",
    )

    st.markdown("""
    <style>
    [data-testid="stSidebar"] .stRadio > div { gap: 2px !important; }
    [data-testid="stSidebar"] .stRadio label {
        background: transparent; border-radius: 6px;
        padding: 7px 10px; cursor: pointer;
        color: #94a3b8 !important; font-size: 13px !important; font-weight: 500 !important;
        display: flex; align-items: center;
    }
    [data-testid="stSidebar"] .stRadio label:has(input:checked) {
        background: #1e293b !important; color: #f1f5f9 !important;
    }
    [data-testid="stSidebar"] .stRadio [data-testid="stMarkdownContainer"] p { color: inherit !important; }
    </style>
    """, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Last Checked
# ══════════════════════════════════════════════════════════════════════════════
if page == "🕐 Last Checked":
    st.markdown('<p class="pg-title">Last Checked</p>'
                '<p class="pg-sub">History of all check runs — visible to everyone with access</p>',
                unsafe_allow_html=True)
    st.divider()

    if st.button("🔄 Refresh", key="refresh_log"):
        fetch_run_log.clear()

    with st.spinner("Loading run history…"):
        try:
            log_df = fetch_run_log()
        except Exception as e:
            st.error(f"Could not load history: {e}")
            st.stop()

    if log_df.empty:
        st.info("No runs logged yet. Run the Mapping Checker and save a log first.")
    else:
        log_df = log_df.iloc[::-1].reset_index(drop=True)   # newest first
        st.caption(f"{len(log_df)} run(s) recorded")
        st.dataframe(log_df, use_container_width=True, hide_index=True, height=500)

        buf = io.BytesIO()
        log_df.to_excel(buf, index=False, engine="openpyxl")
        st.download_button("⬇️ Download History", buf.getvalue(),
                           file_name="check_history.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    st.stop()

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Mapping Checker
# ══════════════════════════════════════════════════════════════════════════════

# ── Header ────────────────────────────────────────────────────────────────────
hc1, hc2 = st.columns([6, 1])
with hc1:
    st.markdown('<p class="pg-title">Mapping Checker</p>'
                '<p class="pg-sub">Validates SU channel manager data against CRS &amp; Prop Level Dashboard</p>',
                unsafe_allow_html=True)
with hc2:
    st.markdown('<div style="text-align:right;padding-top:6px;">'
                '<span class="pg-badge">FabHotels Internal</span></div>', unsafe_allow_html=True)

st.divider()

# ── Step 1 + 2: Upload & Fetch (same row) ─────────────────────────────────────
st.markdown('<div class="step-pill"><span class="step-num">1</span> Data Sources</div>',
            unsafe_allow_html=True)

col_up, col_crs, col_dash = st.columns([3, 2, 2])

with col_up:
    uploaded = st.file_uploader("SU Export file", type=["xlsx", "xls", "csv"],
                                 label_visibility="collapsed",
                                 help="Upload SU channel manager Excel export — all sheets combined automatically")
    if uploaded:
        try:
            with st.spinner("Reading…"):
                su_df, sheets = read_su_file(uploaded)
            st.session_state['su_df'] = su_df
            st.success(f"**{len(su_df):,} rows** · {len(sheets)} sheet(s)")
        except Exception as e:
            st.error(str(e))

with col_crs:
    st.caption("CRS Data (Google Sheet)")
    if st.button("🔄 Fetch CRS", use_container_width=True):
        fetch_crs.clear()
        try:
            with st.spinner("Fetching…"):
                _crs = fetch_crs()
            st.session_state['crs_df'] = _crs
            st.session_state.pop('crs_err', None)
        except Exception as e:
            st.session_state['crs_err'] = str(e)
    if 'crs_df' in st.session_state:
        d = st.session_state['crs_df']
        st.success(f"**{len(d):,} rows** · {len(d.columns)} cols")
    elif 'crs_err' in st.session_state:
        st.error(st.session_state['crs_err'])

with col_dash:
    st.caption("Prop Level Dashboard (optional)")
    if st.button("🔄 Fetch Dashboard", use_container_width=True):
        fetch_dashboard.clear()
        try:
            with st.spinner("Fetching…"):
                _dash = fetch_dashboard()
            st.session_state['dash_raw'] = _dash
            st.session_state.pop('dash_err', None)
        except Exception as e:
            st.session_state['dash_err'] = str(e)
    if 'dash_raw' in st.session_state:
        st.success(f"**{len(st.session_state['dash_raw']) - 1:,} properties** loaded")
    elif 'dash_err' in st.session_state:
        st.warning(st.session_state['dash_err'])

su_df    = st.session_state.get('su_df')
crs_df   = st.session_state.get('crs_df')
dash_raw = st.session_state.get('dash_raw')

if su_df is None or crs_df is None:
    st.info("Upload the SU file and fetch CRS data to continue.")
    st.stop()

su_cols  = list(su_df.columns)
crs_cols = list(crs_df.columns)

# ── Step 3: Column Mapping ─────────────────────────────────────────────────────
st.markdown('<div class="step-pill"><span class="step-num">2</span> Column Mapping</div>',
            unsafe_allow_html=True)

with st.expander("SU File Columns", expanded=True):
    a, b, c, d, e, f = st.columns(6)
    with a: su_room_id    = st.selectbox("PMS Room ID",    su_cols, index=pick(su_cols, ['pms room'], ['room id'], ['roomid']))
    with b: su_rate_id    = st.selectbox("PMS Rate ID",    su_cols, index=pick(su_cols, ['pms rate'], ['rate id'], ['rateid']))
    with c: su_obp        = st.selectbox("OBP Multiplier", su_cols, index=pick(su_cols, ['obp'], ['multiplier'], ['occ']))
    with d: su_channel    = st.selectbox("Channel Code",   [None]+su_cols, index=pick_opt(su_cols, ['channel'], ['ota']))
    with e: su_prop_name  = st.selectbox("Property Name",  [None]+su_cols, index=pick_opt(su_cols, ['property name'], ['hotel name'], ['name']))
    with f: su_app_guests = st.selectbox("Applicable Guests", [None]+su_cols, index=pick_opt(su_cols, ['applicable guests'], ['applicable_guests'], ['appguests']))

with st.expander("CRS Columns", expanded=True):
    a, b, c, d, e = st.columns(5)
    with a: crs_prop_id   = st.selectbox("Property ID",    crs_cols, index=pick(crs_cols, ['property id'], ['prop id'], ['hotel id'], ['property_id']))
    with b: crs_room_type = st.selectbox("Room Type ID",   crs_cols, index=pick(crs_cols, ['room type'], ['room_type'], ['roomtype']))
    with c: crs_rate_code = st.selectbox("Rate Plan Code", crs_cols, index=pick(crs_cols, ['rate plan'], ['rate code'], ['rate_plan'], ['ratecode'], ['rate']))
    with d: crs_max_occ   = st.selectbox("Max Occupancy",  [None]+crs_cols,
                                          index=pick_opt(crs_cols, ['max occ'], ['max_occ'], ['max occupancy'],
                                                         ['maximum occupancy'], ['maxocc'], ['occupancy'], ['pax'], ['max pax']))
    with e: crs_is_active = st.selectbox("Active Filter",  [None]+crs_cols,
                                          index=pick_opt(crs_cols, ['is_active'], ['is active'], ['active'], ['status']))

col_cfg = {
    'su':  {'room_id': su_room_id, 'rate_id': su_rate_id, 'obp': su_obp,
             'prop_name': su_prop_name, 'channel': su_channel, 'app_guests': su_app_guests},
    'int': {'prop_id': crs_prop_id, 'room_type': crs_room_type, 'rate_code': crs_rate_code,
             'max_occ': crs_max_occ, 'is_active': crs_is_active},
}

with st.expander("🔬 OBP Parse Debug", expanded=False):
    st.caption("Verify OBP values are being parsed. Key count should be > 0.")
    rows = []
    for _, r in su_df.head(8).iterrows():
        raw = r.get(su_obp, '')
        parsed = parse_obp(raw)
        rows.append({'OBP Raw Value': str(raw)[:60], 'Parsed Keys': str(list(parsed.keys())), 'Key count': len(parsed)})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption(f"Max Occ column → **{crs_max_occ}** · Active filter → **{crs_is_active}**")

# ── Step 4: Run ────────────────────────────────────────────────────────────────
st.markdown('<div class="step-pill"><span class="step-num">3</span> Run</div>',
            unsafe_allow_html=True)

rc1, rc2 = st.columns([2, 5])
with rc1:
    run = st.button("🚀 Run All Checks", type="primary", use_container_width=True)
with rc2:
    if not crs_max_occ:
        st.warning("No Max Occupancy column selected — OBP Extra/Missing checks will not run.")

if run:
    with st.spinner("Running checks…"):
        results = run_checks(su_df, crs_df, dash_raw, col_cfg)
    st.session_state['results'] = results
    st.rerun()

# ── Results ────────────────────────────────────────────────────────────────────
if 'results' not in st.session_state:
    st.stop()

res  = st.session_state['results']
meta = res['_meta']

st.divider()

m1, m2, m3, m4 = st.columns(4)
m1.metric("CRS Properties",        f"{meta['crs_props']:,}")
m2.metric("SU Rows Analyzed",      f"{meta['total_analyzed']:,}")
m3.metric("Excluded (not in CRS)", f"{meta['su_excluded']:,}")
m4.metric("OCC Map Entries",       f"{meta['occ_map_size']:,}")

CHECKS = [
    ('rr',      "Room-Rate Mismatch",    "Room type in PMS Room ID ≠ PMS Rate ID"),
    ('apg',     "Applicable Guests",     "Non-ch 97 channel has value in Applicable Guests"),
    ('obpv',    "OBP Multiplier ≠ 1",    "Multiplier value is not 1"),
    ('obpoe',   "OBP Extra Occ",         "OBP occupancy > CRS max occ — needs removal"),
    ('obpom',   "OBP Missing Occ",       "OBP occupancy < CRS max occ — needs to be added"),
    ('rpmicp',  "Missing — EP/CP",       "EP or CP in CRS not pushed to SU"),
    ('rpmimap', "Missing — MAP/AP",      "MAP or AP in CRS not pushed to SU"),
    ('rpmi',    "Missing — Other",       "Other rate plans in CRS not pushed to SU"),
    ('rpex',    "Extra in SU",           "Rate plan in SU not found in CRS"),
    ('chlive',  "OTA Live No Mapping",   "OTA is Live but no SU mapping exists"),
    ('chdead',  "Mapped OTA Not Live",   "SU mapping exists but OTA is not Live"),
    ('ncrs',    "Not in CRS",            "SU rows excluded — property not in CRS"),
]

def _icon(k, n):
    if k == 'ncrs': return '⚫'
    return '🔴' if n > 0 else '🟢'

tab_labels = [f"{_icon(k, len(res.get(k,[])))} {lbl} ({len(res.get(k,[]))})" for k, lbl, _ in CHECKS]
tabs = st.tabs(tab_labels)

for i, (k, lbl, desc) in enumerate(CHECKS):
    with tabs[i]:
        st.caption(desc)
        show_table(res.get(k, []), k)

st.divider()

lc1, lc2 = st.columns([3, 4])
with lc1:
    run_by = st.text_input("Your name (for log)", placeholder="e.g. Praveen", label_visibility="collapsed",
                            key="run_by_name")
    if st.button("💾 Save this run to Last Checked log", use_container_width=True):
        try:
            counts = {k: len(res.get(k, [])) for k, _, _ in CHECKS}
            save_run_log(meta, counts, run_by=run_by or 'anonymous')
            fetch_run_log.clear()
            st.success("Run saved — visible to all users in Last Checked.")
        except Exception as e:
            st.error(f"Could not save log: {e}")

if st.button("📥 Export All to Excel"):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for k, lbl, _ in CHECKS:
            rows = res.get(k, [])
            if rows:
                pd.DataFrame(rows).to_excel(writer, sheet_name=lbl[:31], index=False)
    st.download_button("⬇️ Download Full Report", buf.getvalue(), file_name="su_mapping_report.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
