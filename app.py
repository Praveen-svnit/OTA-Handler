import streamlit as st
import pandas as pd
import io

from core.sheets import fetch_crs_data, fetch_dashboard_raw
from core.checks import run_checks, CH_MAP
from core.utils import auto_detect

st.set_page_config(page_title="SU Mapping Checker", layout="wide", page_icon="🔍")

st.title("🔍 SU Mapping Checker")
st.caption("Upload the SU export — CRS data and dashboard are fetched automatically from Google Sheets.")

# ── Sidebar: connection status & last-run summary ────────────────────────────
with st.sidebar:
    st.header("Status")
    if "results" in st.session_state:
        meta = st.session_state.results.get("_meta", {})
        st.success("✅ Checks complete")
        st.metric("CRS Properties", meta.get("crs_props", "—"))
        st.metric("SU Rows Excluded", meta.get("su_excluded", "—"))
        st.metric("SU Rows Analyzed", meta.get("total_analyzed", "—"))
        st.divider()
        issues = {
            "Room-Rate Mismatch":      len(st.session_state.results.get("rr", [])),
            "OBP Multiplier Issues":   len(st.session_state.results.get("obpv", [])),
            "OBP Extra Occ":           len(st.session_state.results.get("obpoe", [])),
            "OBP Missing Occ":         len(st.session_state.results.get("obpom", [])),
            "Missing in SU — EP/CP":   len(st.session_state.results.get("rpmicp", [])),
            "Missing in SU — MAP/AP":  len(st.session_state.results.get("rpmimap", [])),
            "Missing in SU — Other":   len(st.session_state.results.get("rpmi", [])),
            "Extra in SU":             len(st.session_state.results.get("rpex", [])),
            "Applicable Guests":       len(st.session_state.results.get("apg", [])),
            "OTA Live No Mapping":     len(st.session_state.results.get("chlive", [])),
            "Mapped OTA Not Live":     len(st.session_state.results.get("chdead", [])),
            "Not in CRS":              len(st.session_state.results.get("ncrs", [])),
        }
        for label, count in issues.items():
            color = "🔴" if count > 0 else "🟢"
            st.write(f"{color} **{label}**: {count:,}")
    else:
        st.info("Run checks to see results.")

def read_uploaded_file(uploaded_file):
    """Read .xlsx/.xls including HTML-disguised .xls exports from hotel/OTA systems."""
    data = uploaded_file.read()

    # Strategy 1: standard Excel via pandas (xlsx or real xls)
    try:
        xl = pd.ExcelFile(io.BytesIO(data))
        sheets = xl.sheet_names
        dfs = [pd.read_excel(xl, sheet_name=s, dtype=str).fillna('') for s in sheets]
        return pd.concat(dfs, ignore_index=True), sheets
    except Exception:
        pass

    # Strategy 2: xlrd with corruption tolerance (handles slightly corrupt .xls)
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

    # Strategy 3: openpyxl (handles .xlsx disguised as .xls)
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

    # Strategy 4: HTML table exported as .xls
    for parser in ('lxml', 'html5lib', 'html.parser'):
        try:
            tables = pd.read_html(io.BytesIO(data), flavor=parser)
            if tables:
                df = pd.concat(tables, ignore_index=True).astype(str).fillna('')
                return df, ['Sheet1']
        except Exception:
            continue

    # Strategy 5: CSV exported as .xls
    for enc in ('utf-8', 'latin-1', 'cp1252'):
        try:
            df = pd.read_csv(io.BytesIO(data), dtype=str, encoding=enc).fillna('')
            return df, ['Sheet1']
        except Exception:
            continue

    raise Exception("Could not read file. Try opening it in Excel and saving as .xlsx, then re-upload.")


# ── Step 1: Upload SU file ────────────────────────────────────────────────────
st.subheader("1 · Upload SU Export")
uploaded = st.file_uploader("SU Excel file (all sheets will be combined)", type=["xlsx", "xls"])

if uploaded:
    try:
        with st.spinner("Reading file…"):
            su_df, sheets = read_uploaded_file(uploaded)
        st.success(f"✅ {len(su_df):,} rows loaded from {len(sheets)} sheet(s): {', '.join(sheets)}")
        st.session_state.su_df = su_df
        su_cols = list(su_df.columns)
    except Exception as e:
        st.error(str(e))
        su_cols = []
