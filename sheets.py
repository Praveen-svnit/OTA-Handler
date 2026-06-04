import gspread
import gspread.exceptions
import pandas as pd
import streamlit as st
from datetime import datetime

CRS_SHEET_ID    = '1H2lP2zn4Ydeyex504DzmfBwXAX0Ip2H4SIu92DylRLw'
CRS_SHEET_TAB   = 'CRS DATA'
DASH_SHEET_ID   = '1ND1SBFknF1aD4iVA_1XtwXK_u7wEonFUVYesv5sZRXU'
DASH_SHEET_TAB  = 'Prop Level Dashboard'
LOG_SHEET_TAB   = 'Last Checked'          # tab in CRS sheet where run history is stored


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
        raise Exception(f"Tab '{CRS_SHEET_TAB}' not found. Available tabs: {tabs}")
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


# ── Last Checked log (stored in CRS sheet, "Last Checked" tab) ───────────────

LOG_HEADERS = [
    'Run At', 'Run By',
    'CRS Properties', 'SU Rows Analyzed', 'Excluded (not in CRS)',
    'Room-Rate Mismatch', 'Applicable Guests',
    'OBP Multiplier ≠1', 'OBP Extra Occ', 'OBP Missing Occ',
    'Missing EP/CP', 'Missing MAP/AP', 'Missing Other', 'Extra in SU',
    'OTA Live No Mapping', 'Mapped OTA Not Live',
]


def save_run_log(meta: dict, counts: dict, run_by: str = 'unknown'):
    """Append one row to the Last Checked sheet. Creates the tab if missing."""
    gc = _gc()
    wb = gc.open_by_key(CRS_SHEET_ID)
    try:
        ws = wb.worksheet(LOG_SHEET_TAB)
    except gspread.exceptions.WorksheetNotFound:
        ws = wb.add_worksheet(title=LOG_SHEET_TAB, rows=1000, cols=len(LOG_HEADERS))
        ws.append_row(LOG_HEADERS)

    row = [
        datetime.now().strftime('%Y-%m-%d %H:%M'),
        run_by,
        meta.get('crs_props', ''),
        meta.get('total_analyzed', ''),
        meta.get('su_excluded', ''),
        counts.get('rr', ''),
        counts.get('apg', ''),
        counts.get('obpv', ''),
        counts.get('obpoe', ''),
        counts.get('obpom', ''),
        counts.get('rpmicp', ''),
        counts.get('rpmimap', ''),
        counts.get('rpmi', ''),
        counts.get('rpex', ''),
        counts.get('chlive', ''),
        counts.get('chdead', ''),
    ]
    ws.append_row(row)


@st.cache_data(ttl=60, show_spinner=False)
def fetch_run_log() -> pd.DataFrame:
    """Read the Last Checked history sheet."""
    gc = _gc()
    wb = gc.open_by_key(CRS_SHEET_ID)
    try:
        ws = wb.worksheet(LOG_SHEET_TAB)
    except gspread.exceptions.WorksheetNotFound:
        return pd.DataFrame(columns=LOG_HEADERS)
    rows = ws.get_all_values()
    if len(rows) < 2:
        return pd.DataFrame(columns=LOG_HEADERS)
    return pd.DataFrame(rows[1:], columns=rows[0])
