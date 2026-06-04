import gspread
import gspread.exceptions
import pandas as pd
import streamlit as st

CRS_SHEET_ID  = '1H2lP2zn4Ydeyex504DzmfBwXAX0Ip2H4SIu92DylRLw'
CRS_SHEET_TAB = 'CRS DATA'
DASH_SHEET_ID  = '1ND1SBFknF1aD4iVA_1XtwXK_u7wEonFUVYesv5sZRXU'
DASH_SHEET_TAB = 'Prop Level Dashboard'


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