else:
    su_cols = []

# ── Step 2: Fetch Google Sheets ───────────────────────────────────────────────
st.subheader("2 · Fetch CRS & Dashboard")
col1, col2 = st.columns(2)

with col1:
    if st.button("🔄 Fetch CRS Data", use_container_width=True):
        fetch_crs_data.clear()
        try:
            with st.spinner("Fetching CRS data…"):
                crs_df = fetch_crs_data()
            st.session_state.crs_df = crs_df
            st.session_state.pop("crs_error", None)
        except Exception as e:
            st.session_state.crs_error = str(e)

    if "crs_df" in st.session_state:
        df = st.session_state.crs_df
        st.success(f"✅ CRS loaded: {len(df):,} rows, {len(df.columns)} columns")
    elif "crs_error" in st.session_state:
        st.error(f"CRS fetch failed: {st.session_state.crs_error}")
    else:
        st.info("Click to fetch CRS data from Google Sheets")

with col2:
    if st.button("🔄 Fetch Dashboard", use_container_width=True):
        fetch_dashboard_raw.clear()
        try:
            with st.spinner("Fetching dashboard…"):
                dash_raw = fetch_dashboard_raw()
            st.session_state.dash_raw = dash_raw
            st.session_state.pop("dash_error", None)
        except Exception as e:
            st.session_state.dash_error = str(e)

    if "dash_raw" in st.session_state and st.session_state.dash_raw:
        st.success(f"✅ Dashboard loaded: {len(st.session_state.dash_raw) - 1:,} properties")
    elif "dash_error" in st.session_state:
        st.warning(f"Dashboard fetch failed (OTA checks skipped): {st.session_state.dash_error}")
    else:
        st.info("Click to fetch Prop Level Dashboard (optional)")

crs_df  = st.session_state.get("crs_df")
dash_raw = st.session_state.get("dash_raw")

# ── Step 3: Column Configuration ─────────────────────────────────────────────
st.subheader("3 · Column Mapping")

if not su_cols or crs_df is None:
    st.info("Upload the SU file and fetch CRS data first.")
else:
    crs_cols = list(crs_df.columns)

    with st.expander("SU File Columns", expanded=True):
        sc1, sc2, sc3 = st.columns(3)
        with sc1:
            su_room_id = st.selectbox("PMS Room ID", su_cols,
                index=su_cols.index(auto_detect(su_cols, ['pms room'], ['room id'], ['roomid'])))
            su_rate_id = st.selectbox("PMS Rate ID", su_cols,
                index=su_cols.index(auto_detect(su_cols, ['pms rate'], ['rate id'], ['rateid'])))
        with sc2:
            su_obp = st.selectbox("OBP Multiplier Value", su_cols,
                index=su_cols.index(auto_detect(su_cols, ['obp'], ['multiplier'], ['occ'])))
            su_channel = st.selectbox("Channel Code", [None] + su_cols,
                index=([None] + su_cols).index(
                    auto_detect(su_cols, ['channel'], ['ota']) if su_cols else None
                ) if su_cols else 0)
        with sc3:
            su_prop_name = st.selectbox("Property Name (optional)", [None] + su_cols,
                index=([None] + su_cols).index(
                    auto_detect(su_cols, ['property name'], ['hotel name'], ['prop name']) if su_cols else None
                ) if su_cols else 0)
            su_app_guests = st.selectbox("Applicable Guests (optional)", [None] + su_cols,
                index=0)

    with st.expander("CRS / Internal File Columns", expanded=True):
        ic1, ic2, ic3 = st.columns(3)
        with ic1:
            int_prop_id = st.selectbox("Property ID", crs_cols,
                index=crs_cols.index(auto_detect(crs_cols, ['property id'], ['prop id'], ['hotel id'])))
            int_room_type = st.selectbox("Room Type ID", crs_cols,
                index=crs_cols.index(auto_detect(crs_cols, ['room type'], ['roomtype'])))
        with ic2:
            int_rate_code = st.selectbox("Rate Plan Code", crs_cols,
                index=crs_cols.index(auto_detect(crs_cols, ['rate plan'], ['rate code'], ['rate'])))
            int_max_occ = st.selectbox("Max Occupancy (optional)", [None] + crs_cols,
                index=([None] + crs_cols).index(
                    auto_detect(crs_cols, ['max occ'], ['occupancy'], ['max_occ']) if crs_cols else None
                ) if crs_cols else 0)
        with ic3:
            int_is_active = st.selectbox("Active filter (optional)", [None] + crs_cols,
                index=([None] + crs_cols).index(
                    auto_detect(crs_cols, ['is_active'], ['active'], ['status']) if crs_cols else None
                ) if crs_cols else 0)

    col_cfg = {
        'su': {
            'room_id':   su_room_id,
            'rate_id':   su_rate_id,
            'obp':       su_obp,
            'prop_name': su_prop_name,
            'channel':   su_channel,
            'app_guests': su_app_guests,
        },
        'int': {
            'prop_id':   int_prop_id,
            'room_type': int_room_type,
            'rate_code': int_rate_code,
            'max_occ':   int_max_occ,
            'is_active': int_is_active,
        },
    }
    st.session_state.col_cfg = col_cfg

    # ── Step 4: Run Checks ────────────────────────────────────────────────
    st.subheader("4 · Run Checks")
    if st.button("🚀 Run All Checks", type="primary", use_container_width=True):
        su_df = st.session_state.get("su_df")
        if su_df is None:
            st.error("Upload SU file first.")
        elif crs_df is None:
            st.error("Fetch CRS data first.")
        else:
            with st.spinner("Running checks…"):
                results = run_checks(su_df, crs_df, dash_raw, col_cfg)
            st.session_state.results = results
            meta = results["_meta"]
            st.success(
                f"✅ Done — {meta['total_analyzed']:,} rows analyzed · "
                f"{meta['su_excluded']:,} excluded (not in CRS) · "
                f"CRS base: {meta['crs_props']:,} properties"
            )
            st.info("Navigate to the check pages in the sidebar to see results.")

