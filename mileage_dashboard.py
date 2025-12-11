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
import streamlit as st

import mileage_process as mp  # your existing script


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
# Authentication gate
# ---------------------------
if not st.user.is_logged_in:
    st.title("🚗 Mileage Dashboard")
    st.write("Please log in to access this app.")

    # Uses the [auth] config from your Streamlit secrets
    if st.button("Log in with Google"):
        st.login()

    st.stop()

# Show who logged in
st.caption(f"Logged in as: {st.user.email}")

# ---------------------------
# Authorization (whitelist)
# ---------------------------
ALLOWED_EMAILS = {
    "brandonkeithmarkham@gmail.com",
    "friend_email@gmail.com",
    # add others here
}

if st.user.email not in ALLOWED_EMAILS:
    st.error("🚫 You are not authorized to access this application.")
    st.stop()


# ---------------------------
# Data loading using your code
# ---------------------------
@st.cache_data
def load_data():
    """
    Use your existing pipeline to:
    - find CSVs
    - load them
    - normalize & prepare
    - aggregate by vehicle
    """
    csv_files = mp.pick_input_csvs()
    raw_df = mp.load_all_csvs(csv_files)
    df = mp.load_and_prepare(raw_df)
    summary = mp.aggregate_by_vehicle(df)
    return csv_files, raw_df, df, summary


def main():
    st.title("🚗 Mileage Dashboard")

    # Try to load data; show a friendly error if no files are found
    try:
        csv_files, raw_df, df, summary = load_data()
    except SystemExit:
        st.error(
            "No valid mileage CSV files found.\n\n"
            "Place your mileage CSVs in this folder (same as mileage_dashboard.py) "
            "and ensure their names contain 'Mileage', or are .csv files."
        )
        return

    # ---------------------------
    # Sidebar: basic info + filters
    # ---------------------------
    st.sidebar.header("Filters")

    st.sidebar.markdown("**Source CSV files:**")
    for p in csv_files:
        st.sidebar.write(f"- `{Path(p).name}`")

    vehicles = sorted(summary.index.tolist())
    selected_vehicles = st.sidebar.multiselect(
        "Select vehicle(s):", vehicles, default=vehicles
    )

    if selected_vehicles:
        filtered_summary = summary.loc[selected_vehicles]
    else:
        filtered_summary = summary

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
        st.dataframe(df, use_container_width=True)

    with tab2:
        st.markdown("This is the raw combined DataFrame loaded from all CSVs.")
        st.dataframe(raw_df, use_container_width=True)

    with tab3:
        st.markdown("Rows with NaN or negative miles (if any).")
        issues = df[~df["_row_ok"]].copy()
        if issues.empty:
            st.success("✅ No row-level issues detected.")
        else:
            st.warning(f"⚠ {len(issues)} issue row(s) found:")
            st.dataframe(issues, use_container_width=True)


if __name__ == "__main__":
    main()
