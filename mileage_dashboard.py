"""
Mileage Dashboard (Streamlit)
-----------------------------

Interactive dashboard on top of your existing mileage_process.py logic.

- Reuses:
    - pick_input_csvs()
    - load_all_csvs()
    - load_and_prepare()
    - aggregate_by_vehicle()

Run with:
    streamlit run mileage_dashboard.py
"""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
import io
import xlsxwriter
import mileage_process as mp  # your existing script

# ✅ Debug helpers
import traceback
import time

# ---------------------------
# Driver → Google Sheet (published CSV) mapping
# ---------------------------
DRIVER_SHEET_URLS = {
    "Matthew": "https://docs.google.com/spreadsheets/d/e/2PACX-1vSU_J201N5H6rYm0nHh8_Cd1AF-eKAmFIsyrJgNLScdPuMOKW5o0FnVcbBmIvYwYltNmhqCpcvjQvr_/pub?gid=2101586830&single=true&output=csv",
    "Yuri": "https://docs.google.com/spreadsheets/d/e/2PACX-1vT1qTAuNmBmXRKZqf3AgMfOZRfdcgcstRxgXpucxt2dDzIncMUuLfpLAoTaYnx4j0EbVeT_vbcnZZF8/pub?gid=1436279778&single=true&output=csv",
    "Theresa": "https://docs.google.com/spreadsheets/d/e/2PACX-1vSz4wR34RnDlwsgeikOR2xT9kb6IEhCAC6Vz8mzILs9dAoFGjdd6_PNFl25M2qcOyCZH-BiYPMaHwzP/pub?gid=109890295&single=true&output=csv",
    "Amy": "https://docs.google.com/spreadsheets/d/e/2PACX-1vQo8hJXEpCgvzz0CXCk85JBjIoLYfB4J0wy-fHr9UlXtUmFccrVPrjL00WAck563CsEi_1KZ-Ghl-f8/pub?gid=2091739000&single=true&output=csv",
    "Scott":"https://docs.google.com/spreadsheets/d/e/2PACX-1vRtU7Vr75rc0NV0Ly7IqTAl4v8XraWXyHmtAFGVeXolYG2Z5PsXOek7TKl7pQ6txaQt_oZaKXXbNUeY/pub?gid=270074134&single=true&output=csv"
}

# ---------------------------
# Streamlit page config
# ---------------------------
st.set_page_config(
    page_title="Mileage Dashboard",
    layout="wide",
)

# ---------------------------
# Debug logger (stores messages; only renders if DEBUG_MODE True)
# ---------------------------
def dbg(msg: str, data=None):
    """
    Lightweight debug logger:
    - stores messages in st.session_state.debug_log
    - optionally renders live when DEBUG_MODE is enabled
    """
    if "debug_log" not in st.session_state:
        st.session_state.debug_log = []

    stamp = time.strftime("%H:%M:%S")
    line = f"[{stamp}] {msg}"
    st.session_state.debug_log.append(line)

    if st.session_state.get("DEBUG_MODE", False):
        st.write(line)
        if data is not None:
            st.write(data)

# ---------------------------
# Authentication gate
# ---------------------------
if not st.user.is_logged_in:
    st.title("🚗 Mileage Dashboard")
    st.write("Please log in to access this app.")

    if st.button("Log in with Google"):
        st.login()

    st.stop()

st.caption(f"Logged in as: {st.user.email}")

# ---------------------------
# Authorization (whitelist)
# ---------------------------
ALLOWED_EMAILS = {
    "brandonkeithmarkham@gmail.com",
    "laura.miggins@gmail.com",
    "jasonlee091488@gmail.com",
    "elderwheelsatx@gmail.com",
    "elderewheelsoffice@gmail.com",
    "sacredrootsaustin@gmail.com",
}

if st.user.email not in ALLOWED_EMAILS:
    st.error("🚫 You are not authorized to access this application.")
    st.stop()

# ---------------------------
# Debug access control (only you)
# ---------------------------
DEBUG_ALLOWED_EMAILS = {"brandonkeithmarkham@gmail.com"}

def can_debug() -> bool:
    return bool(getattr(st.user, "is_logged_in", False)) and (getattr(st.user, "email", "") in DEBUG_ALLOWED_EMAILS)

# ---------------------------
# Data loading using your code, but from Google Sheets
# ---------------------------
@st.cache_data(ttl=300)  # cache 5 minutes to avoid hammering Google
def load_data():
    """
    Load mileage data from the published Google Sheets for each driver,
    then reuse the existing mileage_process pipeline.
    """
    frames = []
    sheet_errors = []

    for driver_name, sheet_url in DRIVER_SHEET_URLS.items():
        try:
            tmp = pd.read_csv(sheet_url)
            tmp.columns = tmp.columns.str.strip()
            tmp["Driver"] = driver_name
            frames.append(tmp)
        except Exception as e:
            sheet_errors.append((driver_name, str(e)))
            continue

    if not frames:
        raise SystemExit("No driver sheets could be loaded. Check DRIVER_SHEET_URLS.")

    raw_df = pd.concat(frames, ignore_index=True)

    # Reuse your existing processing logic
    df = mp.load_and_prepare(raw_df)
    summary = mp.aggregate_by_vehicle(df)

    sources = list(DRIVER_SHEET_URLS.keys())

    return sources, raw_df, df, summary, sheet_errors

