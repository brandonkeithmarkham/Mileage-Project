#!/usr/bin/env python3
"""
Mileage Processor (Multi-file, Payroll Logs Style)
--------------------------------------------------
- Scans ALL mileage CSVs in the current folder whose names contain "Mileage"
  (pattern: *Mileage*.csv). If none found, falls back to all *.csv.
- Handles CSVs that look like:

    Date, Vehicle, Start Mileage, End Mileage, Total Mileage, Mileage Type

  (with possible trailing spaces in column names, e.g. "Vehicle ", "Start Mileage ").

- Uses columns (after normalization):
    Vehicle, Start Mileage, End Mileage, Mileage Type

- Classifies miles as "Commute" if 'commute' appears in Mileage Type (case-insensitive)
- Aggregates by vehicle and writes:
    - mileage_outputs/mileage_summary.csv
      Columns: Vehicle, Commute Miles, Business Miles, Total Miles
    - mileage_outputs/mileage_summary_table.png (pretty table image)
    - mileage_outputs/commute_vs_business.png (stacked bar chart)
    - mileage_outputs/total_miles.png (total miles bar chart)
    - mileage_outputs/mileage_report.xlsx (Summary + Details sheets)
    - mileage_outputs/rows_with_issues.csv (rows with NaN or negative miles)
"""

from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

# Canonical column names we use internally
VEHICLE_COL = "Vehicle"
BEGIN_COL   = "Start Mileage"
END_COL     = "End Mileage"
TYPE_COL    = "Mileage Type"


def pick_input_csvs():
    """
    Find ALL CSV files to use:
    - Prefer all files whose name contains 'Mileage' (e.g., '*Mileage*.csv')
    - If none found, use ALL '*.csv' files
    """
    mileage_candidates = sorted(Path(".").glob("*Mileage*.csv"))
    if mileage_candidates:
        candidates = mileage_candidates
        print("📄 Using all CSV files matching '*Mileage*.csv':")
    else:
        candidates = sorted(Path(".").glob("*.csv"))
        if not candidates:
            print("❌ No CSV file found in this folder. Place your mileage CSV(s) next to this script.")
            raise SystemExit(1)
        print("📄 No '*Mileage*.csv' files found. Using ALL '*.csv' files:")

    for c in candidates:
        print(f"   • {c.name}")

    return candidates


def load_all_csvs(csv_paths):
    """
    Load and concatenate all given CSV files.
    Adds a 'Source File' column so we know where each row came from.
    Also strips whitespace from column names.
    """
    dfs = []
    for p in csv_paths:
        print(f"📥 Loading: {p.name}")
        df = pd.read_csv(p)

        # Add source file name
        df["Source File"] = p.name

        # Strip whitespace from column names ("Vehicle " -> "Vehicle")
        df.columns = df.columns.str.strip()

        dfs.append(df)

    combined = pd.concat(dfs, ignore_index=True)
    print(f"📊 Combined {len(csv_paths)} file(s) into {len(combined)} total rows.")
    return combined


