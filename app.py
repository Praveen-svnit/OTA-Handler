import streamlit as st
import pandas as pd
import json, ast, re, io

from sheets import (
    fetch_crs, fetch_dashboard, save_run, fetch_log, fetch_details,
    fetch_bcom, fetch_bcom_tab, fetch_bcom_tabs,
    fetch_gommt, fetch_gommt_tab, fetch_gommt_tabs,
    fetch_listing,
)

st.set_page_config(page_title="SU Mapping Checker", layout="wide", page_icon="🔍",
                   initial_sidebar_state="expanded")

# ── CSS — clean professional SaaS theme ───────────────────────────────────────
st.markdown("""
<style>
/* ── Foundation ─────────────────────────────────────────────────────────────── */
html, body, [class*="css"], button, input, select, textarea {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif !important;
  -webkit-font-smoothing: antialiased;
  letter-spacing: -0.005em;
}
body, .stApp { background: #ffffff; color: #18181b; }

/* Hide all Streamlit chrome — clean canvas */
#MainMenu, footer, header { display: none !important; }
[data-testid="stDecoration"], [data-testid="stSidebarNav"], [data-testid="stToolbar"] { display: none !important; }

/* Main container — generous, presentation-ready */
.block-container {
  padding: 1.75rem 2.5rem 2.5rem !important;
  max-width: 1320px !important;
}

/* ── Sidebar (light, professional) ──────────────────────────────────────────── */
[data-testid="stSidebar"] {
  background: #fafafa !important;
  border-right: 1px solid #e4e4e7 !important;
}
[data-testid="stSidebar"] > div:first-child { padding-top: 0 !important; }

/* Sidebar nav (radio) */
[data-testid="stSidebar"] .stRadio > div { gap: 1px !important; padding: 0 10px; }
[data-testid="stSidebar"] .stRadio label {
  border-radius: 6px;
  padding: 8px 12px;
  cursor: pointer;
  color: #52525b !important;
  font-size: 13px !important;
  font-weight: 500 !important;
  transition: all 0.15s;
}
[data-testid="stSidebar"] .stRadio label:hover { background: #f4f4f5 !important; color: #18181b !important; }
[data-testid="stSidebar"] .stRadio label:has(input:checked) {
  background: #18181b !important; color: #ffffff !important; font-weight: 600 !important;
}
/* Hide the actual radio circle */
[data-testid="stSidebar"] .stRadio [role="radio"] { display: none !important; }

/* Sidebar collapse/expand toggles */
[data-testid="stSidebarCollapsedControl"],
[data-testid="collapsedControl"],
[data-testid="stExpandSidebarButton"] {
  background: #f4f4f5 !important;
  border: 1px solid #e4e4e7 !important;
  border-radius: 6px !important;
  padding: 6px !important;
}
[data-testid="stSidebarCollapsedControl"] svg,
[data-testid="collapsedControl"] svg,
[data-testid="stExpandSidebarButton"] svg,
[data-testid="stSidebarCollapseButton"] svg,
[data-testid="baseButton-headerNoPadding"] svg {
  width: 18px !important; height: 18px !important; color: #52525b !important;
}

/* ── Typography ─────────────────────────────────────────────────────────────── */
h1, h2 { font-weight: 600 !important; letter-spacing: -0.025em !important; color: #18181b !important; }
h2 { font-size: 18px !important; margin: 0 0 4px !important; }
h3 { font-size: 14px !important; font-weight: 600 !important; color: #27272a !important; margin: 8px 0 4px !important; }
.stCaption p, [data-testid="stCaptionContainer"] p {
  font-size: 12px !important; color: #71717a !important; font-weight: 400 !important;
}
label p { font-size: 12px !important; color: #3f3f46 !important; font-weight: 500 !important; }

/* ── Metrics (clean cards) ──────────────────────────────────────────────────── */
[data-testid="stMetric"] {
  background: #ffffff !important;
  border: 1px solid #e4e4e7 !important;
  border-radius: 8px !important;
  padding: 12px 16px !important;
  box-shadow: none !important;
}
[data-testid="stMetricLabel"] p { font-size: 11px !important; color: #71717a !important; font-weight: 500 !important; }
[data-testid="stMetricValue"]   { font-size: 24px !important; font-weight: 600 !important; color: #18181b !important; letter-spacing: -0.02em !important; }
[data-testid="stMetricDelta"]   { font-size: 11px !important; }

/* ── Tabs (Vercel-style underline) ──────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
  gap: 0 !important;
  border-bottom: 1px solid #e4e4e7 !important;
  overflow-x: auto;
  flex-wrap: nowrap;
}
.stTabs [data-baseweb="tab"] {
  font-size: 13px !important;
  padding: 8px 16px !important;
  white-space: nowrap;
  font-weight: 500 !important;
  color: #71717a !important;
  border-bottom: 2px solid transparent !important;
  margin-bottom: -1px !important;
}
.stTabs [data-baseweb="tab"][aria-selected="true"] {
  color: #18181b !important;
  border-bottom: 2px solid #18181b !important;
  font-weight: 600 !important;
}
.stTabs [data-baseweb="tab-highlight"] { display: none !important; }

/* ── Buttons ────────────────────────────────────────────────────────────────── */
.stButton button, .stDownloadButton button {
  background: #ffffff !important;
  color: #18181b !important;
  border: 1px solid #e4e4e7 !important;
  border-radius: 6px !important;
  padding: 6px 14px !important;
  font-size: 13px !important;
  font-weight: 500 !important;
  box-shadow: none !important;
  transition: all 0.15s !important;
}
.stButton button:hover, .stDownloadButton button:hover {
  background: #f4f4f5 !important;
  border-color: #d4d4d8 !important;
}
.stButton button[kind="primary"] {
  background: #18181b !important;
  color: #ffffff !important;
  border-color: #18181b !important;
}
.stButton button[kind="primary"]:hover { background: #27272a !important; border-color: #27272a !important; }

/* ── Inputs / selects ───────────────────────────────────────────────────────── */
[data-baseweb="select"] > div, [data-baseweb="input"] {
  background: #ffffff !important;
  border: 1px solid #e4e4e7 !important;
  border-radius: 6px !important;
  min-height: 36px !important;
  font-size: 13px !important;
}
[data-baseweb="select"] > div:hover, [data-baseweb="input"]:hover { border-color: #d4d4d8 !important; }
[data-baseweb="select"] [role="combobox"] { font-size: 13px !important; }

/* ── Tags (multiselect chips) ────────────────────────────────────────────────── */
[data-baseweb="tag"] {
  background: #f4f4f5 !important;
  color: #18181b !important;
  border-radius: 4px !important;
  font-size: 12px !important;
  font-weight: 500 !important;
}

/* ── Expanders ──────────────────────────────────────────────────────────────── */
[data-testid="stExpander"] {
  border: 1px solid #e4e4e7 !important;
  border-radius: 8px !important;
  background: #ffffff !important;
  margin-bottom: 8px !important;
  box-shadow: none !important;
}
[data-testid="stExpander"] summary { padding: 10px 14px !important; font-size: 13px !important; font-weight: 500 !important; }
[data-testid="stExpander"] summary p { font-size: 13px !important; }

/* ── Alerts (minimal, no shouting) ──────────────────────────────────────────── */
[data-testid="stAlert"] {
  padding: 10px 14px !important;
  border-radius: 6px !important;
  border: 1px solid #e4e4e7 !important;
  background: #fafafa !important;
}
[data-testid="stAlert"] p { font-size: 12px !important; margin: 0 !important; color: #3f3f46 !important; }
[data-testid="stAlert"][kind="error"] { background: #fef2f2 !important; border-color: #fecaca !important; }
[data-testid="stAlert"][kind="error"] p { color: #991b1b !important; }
[data-testid="stAlert"][kind="warning"] { background: #fffbeb !important; border-color: #fde68a !important; }
[data-testid="stAlert"][kind="warning"] p { color: #92400e !important; }
[data-testid="stAlert"][kind="success"] { background: #f0fdf4 !important; border-color: #bbf7d0 !important; }
[data-testid="stAlert"][kind="success"] p { color: #166534 !important; }

/* ── DataFrame ──────────────────────────────────────────────────────────────── */
[data-testid="stDataFrame"] {
  border: 1px solid #e4e4e7 !important;
  border-radius: 8px !important;
  overflow: hidden !important;
}

/* ── Divider ────────────────────────────────────────────────────────────────── */
hr { margin: 16px 0 !important; border: none !important; border-top: 1px solid #e4e4e7 !important; }

/* Reduce excessive vertical gap from Streamlit's default block spacing */
[data-testid="stVerticalBlock"] > [data-testid="stVerticalBlock"] { gap: 0.5rem !important; }
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
CH_NAME    = {c['code']: c['name'] for c in CH_MAP}
OTA_OPTIONS = ['Booking.com', 'MakeMyTrip', 'Agoda', 'EMT', 'CT', 'Expedia']

CHECKS = [
    ('rr',      'Room-Rate Mismatch',   'Room type in PMS Room ID ≠ PMS Rate ID'),
    ('apg',     'Applicable Guests',    'Non-ch 97 channel has a value in Applicable Guests'),
    ('obpv',    'OBP Multiplier ≠ 1',   'Multiplier value is not 1'),
    ('obpoe',   'OBP Extra Occ',        'OBP occupancy > CRS max occ — needs removal'),
    ('obpom',   'OBP Missing Occ',      'OBP occupancy < CRS max occ — needs to be added'),
    ('rpmicp',  'Missing — EP/CP',      'EP or CP in CRS not pushed to SU'),
    ('rpmimap', 'Missing — MAP/AP',     'MAP or AP in CRS not pushed to SU'),
    ('rpmi',    'Missing — Other',      'Other rate plans in CRS not pushed to SU'),
    ('rpex',    'Extra in SU',          'Rate plan in SU not found in CRS'),
    ('chlive',  'OTA Live No Mapping',  'OTA is Live but no SU mapping'),
    ('chdead',  'Mapped OTA Not Live',  'SU mapping exists but OTA not Live'),
    ('ncrs',    'Not in CRS',           'SU rows excluded — property not in CRS'),
]

# ── Utilities ──────────────────────────────────────────────────────────────────

def norm_id(v):
    return re.sub(r'\.0+$', '', str(v if v is not None else '').strip())

def parse_room(val):
    p = str(val or '').split('-')
    return {'propId': norm_id(p[0]) if p else '', 'roomType': norm_id(p[1]) if len(p) > 1 else '', 'raw': str(val or '')}

def parse_rate(val):
    p = str(val or '').split('-')
    return {'propId':   norm_id(p[0]) if p else '',
            'roomType': norm_id(p[1]) if len(p) > 1 else '',
            'rateCode': norm_id(p[2]) if len(p) > 2 else '',
            'suffix':   '-'.join(p[3:]) if len(p) > 3 else '',
            'raw':      str(val or '')}

def parse_obp(val):
    if val is None: return {}
    s = str(val).strip()
    if s in ('', 'nan', 'None', 'NaN', '{}'): return {}
    for parser in (json.loads, ast.literal_eval):
        try:
            obj = parser(s)
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

def auto_detect(cols, *groups):
    for hints in groups:
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

def read_file(uploaded):
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
    raise Exception("Could not read file — try saving as .xlsx and re-uploading.")

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
    prop_set = set(); rp_set = set(); occ_map = {}

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
    res  = {k: [] for k, _, _ in CHECKS}

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
            res['ncrs'].append({'Property ID': pid or '(empty)', 'Property Name': pname,
                                'Channel': ch, 'PMS Room ID': rm['raw'], 'PMS Rate ID': rt['raw'],
                                'Reason': 'Not found in CRS'})
            continue

        is_yatra = (ch == YATRA)
        if ch and pid: su_ch.add(f"{pid}|{ch}")
        if pname and pid not in names: names[pid] = pname

        if su.get('app_guests') and not is_yatra and ag:
            res['apg'].append({'Property ID': pid, 'Property Name': pname, 'OTA': chn, 'Ch Code': ch,
                               'PMS Rate ID': rt['raw'], 'Rate Plan': rt['rateCode'],
                               'Applicable Guests Value': ag,
                               'Issue': f'Ch {ch} has "{ag}" in Applicable Guests — only ch {YATRA} (Yatra) should use this'})

        if is_yatra: continue
        analyzed += 1

        if rm['roomType'] != rt['roomType']:
            res['rr'].append({'Property ID': pid, 'Property Name': pname, 'OTA': chn, 'Ch Code': ch,
                              'PMS Room ID': rm['raw'], 'Room Type (Room)': rm['roomType'],
                              'PMS Rate ID': rt['raw'], 'Room Type (Rate)': rt['roomType'],
                              'Rate Plan': rt['rateCode'],
                              'Issue': f'Room type "{rm["roomType"]}" ≠ "{rt["roomType"]}"'})

        bad = [(k, v) for k, v in obp.items() if not_one(v)]
        if bad:
            res['obpv'].append({'Property ID': pid, 'Property Name': pname, 'OTA': chn, 'Ch Code': ch,
                                'PMS Rate ID': rt['raw'], 'Room Type': rt['roomType'], 'Rate Plan': rt['rateCode'],
                                'OBP (raw)': str(obp), 'Bad Values': ', '.join(f'Occ {k}: {v}' for k, v in bad)})

        ok = f"{pid}|{rt['roomType']}"
        if ci.get('max_occ') and ok in occ_map:
            mx  = occ_map[ok]; kys = obp_int_keys(obp)
            ext = [o for o in kys if o > mx]
            mis = [o for o in range(1, mx + 1) if o not in kys]
            base = {'Property ID': pid, 'Property Name': pname, 'OTA': chn, 'Ch Code': ch,
                    'PMS Rate ID': rt['raw'], 'Room Type': rt['roomType'], 'Rate Plan': rt['rateCode'],
                    'Internal Max Occ': mx, 'OBP Occupancies in SU': ', '.join(str(o) for o in kys)}
            if ext: res['obpoe'].append({**base, 'Should Be Removed': ', '.join(str(o) for o in ext),
                                         'Issue': f'Extra: Occ {", ".join(str(o) for o in ext)} — max is {mx}'})
            if mis: res['obpom'].append({**base, 'Needs to be Added': ', '.join(str(o) for o in mis),
                                         'Issue': f'Missing: Occ {", ".join(str(o) for o in mis)} — max is {mx}'})

        if dash:
            cs = dash.get(pid)
            if cs and not cs.get(ch):
                res['chdead'].append({'Property ID': pid, 'Property Name': pname, 'OTA': chn, 'Ch Code': ch,
                                      'PMS Rate ID': rt['raw'], 'Room Type': rt['roomType'], 'Rate Plan': rt['rateCode'],
                                      'Internal Max Occ': occ_map.get(ok, ''),
                                      'Issue': f'Mapped in SU but {chn} (ch {ch}) not Live'})

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
                e = {'Property ID': pid, 'Property Name': names.get(pid, ''),
                     'OTA': ch_obj['name'], 'Ch Code': ch_obj['code'],
                     'Room Type ID': rt_id, 'Rate Plan Code': rc,
                     'PMS Rate ID': f"{pid}-{rt_id}-{rc}-{sfx}" if sfx else f"{pid}-{rt_id}-{rc}",
                     'Internal Max Occ': occ_map.get(f"{pid}|{rt_id}", ''),
                     'Issue': 'In CRS but not pushed to SU'}
                rcu = rc.upper()
                if rcu in ('EP','CP'):    res['rpmicp'].append(e)
                elif rcu in ('MAP','AP'): res['rpmimap'].append(e)
                else:                      res['rpmi'].append(e)

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
                    'total_analyzed': analyzed, 'occ_map_size': len(occ_map),
                    'max_occ_col': ci.get('max_occ')}
    return res

# ── UI helpers ─────────────────────────────────────────────────────────────────

def show_table(data, key):
    if not data:
        st.success('✅ No issues found.')
        return
    df = pd.DataFrame(data)
    q = st.text_input('Search', key=f'q_{key}', placeholder='Filter rows…', label_visibility='collapsed')
    if q:
        mask = df.apply(lambda r: r.astype(str).str.contains(q, case=False, regex=False).any(), axis=1)
        df = df[mask]
    st.caption(f'{len(df):,} row(s)')
    st.dataframe(df, use_container_width=True, height=400, hide_index=True)
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine='openpyxl')
    st.download_button('⬇️ Download', buf.getvalue(), file_name=f'{key}.xlsx',
                       mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                       key=f'dl_{key}')

def section(label):
    st.markdown(f'<p style="font-size:11px;font-weight:700;text-transform:uppercase;'
                f'letter-spacing:.6px;color:#94a3b8;margin:16px 0 6px">{label}</p>',
                unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("""
    <div style="padding:22px 18px 4px">
      <div style="font-size:10px;font-weight:600;text-transform:uppercase;
                  letter-spacing:.08em;color:#71717a;margin-bottom:2px">FabHotels</div>
      <div style="font-size:15px;font-weight:600;color:#18181b;letter-spacing:-0.01em">Revenue Tools</div>
    </div>
    <div style="height:1px;background:#e4e4e7;margin:14px 0 10px"></div>
    """, unsafe_allow_html=True)

    page = st.radio('nav',
                    ['Booking.com', 'GoMMT', 'Listing Tracker',
                     'Mapping Checker', 'Last Checked'],
                    label_visibility='collapsed')

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: LAST CHECKED
# ══════════════════════════════════════════════════════════════════════════════
if page == 'Last Checked':
    st.markdown('## Last Checked')
    st.caption('Full results of every saved run — shared across all users')
    st.divider()

    c1, c2 = st.columns([1, 5])
    with c1:
        if st.button('🔄 Refresh', use_container_width=True):
            fetch_log.clear(); fetch_details.clear()

    try:
        log_df     = fetch_log()
        detail_df  = fetch_details()
    except Exception as e:
        st.error(f'Could not load data: {e}')
        st.stop()

    section('Run History (summary)')
    if log_df.empty:
        st.info('No runs saved yet. Run the Mapping Checker and click Save.')
    else:
        st.dataframe(log_df.iloc[::-1].reset_index(drop=True),
                     use_container_width=True, hide_index=True, height=220)

    section('Last Saved Run — Full Details')
    if detail_df.empty:
        st.info('No detailed results saved yet.')
    else:
        check_types = ['All'] + sorted(detail_df['Check'].unique().tolist()) if 'Check' in detail_df.columns else ['All']
        chosen = st.selectbox('Filter by check type', check_types, key='lc_filter')
        df = detail_df if chosen == 'All' else detail_df[detail_df['Check'] == chosen]

        q = st.text_input('Search details', placeholder='Property ID, OTA, issue…',
                          key='lc_search', label_visibility='collapsed')
        if q:
            mask = df.apply(lambda r: r.astype(str).str.contains(q, case=False, regex=False).any(), axis=1)
            df = df[mask]

        st.caption(f'{len(df):,} row(s)  ·  Run At: {detail_df["Run At"].iloc[0] if "Run At" in detail_df.columns else "—"}')
        st.dataframe(df, use_container_width=True, hide_index=True, height=480)

        buf = io.BytesIO()
        df.to_excel(buf, index=False, engine='openpyxl')
        st.download_button('⬇️ Download Details', buf.getvalue(),
                           file_name='last_run_details.xlsx',
                           mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    st.stop()

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: CHANNEL (Booking.com / GoMMT)
# ══════════════════════════════════════════════════════════════════════════════

def _render_channel_page(channel_name, prefix, fetch_main, fetch_tabs_fn, fetch_tab_fn, cfg):
    """
    cfg = {
      'fh_status_letter':  'I',     # column letter for FH Status (Churned filter)
      'status_letter':     'E',     # column letter for the channel's main status
      'status_label':      'BDC Live',  # display label
      'sub_status_letter': 'F',     # column letter for Sub Status
    }
    """
    # ── Header ───────────────────────────────────────────────────────────────
    _h1, _h2 = st.columns([7, 1])
    with _h1:
        st.markdown(f'## {channel_name}')
        st.caption('Property status, substatus and hygiene checks')
    with _h2:
        st.write('')
        if st.button('Refresh', use_container_width=True, key=f'{prefix}_refresh'):
            fetch_main.clear()

    try:
        with st.spinner(f'Loading {channel_name} sheet…'):
            bdf = fetch_main()
    except Exception as e:
        st.error(f'Could not load sheet: {e}')
        st.info(f'Make sure the service account has been given Viewer access to the {channel_name} sheet.')
        return

    if bdf.empty:
        st.warning('Sheet returned no data.')
        st.stop()

    # ── Helper: column letter → 0-based index ─────────────────────────────────
    def col_idx(letter):
        letter = letter.upper().strip()
        result = 0
        for ch in letter:
            result = result * 26 + (ord(ch) - ord('A') + 1)
        return result - 1

    def get_col(letter):
        i = col_idx(letter)
        cols = list(bdf.columns)
        return cols[i] if i < len(cols) else None

    # ── Exclusions (cached per channel via prefix + data fingerprint) ────────
    fh_letter = cfg['fh_status_letter']
    fh_idx    = col_idx(fh_letter)

    # Data fingerprint: (row_count, columns_tuple). Changes whenever the sheet
    # gains/loses rows or columns — invalidates the cache so new data shows up.
    _fingerprint = (len(bdf), tuple(bdf.columns))

    @st.cache_data(ttl=3600, show_spinner=False)
    def _apply_exclusions(_bdf, fh_index, cache_key, data_fp):
        cols_all = list(_bdf.columns)
        col_a = cols_all[0] if cols_all else None
        blank_mask = _bdf[col_a].str.strip() == '' if col_a else pd.Series(False, index=_bdf.index)

        fh_col = cols_all[fh_index] if fh_index is not None and fh_index < len(cols_all) else None
        churn_mask = (_bdf[fh_col].str.strip().str.lower() == 'churned'
                      if fh_col else pd.Series(False, index=_bdf.index))

        excl = blank_mask | churn_mask
        filtered = _bdf[~excl].reset_index(drop=True)
        return filtered, int(blank_mask.sum()), int(churn_mask.sum())

    bdf_raw = bdf
    bdf, blank_a_cnt, churn_cnt = _apply_exclusions(bdf, fh_idx, prefix, _fingerprint)
    cols = list(bdf.columns)

    # ── Clean stats row ──────────────────────────────────────────────────────
    _stats = [f'**{len(bdf):,}** active', f'{len(cols)} columns']
    if blank_a_cnt: _stats.append(f'{blank_a_cnt:,} blank Col A excluded')
    if churn_cnt:   _stats.append(f'{churn_cnt:,} churned excluded')
    st.caption(' · '.join(_stats))

    # ── Pre-compute hygiene data (cached — runs once per data fetch) ─────────
    sub_idx = col_idx(cfg['sub_status_letter'])
    sub_status_col_f = cols[sub_idx] if sub_idx < len(cols) else None
    hyg_start = col_idx('N')
    hyg_end   = col_idx('AH') + 1
    base_hyg_cols = cols[hyg_start:hyg_end]

    # Channel-specific exclusion list (e.g., status/category cols mixed in N-AH range)
    _hyg_exclude = {e.strip().lower() for e in cfg.get('hyg_exclude', []) if e}
    if _hyg_exclude:
        base_hyg_cols = [c for c in base_hyg_cols if c.strip().lower() not in _hyg_exclude]

    # Read user customization from session_state (UI lives inside Hygiene tab)
    added   = st.session_state.get(f'{prefix}_hyg_add', [])
    removed = st.session_state.get(f'{prefix}_hyg_remove', [])
    _addable = [c for c in cols if c not in base_hyg_cols]

    # Apply user additions + removals
    hyg_cols = [c for c in base_hyg_cols if c not in set(removed)]
    for c in added:
        if c not in hyg_cols:
            hyg_cols.append(c)

    # Fingerprint for the post-exclusion DataFrame — invalidates this layer
    # whenever the underlying data changes (new col, new row, etc.).
    _fingerprint2 = (len(bdf), tuple(bdf.columns), tuple(hyg_cols))

    @st.cache_data(ttl=3600, show_spinner=False)
    def _build_hyg_data(_bdf, sub_col, h_cols, cache_key, data_fp):
        if sub_col is not None:
            _hyg = _bdf[_bdf[sub_col].str.strip().str.lower() == 'live'].reset_index(drop=True)
        else:
            _hyg = _bdf
        if not h_cols:
            return _hyg, {}, {}, {}
        _stripped = {hc: _hyg[hc].astype(str).str.strip() for hc in h_cols}
        _vcounts  = {hc: _stripped[hc].value_counts(dropna=False) for hc in h_cols}
        _filled   = {hc: int(_stripped[hc].ne('').sum()) for hc in h_cols}
        return _hyg, _stripped, _vcounts, _filled

    bdf_hyg, stripped, hyg_vcounts, hyg_filled = _build_hyg_data(
        bdf, sub_status_col_f, hyg_cols, prefix, _fingerprint2
    )
    hyg_df = bdf_hyg[hyg_cols] if hyg_cols else pd.DataFrame()

    # ── Sub-page tabs ─────────────────────────────────────────────────────────
    _mx_label = '-'.join(cfg.get('matrix_letters', ('E', 'F', 'L', 'M')))
    bcom_tab1, bcom_tab2, bcom_tab3, bcom_tab4 = st.tabs(
        ['📊 Status & Tracker', '🧹 Hygiene Checks', '📋 Value Summaries', f'🗂 {_mx_label} Matrix']
    )

    # Each tab is wrapped in @st.fragment so a click inside one tab does NOT
    # rerun the other three (10× faster click response).
    # The fragment decorator on a closure means the entire body skips re-execution
    # when no Streamlit widget *inside* that fragment changed.

    def _render_tab1():
        section('Status & Substatus Summary')

        # Detect columns — prefer exact names, exclude .N duplicates
        _dup_sfx = tuple(f'.{i}' for i in range(1, 20))
        def _is_dup(c): return c.strip().lower().endswith(_dup_sfx)

        # Default to the channel-configured columns (positional)
        _sub_idx = col_idx(cfg['sub_status_letter'])
        _sta_idx = col_idx(cfg['status_letter'])
        _sub_default = cols[_sub_idx] if _sub_idx < len(cols) else None
        _sta_default = cols[_sta_idx] if _sta_idx < len(cols) else None

        # CLEAN stale session_state: remove values that no longer exist in cols
        for _k, _dflt in ((f'{prefix}_sub_col', _sub_default),
                          (f'{prefix}_stat_col', _sta_default)):
            _v = st.session_state.get(_k)
            if _v is not None and _v not in cols:
                st.session_state.pop(_k, None)

        substatus_col = _sub_default
        status_col    = _sta_default

        with st.expander('⚙️ Column configuration',
                         expanded=(substatus_col is None or status_col is None)):
            cc1, cc2 = st.columns(2)
            with cc1:
                substatus_col = st.selectbox(
                    'Sub Status column', [None] + cols,
                    index=([None] + cols).index(_sub_default) if _sub_default in cols else 0,
                    key=f'{prefix}_sub_col',
                )
            with cc2:
                status_col = st.selectbox(
                    'Status column', [None] + cols,
                    index=([None] + cols).index(_sta_default) if _sta_default in cols else 0,
                    key=f'{prefix}_stat_col',
                )
            if not substatus_col and not status_col:
                st.caption('Columns: ' + ' · '.join(cols[:20]) + (' …' if len(cols) > 20 else ''))

        # Final safety: ensure both columns actually exist in bdf
        if substatus_col not in cols: substatus_col = None
        if status_col    not in cols: status_col    = None

        if substatus_col and status_col:
            # Build pivot keeping ORIGINAL column names (do NOT rename to
            # 'Sub Status' / 'Status' literally — that would break later when
            # group_cols references the original names like 'BDC Live').
            pivot = (
                bdf.assign(
                    **{substatus_col: bdf[substatus_col].astype(str).str.strip(),
                       status_col:    bdf[status_col].astype(str).str.strip()}
                )
                .groupby([substatus_col, status_col], dropna=False)
                .size().reset_index(name='Count')
                .sort_values([substatus_col, 'Count'], ascending=[True, False])
            )

            # ── Auto-fetch tracker comparison ─────────────────────────────────
            try:
                available_tabs = fetch_tabs_fn()
            except Exception:
                available_tabs = []

            # Channel-configured defaults take priority; fall back to keyword search
            _cfg_live    = cfg.get('default_live_tab')
            _cfg_tracker = cfg.get('default_tracker_tab')

            if _cfg_live and _cfg_live in available_tabs:
                _live_default = available_tabs.index(_cfg_live)
            else:
                _live_default = next((i for i, t in enumerate(available_tabs) if 'live' in t.lower()), 0)

            if _cfg_tracker and _cfg_tracker in available_tabs:
                _tracker_default = available_tabs.index(_cfg_tracker)
            else:
                _tracker_default = next((i for i, t in enumerate(available_tabs) if 'tracker' in t.lower()),
                                       min(1, len(available_tabs)-1))

            # User-selected tabs override auto-detected defaults
            _user_live    = st.session_state.get(f'{prefix}_live_tab')
            _user_tracker = st.session_state.get(f'{prefix}_tracker_tab')

            # User-selected ID column indices (default to col A = 0)
            # Defensive cast — older sessions might have stale non-int values
            def _safe_int(v, default=0):
                try:
                    return int(v) if v is not None and v != '' else default
                except (ValueError, TypeError):
                    return default

            _user_live_idx    = _safe_int(st.session_state.get(f'{prefix}_live_id_idx'))
            _user_tracker_idx = _safe_int(st.session_state.get(f'{prefix}_tracker_id_idx'))

            # Auto-run comparison every time (no button needed)
            if available_tabs:
                _live_tab    = _user_live    if _user_live    in available_tabs else available_tabs[_live_default]
                _tracker_tab = _user_tracker if _user_tracker in available_tabs else available_tabs[_tracker_default]
                _cmp_key     = f'{prefix}_cmp_{_live_tab}_{_tracker_tab}_{_user_live_idx}_{_user_tracker_idx}'
                if _cmp_key not in st.session_state:
                    try:
                        with st.spinner('Fetching tracker comparison…'):
                            live_df    = fetch_tab_fn(_live_tab)
                            tracker_df = fetch_tab_fn(_tracker_tab)
                        _lc = list(live_df.columns)
                        _tc = list(tracker_df.columns)
                        if not _lc or not _tc:
                            raise Exception('One of the tabs has no columns / is empty.')
                        _li = max(0, min(int(_user_live_idx),    len(_lc) - 1))
                        _ti = max(0, min(int(_user_tracker_idx), len(_tc) - 1))
                        live_id_col    = _lc[_li]
                        tracker_id_col = _tc[_ti]
                        live_ids    = set(live_df[live_id_col].str.strip().str.lower().replace('', pd.NA).dropna())
                        tracker_ids = set(tracker_df[tracker_id_col].str.strip().str.lower().replace('', pd.NA).dropna())
                        missing_ids = live_ids - tracker_ids
                        st.session_state[_cmp_key]               = True
                        st.session_state[f'{prefix}_missing_ids']     = missing_ids
                        st.session_state[f'{prefix}_live_ids']        = live_ids
                        st.session_state[f'{prefix}_tracker_ids']     = tracker_ids
                        st.session_state[f'{prefix}_live_df']         = live_df
                        st.session_state[f'{prefix}_tracker_df']      = tracker_df
                        st.session_state[f'{prefix}_live_id_col']     = live_id_col
                        st.session_state[f'{prefix}_tracker_id_col']  = tracker_id_col
                        st.session_state[f'{prefix}_live_tab_used']   = _live_tab
                        st.session_state[f'{prefix}_tracker_tab_used'] = _tracker_tab
                    except Exception as e:
                        st.session_state[_cmp_key] = False
                        st.warning(f'Tracker comparison failed: {e}')

            missing_ids   = st.session_state.get(f'{prefix}_missing_ids')
            live_df_s     = st.session_state.get(f'{prefix}_live_df')
            live_id_col_s = st.session_state.get(f'{prefix}_live_id_col')

            display_pivot = pivot.copy()
            if missing_ids is not None and live_df_s is not None:
                live_missing = live_df_s[live_df_s[live_id_col_s].str.strip().str.lower().isin(missing_ids)].copy()
                if substatus_col in live_missing.columns and status_col in live_missing.columns:
                    miss_grp = (
                        live_missing.assign(
                            **{substatus_col: live_missing[substatus_col].astype(str).str.strip(),
                               status_col:    live_missing[status_col].astype(str).str.strip()}
                        )
                        .groupby([substatus_col, status_col], dropna=False)
                        .size().reset_index(name='Missing from Tracker')
                    )
                    display_pivot = display_pivot.merge(
                        miss_grp, on=[substatus_col, status_col], how='left',
                    )
                    display_pivot['Missing from Tracker'] = display_pivot['Missing from Tracker'].fillna(0).astype(int)
                else:
                    _li = st.session_state.get(f'{prefix}_live_ids', set())
                    _ti = st.session_state.get(f'{prefix}_tracker_ids', set())
                    m1, m2, m3 = st.columns(3)
                    m1.metric('Live', f'{len(_li):,}')
                    m2.metric('In Tracker', f'{len(_ti):,}')
                    m3.metric('Missing', f'{len(missing_ids):,}')

            # ── Group-by columns picker (max 5) ───────────────────────────────
            # Default groupings: Sub Status + Status. User can add up to 3 more.
            _default_group = [c for c in (substatus_col, status_col) if c]

            # Clean stale session_state — drop column names no longer in the sheet
            _stored = st.session_state.get(f'{prefix}_group_cols')
            if _stored is not None:
                _cleaned = [c for c in _stored if c in cols]
                if _cleaned != _stored:
                    st.session_state[f'{prefix}_group_cols'] = _cleaned

            gcol1, gcol2 = st.columns([6, 1])
            with gcol1:
                # If session_state has a valid list, the widget uses it; otherwise default applies
                if f'{prefix}_group_cols' in st.session_state and st.session_state[f'{prefix}_group_cols']:
                    group_cols = st.multiselect(
                        'Group by (max 5)',
                        options=cols,
                        max_selections=5,
                        key=f'{prefix}_group_cols',
                    )
                else:
                    group_cols = st.multiselect(
                        'Group by (max 5)',
                        options=cols,
                        default=_default_group,
                        max_selections=5,
                        key=f'{prefix}_group_cols',
                    )
            with gcol2:
                st.write(' ')
                if st.button('Reset', key=f'{prefix}_reset_group', use_container_width=True):
                    st.session_state.pop(f'{prefix}_group_cols', None)
                    st.rerun()

            # Final safety net — drop anything that ISN'T a real column
            group_cols = [c for c in (group_cols or []) if c in cols]
            if not group_cols:
                group_cols = _default_group

            # ── Rebuild pivot if user changed grouping columns ────────────────
            if group_cols != _default_group:
                _strip_grp = {c: bdf[c].astype(str).str.strip() for c in group_cols}
                pivot = (
                    pd.DataFrame({c: _strip_grp[c] for c in group_cols})
                      .groupby(group_cols, dropna=False)
                      .size().reset_index(name='Count')
                      .sort_values('Count', ascending=False)
                )
                # Recompute Missing from Tracker for the new grouping if applicable
                display_pivot = pivot.copy()
                if missing_ids is not None and live_df_s is not None:
                    _all_in_live = all(c in live_df_s.columns for c in group_cols)
                    if _all_in_live:
                        live_missing = live_df_s[
                            live_df_s[live_id_col_s].str.strip().str.lower().isin(missing_ids)
                        ].copy()
                        _grp_strips = {c: live_missing[c].astype(str).str.strip() for c in group_cols}
                        miss_grp = (
                            pd.DataFrame({c: _grp_strips[c] for c in group_cols})
                              .groupby(group_cols, dropna=False)
                              .size().reset_index(name='Missing from Tracker')
                        )
                        display_pivot = display_pivot.merge(miss_grp, on=group_cols, how='left')
                        display_pivot['Missing from Tracker'] = display_pivot['Missing from Tracker'].fillna(0).astype(int)

            # ── Filters: one per grouping column with Select all / Clear ──────
            st.markdown('<div style="font-size:11px;font-weight:600;color:#64748b;'
                        'text-transform:uppercase;letter-spacing:.5px;margin:8px 0 4px">'
                        'Filters</div>', unsafe_allow_html=True)

            filters_per_row = 3
            _selected = {}
            for i, gc in enumerate(group_cols):
                if i % filters_per_row == 0:
                    _frow = st.columns(min(filters_per_row, len(group_cols) - i))
                _ccol = _frow[i % filters_per_row]
                with _ccol:
                    _vals = sorted({str(v) for v in display_pivot[gc].dropna().tolist()})
                    _key  = f'{prefix}_pivf_{gc}'

                    # Top row: label + Select all / Clear buttons
                    _lblc, _allc, _clrc = st.columns([4, 1, 1])
                    with _lblc:
                        st.caption(gc)
                    with _allc:
                        if st.button('All', key=f'{_key}_all', use_container_width=True):
                            st.session_state[_key] = _vals
                            st.rerun()
                    with _clrc:
                        if st.button('×', key=f'{_key}_clr', use_container_width=True):
                            st.session_state[_key] = []
                            st.rerun()

                    _sel = st.multiselect(
                        ' ', options=_vals,
                        placeholder=f'All {gc}',
                        key=_key, label_visibility='collapsed',
                    )
                    _selected[gc] = _sel

            _fbar = st.columns([1, 4])
            with _fbar[0]:
                show_zero = st.checkbox('Hide zero', value=True, key=f'{prefix}_piv_hide_zero')

            # Apply filters (vectorized — much faster on large pivots)
            mask = pd.Series(True, index=display_pivot.index)
            for gc, sel in _selected.items():
                if sel:
                    mask &= display_pivot[gc].astype(str).isin(sel)
            view_pivot = display_pivot[mask]
            if show_zero and 'Count' in view_pivot.columns:
                view_pivot = view_pivot[view_pivot['Count'] > 0]

            # Totals row
            total_row = {c: ('TOTAL' if i == len(group_cols)-1 else '—') for i, c in enumerate(group_cols)}
            total_row['Count'] = int(view_pivot['Count'].sum())
            if 'Missing from Tracker' in view_pivot.columns:
                total_row['Missing from Tracker'] = int(view_pivot['Missing from Tracker'].sum())
            view_pivot = pd.concat([view_pivot, pd.DataFrame([total_row])], ignore_index=True)

            # ── Style (skip on very large pivots for speed) ───────────────────
            _STYLE_LIMIT = 200   # threshold

            def _style_pivot_fast(df):
                """Vectorized styling — fast even on large tables."""
                styles = pd.DataFrame('', index=df.index, columns=df.columns)
                styles.iloc[-1] = 'font-weight:700;background-color:#f1f5f9'
                if 'Count' in df.columns and len(df) > 1:
                    body = df['Count'].iloc[:-1].astype(float)
                    max_c = body.max() or 1
                    intensities = (220 - 80 * body / max_c).astype(int)
                    styles.loc[body.index, 'Count'] = (
                        'background-color:rgb(' + intensities.astype(str) + ',' +
                        (intensities + 20).astype(str) + ',255);color:#1e3a8a'
                    )
                if 'Missing from Tracker' in df.columns and len(df) > 1:
                    body = df['Missing from Tracker'].iloc[:-1]
                    red_mask = body > 0
                    styles.loc[body.index[red_mask], 'Missing from Tracker'] = (
                        'background-color:#fee2e2;color:#991b1b;font-weight:600'
                    )
                return styles

            # Caption
            _live_used    = st.session_state.get(f'{prefix}_live_tab_used', '?')
            _tracker_used = st.session_state.get(f'{prefix}_tracker_tab_used', '?')
            st.caption(
                f'**{" × ".join(group_cols)}** · '
                f'{len(view_pivot)-1:,} groups · {int(view_pivot["Count"].iloc[:-1].sum()):,} properties'
                + (f' · Missing from Tracker vs **{_live_used}** ↔ **{_tracker_used}**' if missing_ids is not None else '')
            )

            # Render with click-to-drill-down
            _table_to_show = (
                view_pivot.style.apply(_style_pivot_fast, axis=None)
                if len(view_pivot) <= _STYLE_LIMIT else view_pivot
            )
            _piv_sel = st.dataframe(
                _table_to_show,
                use_container_width=True, hide_index=True,
                height=min(60 + len(view_pivot) * 35, 520),
                selection_mode='single-row',
                on_select='rerun',
                key=f'{prefix}_piv_table_sel',
            )

            # ── Drill-down: click any row to load property-level view ─────────
            _piv_rows = _piv_sel.selection.rows if hasattr(_piv_sel, 'selection') else []
            # Exclude the TOTAL row at the end
            if _piv_rows and _piv_rows[0] < len(view_pivot) - 1:
                _picked = view_pivot.iloc[_piv_rows[0]]

                # Build mask on bdf for the selected group values
                _drill_mask = pd.Series(True, index=bdf.index)
                for gc in group_cols:
                    _drill_mask &= bdf[gc].astype(str).str.strip() == str(_picked[gc])

                # Identifier columns
                _prop_id_c   = cols[0] if len(cols) > 0 else None
                _bdc_id_c    = cols[3] if len(cols) > 3 else None
                _prop_name_c = next((c for c in cols if 'name' in c.lower()), None)
                _show = []
                for c in [_prop_id_c, _bdc_id_c, _prop_name_c, *group_cols]:
                    if c and c not in _show:
                        _show.append(c)

                _detail = bdf.loc[_drill_mask.values, _show]

                st.markdown('###### Property View')
                _selection_summary = ' · '.join(f'**{gc}**: {_picked[gc]}' for gc in group_cols)
                st.caption(_selection_summary + f' — {len(_detail):,} properties')
                st.dataframe(_detail, use_container_width=True, hide_index=True, height=380)
                st.download_button(
                    'Download CSV', _detail.to_csv(index=False).encode('utf-8'),
                    file_name=f'{prefix}_drill.csv', mime='text/csv',
                    key=f'dl_{prefix}_piv_drill',
                )

            # ── Tracker tab config + ID column picker ─────────────────────────
            if available_tabs:
                # Live count summary at the top so the user can verify the match
                _li_ct = len(st.session_state.get(f'{prefix}_live_ids', []))
                _ti_ct = len(st.session_state.get(f'{prefix}_tracker_ids', []))
                _ms_ct = len(st.session_state.get(f'{prefix}_missing_ids', []))
                _li_col = st.session_state.get(f'{prefix}_live_id_col', '?')
                _ti_col = st.session_state.get(f'{prefix}_tracker_id_col', '?')
                tm1, tm2, tm3 = st.columns(3)
                tm1.metric('Live IDs',     f'{_li_ct:,}', help=f'From column: {_li_col}')
                tm2.metric('In Tracker',   f'{_ti_ct:,}', help=f'From column: {_ti_col}')
                tm3.metric('Missing',      f'{_ms_ct:,}',
                           delta=f'-{_ms_ct}' if _ms_ct else None, delta_color='inverse')

                with st.expander('⚙️ Change comparison tabs / ID columns', expanded=False):
                    tc1, tc2 = st.columns(2)
                    with tc1:
                        new_live = st.selectbox('Live Properties tab', available_tabs,
                            index=_live_default, key=f'{prefix}_live_tab')
                        # ID column picker for Live tab (reads cached fetched df)
                        _live_cols = list(st.session_state.get(f'{prefix}_live_df', pd.DataFrame()).columns)
                        if _live_cols:
                            _safe_live_idx = max(0, min(_safe_int(_user_live_idx), len(_live_cols)-1))
                            # Clear stale value if present
                            if not isinstance(st.session_state.get(f'{prefix}_live_id_idx'), int):
                                st.session_state.pop(f'{prefix}_live_id_idx', None)
                            st.selectbox(
                                'Live ID column',
                                options=list(range(len(_live_cols))),
                                format_func=lambda i: f'Col {chr(65 + i) if i < 26 else i+1}: {str(_live_cols[i])[:30]}',
                                index=_safe_live_idx,
                                key=f'{prefix}_live_id_idx',
                            )
                    with tc2:
                        new_tracker = st.selectbox('Properties Tracker tab', available_tabs,
                            index=_tracker_default, key=f'{prefix}_tracker_tab')
                        _tracker_cols = list(st.session_state.get(f'{prefix}_tracker_df', pd.DataFrame()).columns)
                        if _tracker_cols:
                            _safe_tracker_idx = max(0, min(_safe_int(_user_tracker_idx), len(_tracker_cols)-1))
                            if not isinstance(st.session_state.get(f'{prefix}_tracker_id_idx'), int):
                                st.session_state.pop(f'{prefix}_tracker_id_idx', None)
                            st.selectbox(
                                'Tracker ID column',
                                options=list(range(len(_tracker_cols))),
                                format_func=lambda i: f'Col {chr(65 + i) if i < 26 else i+1}: {str(_tracker_cols[i])[:30]}',
                                index=_safe_tracker_idx,
                                key=f'{prefix}_tracker_id_idx',
                            )

                    if st.button('🔄 Re-run comparison', key=f'{prefix}_rerun_cmp', type='primary'):
                        # Clear all cached comparison state for this channel
                        for k in list(st.session_state.keys()):
                            if isinstance(k, str) and (
                                k.startswith(f'{prefix}_cmp_')
                                or k in (
                                    f'{prefix}_missing_ids',
                                    f'{prefix}_live_ids',
                                    f'{prefix}_tracker_ids',
                                    f'{prefix}_live_df',
                                    f'{prefix}_tracker_df',
                                    f'{prefix}_live_id_col',
                                    f'{prefix}_tracker_id_col',
                                )
                            ):
                                st.session_state.pop(k, None)
                        # Also clear the cached sheet fetch so a real reload happens
                        try:
                            fetch_tab_fn.clear()
                        except Exception:
                            pass
                        # scope='app' forces full app rerun, not just the fragment
                        st.rerun(scope='app')

                    # Quick peek of sample IDs to help the user pick correctly
                    _ld = st.session_state.get(f'{prefix}_live_df')
                    _td = st.session_state.get(f'{prefix}_tracker_df')
                    if _ld is not None and _td is not None and not _ld.empty and not _td.empty:
                        st.markdown('**Sample IDs (first 5 rows)** — confirm both columns look the same')
                        sc1, sc2 = st.columns(2)
                        with sc1:
                            st.caption(f'Live → `{_li_col}`')
                            st.dataframe(_ld[[_li_col]].head(5), use_container_width=True, hide_index=True)
                        with sc2:
                            st.caption(f'Tracker → `{_ti_col}`')
                            st.dataframe(_td[[_ti_col]].head(5), use_container_width=True, hide_index=True)

            if missing_ids:
                missing_df = live_df_s[live_df_s[live_id_col_s].str.strip().str.lower().isin(missing_ids)].copy()
                with st.expander(f'⚠️ {len(missing_df):,} properties missing from Tracker', expanded=False):
                    qm = st.text_input('Search', placeholder='Filter…', key=f'{prefix}_miss_q', label_visibility='collapsed')
                    if qm:
                        mask = missing_df.apply(lambda r: r.astype(str).str.contains(qm, case=False, regex=False).any(), axis=1)
                        missing_df = missing_df[mask]
                    st.caption(f'{len(missing_df):,} row(s)')
                    st.dataframe(missing_df, use_container_width=True, hide_index=True, height=360)
                    buf = io.BytesIO()
                    missing_df.to_excel(buf, index=False, engine='openpyxl')
                    st.download_button('⬇️ Download Missing', buf.getvalue(),
                                       file_name='missing_from_tracker.xlsx',
                                       mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                                       key=f'dl_{prefix}_missing_tracker')
            elif missing_ids is not None:
                st.success('✅ All Live properties are in the Tracker.')
        else:
            st.warning('Select Sub Status and Status columns above.')

        st.divider()
        with st.expander('📄 Raw Data (incl. churn)', expanded=False):
            q = st.text_input('Search', placeholder='Filter rows…', key=f'{prefix}_raw_q',
                              label_visibility='collapsed')
            view = bdf_raw.copy()
            if q:
                mask = view.apply(lambda r: r.astype(str).str.contains(q, case=False, regex=False).any(), axis=1)
                view = view[mask]
            st.caption(f'{len(view):,} row(s)')
            st.dataframe(view, use_container_width=True, hide_index=True, height=400)
            buf = io.BytesIO()
            bdf_raw.to_excel(buf, index=False, engine='openpyxl')
            st.download_button('⬇️ Download full sheet', buf.getvalue(),
                               file_name=f'{prefix}_data.xlsx',
                               mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                               key=f'dl_{prefix}_raw')

    # ── TAB 2: Hygiene Checks ─────────────────────────────────────────────────
    def _render_tab2():
        if sub_status_col_f:
            st.info(f'Filtered to **{sub_status_col_f} = Live** · {len(bdf_hyg):,} properties (of {len(bdf):,} total)')
        if hyg_df.empty:
            st.warning('Columns N–AH not found in the sheet.')
        else:
            summary_rows = []
            total = len(hyg_df)
            for hc in hyg_cols:
                filled = hyg_filled[hc]
                empty  = total - filled
                pct    = round(filled / total * 100, 1) if total else 0
                vc_s   = hyg_vcounts[hc].drop('', errors='ignore')
                top    = ' · '.join(f'{v} ({n})' for v, n in list(vc_s.head(3).items()))
                summary_rows.append({
                    'Check':        hc,
                    '✅ Filled':    filled,
                    '❌ Missing':   empty,
                    'Completion %': pct,
                    'Top Values':   top,
                })

            summary = pd.DataFrame(summary_rows)
            avg_pct = round(summary['Completion %'].mean(), 1)
            issues  = int((summary['Completion %'] < 100).sum())

            sm1, sm2, sm3 = st.columns(3)
            sm1.metric('Hygiene Columns',   len(hyg_cols))
            sm2.metric('Avg Completion',    f'{avg_pct}%')
            sm3.metric('Columns with Gaps', issues)

            st.markdown(' ')

            def _cpct(val):
                if val == 100: return 'background-color:#d1fae5;color:#065f46'
                if val >= 80:  return 'background-color:#fef9c3;color:#713f12'
                return 'background-color:#fee2e2;color:#991b1b'

            styled = summary.style.map(_cpct, subset=['Completion %'])
            st.dataframe(styled, use_container_width=True, hide_index=True, height=560)

    # ── TAB 3: Value Summaries ────────────────────────────────────────────────
    def _render_tab3():
        if sub_status_col_f:
            st.info(f'Filtered to **{sub_status_col_f} = Live** · {len(bdf_hyg):,} properties (of {len(bdf):,} total)')
        if hyg_df.empty:
            st.warning('Columns N–AH not found.')
        else:
            section('Value Summaries — per hygiene column (N to AH)')
            st.caption('Expand any column to see its full value distribution and missing properties')

            # Detect helper columns once
            def _find_col(*keywords):
                for kw in keywords:
                    for c in cols:
                        if kw.lower() in c.lower():
                            return c
                return None

            prop_id_col  = _find_col('property id', 'property_id', 'prop id', 'fh id')
            # BDC ID = col D (index 3), fall back to name match
            bdc_id_col   = cols[3] if len(cols) > 3 else None
            if bdc_id_col is None or 'id' not in bdc_id_col.lower():
                bdc_id_col = _find_col('booking.com id', 'bdc id', 'booking id', 'bdc_id') or (cols[3] if len(cols) > 3 else None)
            prop_name_col = _find_col('property name', 'hotel name', 'prop name')

            total_c = len(hyg_df)
            # Pre-build the property base table once (Property ID, BDC ID, Name)
            base_cols = []
            if prop_id_col:   base_cols.append(prop_id_col)
            if bdc_id_col:    base_cols.append(bdc_id_col)
            if prop_name_col: base_cols.append(prop_name_col)
            base_cols = list(dict.fromkeys(base_cols))
            bdf_base = bdf_hyg[base_cols] if base_cols else bdf_hyg.iloc[:, :0]

            for hc in hyg_cols:
                filled_c  = hyg_filled[hc]
                missing_c = total_c - filled_c
                pct_c     = round(filled_c / total_c * 100, 1) if total_c else 0
                icon_c    = '🟢' if pct_c == 100 else ('🟡' if pct_c >= 80 else '🔴')
                label_c   = f'{icon_c} {hc}  ({pct_c}% filled · {filled_c:,}/{total_c:,})'

                with st.expander(label_c, expanded=False):
                    # ── Special handling: link columns ────────────────────────
                    is_link_col = 'link' in hc.lower() or 'url' in hc.lower()

                    if is_link_col:
                        # Table 1: With link vs Without link
                        sk_status = f'link_status_{hc}'
                        if sk_status not in st.session_state:
                            st.session_state[sk_status] = None

                        c1, c2 = st.columns([1, 2])
                        with c1:
                            st.markdown('**Summary**')
                            summary_data = pd.DataFrame([
                                {'Status': '✅ With Link',    'Count': filled_c},
                                {'Status': '❌ Without Link', 'Count': missing_c},
                            ])
                            sel = st.dataframe(
                                summary_data,
                                use_container_width=True,
                                hide_index=True,
                                selection_mode='single-row',
                                on_select='rerun',
                                key=f'{prefix}_sel_link_{hc}',
                            )
                            rows_sel = sel.selection.rows if hasattr(sel, 'selection') else []
                            if rows_sel:
                                st.session_state[sk_status] = 'with' if rows_sel[0] == 0 else 'without'
                            chosen = st.session_state.get(sk_status)
                            if chosen:
                                st.caption(f'Showing: **{chosen.title()} Link** properties')
                            else:
                                st.caption('Click a row above to view properties →')

                        with c2:
                            st.markdown('**Properties**')
                            chosen = st.session_state.get(sk_status)
                            if chosen is None:
                                st.info('Select "With Link" or "Without Link" from the table on the left.')
                            else:
                                # Use pre-stripped column for speed
                                col_stripped = stripped[hc]
                                if chosen == 'with':
                                    mask = col_stripped.ne('')
                                else:
                                    mask = col_stripped.eq('')

                                show_cols = list(base_cols) + ([hc] if hc not in base_cols else [])
                                detail = bdf_hyg.loc[mask.values, show_cols]
                                st.caption(f'{len(detail):,} properties')

                                # Make link clickable for "with link" view
                                col_config = {}
                                if chosen == 'with':
                                    col_config[hc] = st.column_config.LinkColumn(hc, display_text='Open ↗')

                                st.dataframe(
                                    detail, use_container_width=True, hide_index=True,
                                    height=380, column_config=col_config,
                                )
                                # CSV is much faster than Excel — instant generation
                                st.download_button(
                                    f'⬇️ Download {chosen} link properties',
                                    detail.to_csv(index=False).encode('utf-8'),
                                    file_name=f'{chosen}_link_{hc[:20]}.csv',
                                    mime='text/csv',
                                    key=f'dl_{prefix}_link_{hc[:20]}',
                                )
                    else:
                        # ── Default: clickable value counts (using cached vcounts) ─
                        vc_c = hyg_vcounts[hc].reset_index()
                        vc_c.columns = ['Value', 'Count']
                        vc_c['Value'] = vc_c['Value'].fillna('(blank)').replace('', '(blank)')

                        sk_val = f'val_sel_{hc}'

                        c1, c2 = st.columns([2, 3])
                        with c1:
                            st.markdown('**Value Distribution**')
                            sel = st.dataframe(
                                vc_c,
                                use_container_width=True,
                                hide_index=True,
                                selection_mode='single-row',
                                on_select='rerun',
                                key=f'{prefix}_sel_val_{hc}',
                            )
                            rows_sel = sel.selection.rows if hasattr(sel, 'selection') else []
                            if rows_sel:
                                st.session_state[sk_val] = vc_c.iloc[rows_sel[0]]['Value']
                            chosen_val = st.session_state.get(sk_val)
                            if chosen_val is not None:
                                st.caption(f'Showing: **{chosen_val}**')
                            else:
                                st.caption('Click a row to view properties →')

                        with c2:
                            st.markdown('**Properties**')
                            chosen_val = st.session_state.get(sk_val)
                            if chosen_val is None:
                                st.info('Select a value from the table on the left.')
                            else:
                                # Use pre-stripped column for speed
                                col_stripped = stripped[hc]
                                if chosen_val == '(blank)':
                                    mask = col_stripped.eq('')
                                else:
                                    mask = col_stripped.eq(chosen_val)

                                show_cols = list(base_cols) + ([hc] if hc not in base_cols else [])
                                detail = bdf_hyg.loc[mask.values, show_cols]
                                st.caption(f'{len(detail):,} properties')
                                st.dataframe(detail, use_container_width=True,
                                             hide_index=True, height=320)

    # ── TAB 4: E-F-L-M Matrix (excludes ColI = churned) ───────────────────────
    def _render_tab4():
        # Channel-configured matrix grouping columns
        _mx_letters = cfg.get('matrix_letters', ('E', 'F', 'L', 'M'))
        _mx_idx     = [col_idx(L) for L in _mx_letters]
        _picked     = [cols[i] if i < len(cols) else None for i in _mx_idx]
        col_e, col_f, col_l, col_m = _picked

        # Churn filter still uses the channel's FH Status column
        churn_col = cols[fh_idx] if fh_idx < len(cols) else None

        if not all(_picked):
            st.warning(f'Required columns ({", ".join(_mx_letters)}) not all present.')
        else:
            # Filter out churned via configured FH status column
            if churn_col:
                churn_strip = bdf[churn_col].astype(str).str.strip().str.lower()
                bdf_matrix = bdf[churn_strip != 'churned'].reset_index(drop=True)
                excluded   = len(bdf) - len(bdf_matrix)
            else:
                bdf_matrix = bdf
                excluded   = 0

            st.info(
                f'Grouped by **{col_e}** · **{col_f}** · **{col_l}** · **{col_m}** · '
                f'{len(bdf_matrix):,} properties'
                + (f' (excluded {excluded:,} where {churn_col}=Churned)' if excluded else '')
            )

            grp_cols = [col_e, col_f, col_l, col_m]
            stripped_grp = {c: bdf_matrix[c].astype(str).str.strip() for c in grp_cols}

            matrix = (
                pd.DataFrame({c: stripped_grp[c] for c in grp_cols})
                  .groupby(grp_cols, dropna=False)
                  .size()
                  .reset_index(name='Count')
                  .sort_values('Count', ascending=False)
            )

            # Filters
            f1, f2, f3, f4, f5 = st.columns([2, 2, 2, 2, 1])
            with f1:
                sel_e = st.multiselect(col_e, sorted(matrix[col_e].dropna().unique().tolist()),
                                       placeholder=f'All {col_e}', key=f'{prefix}_mx_e')
            with f2:
                sel_f = st.multiselect(col_f, sorted(matrix[col_f].dropna().unique().tolist()),
                                       placeholder=f'All {col_f}', key=f'{prefix}_mx_f')
            with f3:
                sel_l = st.multiselect(col_l, sorted(matrix[col_l].dropna().unique().tolist()),
                                       placeholder=f'All {col_l}', key=f'{prefix}_mx_l')
            with f4:
                sel_m = st.multiselect(col_m, sorted(matrix[col_m].dropna().unique().tolist()),
                                       placeholder=f'All {col_m}', key=f'{prefix}_mx_m')
            with f5:
                st.markdown(' ')
                hide_zero_mx = st.checkbox('Hide zero', value=True, key=f'{prefix}_mx_hide_zero')

            view = matrix.copy()
            if sel_e: view = view[view[col_e].isin(sel_e)]
            if sel_f: view = view[view[col_f].isin(sel_f)]
            if sel_l: view = view[view[col_l].isin(sel_l)]
            if sel_m: view = view[view[col_m].isin(sel_m)]
            if hide_zero_mx: view = view[view['Count'] > 0]

            # Totals row
            total_row = {col_e: '—', col_f: '—', col_l: '—', col_m: 'TOTAL', 'Count': int(view['Count'].sum())}
            view_display = pd.concat([view, pd.DataFrame([total_row])], ignore_index=True)

            def _style_mx(df):
                styles = pd.DataFrame('', index=df.index, columns=df.columns)
                styles.iloc[-1] = 'font-weight:700;background-color:#f1f5f9'
                if 'Count' in df.columns and len(df) > 1:
                    max_c = df['Count'].iloc[:-1].max() or 1
                    for i in range(len(df) - 1):
                        intensity = int(220 - 80 * df['Count'].iloc[i] / max_c)
                        styles.at[df.index[i], 'Count'] = f'background-color:rgb({intensity},{intensity+20},255);color:#1e3a8a'
                return styles

            st.caption(f'{len(view):,} groups · {int(view["Count"].sum()):,} properties')
            sel_matrix = st.dataframe(
                view_display.style.apply(_style_mx, axis=None),
                use_container_width=True, hide_index=True,
                height=min(60 + len(view_display) * 35, 520),
                selection_mode='single-row',
                on_select='rerun',
                key=f'{prefix}_mx_table_sel',
            )

            # Drill-down: click a row → show matching properties
            rows_picked = sel_matrix.selection.rows if hasattr(sel_matrix, 'selection') else []
            # Full matrix export — right under the table
            st.download_button(
                '⬇️ Download full matrix',
                view.to_csv(index=False).encode('utf-8'),
                file_name='efmlm_matrix.csv',
                mime='text/csv',
                key=f'dl_{prefix}_mx_full',
            )

            # ── Property View (drill-down) at the bottom ──────────────────────
            st.divider()
            section('🏨 Property View')

            if rows_picked and rows_picked[0] < len(view):
                picked = view.iloc[rows_picked[0]]
                drill_mask = (
                    (stripped_grp[col_e] == picked[col_e]) &
                    (stripped_grp[col_f] == picked[col_f]) &
                    (stripped_grp[col_l] == picked[col_l]) &
                    (stripped_grp[col_m] == picked[col_m])
                )

                # Property identifier columns
                prop_id_c   = cols[0] if len(cols) > 0 else None
                bdc_id_c    = cols[3] if len(cols) > 3 else None
                prop_name_c = next((c for c in cols if 'name' in c.lower()), None)

                detail_cols = []
                for c in [prop_id_c, bdc_id_c, prop_name_c, col_e, col_f, col_l, col_m]:
                    if c and c not in detail_cols:
                        detail_cols.append(c)

                detail = bdf_matrix.loc[drill_mask.values, detail_cols]

                # Selection chips
                st.markdown(
                    f'<div style="margin-bottom:10px">'
                    f'<span style="background:#eff6ff;color:#1e40af;font-size:11px;padding:3px 9px;border-radius:10px;margin-right:6px">{col_e}: <b>{picked[col_e]}</b></span>'
                    f'<span style="background:#eff6ff;color:#1e40af;font-size:11px;padding:3px 9px;border-radius:10px;margin-right:6px">{col_f}: <b>{picked[col_f]}</b></span>'
                    f'<span style="background:#eff6ff;color:#1e40af;font-size:11px;padding:3px 9px;border-radius:10px;margin-right:6px">{col_l}: <b>{picked[col_l]}</b></span>'
                    f'<span style="background:#eff6ff;color:#1e40af;font-size:11px;padding:3px 9px;border-radius:10px">{col_m}: <b>{picked[col_m]}</b></span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                st.caption(f'**{len(detail):,} properties** matching the selection')

                # Search inside the property view
                q_drill = st.text_input(
                    'Search', placeholder='Filter properties by ID, name…',
                    key=f'{prefix}_mx_drill_q', label_visibility='collapsed',
                )
                if q_drill:
                    mask_q = detail.apply(
                        lambda r: r.astype(str).str.contains(q_drill, case=False, regex=False).any(), axis=1
                    )
                    detail = detail[mask_q]

                st.dataframe(detail, use_container_width=True, hide_index=True, height=420)
                st.download_button(
                    '⬇️ Download selected properties',
                    detail.to_csv(index=False).encode('utf-8'),
                    file_name='efmlm_matrix_drill.csv',
                    mime='text/csv',
                    key=f'dl_{prefix}_mx_drill',
                )
            else:
                st.markdown(
                    '<div style="border:1.5px dashed #cbd5e1;border-radius:8px;padding:30px;text-align:center;color:#94a3b8;background:white">'
                    '👆 <b>Click any row in the table above</b> to load matching properties here'
                    '</div>',
                    unsafe_allow_html=True,
                )

    # ── Mount each fragment into its tab (guarded so render is robust) ───────
    try:
        with bcom_tab1: _render_tab1()
    except Exception as _e:
        with bcom_tab1: st.error(f'Status tab error: {_e}')
    try:
        with bcom_tab2:
            # Customization UI lives here so it only appears on the Hygiene page.
            # Rendered OUTSIDE the fragment so changes trigger a full app rerun
            # (which recomputes hyg_cols at the top and updates all tabs).
            with st.expander('⚙️ Customize hygiene check columns', expanded=False):
                _cc1, _cc2 = st.columns(2)
                with _cc1:
                    st.multiselect(
                        '➕ Add columns to Hygiene/Value Summary',
                        options=_addable,
                        placeholder='Pick any column outside the N–AH range…',
                        key=f'{prefix}_hyg_add',
                    )
                with _cc2:
                    st.multiselect(
                        '➖ Remove columns from default range',
                        options=base_hyg_cols,
                        placeholder='Pick default columns to hide…',
                        key=f'{prefix}_hyg_remove',
                    )
                st.caption('Selections persist in your session and apply to both Hygiene Checks and Value Summaries.')

            _render_tab2()
    except Exception as _e:
        with bcom_tab2: st.error(f'Hygiene tab error: {_e}')
    try:
        with bcom_tab3: _render_tab3()
    except Exception as _e:
        with bcom_tab3: st.error(f'Value Summaries tab error: {_e}')
    try:
        with bcom_tab4: _render_tab4()
    except Exception as _e:
        with bcom_tab4: st.error(f'Matrix tab error: {_e}')


# ── Channel column configs ────────────────────────────────────────────────────
_BCOM_CFG = {
    'fh_status_letter':  'I',
    'status_letter':     'E',
    'status_label':      'BDC Live',
    'sub_status_letter': 'F',
    'default_live_tab':    None,    # auto-detect "live" in tab name
    'default_tracker_tab': None,    # auto-detect "tracker" in tab name
    'hyg_exclude': [],
    'matrix_letters': ('E', 'F', 'L', 'M'),
}
_GOMMT_CFG = {
    'fh_status_letter':  'N',
    'status_letter':     'O',
    'status_label':      'MMT',
    'sub_status_letter': 'P',
    'default_live_tab':    'Live Sheet',
    'default_tracker_tab': 'Main',
    'hyg_exclude': ['FH Live Prop', 'MMT Shell Status', 'GO-MMT Sub Status', 'Set'],
    'matrix_letters': ('O', 'P', 'Q', 'R'),
}

# ── Dispatch to channel page ──────────────────────────────────────────────────
if page == 'Booking.com':
    _render_channel_page('Booking.com', 'bcom', fetch_bcom, fetch_bcom_tabs, fetch_bcom_tab, _BCOM_CFG)
    st.stop()
elif page == 'GoMMT':
    _render_channel_page('GoMMT', 'gommt', fetch_gommt, fetch_gommt_tabs, fetch_gommt_tab, _GOMMT_CFG)
    st.stop()


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: LISTING TRACKER
# ══════════════════════════════════════════════════════════════════════════════
if page == 'Listing Tracker':
    _h1, _h2 = st.columns([7, 1])
    with _h1:
        st.markdown('## Listing Tracker')
        st.caption('Property listing data from the dashboard sheet')
    with _h2:
        st.write('')
        if st.button('Refresh', use_container_width=True, key='listing_refresh'):
            fetch_listing.clear()

    try:
        with st.spinner('Loading…'):
            ldf = fetch_listing()
    except Exception as e:
        st.error(f'Could not load: {e}')
        st.info('Make sure the service account has Viewer access to the dashboard sheet.')
        st.stop()

    if ldf.empty:
        st.warning('Sheet returned no data.')
        st.stop()

    _lcols = list(ldf.columns)
    st.caption(f'**{len(ldf):,}** rows · {len(_lcols)} columns')

    # Filters + search row
    fcol, scol = st.columns([3, 5])
    with fcol:
        # Optional column-value filter
        _filter_col = st.selectbox(
            'Filter by column',
            options=[None] + _lcols,
            placeholder='Pick a column to filter by…',
            key='listing_filter_col',
        )
        if _filter_col:
            _opts = sorted({str(v) for v in ldf[_filter_col].dropna().tolist() if str(v).strip()})
            _filter_vals = st.multiselect(
                f'Values of {_filter_col}',
                options=_opts,
                placeholder='All values',
                key='listing_filter_vals',
            )
        else:
            _filter_vals = []

    with scol:
        st.write(' ')
        q = st.text_input(
            'Search', placeholder='Search across all columns…',
            key='listing_search', label_visibility='collapsed',
        )

    # Apply filters
    view = ldf.copy()
    if _filter_col and _filter_vals:
        view = view[view[_filter_col].astype(str).isin(_filter_vals)]
    if q:
        mask = view.apply(
            lambda r: r.astype(str).str.contains(q, case=False, regex=False).any(), axis=1
        )
        view = view[mask]

    st.caption(f'{len(view):,} row(s)')
    st.dataframe(view, use_container_width=True, hide_index=True, height=560)

    st.download_button(
        '⬇️ Download (CSV)',
        view.to_csv(index=False).encode('utf-8'),
        file_name='listing_tracker.csv',
        mime='text/csv',
        key='dl_listing',
    )

    st.stop()

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: MAPPING CHECKER
# ══════════════════════════════════════════════════════════════════════════════

# Hard guard: if we got here while on a non-Mapping page, do nothing
if page != 'Mapping Checker':
    st.stop()

# Header
hdr1, hdr2 = st.columns([7, 1])
with hdr1:
    st.markdown('## Mapping Checker')
    st.caption('Validates SU channel manager data against CRS & Prop Level Dashboard')
with hdr2:
    st.write('')

st.divider()

# ── Step 1: Data sources ───────────────────────────────────────────────────────
section('Step 1 — Data Sources')

up_col, crs_col, dash_col = st.columns([3, 2, 2])

with up_col:
    uploaded = st.file_uploader('SU Export (.xlsx / .xls / .csv)', type=['xlsx','xls','csv'],
                                 label_visibility='visible')
    if uploaded:
        try:
            with st.spinner('Reading…'):
                su_df_new, sheets = read_file(uploaded)
            st.session_state['su_df'] = su_df_new
            st.success(f'**{len(su_df_new):,} rows** · {len(sheets)} sheet(s): {", ".join(str(s) for s in sheets)}')
        except Exception as e:
            st.error(str(e))

with crs_col:
    st.caption('CRS Data — Google Sheet')
    if st.button('🔄 Fetch CRS', use_container_width=True):
        fetch_crs.clear()
        try:
            with st.spinner('Fetching…'):
                st.session_state['crs_df'] = fetch_crs()
            st.session_state.pop('crs_err', None)
        except Exception as e:
            st.session_state['crs_err'] = str(e)
    if 'crs_df' in st.session_state:
        d = st.session_state['crs_df']
        st.success(f'**{len(d):,} rows** · {len(d.columns)} cols')
    elif 'crs_err' in st.session_state:
        st.error(st.session_state['crs_err'])

with dash_col:
    st.caption('Prop Level Dashboard — optional')
    if st.button('🔄 Fetch Dashboard', use_container_width=True):
        fetch_dashboard.clear()
        try:
            with st.spinner('Fetching…'):
                st.session_state['dash_raw'] = fetch_dashboard()
            st.session_state.pop('dash_err', None)
        except Exception as e:
            st.session_state['dash_err'] = str(e)
    if 'dash_raw' in st.session_state:
        st.success(f'**{len(st.session_state["dash_raw"]) - 1:,} properties** loaded')
    elif 'dash_err' in st.session_state:
        st.warning(st.session_state['dash_err'])

su_df    = st.session_state.get('su_df')
crs_df   = st.session_state.get('crs_df')
dash_raw = st.session_state.get('dash_raw')

# ── OTA Channel Data ───────────────────────────────────────────────────────────
OTA_TABS = [
    ('Booking.com', '19',  '🔵'),
    ('MakeMyTrip',  '105', '🔴'),
    ('Agoda',       '189', '🟢'),
    ('Expedia',     '9',   '🟠'),
    ('EMT',         '217', '🟣'),
    ('CT',          '351', '⚫'),
]

with st.expander('📡 OTA Channel Data (optional — upload data received from each OTA)', expanded=False):
    ota_tabs = st.tabs([f"{icon} {name}" for name, _, icon in OTA_TABS])
    for ota_tab, (ota_name, ota_code, ota_icon) in zip(ota_tabs, OTA_TABS):
        with ota_tab:
            sk = f'ota_df_{ota_code}'
            up_c, info_c = st.columns([3, 3])
            with up_c:
                f = st.file_uploader(
                    f'{ota_name} data file',
                    type=['xlsx', 'xls', 'csv'],
                    key=f'uf_{ota_code}',
                )
                if f:
                    try:
                        with st.spinner('Reading…'):
                            df_raw, ota_sheets = read_file(f)
                        st.session_state[sk] = {'df': df_raw, 'sheets': ota_sheets, 'name': f.name}
                    except Exception as e:
                        st.error(str(e))
            with info_c:
                if sk in st.session_state:
                    d = st.session_state[sk]
                    st.success(f"**{d['name']}** — {len(d['df']):,} rows · {len(d['df'].columns)} cols")
                    buf = io.BytesIO()
                    d['df'].to_excel(buf, index=False, engine='openpyxl')
                    st.download_button('⬇️ Download', buf.getvalue(),
                                       file_name=f"{ota_name.lower().replace('.','')}_data.xlsx",
                                       mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                                       key=f'dl_ota_{ota_code}')

            if sk in st.session_state:
                df_ = st.session_state[sk]['df']
                qc1, qc2 = st.columns([5, 1])
                with qc1:
                    q = st.text_input('Search', placeholder='Filter rows…',
                                      key=f'q_ota_{ota_code}', label_visibility='collapsed')
                with qc2:
                    if st.button('✕ Clear', key=f'clr_{ota_code}'):
                        del st.session_state[sk]; st.rerun()
                view = df_.copy()
                if q:
                    mask = view.apply(lambda r: r.astype(str).str.contains(q, case=False, regex=False).any(), axis=1)
                    view = view[mask]
                st.caption(f'{len(view):,} row(s)')
                st.dataframe(view, use_container_width=True, height=340, hide_index=True)
            else:
                st.caption(f'No {ota_name} data uploaded yet.')

if su_df is None or crs_df is None:
    st.info('Upload the SU file and fetch CRS data to continue.')
    st.stop()

su_cols  = list(su_df.columns)
crs_cols = list(crs_df.columns)

# ── Step 2: Column mapping ─────────────────────────────────────────────────────
section('Step 2 — Column Mapping')

with st.expander('SU File Columns', expanded=True):
    c1,c2,c3,c4,c5,c6 = st.columns(6)
    with c1: su_room_id    = st.selectbox('PMS Room ID',       su_cols, index=pick(su_cols, ['pms room'],['room id'],['roomid']))
    with c2: su_rate_id    = st.selectbox('PMS Rate ID',       su_cols, index=pick(su_cols, ['pms rate'],['rate id'],['rateid']))
    with c3: su_obp        = st.selectbox('OBP Multiplier',    su_cols, index=pick(su_cols, ['obp'],['multiplier'],['occ']))
    with c4: su_channel    = st.selectbox('Channel Code',      [None]+su_cols, index=pick_opt(su_cols, ['channel'],['ota']))
    with c5: su_prop_name  = st.selectbox('Property Name',     [None]+su_cols, index=pick_opt(su_cols, ['property name'],['hotel name'],['name']))
    with c6: su_app_guests = st.selectbox('Applicable Guests', [None]+su_cols, index=pick_opt(su_cols, ['applicable guests'],['applicable_guests'],['appguests']))

with st.expander('CRS Columns', expanded=True):
    c1,c2,c3,c4,c5 = st.columns(5)
    with c1: crs_prop_id   = st.selectbox('Property ID',    crs_cols, index=pick(crs_cols, ['property id'],['prop id'],['hotel id'],['property_id']))
    with c2: crs_room_type = st.selectbox('Room Type ID',   crs_cols, index=pick(crs_cols, ['room type'],['room_type'],['roomtype']))
    with c3: crs_rate_code = st.selectbox('Rate Plan Code', crs_cols, index=pick(crs_cols, ['rate plan'],['rate code'],['rate_plan'],['ratecode'],['rate']))
    with c4: crs_max_occ   = st.selectbox('Max Occupancy',  [None]+crs_cols,
                                           index=pick_opt(crs_cols, ['max occ'],['max_occ'],['max occupancy'],
                                                          ['maximum occupancy'],['maxocc'],['occupancy'],['pax'],['max pax']))
    with c5: crs_is_active = st.selectbox('Active Filter',  [None]+crs_cols,
                                           index=pick_opt(crs_cols, ['is_active'],['is active'],['active'],['status']))

col_cfg = {
    'su':  {'room_id': su_room_id, 'rate_id': su_rate_id, 'obp': su_obp,
             'prop_name': su_prop_name, 'channel': su_channel, 'app_guests': su_app_guests},
    'int': {'prop_id': crs_prop_id, 'room_type': crs_room_type, 'rate_code': crs_rate_code,
             'max_occ': crs_max_occ, 'is_active': crs_is_active},
}

with st.expander('🔬 OBP Parse Debug', expanded=False):
    rows = [{'OBP Raw': str(r.get(su_obp,''))[:60],
             'Parsed Keys': str(list(parse_obp(r.get(su_obp,'')).keys())),
             'Count': len(parse_obp(r.get(su_obp,'')))}
            for _, r in su_df.head(8).iterrows()]
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    st.caption(f'Max Occ col → **{crs_max_occ}** · Active filter → **{crs_is_active}**')

# ── Step 3: Run ────────────────────────────────────────────────────────────────
section('Step 3 — Run')

btn_col, warn_col = st.columns([2, 5])
with btn_col:
    do_run = st.button('🚀 Run All Checks', type='primary', use_container_width=True)
with warn_col:
    if not crs_max_occ:
        st.warning('No Max Occupancy column selected — OBP Extra/Missing checks will be skipped.')

if do_run:
    with st.spinner('Running checks…'):
        results = run_checks(su_df, crs_df, dash_raw, col_cfg)
    st.session_state['results'] = results
    st.rerun()

if 'results' not in st.session_state:
    st.stop()

res  = st.session_state['results']
meta = res['_meta']

# ── Metrics ────────────────────────────────────────────────────────────────────
st.divider()
m1,m2,m3,m4 = st.columns(4)
m1.metric('CRS Properties',        f"{meta['crs_props']:,}")
m2.metric('SU Rows Analyzed',      f"{meta['total_analyzed']:,}")
m3.metric('Excluded (not in CRS)', f"{meta['su_excluded']:,}")
m4.metric('OCC Map Entries',       f"{meta['occ_map_size']:,}")

# ── Results tabs ───────────────────────────────────────────────────────────────
def _icon(k, n): return '⚫' if k == 'ncrs' else ('🔴' if n > 0 else '🟢')
tab_labels = [f"{_icon(k,len(res.get(k,[])))} {lbl} ({len(res.get(k,[]))})" for k,lbl,_ in CHECKS]
tabs = st.tabs(tab_labels)
for i, (k, lbl, desc) in enumerate(CHECKS):
    with tabs[i]:
        st.caption(desc)
        show_table(res.get(k, []), k)

# ── Save + Export ──────────────────────────────────────────────────────────────
st.divider()
sv1, sv2, sv3 = st.columns([2, 2, 3])

with sv1:
    run_by = st.text_input('Your name', placeholder='e.g. Praveen',
                            key='run_by', label_visibility='visible')
with sv2:
    st.write('')  # vertical align
    st.write('')
    if st.button('💾 Save to Last Checked', use_container_width=True):
        try:
            with st.spinner('Saving…'):
                save_run(meta, res, run_by=run_by or 'anonymous')
            fetch_log.clear(); fetch_details.clear()
            st.success('Saved — visible to all users in Last Checked.')
        except Exception as e:
            st.error(f'Save failed: {e}')

with sv3:
    st.write(''); st.write('')
    if st.button('📥 Export All Results to Excel', use_container_width=True):
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='openpyxl') as writer:
            for k, lbl, _ in CHECKS:
                rows = res.get(k, [])
                if rows:
                    pd.DataFrame(rows).to_excel(writer, sheet_name=lbl[:31], index=False)
        st.download_button('⬇️ Download', buf.getvalue(), file_name='su_mapping_report.xlsx',
                           mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                           key='dl_full')