# ---------------------------
# Build master Excel workbook (Summary + Details)
# ---------------------------
def build_master_excel(df: pd.DataFrame, summary: pd.DataFrame) -> io.BytesIO:
    """
    Create an in-memory Excel file with:
      - 'Summary' sheet: aggregated mileage by vehicle
      - 'Details' sheet: all prepared rows

    Styling (via xlsxwriter):
      - Bold yellow header row
      - Borders around all cells
      - Auto-fit columns
      - Frozen header row
    """
    summary_export = summary.rename(
        columns={
            "Commute_Miles": "Commute Miles",
            "Business_Miles": "Business Miles",
            "Total_Miles": "Total Miles",
        }
    )

    buffer = io.BytesIO()

    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        summary_df = summary_export.reset_index()
        details_df = df.copy()

        summary_df.to_excel(writer, sheet_name="Summary", index=False)
        details_df.to_excel(writer, sheet_name="Details", index=False)

        workbook = writer.book

        header_format = workbook.add_format({"bold": True, "bg_color": "#FFFF99", "border": 1})
        cell_border = workbook.add_format({"border": 1})

        def style_sheet(sheet_name: str, data: pd.DataFrame) -> None:
            ws = writer.sheets[sheet_name]
            n_rows, n_cols = data.shape

            ws.freeze_panes(1, 0)

            for col_idx, col_name in enumerate(data.columns):
                ws.write(0, col_idx, col_name, header_format)

                col_series = data[col_name].astype(str)
                max_len = max(
                    col_series.map(len).max() if not col_series.empty else 0,
                    len(str(col_name)),
                )
                ws.set_column(col_idx, col_idx, max_len + 2)

            if n_cols > 0:
                ws.conditional_format(
                    0, 0, n_rows, n_cols - 1,
                    {"type": "no_blanks", "format": cell_border},
                )
                ws.conditional_format(
                    0, 0, n_rows, n_cols - 1,
                    {"type": "blanks", "format": cell_border},
                )

        style_sheet("Summary", summary_df)
        style_sheet("Details", details_df)

    buffer.seek(0)
    return buffer