def normalize_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize the various possible column names into our canonical ones:
      - 'Vehicle' or 'Vehicle Used' -> 'Vehicle'
      - 'Start Mileage' -> 'Start Mileage'
      - 'End Mileage' -> 'End Mileage'
      - 'Mileage Type' -> 'Mileage Type'
    Assumes df.columns already had whitespace stripped.
    """
    col_map = {}

    # Vehicle column
    if "Vehicle" in df.columns:
        col_map["Vehicle"] = VEHICLE_COL
    elif "Vehicle Used" in df.columns:
        col_map["Vehicle Used"] = VEHICLE_COL

    # Start Mileage
    if "Start Mileage" in df.columns:
        col_map["Start Mileage"] = BEGIN_COL

    # End Mileage
    if "End Mileage" in df.columns:
        col_map["End Mileage"] = END_COL

    # Mileage Type
    if "Mileage Type" in df.columns:
        col_map["Mileage Type"] = TYPE_COL

    # Apply renames
    df = df.rename(columns=col_map)

    # Check that required columns exist
    expected = [VEHICLE_COL, BEGIN_COL, END_COL, TYPE_COL]
    missing = [c for c in expected if c not in df.columns]
    if missing:
        print("❌ Missing expected column(s):", ", ".join(missing))
        print("   Found columns:", list(df.columns))
        raise SystemExit(1)

    return df


def load_and_prepare(df: pd.DataFrame) -> pd.DataFrame:
    """
    - Normalizes column names
    - Normalizes vehicle names (" jim " -> "Jim")
    - Ensures numeric start/end mileage
    - Computes Miles = End - Start (ignores 'Total Mileage' column)
    - Flags bad rows (NaN or negative miles)
    - Flags commute rows (Mileage Type contains 'commute')
    """
    # Normalize the various header names to our canonical ones
    df = normalize_column_names(df)

    # 🔧 Normalize vehicle names so "jim", " Jim ", "JIM" → "Jim"
    df[VEHICLE_COL] = (
        df[VEHICLE_COL]
        .astype(str)      # ensure string
        .str.strip()      # remove leading/trailing spaces
        .str.title()      # capitalize like "Jim", "Emily", etc.
    )

    # Ensure numeric odometers
    df[BEGIN_COL] = pd.to_numeric(df[BEGIN_COL], errors="coerce")
    df[END_COL]   = pd.to_numeric(df[END_COL], errors="coerce")

    # Compute miles from odometers (ignore existing 'Total Mileage' field)
    df["Miles"] = df[END_COL] - df[BEGIN_COL]

    # Mark problems but don't fix them
    df["_row_ok"] = df["Miles"].notna() & (df["Miles"] >= 0)

    # Commute flag
    df["_is_commute"] = df[TYPE_COL].astype(str).str.contains("commute", case=False, na=False)

    # Base columns we always want in some order
    cols = [VEHICLE_COL, BEGIN_COL, END_COL, TYPE_COL, "Miles", "_is_commute", "_row_ok"]

    # If Source File exists, keep it at the front
    if "Source File" in df.columns:
        cols = ["Source File"] + cols

    # Include any extra columns (like Date, Total Mileage) at the end for Details sheet
    extra_cols = [c for c in df.columns if c not in cols]
    cols = cols + extra_cols

    return df[cols]


def aggregate_by_vehicle(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregates valid rows by vehicle and commute/business classification.
    """
    # Use only valid rows
    ok = df[df["_row_ok"]].copy()

    # Group by Vehicle + commute flag and sum miles
    grp = ok.groupby([VEHICLE_COL, "_is_commute"])["Miles"].sum().reset_index()

    # Pivot to get columns for Business vs Commute
    pivot = grp.pivot(index=VEHICLE_COL, columns="_is_commute", values="Miles").fillna(0.0)
    pivot = pivot.rename(columns={False: "Business_Miles", True: "Commute_Miles"})

    # Ensure both columns exist
    if "Business_Miles" not in pivot.columns:
        pivot["Business_Miles"] = 0.0
    if "Commute_Miles" not in pivot.columns:
        pivot["Commute_Miles"] = 0.0

    # Total
    pivot["Total_Miles"] = pivot["Business_Miles"] + pivot["Commute_Miles"]

    # Name the index for nicer CSV header
    pivot.index.name = "Vehicle"

    # Sort by vehicle name
    pivot = pivot.sort_index()

    return pivot


