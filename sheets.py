import gspread
import gspread.exceptions
import pandas as pd
import streamlit as st
from datetime import datetime

CRS_SHEET_ID   = '1H2lP2zn4Ydeyex504DzmfBwXAX0Ip2H4SIu92DylRLw'
BCOM_SHEET_ID  = '1vjm8BX1QZKMqXiLjbokCD0R91JvlscXcg5812p_IolI'
CRS_SHEET_TAB  = 'CRS DATA'
DASH_SHEET_ID  = '1ND1SBFknF1aD4iVA_1XtwXK_u7wEonFUVYesv5sZRXU'
DASH_SHEET_TAB = 'Prop Level Dashboard'
LOG_TAB        = 'Last Checked'
DETAIL_TAB     = 'Last Run Details'


def _gc():
    return gspread.service_account_from_dict(st.secrets["gcp_service_account"])


@st.cache_data(ttl=300, show_spinner=False)
def fetch_crs() -> pd.DataFrame:
    gc = _gc()
    wb = gc.open_by_key(CRS_SHEET_ID)
    try:
        ws = wb.worksheet(CRS_SHEET_TAB)
    except gspread.exceptions.WorksheetNotFound:
        tabs = [w.title for w in wb.worksheets()]
        raise Exception(f"Tab '{CRS_SHEET_TAB}' not found. Available: {tabs}")
    rows = ws.get_all_values()
    if not rows:
        return pd.DataFrame()
    headers = rows[0]
    seen, deduped = {}, []
    for h in headers:
        if h in seen:
            seen[h] += 1
            deduped.append(f"{h}.{seen[h]}")
        else:
            seen[h] = 0
            deduped.append(h)
    return pd.DataFrame(rows[1:], columns=deduped).fillna('')


@st.cache_data(ttl=300, show_spinner=False)
def fetch_bcom() -> pd.DataFrame:
    """Fetch Booking.com property data from the first tab of the BCOM sheet."""
    gc  = _gc()
    ws  = gc.open_by_key(BCOM_SHEET_ID).get_worksheet(0)
    rows = ws.get_all_values()
    if not rows:
        return pd.DataFrame()
    headers = rows[0]
    seen, deduped = {}, []
    for h in headers:
        if h in seen:
            seen[h] += 1
            deduped.append(f"{h}.{seen[h]}")
        else:
            seen[h] = 0
            deduped.append(h)
    return pd.DataFrame(rows[1:], columns=deduped).fillna('')


@st.cache_data(ttl=300, show_spinner=False)
def fetch_dashboard() -> list:
    gc = _gc()
    ws = gc.open_by_key(DASH_SHEET_ID).worksheet(DASH_SHEET_TAB)
    return ws.get_all_values()


# ── Run log helpers ────────────────────────────────────────────────────────────

SUMMARY_HEADERS = [
    'Run At', 'Run By', 'CRS Properties', 'SU Analyzed', 'Excluded',
    'Room-Rate', 'App Guests', 'OBP Mult', 'OBP Extra Occ', 'OBP Missing Occ',
    'Missing EP/CP', 'Missing MAP/AP', 'Missing Other', 'Extra in SU',
    'OTA Live No Map', 'Mapped Not Live',
]

CHECK_KEYS = ['rr','apg','obpv','obpoe','obpom','rpmicp','rpmimap','rpmi','rpex','chlive','chdead']


def _ensure_tab(wb, title, rows=5000, cols=30):
    try:
        return wb.worksheet(title)
    except gspread.exceptions.WorksheetNotFound:
        return wb.add_worksheet(title=title, rows=rows, cols=cols)


def save_run(meta: dict, results: dict, run_by: str = 'anonymous'):
    """
    Save a run:
      - Append one summary row to LOG_TAB
      - Overwrite DETAIL_TAB with all detailed result rows from this run
    """
    gc = _gc()
    wb = gc.open_by_key(CRS_SHEET_ID)
    ts = datetime.now().strftime('%Y-%m-%d %H:%M')

    # ── Summary row ───────────────────────────────────────────────────────────
    log_ws = _ensure_tab(wb, LOG_TAB, rows=2000, cols=len(SUMMARY_HEADERS))
    if log_ws.row_count < 1 or not log_ws.get_all_values():
        log_ws.append_row(SUMMARY_HEADERS)

    summary_row = [
        ts, run_by,
        meta.get('crs_props', ''),
        meta.get('total_analyzed', ''),
        meta.get('su_excluded', ''),
    ] + [len(results.get(k, [])) for k in CHECK_KEYS]
    log_ws.append_row(summary_row)

    # ── Full detail rows ───────────────────────────────────────────────────────
    # Build a flat list of all result rows tagged with check type and run info
    CHECK_LABELS = {
        'rr':      'Room-Rate Mismatch',
        'apg':     'Applicable Guests',
        'obpv':    'OBP Multiplier ≠1',
        'obpoe':   'OBP Extra Occ',
        'obpom':   'OBP Missing Occ',
        'rpmicp':  'Missing EP/CP',
        'rpmimap': 'Missing MAP/AP',
        'rpmi':    'Missing Other',
        'rpex':    'Extra in SU',
        'chlive':  'OTA Live No Mapping',
        'chdead':  'Mapped OTA Not Live',
        'ncrs':    'Not in CRS',
    }

    all_rows = []
    for key, label in CHECK_LABELS.items():
        for row in results.get(key, []):
            flat = {'Run At': ts, 'Run By': run_by, 'Check': label}
            flat.update(row)
            all_rows.append(flat)

    detail_ws = _ensure_tab(wb, DETAIL_TAB, rows=max(len(all_rows) + 5, 5000), cols=30)
    detail_ws.clear()

    if all_rows:
        df = pd.DataFrame(all_rows).fillna('')
        detail_ws.update([df.columns.tolist()] + df.values.tolist())
    else:
        detail_ws.update([['Run At', 'Run By', 'Check', 'Note'],
                          [ts, run_by, '—', 'No issues found']])


@st.cache_data(ttl=60, show_spinner=False)
def fetch_log() -> pd.DataFrame:
    gc = _gc()
    wb = gc.open_by_key(CRS_SHEET_ID)
    try:
        ws = wb.worksheet(LOG_TAB)
    except gspread.exceptions.WorksheetNotFound:
        return pd.DataFrame(columns=SUMMARY_HEADERS)
    rows = ws.get_all_values()
    if len(rows) < 2:
        return pd.DataFrame(columns=SUMMARY_HEADERS)
    return pd.DataFrame(rows[1:], columns=rows[0])


@st.cache_data(ttl=60, show_spinner=False)
def fetch_details() -> pd.DataFrame:
    gc = _gc()
    wb = gc.open_by_key(CRS_SHEET_ID)
    try:
        ws = wb.worksheet(DETAIL_TAB)
    except gspread.exceptions.WorksheetNotFound:
        return pd.DataFrame()
    rows = ws.get_all_values()
    if len(rows) < 2:
        return pd.DataFrame()
    return pd.DataFrame(rows[1:], columns=rows[0])
