import gspread
import gspread.exceptions
import pandas as pd
import streamlit as st

CRS_SHEET_ID  = '1H2lP2zn4Ydeyex504DzmfBwXAX0Ip2H4SIu92DylRLw'
CRS_SHEET_TAB = 'CRS DATA'
DASH_SHEET_ID  = '1ND1SBFknF1aD4iVA_1XtwXK_u7wEonFUVYesv5sZRXU'
DASH_SHEET_TAB = 'Prop Level Dashboard'


def _get_gc():
    return gspread.service_account_from_dict(st.secrets["gcp_service_account"])


@st.cache_data(ttl=300, show_spinner=False)
def fetch_crs_data() -> pd.DataFrame:
    gc = _get_gc()
    spreadsheet = gc.open_by_key(CRS_SHEET_ID)
    try:
        ws = spreadsheet.worksheet(CRS_SHEET_TAB)
    except gspread.exceptions.WorksheetNotFound:
        available = [w.title for w in spreadsheet.worksheets()]
        raise Exception(f"Tab '{CRS_SHEET_TAB}' not found. Available tabs: {available}")
    return pd.DataFrame(ws.get_all_records())


@st.cache_data(ttl=300, show_spinner=False)
def fetch_dashboard_raw() -> list:
    """Returns list-of-lists (row 0 = headers) for column-index access."""
    gc = _get_gc()
    ws = gc.open_by_key(DASH_SHEET_ID).worksheet(DASH_SHEET_TAB)
    return ws.get_all_values()
