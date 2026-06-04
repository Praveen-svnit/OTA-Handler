import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="OBP Checks", layout="wide", page_icon="📊")
st.title("📊 OBP Checks")

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


tab1, tab2, tab3 = st.tabs([
    f"Multiplier ≠ 1  ({len(res.get('obpv', []))})",
    f"Extra Occ — Remove  ({len(res.get('obpoe', []))})",
    f"Missing Occ — Add  ({len(res.get('obpom', []))})",
])

with tab1:
    st.caption("OBP multiplier value is not 1 for one or more occupancy levels. Excl. channel 97.")
    show_table(res.get("obpv", []), "obpv", "obp_multiplier_issues")

with tab2:
    st.caption("Occupancy level exists in SU but exceeds internal max occupancy — should be removed.")
    show_table(res.get("obpoe", []), "obpoe", "obp_extra_occ")

with tab3:
    st.caption("Occupancy level required internally but missing in SU — needs to be added.")
    show_table(res.get("obpom", []), "obpom", "obp_missing_occ")
