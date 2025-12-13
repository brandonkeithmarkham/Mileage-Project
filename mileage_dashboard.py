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

# ---------------------------
# Driver → Google Sheet (published CSV) mapping
# ---------------------------
DRIVER_SHEET_URLS = {
     "Matthew":"https://docs.google.com/spreadsheets/d/e/2PACX-1vTGcp1pt0bM4eKOdeUIn7jp4PIiuVf5Q2snBk8Tr9fc0kQg553-tObI58fyH4fcozmd3WgYwF6RJcJk/pub?gid=0&single=true&output=csv",
     "Yuri":"https://docs.google.com/spreadsheets/d/e/2PACX-1vSKC_Kj5Jbravp-RpmOOeZd_JxVQug1Jq4mt1gCYFIRL88GPO8fEwNCaooH47rGJTKdKjD18ceHF9TU/pub?gid=0&single=true&output=csv",
     "Theresa":"https://docs.google.com/spreadsheets/d/e/2PACX-1vRoqxBfrk20Hlb-foWIhLqBQwYDoYQzJ7XUKnScd5WjxM5XHr5MmBGECkCAh62oq3zXI3tMxkVLFgMP/pub?gid=0&single=true&output=csv",
}



# ---------------------------
# Streamlit page config
# ---------------------------
st.set_page_config(
    page_title="Mileage Dashboard",
    layout="wide",
)
# ---------------------------
# Authentication gate
# ---------------------------
if not st.user.is_logged_in:
    st.title("🚗 Mileage Dashboard")
    st.write("Please log in to access this app.")

    # Uses the [auth] config from your Streamlit secrets
    if st.button("Log in with Google"):
        st.login()  # default provider from [auth]

    st.stop()  # Don't run the rest of the app for anonymous users

# Optional: show who is logged in
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
    "sacredrootsaustin@gmail.com"
}

if st.user.email not in ALLOWED_EMAILS:
    st.error("🚫 You are not authorized to access this application.")
    st.stop()



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
    for driver_name, sheet_url in DRIVER_SHEET_URLS.items():
        try:
            tmp = pd.read_csv(sheet_url)
        except Exception as e:
            # If one sheet is broken, skip it but log a warning in the UI later
            # You could also collect these errors in a list if you want.
            continue
        tmp.columns = tmp.columns.str.strip()    
        # Tag each row with the driver name
        tmp["Driver"] = driver_name
        frames.append(tmp)

    if not frames:
        raise SystemExit("No driver sheets could be loaded. Check DRIVER_SHEET_URLS.")

    # Combine all driver sheets into one raw DataFrame
    raw_df = pd.concat(frames, ignore_index=True)

    # Reuse your existing processing logic
    df = mp.load_and_prepare(raw_df)
    summary = mp.aggregate_by_vehicle(df)

    # Instead of CSV files, we just keep a list of driver names as "sources"
    sources = list(DRIVER_SHEET_URLS.keys())

    return sources, raw_df, df, summary

# ---------------------------
# Build master Excel workbook (Summary + Details), like mileage_process.py
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
    # Rename columns for consistency with your reports
    summary_export = summary.rename(
        columns={
            "Commute_Miles": "Commute Miles",
            "Business_Miles": "Business Miles",
            "Total_Miles": "Total Miles",
        }
    )

    buffer = io.BytesIO()

    # Use xlsxwriter engine
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        # Write data first (let pandas handle NaNs etc.)
        summary_df = summary_export.reset_index()
        details_df = df.copy()

        summary_df.to_excel(writer, sheet_name="Summary", index=False)
        details_df.to_excel(writer, sheet_name="Details", index=False)

        workbook = writer.book

        # Styles
        header_format = workbook.add_format(
            {"bold": True, "bg_color": "#FFFF99", "border": 1}
        )
        cell_border = workbook.add_format({"border": 1})

        # Helper to style a sheet
        def style_sheet(sheet_name: str, data: pd.DataFrame) -> None:
            ws = writer.sheets[sheet_name]
            n_rows, n_cols = data.shape

            # Freeze header row
            ws.freeze_panes(1, 0)

            # Header styling + column widths
            for col_idx, col_name in enumerate(data.columns):
                # Overwrite header cell with styling
                ws.write(0, col_idx, col_name, header_format)

                # Auto-fit: max length of header or any cell in this column
                col_series = data[col_name].astype(str)
                max_len = max(col_series.map(len).max() if not col_series.empty else 0,
                              len(str(col_name)))
                ws.set_column(col_idx, col_idx, max_len + 2)

            # Apply borders to all used cells via conditional formatting
            if n_cols > 0:
                # rows 0..n_rows, cols 0..n_cols-1
                ws.conditional_format(
                    0, 0, n_rows, n_cols - 1,
                    {"type": "no_blanks", "format": cell_border},
                )
                ws.conditional_format(
                    0, 0, n_rows, n_cols - 1,
                    {"type": "blanks", "format": cell_border},
                )

        # Style both sheets
        style_sheet("Summary", summary_df)
        style_sheet("Details", details_df)

    buffer.seek(0)
    return buffer




