import streamlit as st
import pandas as pd
import io

from core.sheets import fetch_crs_data, fetch_dashboard_raw
from core.checks import run_checks, CH_MAP
from core.utils import auto_detect

st.set_page_config(page_title="SU Mapping Checker", layout="wide", page_icon="🔍")

st.markdown("""
<style>
/* Header */
.su-header { display:flex; align-items:center; gap:12px; margin-bottom:4px; }
.su-header h1 { margin:0; font-size:24px; }
.su-tag { background:#e8f4fd; color:#1a73e8; font-size:11px; font-weight:600;
          padding:3px 8px; border-radius:12px; }

/* Step labels */
.step-label { font-size:13px; font-weight:700; color:#555; text-transform:uppercase;
              letter-spacing:.5px; margin:18px 0 6px; }

/* Summary metric cards */
[data-testid="stMetric"] {
    background:#f8f9fa; border:1px solid #e9ecef;
    border-radius:8px; padding:10px 14px;
}

/* Result tabs — make scrollable for 12 items */
.stTabs [data-baseweb="tab-list"] { gap:2px; flex-wrap:nowrap; overflow-x:auto; }
.stTabs [data-baseweb="tab"] { font-size:12px; padding:6px 10px; white-space:nowrap; }

/* Table */
[data-testid="stDataFrame"] { border:1px solid #e9ecef; border-radius:6px; }

/* Issue count badge colours */
.cnt-red  { color:#dc3545; font-weight:700; }
.cnt-ok   { color:#198754; font-weight:700; }
</style>
""", unsafe_allow_html=True)

# ── Helpers ───────────────────────────────────────────────────────────────────
def _det(cols, *hints):
    """auto_detect wrapper; returns index into cols (0 if nothing found)."""
    v = auto_detect(cols, *hints)
    return cols.index(v) if v and v in cols else 0

def _det_opt(cols, *hints):
    """For [None]+cols selects; returns 0 (→ None) when nothing found."""
    v = auto_detect(cols, *hints)
    lst = [None] + cols
    return lst.index(v) if v and v in lst else 0

def read_uploaded_file(uploaded_file):
    data = uploaded_file.read()

    try:
        xl = pd.ExcelFile(io.BytesIO(data))
        sheets = xl.sheet_names
        dfs = [pd.read_excel(xl, sheet_name=s, dtype=str).fillna('') for s in sheets]
        return pd.concat(dfs, ignore_index=True), sheets
    except Exception:
        pass

    try:
        import xlrd
        book = xlrd.open_workbook(file_contents=data, ignore_workbook_corruption=True)
        sheets = book.sheet_names()
        dfs = []
        for sname in sheets:
            ws = book.sheet_by_name(sname)
            rows = [ws.row_values(i) for i in range(ws.nrows)]
            if rows:
                headers = [str(h) for h in rows[0]]
                body    = [[str(c) for c in r] for r in rows[1:]]
                dfs.append(pd.DataFrame(body, columns=headers))
        if dfs:
            return pd.concat(dfs, ignore_index=True), sheets
    except Exception:
        pass

    try:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        sheets = wb.sheetnames
        dfs = []
        for sname in sheets:
            ws = wb[sname]
            rows = list(ws.values)
            if rows:
                headers = [str(h) if h is not None else '' for h in rows[0]]
                body    = [[str(c) if c is not None else '' for c in r] for r in rows[1:]]
                dfs.append(pd.DataFrame(body, columns=headers))
        if dfs:
            return pd.concat(dfs, ignore_index=True), sheets
    except Exception:
        pass

    for parser in ('lxml', 'html5lib', 'html.parser'):
        try:
            tables = pd.read_html(io.BytesIO(data), flavor=parser)
            if tables:
                df = pd.concat(tables, ignore_index=True).fillna('').astype(str)
                return df, ['Sheet1']
        except Exception:
            continue

    for enc in ('utf-8', 'latin-1', 'cp1252'):
        try:
            df = pd.read_csv(io.BytesIO(data), dtype=str, encoding=enc).fillna('')
            return df, ['Sheet1']
        except Exception:
            continue

    raise Exception("Could not read file. Try opening it in Excel and saving as .xlsx, then re-upload.")


