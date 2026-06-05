import streamlit as st
import pandas as pd
import json, ast, re, io

from sheets import fetch_crs, fetch_dashboard, save_run, fetch_log, fetch_details, fetch_bcom, fetch_bcom_tab, fetch_bcom_tabs

st.set_page_config(page_title="SU Mapping Checker", layout="wide", page_icon="🔍",
                   initial_sidebar_state="expanded")

# ── CSS ────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
html, body, [class*="css"] {
  font-family: -apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', sans-serif;
}
#MainMenu, footer, header { visibility: hidden; }
[data-testid="stDecoration"], [data-testid="stSidebarNav"] { display: none; }

/* layout */
.block-container { padding: 1.5rem 2.5rem 2rem !important; max-width: 1400px !important; }

/* sidebar */
[data-testid="stSidebar"] { background: #0f172a !important; border-right: 1px solid #1e293b !important; }
[data-testid="stSidebar"] > div:first-child { padding-top: 0 !important; }

/* sidebar radio override */
[data-testid="stSidebar"] .stRadio > div { gap: 2px !important; padding: 0 8px; }
[data-testid="stSidebar"] .stRadio label {
  border-radius: 6px; padding: 8px 10px; cursor: pointer;
  color: #94a3b8 !important; font-size: 13px !important; font-weight: 500 !important;
}
[data-testid="stSidebar"] .stRadio label:has(input:checked) {
  background: #1e293b !important; color: #f1f5f9 !important;
}

/* metrics */
[data-testid="stMetric"] {
  background: white !important; border: 1px solid #e2e8f0 !important;
  border-radius: 8px !important; padding: 10px 16px !important;
}
[data-testid="stMetricLabel"] p { font-size: 11px !important; color: #64748b !important; }
[data-testid="stMetricValue"]   { font-size: 22px !important; font-weight: 700 !important; color: #0f172a !important; }

/* tabs */
.stTabs [data-baseweb="tab-list"] { gap: 0; border-bottom: 1px solid #e2e8f0; overflow-x: auto; flex-wrap: nowrap; }
.stTabs [data-baseweb="tab"] { font-size: 11px !important; padding: 6px 12px !important; white-space: nowrap; font-weight: 500; }

/* expanders */
[data-testid="stExpander"] { border: 1px solid #e2e8f0 !important; border-radius: 8px !important; background: white !important; margin-bottom: 6px !important; }

/* alerts */
[data-testid="stAlert"] { padding: 7px 12px !important; border-radius: 6px !important; }
[data-testid="stAlert"] p { font-size: 12px !important; margin: 0 !important; }

/* dataframe */
[data-testid="stDataFrame"] { border: 1px solid #e2e8f0; border-radius: 6px; }

/* caption */
.stCaption p { font-size: 11px !important; color: #94a3b8 !important; }

/* divider */
hr { margin: 12px 0 !important; border-color: #e2e8f0 !important; }

/* select label */
label p { font-size: 12px !important; color: #374151 !important; font-weight: 500 !important; }
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
    <div style="padding:20px 16px 6px">
      <div style="font-size:10px;font-weight:700;text-transform:uppercase;
                  letter-spacing:1.2px;color:#3b82f6;margin-bottom:3px">FabHotels</div>
      <div style="font-size:15px;font-weight:700;color:#f1f5f9">Revenue Tools</div>
    </div>
    <div style="height:1px;background:#1e293b;margin:8px 0 10px"></div>
    <div style="padding:0 16px 6px;font-size:10px;font-weight:600;text-transform:uppercase;
                letter-spacing:1px;color:#475569">Tools</div>
    """, unsafe_allow_html=True)

    page = st.radio('nav', ['📊  Mapping Checker', '🕐  Last Checked', '📋  Booking.com'],
                    label_visibility='collapsed')

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: LAST CHECKED
# ══════════════════════════════════════════════════════════════════════════════
if page == '🕐  Last Checked':
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
# PAGE: BOOKING.COM
# ══════════════════════════════════════════════════════════════════════════════
if page == '📋  Booking.com':
    st.markdown('## Booking.com')
    st.caption('Live status, substatus summary and hygiene checks from the Booking.com property sheet')
    st.divider()

    rc1, rc2 = st.columns([2, 6])
    with rc1:
        if st.button('🔄 Refresh Data', use_container_width=True):
            fetch_bcom.clear()

    try:
        with st.spinner('Loading Booking.com sheet…'):
            bdf = fetch_bcom()
    except Exception as e:
        st.error(f'Could not load sheet: {e}')
        st.info('Make sure the service account has been given Viewer access to the Booking.com sheet.')
        st.stop()

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

    # ── Exclusions ────────────────────────────────────────────────────────────
    bdf_raw = bdf.copy()   # keep untouched for raw view
    cols_all = list(bdf.columns)

    # 1. Drop rows where col A (index 0) is blank
    col_a = cols_all[0] if cols_all else None
    blank_a_mask = bdf[col_a].str.strip() == '' if col_a else pd.Series(False, index=bdf.index)

    # 2. Drop rows where "FH Status" column value is "churned"
    fh_status_col = next((c for c in cols_all if c.strip().lower() == 'fh status'), None)
    if fh_status_col is None:
        # fallback: find column containing "fh status"
        fh_status_col = next((c for c in cols_all if 'fh status' in c.strip().lower()), None)

    churned_mask = (
        bdf[fh_status_col].str.strip().str.lower() == 'churned'
        if fh_status_col else pd.Series(False, index=bdf.index)
    )

    exclude_mask = blank_a_mask | churned_mask
    bdf          = bdf[~exclude_mask].reset_index(drop=True)
    cols         = list(bdf.columns)

    blank_a_cnt  = int(blank_a_mask.sum())
    churn_cnt    = int(churned_mask.sum())

    st.caption(
        f'{len(bdf):,} active properties · {len(cols)} columns'
        + (f' · {blank_a_cnt} blank Col A removed' if blank_a_cnt else '')
        + (f' · {churn_cnt} churned (FH Status) removed' if churn_cnt else '')
    )

    # ── REPORT 1: Substatus × Status pivot + Missing from Tracker ────────────
    section('Report 1 — Status Summary & Missing from Tracker')

    # ── 1a: Substatus × Status pivot ──────────────────────────────────────────
    # Find exactly one substatus column and one status column (exclude duplicates like status.1)
    substatus_col = next((c for c in cols if c.strip().lower() == 'substatus'
                          or c.strip().lower().startswith('substatus')), None)
    status_col    = next((c for c in cols if c.strip().lower() == 'status'), None)

    # Fallback: pick first column whose name contains the keyword (exact match preferred)
    if not substatus_col:
        substatus_col = next((c for c in cols if 'substatus' in c.lower()), None)
    if not status_col:
        status_col = next((c for c in cols if 'status' in c.lower()
                           and 'substatus' not in c.lower() and 'fh' not in c.lower()), None)

    if substatus_col and status_col:
        pivot = (
            bdf.groupby([substatus_col, status_col], dropna=False)
               .size()
               .reset_index(name='Count')
               .rename(columns={substatus_col: 'Sub Status', status_col: 'Status'})
               .sort_values(['Sub Status', 'Count'], ascending=[True, False])
        )
        st.caption(f'Grouped by **{substatus_col}** × **{status_col}** — {len(bdf):,} properties')
        st.dataframe(pivot, use_container_width=False, hide_index=True, height=400)
    elif status_col:
        vc = bdf[status_col].str.strip().value_counts().reset_index()
        vc.columns = ['Status', 'Count']
        st.dataframe(vc, use_container_width=False, hide_index=True)
    else:
        st.info('No status / substatus columns detected. Select manually:')
        c1, c2 = st.columns(2)
        with c1:
            status_col    = st.selectbox('Status column',    cols,          key='bcom_scol')
        with c2:
            substatus_col = st.selectbox('Substatus column', [None] + cols, key='bcom_sscol')
        if substatus_col:
            pivot = bdf.groupby([substatus_col, status_col]).size().reset_index(name='Count')
            pivot.columns = ['Sub Status', 'Status', 'Count']
            st.dataframe(pivot, use_container_width=False, hide_index=True)

    st.divider()

    # ── 1b: Missing from Properties Tracker ───────────────────────────────────
    section('Missing from Properties Tracker')

    try:
        available_tabs = fetch_bcom_tabs()
    except Exception as e:
        available_tabs = []
        st.warning(f'Could not list sheet tabs: {e}')

    col_pos = {'A (col 1)': 0, 'B (col 2)': 1, 'C (col 3)': 2, 'D (col 4)': 3, 'E (col 5)': 4}

    cfg1, cfg2 = st.columns(2)
    with cfg1:
        live_tab    = st.selectbox('Live Properties tab', available_tabs,
                                   index=next((i for i, t in enumerate(available_tabs) if 'live' in t.lower()), 0),
                                   key='bcom_live_tab')
        live_id_col = st.selectbox('Property ID column (Live tab)',
                                   list(col_pos.keys()), key='live_id_col')
    with cfg2:
        tracker_tab    = st.selectbox('Properties Tracker tab', available_tabs,
                                      index=next((i for i, t in enumerate(available_tabs) if 'tracker' in t.lower()),
                                                 min(1, len(available_tabs) - 1)),
                                      key='bcom_tracker_tab')
        tracker_id_col = st.selectbox('Property ID column (Tracker tab)',
                                      list(col_pos.keys()), key='tracker_id_col')

    if st.button('🔍 Run Comparison', key='bcom_compare_btn'):
        try:
            with st.spinner(f'Fetching "{live_tab}"…'):
                live_df = fetch_bcom_tab(live_tab)
            with st.spinner(f'Fetching "{tracker_tab}"…'):
                tracker_df = fetch_bcom_tab(tracker_tab)

            live_id_name    = list(live_df.columns)[col_pos[live_id_col]]
            tracker_id_name = list(tracker_df.columns)[col_pos[tracker_id_col]]

            live_ids    = set(live_df[live_id_name].str.strip().str.lower().replace('', pd.NA).dropna())
            tracker_ids = set(tracker_df[tracker_id_name].str.strip().str.lower().replace('', pd.NA).dropna())
            missing_ids = live_ids - tracker_ids

            m1, m2, m3 = st.columns(3)
            m1.metric(f'In "{live_tab}"',    f'{len(live_ids):,}')
            m2.metric(f'In "{tracker_tab}"', f'{len(tracker_ids):,}')
            m3.metric('Missing from Tracker', f'{len(missing_ids):,}',
                      delta=f'-{len(missing_ids)}' if missing_ids else None,
                      delta_color='inverse')

            if missing_ids:
                missing_df = live_df[live_df[live_id_name].str.strip().str.lower().isin(missing_ids)].copy()
                st.error(f'**{len(missing_df):,} properties** are Live on Booking.com but missing from the Tracker.')
                q_miss = st.text_input('Search missing', placeholder='Filter…',
                                       key='miss_q', label_visibility='collapsed')
                if q_miss:
                    mask = missing_df.apply(lambda r: r.astype(str).str.contains(q_miss, case=False, regex=False).any(), axis=1)
                    missing_df = missing_df[mask]
                st.caption(f'{len(missing_df):,} row(s)')
                st.dataframe(missing_df, use_container_width=True, hide_index=True, height=400)
                buf = io.BytesIO()
                missing_df.to_excel(buf, index=False, engine='openpyxl')
                st.download_button('⬇️ Download Missing Properties', buf.getvalue(),
                                   file_name='missing_from_tracker.xlsx',
                                   mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                                   key='dl_missing_tracker')
            else:
                st.success('✅ All Live properties are present in the Properties Tracker.')
        except Exception as e:
            st.error(str(e))

    st.divider()

    # ── REPORT 2: Hygiene Checks (col N → AH) ────────────────────────────────
    section('Report 2 — Hygiene Checks (Col N to AH)')

    hyg_start = col_idx('N')
    hyg_end   = col_idx('AH') + 1
    hyg_cols  = cols[hyg_start:hyg_end]

    if hyg_cols:
        hyg_df = bdf[hyg_cols].copy()

        summary_rows = []
        for hc in hyg_cols:
            total  = len(hyg_df)
            filled = int(hyg_df[hc].str.strip().ne('').sum())
            empty  = total - filled
            pct    = round(filled / total * 100, 1) if total else 0
            summary_rows.append({
                'Check':        hc,
                '✅ Filled':    filled,
                '❌ Missing':   empty,
                'Completion %': pct,
            })

        summary = pd.DataFrame(summary_rows)
        avg_pct = round(summary['Completion %'].mean(), 1)
        issues  = int((summary['Completion %'] < 100).sum())

        sm1, sm2, sm3 = st.columns(3)
        sm1.metric('Hygiene Columns Checked', len(hyg_cols))
        sm2.metric('Avg Completion',          f'{avg_pct}%')
        sm3.metric('Columns with Gaps',       issues)

        st.markdown(' ')

        def color_pct(val):
            if val == 100: return 'background-color:#d1fae5;color:#065f46'
            if val >= 80:  return 'background-color:#fef9c3;color:#713f12'
            return 'background-color:#fee2e2;color:#991b1b'

        styled = summary.style.map(color_pct, subset=['Completion %'])
        st.dataframe(styled, use_container_width=True, hide_index=True, height=600)

        with st.expander('🔍 Drill down — rows missing a specific check', expanded=False):
            chosen_check = st.selectbox('Select hygiene column', hyg_cols, key='hyg_drill')
            missing_rows = bdf[bdf[chosen_check].str.strip() == ''].copy()
            st.caption(f'{len(missing_rows):,} properties missing **{chosen_check}**')
            if not missing_rows.empty:
                display_cols = cols[:5] + ([chosen_check] if chosen_check not in cols[:5] else [])
                st.dataframe(missing_rows[display_cols], use_container_width=True,
                             hide_index=True, height=360)
                buf = io.BytesIO()
                missing_rows.to_excel(buf, index=False, engine='openpyxl')
                st.download_button('⬇️ Download missing rows', buf.getvalue(),
                                   file_name=f'missing_{chosen_check[:20]}.xlsx',
                                   mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                                   key='dl_hyg_drill')
    else:
        st.warning('Columns N–AH not found.')

    st.divider()

    with st.expander('📄 Raw Data (incl. churn)', expanded=False):
        q = st.text_input('Search', placeholder='Filter rows…', key='bcom_raw_q',
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
                           file_name='bcom_data.xlsx',
                           mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                           key='dl_bcom_raw')

    st.stop()

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: MAPPING CHECKER
# ══════════════════════════════════════════════════════════════════════════════

# Header
hdr1, hdr2 = st.columns([7, 1])
with hdr1:
    st.markdown('## Mapping Checker')
    st.caption('Validates SU channel manager data against CRS & Prop Level Dashboard')
with hdr2:
    st.markdown('<div style="text-align:right;padding-top:14px">'
                '<span style="background:#eff6ff;color:#2563eb;font-size:10px;font-weight:600;'
                'padding:3px 10px;border-radius:10px">FabHotels Internal</span></div>',
                unsafe_allow_html=True)

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