def main():
    st.title("🚗 Mileage Dashboard")
    if st.button("🔄 Refresh data now"):
        st.cache_data.clear()

    # Try to load data; show a friendly error if no files are found
    try:
        sources, raw_df, df, summary = load_data()
    except SystemExit as e:
        st.error(
            "No driver mileage data could be loaded.\n\n"
            "Check that DRIVER_SHEET_URLS is populated with valid published "
            "Google Sheets CSV URLs and that the sheets are accessible."
        )
        return

    # ---------------------------
    # Master export download
    # ---------------------------
    st.subheader("Export")

    master_excel = build_master_excel(df, summary)

    st.download_button(
        label="📥 Download full master Excel report (all drivers, all vehicles)",
        data=master_excel,
        file_name="mileage_report.xlsx",
        mime=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
    )

    # ---------------------------
    # Sidebar: basic info + filters
    # ---------------------------
    st.sidebar.header("Filters")

    # Show which drivers are configured as data sources
    st.sidebar.markdown("**Drivers (data sources):**")
    for name in sources:
        st.sidebar.write(f"- {name}")

    # --- Driver filter ---
    if "Driver" in df.columns:
        driver_list = sorted(df["Driver"].dropna().unique())
    else:
        driver_list = []

    selected_drivers = st.sidebar.multiselect(
        "Filter by driver:", driver_list, default=driver_list
    )

    # Apply driver filter to the prepared dataframe
    df_filtered = df.copy()
    if selected_drivers and "Driver" in df_filtered.columns:
        df_filtered = df_filtered[df_filtered["Driver"].isin(selected_drivers)]

    # Recompute summary based on driver-filtered data
    summary_driver = mp.aggregate_by_vehicle(df_filtered)

    # --- Vehicle filter (based on driver-filtered summary) ---
    vehicles = sorted(summary_driver.index.tolist())
    selected_vehicles = st.sidebar.multiselect(
        "Select vehicle(s):", vehicles, default=vehicles
    )

    if selected_vehicles:
        filtered_summary = summary_driver.loc[selected_vehicles]
    else:
        filtered_summary = summary_driver


    # Rename columns for display (match your CSV header style)
    summary_display = filtered_summary.rename(
        columns={
            "Commute_Miles": "Commute Miles",
            "Business_Miles": "Business Miles",
            "Total_Miles": "Total Miles",
        }
    ).round(2)

    # ---------------------------
    # Top-level metrics
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

    # Layout: 2 charts side by side
    chart_col1, chart_col2 = st.columns(2)

    # 1) Total miles bar chart
    with chart_col1:
        st.markdown("**Total Miles by Vehicle**")
        fig1, ax1 = plt.subplots()
        ax1.bar(summary_display.index, summary_display["Total Miles"])
        ax1.set_ylabel("Miles")
        ax1.set_xlabel("Vehicle")
        ax1.set_title("Total Miles by Vehicle")
        plt.xticks(rotation=30, ha="right")
        st.pyplot(fig1)



    # --- 2) Pie charts: Commute vs Business miles for each vehicle ---
    st.markdown("**Commute vs Business Miles by Vehicle (Pie Charts)**")

    num_vehicles = len(filtered_summary)
    if num_vehicles > 0:
        # Decide grid layout (3 columns, N rows)
        cols = 3
        rows = (num_vehicles + cols - 1) // cols  # ceiling division

        fig, axes = plt.subplots(rows, cols, figsize=(cols * 4, rows * 4))

        # axes can be a single Axes if rows*cols == 1
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

            ax.pie(
                values,
                labels=labels,
                autopct="%1.1f%%",
                startangle=90,
            )
            ax.set_title(vehicle)
            ax.axis("equal")  # circular pies

        # Turn off any unused axes (if grid bigger than number of vehicles)
        for ax in axes[num_vehicles:]:
            ax.axis("off")

        fig.tight_layout()
        st.pyplot(fig)
    else:
        st.info("No vehicles selected for pie charts.")

    # ---------------------------
    # Details / Data quality section
    # ---------------------------
    st.subheader("Detailed Data")

    tab1, tab2, tab3 = st.tabs(
        ["All Rows (Prepared)", "Raw Imported Data", "Potential Issues"]
    )

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
        issues = df_filtered[~df_filtered["_row_ok"]].copy()
        if issues.empty:
            st.success("✅ No row-level issues detected.")
        else:
            st.warning(f"⚠ {len(issues)} issue row(s) found:")
            st.dataframe(issues, use_container_width=True)


if __name__ == "__main__":
    main()