# ── Summary overview (after checks run) ──────────────────────────────────────
if "results" in st.session_state:
    st.subheader("Summary")
    res = st.session_state.results
    categories = [
        ("Room-Rate Mismatch",     "rr",      "🔴"),
        ("OBP Multiplier ≠ 1",    "obpv",    "🟠"),
        ("OBP Extra Occ",          "obpoe",   "🟠"),
        ("OBP Missing Occ",        "obpom",   "🟠"),
        ("Missing in SU — EP/CP",  "rpmicp",  "🔵"),
        ("Missing in SU — MAP/AP", "rpmimap", "🔵"),
        ("Missing in SU — Other",  "rpmi",    "🔵"),
        ("Extra in SU",            "rpex",    "🟣"),
        ("Applicable Guests",      "apg",     "🔴"),
        ("OTA Live No Mapping",    "chlive",  "🟠"),
        ("Mapped OTA Not Live",    "chdead",  "🟠"),
        ("Not in CRS (excluded)",  "ncrs",    "⚫"),
    ]
    cols = st.columns(4)
    for i, (label, key, icon) in enumerate(categories):
        count = len(res.get(key, []))
        with cols[i % 4]:
            st.metric(f"{icon} {label}", f"{count:,}")

    # Full export
    st.divider()
    if st.button("📥 Export All to Excel"):
        buf = io.BytesIO()
        sheet_map = {
            "Room-Rate Mismatch":   "rr",
            "OBP Multiplier":       "obpv",
            "OBP Extra Occ":        "obpoe",
            "OBP Missing Occ":      "obpom",
            "Missing SU - EP-CP":   "rpmicp",
            "Missing SU - MAP-AP":  "rpmimap",
            "Missing SU - Other":   "rpmi",
            "Extra in SU":          "rpex",
            "Applicable Guests":    "apg",
            "OTA Live No Mapping":  "chlive",
            "Mapped OTA Not Live":  "chdead",
            "Not in CRS":           "ncrs",
        }
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            for sheet_name, key in sheet_map.items():
                rows = res.get(key, [])
                if rows:
                    pd.DataFrame(rows).to_excel(writer, sheet_name=sheet_name, index=False)
        st.download_button(
            "⬇️ Download Excel",
            buf.getvalue(),
            file_name="su_mapping_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
