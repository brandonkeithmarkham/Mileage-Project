import pandas as pd

FILE_PATH = "gaps.xlsx"
MAX_REASONABLE_GAP = None  # set to e.g. 5000 to flag huge gaps

# --- Load all sheets, normalize to one table ---
xls = pd.ExcelFile(FILE_PATH)
all_rows = []

for sheet in xls.sheet_names:
    df = pd.read_excel(FILE_PATH, sheet_name=sheet)

    # Expect columns like: Driver | Vehicle | Begin | End | Gap
    # If your sheet is Vehicle | Begin | End | Gap (no Driver), set Driver = sheet name
    cols = [c.lower().strip() for c in df.columns.astype(str)]

    if "driver" in cols and "vehicle" in cols:
        # already has Driver + Vehicle
        pass
    else:
        # Assume first column is Vehicle, and driver is the sheet name
        df.insert(0, "Driver", sheet)

        # Rename first 5 columns to standard names where possible
        rename_map = {}
        if len(df.columns) >= 5:
            rename_map[df.columns[1]] = "Vehicle"
            rename_map[df.columns[2]] = "Begin"
            rename_map[df.columns[3]] = "End"
            rename_map[df.columns[4]] = "Gap"
        df = df.rename(columns=rename_map)

    # Keep only needed columns
    keep = [c for c in ["Driver", "Vehicle", "Begin", "End", "Gap"] if c in df.columns]
    df = df[keep].copy()

    # Make numeric columns numeric
    df["Begin"] = pd.to_numeric(df["Begin"], errors="coerce")
    df["End"] = pd.to_numeric(df["End"], errors="coerce")
    df["Gap"] = pd.to_numeric(df.get("Gap", df["End"] - df["Begin"]), errors="coerce")

    # Drop blank rows
    df = df.dropna(subset=["Vehicle", "Begin", "End"])
    all_rows.append(df)

master = pd.concat(all_rows, ignore_index=True)

# --- Infer Elsa gaps per vehicle ---
master = master.sort_values(["Vehicle", "Begin"]).reset_index(drop=True)

elsa_rows = []
anomalies = []

for vehicle, vdf in master.groupby("Vehicle"):
    vdf = vdf.sort_values("Begin").reset_index(drop=True)

    for i in range(len(vdf) - 1):
        curr_end = vdf.loc[i, "End"]
        next_begin = vdf.loc[i + 1, "Begin"]
        gap = next_begin - curr_end

        if gap > 0:
            if MAX_REASONABLE_GAP and gap > MAX_REASONABLE_GAP:
                anomalies.append({
                    "Vehicle": vehicle,
                    "From_End": curr_end,
                    "To_Begin": next_begin,
                    "Gap": gap,
                    "Reason": "Large gap"
                })
            else:
                elsa_rows.append({
                    "Driver": "Elsa",
                    "Vehicle": vehicle,
                    "Begin": curr_end,
                    "End": next_begin,
                    "Gap": gap
                })
        elif gap < 0:
            anomalies.append({
                "Vehicle": vehicle,
                "From_End": curr_end,
                "To_Begin": next_begin,
                "Gap": gap,
                "Reason": "Overlap / out-of-order logs"
            })

elsa_df = pd.DataFrame(elsa_rows)
anomaly_df = pd.DataFrame(anomalies)

summary = (elsa_df.groupby("Vehicle")["Gap"]
           .sum()
           .reset_index()
           .rename(columns={"Gap": "Elsa_Estimated_Miles"}))

with pd.ExcelWriter("elsa_mileage_output.xlsx", engine="openpyxl") as writer:
    master.to_excel(writer, sheet_name="All_Logs_Master", index=False)
    elsa_df.to_excel(writer, sheet_name="Elsa_Detail", index=False)
    summary.to_excel(writer, sheet_name="Elsa_Summary", index=False)
    anomaly_df.to_excel(writer, sheet_name="Anomalies", index=False)

print("Wrote elsa_mileage_output.xlsx")
