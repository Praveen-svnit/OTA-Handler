import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Rate Plan Checks", layout="wide", page_icon="📋")
st.title("📋 Rate Plan Checks")

if "results" not in st.session_state:
    st.warning("No results yet — go to the home page, upload the SU file and run checks.")
    st.stop()

res = st.session_state.results


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


tab1, tab2, tab3, tab4 = st.tabs([
    f"Missing EP/CP  ({len(res.get('rpmicp', []))})",
    f"Missing MAP/AP  ({len(res.get('rpmimap', []))})",
    f"Missing Other  ({len(res.get('rpmi', []))})",
    f"Extra in SU  ({len(res.get('rpex', []))})",
])

with tab1:
    st.caption("EP or CP rate plan exists in CRS but is not pushed to SU for this channel. Excl. ch 97.")
    show_table(res.get("rpmicp", []), "rpmicp", "missing_su_ep_cp")

with tab2:
    st.caption("MAP or AP rate plan exists in CRS but is not pushed to SU for this channel. Excl. ch 97.")
    show_table(res.get("rpmimap", []), "rpmimap", "missing_su_map_ap")

with tab3:
    st.caption("Other rate plan codes in CRS not pushed to SU. Excl. ch 97.")
    show_table(res.get("rpmi", []), "rpmi", "missing_su_other")

with tab4:
    st.caption("Rate plan mapped in SU but not found in CRS data. Excl. ch 97.")
    show_table(res.get("rpex", []), "rpex", "extra_in_su")
