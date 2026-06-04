import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="OTA Status", layout="wide", page_icon="📡")
st.title("📡 OTA Live Status")

if "results" not in st.session_state:
    st.warning("No results yet — go to the home page, upload the SU file and run checks.")
    st.stop()

res = st.session_state.results
dash_connected = bool(st.session_state.get("dash_raw"))

if not dash_connected:
    st.warning("Dashboard not connected — fetch the Prop Level Dashboard on the home page to enable these checks.")


def show_table(data, key, download_name):
    if not data:
        st.success("✅ No issues found.")
        return
    df = pd.DataFrame(data)
    search = st.text_input("Search", key=f"search_{key}", placeholder="Filter rows…")
    if search:
        mask = df.apply(lambda row: row.astype(str).str.contains(search, case=False, regex=False).any(), axis=1)
        df = df[mask]
    st.caption(f"{len(df):,} rows")
    st.dataframe(df, use_container_width=True, height=420)
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    st.download_button("⬇️ Download", buf.getvalue(), file_name=f"{download_name}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       key=f"dl_{key}")


tab1, tab2, tab3 = st.tabs([
    f"OTA Live, No Mapping  ({len(res.get('chlive', []))})",
    f"Mapped, OTA Not Live  ({len(res.get('chdead', []))})",
    f"Not in CRS (excluded)  ({len(res.get('ncrs', []))})",
])

with tab1:
    st.caption("Channel is Live in dashboard but no SU mapping exists for that property. Requires dashboard.")
    show_table(res.get("chlive", []), "chlive", "ota_live_no_mapping")

with tab2:
    st.caption("SU mapping exists for the row but that channel is not Live in dashboard. Requires dashboard.")
    show_table(res.get("chdead", []), "chdead", "mapped_ota_not_live")

with tab3:
    st.caption("SU rows excluded because the property ID was not found in CRS data.")
    show_table(res.get("ncrs", []), "ncrs", "not_in_crs")