def save_outputs(df: pd.DataFrame, summary: pd.DataFrame, outdir: Path):
    outdir.mkdir(exist_ok=True, parents=True)

    # --- 1) Summary CSV (the main thing you asked for) ---

    # Rename columns to match your desired header
    summary_export = summary.rename(
        columns={
            "Commute_Miles": "Commute Miles",
            "Business_Miles": "Business Miles",
            "Total_Miles": "Total Miles",
        }
    )

    summary_csv = outdir / "mileage_summary.csv"
    summary_export.to_csv(summary_csv)
    print(f"✅ Wrote summary CSV: {summary_csv}")

    # --- 2) Summary table image ---
    table_png = outdir / "mileage_summary_table.png"

    # Convert index → column for proper header
    summary_table = summary_export.round(2).reset_index()
    summary_table = summary_table.rename(columns={summary_table.columns[0]: "Vehicle"})

    fig, ax = plt.subplots(figsize=(8, len(summary_table) * 0.6 + 1))
    ax.axis("off")

    # Create the table
    tbl = ax.table(
        cellText=summary_table.values,
        colLabels=summary_table.columns,
        loc="center",
        cellLoc="center",
    )

    tbl.auto_set_font_size(False)
    tbl.set_fontsize(10)
    tbl.scale(1, 1.4)

    # -----------------------------
    #  BOLD + YELLOW HEADER ONLY
    # -----------------------------
    header_color = "#fff2a8"  # soft yellow

    for (row, col), cell in tbl.get_celld().items():
        if row == 0:  # header row
            cell.set_text_props(weight="bold")
            cell.set_facecolor(header_color)
        else:
            cell.set_facecolor("white")  # ensure other rows stay white

    # Title & save
    plt.title("Mileage Summary by Vehicle", pad=20)
    fig.tight_layout()
    fig.savefig(table_png, dpi=200)
    plt.close(fig)

    print(f"✅ Wrote summary table image: {table_png}")

   # --- 3) Pie charts: Commute vs Business miles for each vehicle ---
    num_vehicles = len(summary.index)

    # Determine subplot layout (e.g., 1x3, 2x3, etc.)
    cols = 3
    rows = (num_vehicles + cols - 1) // cols  # ceiling division

    fig, axes = plt.subplots(rows, cols, figsize=(cols * 4, rows * 4))
    axes = axes.flatten()

    labels = ["Business", "Commute"]
    colors = ["#4c72b0", "#55a868"]  # optional colors

    for ax, (vehicle, row) in zip(axes, summary.iterrows()):
        values = [row["Business_Miles"], row["Commute_Miles"]]

        ax.pie(
            values,
            labels=labels,
            autopct="%1.1f%%",
            startangle=90,
            colors=colors,
        )
        ax.set_title(vehicle)

    # Turn off any unused subplots
    for ax in axes[num_vehicles:]:
        ax.axis("off")

    plt.suptitle("Commute vs Business Miles by Vehicle (Pie Charts)", fontsize=16, y=1.02)
    fig.tight_layout()

    pie_png = outdir / "vehicle_pies.png"
    fig.savefig(pie_png, dpi=150, bbox_inches="tight")
    plt.close(fig)

    print(f"✅ Wrote pie chart grid: {pie_png}")

    # --- 4) Total miles chart ---
    idx = range(len(summary.index))


    fig2 = plt.figure()
    plt.bar(idx, summary["Total_Miles"].values)
    plt.xticks(idx, summary.index, rotation=0)
    plt.ylabel("Miles")
    plt.title("Total Miles by Vehicle")
    fig2.tight_layout()
    total_png = outdir / "total_miles.png"
    fig2.savefig(total_png, dpi=150)
    plt.close(fig2)
    print(f"✅ Wrote chart: {total_png}")

    # --- 5) Excel workbook: Summary + Details (no per-vehicle sheets) ---
    xlsx_path = outdir / "mileage_report.xlsx"
    with pd.ExcelWriter(xlsx_path, engine="xlsxwriter") as writer:
        # Summary sheet
        summary_export.reset_index().to_excel(writer, sheet_name="Summary", index=False)

        # Details sheet with all rows
        details_view = df.copy()
        details_view = details_view.rename(
            columns={
                "_is_commute": "Is_Commute",
                "_row_ok": "Row_OK",
            }
        )
        details_view.to_excel(writer, index=False, sheet_name="Details")

    print(f"✅ Wrote Excel workbook: {xlsx_path}")

    # --- 6) Data-quality export (rows with NaN or negative miles) ---
    bad = df[~df["_row_ok"]].copy()
    if not bad.empty:
        bad_csv = outdir / "rows_with_issues.csv"
        bad.to_csv(bad_csv, index=False)
        print(f"⚠ Found {len(bad)} row(s) with NaN or negative miles. See: {bad_csv}")
    else:
        print("✅ No row-level issues detected.")


def main():
    # 1) Find ALL CSVs we care about
    csv_files = pick_input_csvs()
    outdir = Path("mileage_outputs")

    # 2) Load and combine them
    raw_df = load_all_csvs(csv_files)

    # 3) Prepare / classify
    df = load_and_prepare(raw_df)

    # 4) Aggregate
    summary = aggregate_by_vehicle(df)

    # 5) Save outputs
    save_outputs(df, summary, outdir)

    print("\n🎉 Done! Open the 'mileage_outputs' folder for results.")


if __name__ == "__main__":
    main()
