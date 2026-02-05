import pandas as pd
from pathlib import Path
import re
from datetime import datetime
import sys


# -------------------------
# CONFIG
# -------------------------
INPUT_FILENAME = "gaps.xlsx"
PREFERRED_SHEET = "GAPS"          # uses this if present, else first sheet
OUTPUT_FILENAME = "elsa_mileage_output.xlsx"

# If you want to normalize case to avoid "adrienne" vs "Adrienne"
NORMALIZE_CASE = True            # True -> title case for Driver/Vehicle


# -------------------------
# NORMALIZATION
# -------------------------
def normalize_text(x):
    if pd.isna(x):
        return x
    if not isinstance(x, str):
        return x
    x = x.replace("\ufeff", "")      # BOM
    x = x.replace("\u00A0", " ")     # NBSP
    x = x.strip()
    x = re.sub(r"\s+", " ", x)       # collapse whitespace
    return x


def normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [normalize_text(str(c)) for c in df.columns]
    # Include both object and string dtypes (pandas 3+)
    obj_cols = df.select_dtypes(include=["object", "string"]).columns
    for c in obj_cols:
        df[c] = df[c].map(normalize_text)
    return df


# -------------------------
# COLUMN STANDARDIZATION
# -------------------------
def to_standard_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Map your sheet columns to standard names:
      Driver, Vehicle, Begin, End, Gap

    Typical input:
      Driver | Vehicle | Begin Gap | End Gap | Total Gap
    """
    df = normalize_dataframe(df)

    rename_map = {}

    for col in df.columns:
        cl = str(col).lower()

        if "driver" == cl or cl.startswith("driver"):
            rename_map[col] = "Driver"
        elif "vehicle" == cl or cl.startswith("vehicle"):
            rename_map[col] = "Vehicle"
        elif "begin" in cl or "start" in cl:
            rename_map[col] = "Begin"
        elif "end" in cl or "stop" in cl or "finish" in cl:
            rename_map[col] = "End"
        elif "total gap" in cl or cl == "gap" or ("mileage" in cl and "gap" in cl):
            rename_map[col] = "Gap"

    df = df.rename(columns=rename_map)

    required = {"Driver", "Vehicle", "Begin", "End"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"Missing required columns: {missing}\n"
            f"Found columns: {list(df.columns)}\n"
            f"Expected something like Driver, Vehicle, Begin Gap, End Gap, Total Gap."
        )

    # If Gap missing, compute it
    if "Gap" not in df.columns:
        df["Gap"] = pd.to_numeric(df["End"], errors="coerce") - pd.to_numeric(df["Begin"], errors="coerce")

    df = df[["Driver", "Vehicle", "Begin", "End", "Gap"]].copy()
    return df


# -------------------------
# INTERVAL HELPERS
# -------------------------
def merge_intervals(intervals):
    """Merge overlapping/touching [start,end] intervals. Assumes start <= end."""
    if not intervals:
        return []
    intervals = sorted(intervals, key=lambda x: (x[0], x[1]))
    merged = [intervals[0]]
    for s, e in intervals[1:]:
        ps, pe = merged[-1]
        if s <= pe:  # overlap or touch
            merged[-1] = (ps, max(pe, e))
        else:
            merged.append((s, e))
    return merged


def subtract_intervals(base_intervals, subtract_intervals_merged):
    """
    Subtract a merged set of intervals from base_intervals.
    Returns list of residual intervals.
    """
    residuals = []

    for bs, be in base_intervals:
        cur_s = bs
        for ss, se in subtract_intervals_merged:
            if se <= cur_s:
                continue
            if ss >= be:
                break

            # If subtract starts after current start, keep left piece
            if ss > cur_s:
                residuals.append((cur_s, min(ss, be)))

            # Advance current start beyond the subtract interval
            cur_s = max(cur_s, se)
            if cur_s >= be:
                break

        # If anything remains to the right
        if cur_s < be:
            residuals.append((cur_s, be))

    # Remove zero-length
    residuals = [(s, e) for s, e in residuals if e > s]
    return residuals


# -------------------------
# SAFE OUTPUT WRITER
# -------------------------
def safe_output_path(path: Path) -> Path:
    """If output file is locked (open in Excel), write a timestamped copy."""
    if not path.exists():
        return path
    try:
        with open(path, "a"):
            return path
    except PermissionError:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return path.with_name(f"{path.stem}_{stamp}{path.suffix}")


# -------------------------
# MAIN
# -------------------------
def main():
    in_path = Path(__file__).with_name(INPUT_FILENAME)
    if not in_path.exists():
        print(f"ERROR: Input file not found: {in_path}")
        sys.exit(1)

    xls = pd.ExcelFile(in_path)
    chosen_sheet = None
    for s in xls.sheet_names:
        if normalize_text(s) == PREFERRED_SHEET:
            chosen_sheet = s
            break
    if chosen_sheet is None:
        chosen_sheet = xls.sheet_names[0]

    raw = pd.read_excel(in_path, sheet_name=chosen_sheet)
    df = to_standard_columns(raw)
    df = normalize_dataframe(df)

    # Optional casing normalization
    if NORMALIZE_CASE:
        df["Driver"] = df["Driver"].astype(str).map(normalize_text).str.strip().str.title()
        df["Vehicle"] = df["Vehicle"].astype(str).map(normalize_text).str.strip().str.title()
    else:
        df["Driver"] = df["Driver"].map(normalize_text)
        df["Vehicle"] = df["Vehicle"].map(normalize_text)

    # Numeric coercion
    df["Begin"] = pd.to_numeric(df["Begin"], errors="coerce")
    df["End"] = pd.to_numeric(df["End"], errors="coerce")
    df["Gap"] = pd.to_numeric(df["Gap"], errors="coerce")

    df = df.dropna(subset=["Driver", "Vehicle", "Begin", "End"]).copy()

    # Ensure Begin <= End (fix any reversed entries safely)
    swapped = df["Begin"] > df["End"]
    if swapped.any():
        df.loc[swapped, ["Begin", "End"]] = df.loc[swapped, ["End", "Begin"]].to_numpy()
        # Recompute Gap for swapped rows
        df.loc[swapped, "Gap"] = df.loc[swapped, "End"] - df.loc[swapped, "Begin"]

    # -------------------------
    # CORE LOGIC:
    # For each vehicle:
    #   For each driver:
    #     residual = driver_intervals - union(other_driver_intervals)
    #   Elsa intervals = union(residuals across drivers)
    # -------------------------
    elsa_rows = []
    overlap_rows = []

    for vehicle, vdf in df.groupby("Vehicle"):
        # Build intervals per driver for this vehicle
        driver_intervals = {}
        for driver, ddf in vdf.groupby("Driver"):
            intervals = [(float(b), float(e)) for b, e in zip(ddf["Begin"], ddf["End"]) if pd.notna(b) and pd.notna(e) and e > b]
            driver_intervals[driver] = merge_intervals(intervals)

        drivers = list(driver_intervals.keys())

        # For overlap report (informational): total miles covered by >=2 drivers
        # Compute pairwise overlaps roughly by scanning merged unions
        # (Not required for Elsa logic; just helpful to inspect)
        # We'll do a simple overlap estimate by building per-driver merged intervals and intersecting pairs.
        def intersect_two(a, b):
            i, j = 0, 0
            out = []
            while i < len(a) and j < len(b):
                s1, e1 = a[i]
                s2, e2 = b[j]
                s = max(s1, s2)
                e = min(e1, e2)
                if e > s:
                    out.append((s, e))
                if e1 < e2:
                    i += 1
                else:
                    j += 1
            return out

        for idx_i in range(len(drivers)):
            for idx_j in range(idx_i + 1, len(drivers)):
                di, dj = drivers[idx_i], drivers[idx_j]
                ov = intersect_two(driver_intervals[di], driver_intervals[dj])
                if ov:
                    ov_miles = sum(e - s for s, e in ov)
                    overlap_rows.append({
                        "Vehicle": vehicle,
                        "Driver_A": di,
                        "Driver_B": dj,
                        "Overlap_Miles": ov_miles
                    })

        # Elsa residuals: subtract others from each driver's intervals
        elsa_intervals_vehicle = []
        for driver in drivers:
            base = driver_intervals[driver]

            # union of all other drivers' intervals
            others = []
            for other_driver in drivers:
                if other_driver == driver:
                    continue
                others.extend(driver_intervals[other_driver])
            others_merged = merge_intervals(others)

            residual = subtract_intervals(base, others_merged)

            # residual belongs to Elsa
            elsa_intervals_vehicle.extend(residual)

        # Merge Elsa residuals so we don't duplicate
        elsa_intervals_vehicle = merge_intervals(elsa_intervals_vehicle)

        for s, e in elsa_intervals_vehicle:
            elsa_rows.append({
                "Driver": "Elsa",
                "Vehicle": vehicle,
                "Begin": s,
                "End": e,
                "Gap": e - s
            })

    elsa_df = pd.DataFrame(elsa_rows)
    overlap_df = pd.DataFrame(overlap_rows)

    # Summary
    if elsa_df.empty:
        summary = pd.DataFrame(columns=["Vehicle", "Elsa_Estimated_Miles"])
    else:
        summary = (
            elsa_df.groupby("Vehicle")["Gap"]
            .sum()
            .reset_index()
            .rename(columns={"Gap": "Elsa_Estimated_Miles"})
            .sort_values("Elsa_Estimated_Miles", ascending=False)
            .reset_index(drop=True)
        )

    # Output
    out_path = safe_output_path(Path(__file__).with_name(OUTPUT_FILENAME))

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        df.sort_values(["Vehicle", "Driver", "Begin"]).to_excel(writer, sheet_name="All_Logs_Master", index=False)
        elsa_df.sort_values(["Vehicle", "Begin"]).to_excel(writer, sheet_name="Elsa_Detail", index=False)
        summary.to_excel(writer, sheet_name="Elsa_Summary", index=False)
        overlap_df.sort_values(["Vehicle", "Overlap_Miles"], ascending=[True, False]).to_excel(writer, sheet_name="Overlap_Report", index=False)

    print(f"Input file : {in_path}")
    print(f"Sheet used : {chosen_sheet}")
    print(f"Output file: {out_path}")
    print("Done. (No negative anomalies are produced by this logic.)")


if __name__ == "__main__":
    main()