def main():
    st.title("🚗 Mileage Dashboard")

    # ---------------------------
    # Debug UI (ADMIN ONLY)
    # ---------------------------
    if can_debug():
        with st.sidebar:
            st.markdown("### Debug (Admin)")
            st.session_state.DEBUG_MODE = st.toggle("Enable debug mode", value=False)

            if st.button("Clear debug log"):
                st.session_state.debug_log = []

            if st.session_state.get("DEBUG_MODE", False) and st.session_state.get("debug_log"):
                st.markdown("**Debug log:**")
                st.code("\n".join(st.session_state.debug_log[-250:]))
    else:
        # Force debug off for everyone else
        st.session_state.DEBUG_MODE = False

    try:
        dbg("App start: entering main()")

        if st.button("🔄 Refresh data now"):
            dbg("Refresh requested: clearing cache_data")
            st.cache_data.clear()

        dbg("Calling load_data()")
        sources, raw_df, df, summary, sheet_errors = load_data()

        dbg("load_data() returned", {
            "sources": sources,
            "raw_df_shape": raw_df.shape if raw_df is not None else None,
            "df_shape": df.shape if df is not None else None,
            "summary_shape": summary.shape if summary is not None else None,
            "sheet_errors_count": len(sheet_errors),
        })

        # Only show sheet load errors to admin in debug mode
        if sheet_errors and can_debug() and st.session_state.get("DEBUG_MODE", False):
            st.warning("Some driver sheets failed to load (admin view).")
            st.write(sheet_errors)

        if df is None or summary is None:
            dbg("ERROR: df or summary is None", {"df_is_none": df is None, "summary_is_none": summary is None})
            st.error("Data processing returned None unexpectedly. Please contact Brandon.")
            st.stop()

        # ---------------------------
        # Export
        # ---------------------------
        st.subheader("Export")

        dbg("Building master Excel")
        master_excel = build_master_excel(df, summary)

        # ✅ pass bytes, not BytesIO
        excel_bytes = master_excel.getvalue()
        dbg("Master Excel built", {"bytes_len": len(excel_bytes)})

        st.download_button(
            label="📥 Download full master Excel report (all drivers, all vehicles)",
            data=excel_bytes,
            file_name="mileage_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        # ---------------------------
        # Sidebar filters
        # ---------------------------
        st.sidebar.header("Filters")
        st.sidebar.markdown("**Drivers (data sources):**")
        for name in sources:
            st.sidebar.write(f"- {name}")

        # Driver filter
        if "Driver" in df.columns:
            driver_list = sorted(df["Driver"].dropna().unique())
        else:
            driver_list = []

        dbg("Driver list computed", {"driver_list": driver_list})

        selected_drivers = st.sidebar.multiselect("Filter by driver:", driver_list, default=driver_list)

        df_filtered = df.copy()
        if selected_drivers and "Driver" in df_filtered.columns:
            df_filtered = df_filtered[df_filtered["Driver"].isin(selected_drivers)]

        dbg("df_filtered after driver filter", {"shape": df_filtered.shape})

        summary_driver = mp.aggregate_by_vehicle(df_filtered)
        dbg("summary_driver recomputed", {"shape": summary_driver.shape})

        vehicles = sorted(summary_driver.index.tolist())
        selected_vehicles = st.sidebar.multiselect("Select vehicle(s):", vehicles, default=vehicles)

        if selected_vehicles:
            filtered_summary = summary_driver.loc[selected_vehicles]
        else:
            filtered_summary = summary_driver

        dbg("filtered_summary prepared", {"shape": filtered_summary.shape})

        summary_display = filtered_summary.rename(
            columns={
                "Commute_Miles": "Commute Miles",
                "Business_Miles": "Business Miles",
                "Total_Miles": "Total Miles",
            }
        ).round(2)

        # ---------------------------
        # Metrics
        # ---------------------------
        st.subheader("Overall Mileage Totals")

        total_business = filtered_summary["Business_Miles"].sum()
        total_commute = filtered_summary["Commute_Miles"].sum()
        total_miles = filtered_summary["Total_Miles"].sum()

        col1, col2, col3 = st.columns(3)
        col1.metric("Business Miles", f"{total_business:,.1f}")
        col2.metric("Commute Miles", f"{total_commute:,.1f}")
        col3.metric("Total Miles", f"{total_miles:,.1f}")

        # ---------------------------
        # Summary table
        # ---------------------------
        st.subheader("Mileage Summary by Vehicle")
        st.dataframe(summary_display, use_container_width=True)

        # ---------------------------
        # Charts
        # ---------------------------
        st.subheader("Charts")

        chart_col1, chart_col2 = st.columns(2)

        with chart_col1:
            st.markdown("**Total Miles by Vehicle**")
            fig1, ax1 = plt.subplots()
            ax1.bar(summary_display.index, summary_display["Total Miles"])
            ax1.set_ylabel("Miles")
            ax1.set_xlabel("Vehicle")
            ax1.set_title("Total Miles by Vehicle")
            plt.xticks(rotation=30, ha="right")
            st.pyplot(fig1)

        st.markdown("**Commute vs Business Miles by Vehicle (Pie Charts)**")

        num_vehicles = len(filtered_summary)
        if num_vehicles > 0:
            cols = 3
            rows = (num_vehicles + cols - 1) // cols

            fig, axes = plt.subplots(rows, cols, figsize=(cols * 4, rows * 4))

            if rows * cols == 1:
                axes = [axes]
            else:
                axes = axes.flatten()

            labels = ["Business", "Commute"]

            for ax, (vehicle, row) in zip(axes, filtered_summary.iterrows()):
                values = [row["Business_Miles"], row["Commute_Miles"]]
                total = sum(values)

                if total <= 0:
                    ax.text(0.5, 0.5, "No data", ha="center", va="center")
                    ax.set_title(vehicle)
                    ax.axis("off")
                    continue

                ax.pie(values, labels=labels, autopct="%1.1f%%", startangle=90)
                ax.set_title(vehicle)
                ax.axis("equal")

            for ax in axes[num_vehicles:]:
                ax.axis("off")

            fig.tight_layout()
            st.pyplot(fig)
        else:
            st.info("No vehicles selected for pie charts.")

        # ---------------------------
        # Details / Data quality
        # ---------------------------
        st.subheader("Detailed Data")

        tab1, tab2, tab3 = st.tabs(["All Rows (Prepared)", "Raw Imported Data", "Potential Issues"])

        with tab1:
            st.markdown(
                "This is the fully prepared dataset after column normalization, "
                "mileage calculation, and commute flagging."
            )
            st.dataframe(df_filtered, use_container_width=True)

        with tab2:
            st.markdown("This is the raw combined DataFrame loaded from all driver Google Sheets.")
            st.dataframe(raw_df, use_container_width=True)

        with tab3:
            st.markdown("Rows with NaN or negative miles (if any).")
            if "_row_ok" in df_filtered.columns:
                issues = df_filtered[~df_filtered["_row_ok"]].copy()
            else:
                issues = pd.DataFrame()

            if issues.empty:
                st.success("✅ No row-level issues detected.")
            else:
                st.warning(f"⚠ {len(issues)} issue row(s) found:")
                st.dataframe(issues, use_container_width=True)

        dbg("main() completed successfully")

    except Exception as e:
        dbg("FATAL EXCEPTION hit", str(e))

        # Client-safe message
        st.error("Something went wrong. Please contact Brandon for support.")

        # Only show traceback to admin when debug toggle is enabled
        if can_debug() and st.session_state.get("DEBUG_MODE", False):
            st.code(traceback.format_exc())

        st.stop()

if __name__ == "__main__":
    main()