def show_table(data, key):
    if not data:
        st.success("No issues found.")
        return
    df = pd.DataFrame(data)
    search = st.text_input("Search / filter rows", key=f"s_{key}", placeholder="Type to filter…")
    if search:
        mask = df.apply(lambda r: r.astype(str).str.contains(search, case=False, regex=False).any(), axis=1)
        df = df[mask]
    st.caption(f"{len(df):,} row(s)")
    st.dataframe(df, use_container_width=True, height=420)
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    st.download_button("Download Excel", buf.getvalue(),
                       file_name=f"{key}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       key=f"dl_{key}")


# ── Header ────────────────────────────────────────────────────────────────────
st.markdown('<div class="su-header"><h1>🔍 SU Mapping Checker</h1>'
            '<span class="su-tag">FabHotels Internal</span></div>'
            '<p style="color:#666;font-size:13px;margin-bottom:20px">'
            'Validates SU channel manager data against CRS &amp; Prop Level Dashboard</p>',
            unsafe_allow_html=True)

# ── Step 1: Upload ────────────────────────────────────────────────────────────
st.markdown('<div class="step-label">Step 1 — Upload SU Export</div>', unsafe_allow_html=True)
uploaded = st.file_uploader("SU Excel file (.xlsx or .xls, all sheets combined)", type=["xlsx", "xls"])

if uploaded:
    try:
        with st.spinner("Reading file…"):
            su_df, sheets = read_uploaded_file(uploaded)
        st.success(f"{len(su_df):,} rows loaded from {len(sheets)} sheet(s): {', '.join(str(s) for s in sheets)}")
        st.session_state.su_df = su_df
        su_cols = list(su_df.columns)
    except Exception as e:
        st.error(str(e))
        su_cols = []
else:
    su_cols = list(st.session_state.su_df.columns) if "su_df" in st.session_state else []

# ── Step 2: Fetch CRS & Dashboard ────────────────────────────────────────────
st.markdown('<div class="step-label">Step 2 — Fetch CRS &amp; Dashboard</div>', unsafe_allow_html=True)
c1, c2 = st.columns(2)

with c1:
    if st.button("🔄 Fetch CRS Data", use_container_width=True):
        fetch_crs_data.clear()
        try:
            with st.spinner("Fetching CRS data…"):
                _crs = fetch_crs_data()
            st.session_state.crs_df = _crs
            st.session_state.pop("crs_error", None)
        except Exception as e:
            st.session_state.crs_error = str(e)
    if "crs_df" in st.session_state:
        _d = st.session_state.crs_df
        st.success(f"CRS loaded: {len(_d):,} rows · {len(_d.columns)} columns")
    elif "crs_error" in st.session_state:
        st.error(f"CRS fetch failed: {st.session_state.crs_error}")
    else:
        st.info("Click to fetch CRS data from Google Sheets")

with c2:
    if st.button("🔄 Fetch Dashboard", use_container_width=True):
        fetch_dashboard_raw.clear()
        try:
            with st.spinner("Fetching dashboard…"):
                _dash = fetch_dashboard_raw()
            st.session_state.dash_raw = _dash
            st.session_state.pop("dash_error", None)
        except Exception as e:
            st.session_state.dash_error = str(e)
    if "dash_raw" in st.session_state and st.session_state.dash_raw:
        st.success(f"Dashboard loaded: {len(st.session_state.dash_raw) - 1:,} properties")
    elif "dash_error" in st.session_state:
        st.warning(f"Dashboard fetch failed (OTA live checks skipped): {st.session_state.dash_error}")
    else:
        st.info("Click to fetch Prop Level Dashboard (optional)")

crs_df   = st.session_state.get("crs_df")
dash_raw = st.session_state.get("dash_raw")

# ── Step 3: Column Mapping ────────────────────────────────────────────────────
st.markdown('<div class="step-label">Step 3 — Column Mapping</div>', unsafe_allow_html=True)

if not su_cols or crs_df is None:
    st.info("Upload the SU file and fetch CRS data first.")
else:
    crs_cols = list(crs_df.columns)

    with st.expander("SU File Columns", expanded=True):
        sc1, sc2, sc3 = st.columns(3)
        with sc1:
            su_room_id = st.selectbox("PMS Room ID", su_cols,
                index=_det(su_cols, ['pms room'], ['room id'], ['roomid']))
            su_rate_id = st.selectbox("PMS Rate ID", su_cols,
                index=_det(su_cols, ['pms rate'], ['rate id'], ['rateid']))
        with sc2:
            su_obp = st.selectbox("OBP Multiplier Value", su_cols,
                index=_det(su_cols, ['obp'], ['multiplier'], ['occ']))
            su_channel = st.selectbox("Channel Code", [None] + su_cols,
                index=_det_opt(su_cols, ['channel'], ['ota']))
        with sc3:
            su_prop_name = st.selectbox("Property Name (optional)", [None] + su_cols,
                index=_det_opt(su_cols, ['property name'], ['hotel name'], ['prop name']))
            su_app_guests = st.selectbox("Applicable Guests (optional)", [None] + su_cols, index=0)

    with st.expander("CRS / Internal Columns", expanded=True):
        ic1, ic2, ic3 = st.columns(3)
        with ic1:
            int_prop_id = st.selectbox("Property ID", crs_cols,
                index=_det(crs_cols, ['property id'], ['prop id'], ['hotel id']))
            int_room_type = st.selectbox("Room Type ID", crs_cols,
                index=_det(crs_cols, ['room type'], ['roomtype']))
        with ic2:
            int_rate_code = st.selectbox("Rate Plan Code", crs_cols,
                index=_det(crs_cols, ['rate plan'], ['rate code'], ['rate']))
            int_max_occ = st.selectbox("Max Occupancy (optional)", [None] + crs_cols,
                index=_det_opt(crs_cols, ['max occ'], ['max_occ'], ['max occupancy'],
                               ['maximum occupancy'], ['maxocc'], ['pax'], ['max pax']))
        with ic3:
            int_is_active = st.selectbox("Active filter (optional)", [None] + crs_cols,
                index=_det_opt(crs_cols, ['is_active'], ['is active']))

    col_cfg = {
        'su':  {'room_id': su_room_id, 'rate_id': su_rate_id, 'obp': su_obp,
                'prop_name': su_prop_name, 'channel': su_channel, 'app_guests': su_app_guests},
        'int': {'prop_id': int_prop_id, 'room_type': int_room_type, 'rate_code': int_rate_code,
                'max_occ': int_max_occ, 'is_active': int_is_active},
    }
    st.session_state.col_cfg = col_cfg

    # ── Parse preview ─────────────────────────────────────────────────────────
    with st.expander("Verify parsed IDs (check column mapping is correct)", expanded=False):
        from core.utils import norm_id, parse_pms_rate, parse_pms_room
        _su_prev = st.session_state.get("su_df")
        if _su_prev is not None:
            _sample = _su_prev.head(10)
            rows_preview = []
            for _, r in _sample.iterrows():
                rm = parse_pms_room(r.get(su_room_id, ''))
                rt = parse_pms_rate(r.get(su_rate_id, ''))
                ch_raw = r.get(su_channel, '') if su_channel else ''
                rows_preview.append({
                    'PMS Room ID (raw)':     rm['raw'],
                    'Room → PropID':         rm['propId'],
                    'Room → RoomType':       rm['roomType'],
                    'PMS Rate ID (raw)':     rt['raw'],
                    'Rate → PropID':         rt['propId'],
                    'Rate → RoomType':       rt['roomType'],
                    'Rate → RateCode':       rt['rateCode'],
                    'Channel (raw)':         str(ch_raw),
                    'Channel (normalized)':  norm_id(str(ch_raw)),
                    'RoomType match?':       '✅' if rm['roomType'] == rt['roomType'] else '❌ MISMATCH',
                })
            st.caption("First 10 SU rows — verify PropID and RoomType are parsed correctly")
            st.dataframe(pd.DataFrame(rows_preview), use_container_width=True)

            # Also show a sample of CRS property IDs for comparison
            st.caption("Sample CRS Property IDs (from selected column)")
            _crs_sample = crs_df[int_prop_id].apply(norm_id).drop_duplicates().head(10).reset_index(drop=True)
            st.write(_crs_sample.tolist())

    # ── Step 4: Run ───────────────────────────────────────────────────────────
    st.markdown('<div class="step-label">Step 4 — Run Checks</div>', unsafe_allow_html=True)
    if st.button("🚀 Run All Checks", type="primary", use_container_width=True):
        _su = st.session_state.get("su_df")
        if _su is None:
            st.error("Upload SU file first.")
        else:
            with st.spinner("Running checks…"):
                results = run_checks(_su, crs_df, dash_raw, col_cfg)
            st.session_state.results = results
            _m = results["_meta"]
            st.success(
                f"Done — {_m['total_analyzed']:,} rows analyzed · "
                f"{_m['su_excluded']:,} excluded (not in CRS) · "
                f"CRS base: {_m['crs_props']:,} properties"
            )
            st.rerun()

# ── Results ───────────────────────────────────────────────────────────────────
if "results" in st.session_state:
    res  = st.session_state.results
    meta = res.get("_meta", {})

    st.divider()

    # Summary row
    m1, m2, m3 = st.columns(3)
    m1.metric("CRS Properties", f"{meta.get('crs_props', 0):,}")
    m2.metric("SU Rows Analyzed", f"{meta.get('total_analyzed', 0):,}")
    m3.metric("Excluded (not in CRS)", f"{meta.get('su_excluded', 0):,}")

    st.markdown("#### Check Results")

    CHECKS = [
        ("rr",      "Room-Rate Mismatch",       "Room type in PMS Room ID ≠ PMS Rate ID (excl. ch 97)"),
        ("obpv",    "OBP Multiplier ≠ 1",        "Multiplier value is not 1 (excl. ch 97)"),
        ("obpoe",   "OBP Extra Occ",             "Occupancy in SU exceeds internal max — should be removed"),
        ("obpom",   "OBP Missing Occ",           "Occupancy present internally but missing in SU — needs to be added"),
        ("rpmicp",  "Missing in SU — EP/CP",     "EP or CP rate plans available internally but not pushed to SU"),
        ("rpmimap", "Missing in SU — MAP/AP",    "MAP or AP rate plans available internally but not pushed to SU"),
        ("rpmi",    "Missing in SU — Other",     "Other rate plans available internally but not pushed to SU"),
        ("rpex",    "Extra in SU",               "Rate plans mapped in SU but not found internally"),
        ("apg",     "Applicable Guests Issue",   "Non-ch 97 channel has a value in Applicable Guests"),
        ("chlive",  "OTA Live — No SU Mapping",  "OTA is Live in dashboard but no mapping found in SU"),
        ("chdead",  "Mapped — OTA Not Live",     "Mapping exists in SU but OTA is not Live in dashboard"),
        ("ncrs",    "Not in CRS (excluded)",     "SU rows whose Property ID was not found in CRS data"),
    ]

    def _tab_label(k, lbl):
        n = len(res.get(k, []))
        color = "🔴" if n > 0 and k not in ("ncrs",) else ("⚫" if k == "ncrs" and n > 0 else "🟢")
        return f"{color} {lbl} ({n:,})"

    tabs = st.tabs([_tab_label(k, lbl) for k, lbl, _ in CHECKS])

    for i, (k, lbl, desc) in enumerate(CHECKS):
        with tabs[i]:
            st.caption(desc)
            show_table(res.get(k, []), k)

    # Full export
    st.divider()
    if st.button("📥 Export All Sheets to Excel"):
        buf = io.BytesIO()
        sheet_names = {
            "Room-Rate Mismatch":  "rr",
            "OBP Multiplier":      "obpv",
            "OBP Extra Occ":       "obpoe",
            "OBP Missing Occ":     "obpom",
            "Missing SU - EP-CP":  "rpmicp",
            "Missing SU - MAP-AP": "rpmimap",
            "Missing SU - Other":  "rpmi",
            "Extra in SU":         "rpex",
            "Applicable Guests":   "apg",
            "OTA Live No Mapping": "chlive",
            "Mapped OTA Not Live": "chdead",
            "Not in CRS":          "ncrs",
        }
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            for sheet, key in sheet_names.items():
                rows = res.get(key, [])
                if rows:
                    pd.DataFrame(rows).to_excel(writer, sheet_name=sheet, index=False)
        st.download_button(
            "⬇️ Download Full Report",
            buf.getvalue(),
            file_name="su_mapping_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
