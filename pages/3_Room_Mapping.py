import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Room Mapping", layout="wide", page_icon="🏨")
st.title("🏨 Room Mapping Checks")

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


tab1, tab2 = st.tabs([
    f"Room-Rate Mismatch  ({len(res.get('rr', []))})",
    f"Applicable Guests Issue  ({len(res.get('apg', []))})",
])

with tab1:
    st.caption("Room type extracted from PMS Room ID ≠ room type from PMS Rate ID. Excl. ch 97.")
    show_table(res.get("rr", []), "rr", "room_rate_mismatch")

with tab2:
    st.caption("Non-ch 97 channel has a value in the Applicable Guests field (should be empty).")
    show_table(res.get("apg", []), "apg", "applicable_guests_issues")
