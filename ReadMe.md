📘 README — Mileage Processor (Payroll Logs)

This project contains a Python script that automates processing of mileage logs exported from payroll spreadsheets. It scans, cleans, aggregates, and visualizes mileage data across multiple CSV files and produces reports suitable for accounting and administrative review.

🚀 What This Script Does

The script:

Scans the current directory for all CSV files containing “Mileage” in their filename
(e.g., Matthew_Mileage.csv, Mileage Log - Theresa.csv).

Loads all matching files and combines them into a single dataset.

Cleans and normalizes each file so that:

Columns with slightly different names map to the same canonical names.

Vehicle names are standardized (e.g., " jim " → "Jim").

Mileage values are converted to numeric types.

Computes Miles = End Mileage – Start Mileage for each trip.

Detects whether a trip is Commute or Business based on the Mileage Type field.

Aggregates mileage totals by vehicle, producing:

Business miles

Commute miles

Combined total miles

Generates several output files including CSVs, Excel reports, and visual charts.

Flags invalid rows (missing or negative mileage) for data cleanup.

📁 Expected CSV Format

Each vehicle log should follow the general format:

Date, Vehicle or Vehicle Used, Start Mileage, End Mileage, Total Mileage, Mileage Type


The script automatically handles:

Extra spaces in header names ("Vehicle " → "Vehicle").

Differences between "Vehicle" and "Vehicle Used".

Unused "Total Mileage" column (it is ignored and recomputed).

Mixed-case or noisy vehicle names.

As long as the CSV contains:

A vehicle name column

Start mileage

End mileage

Mileage type

…it will be processed correctly.

🧠 How the Script Works (Conceptual Overview)
1. File Selection

Searches for all *Mileage*.csv files.
If none are found, falls back to all .csv files.

2. Data Loading

Loads each CSV with pandas and adds a Source File column so every row is traceable to the original file.

3. Normalization & Cleaning

Standardizes column names, formats vehicle names, converts odometer readings to numbers, and computes:

Miles = End Mileage – Start Mileage


Rows are flagged as:

_row_ok = True → valid

_row_ok = False → missing or negative miles

A _is_commute flag is created based on text inside the Mileage Type column.

4. Aggregation

Valid rows are grouped by Vehicle and Commute/Business, then pivoted into a summary table:

| Vehicle | Business Miles | Commute Miles | Total Miles |

5. Report Generation

The script writes multiple outputs to mileage_outputs/:

File	Description
mileage_summary.csv	Clean per-vehicle totals
mileage_summary_table.png	Table image with highlighted header
vehicle_pies.png	Grid of pie charts (Business vs Commute per vehicle)
total_miles.png	Bar chart of total miles per vehicle
mileage_report.xlsx	Two-tab workbook: Summary + Details
rows_with_issues.csv	Problematic rows requiring user review
📊 Output Examples
✔ Mileage Summary Table

An easy-to-read image with bold headers for quick reference.

✔ Pie Charts Per Vehicle

Shows the proportion of commute vs business mileage for each vehicle.

✔ Total Mileage Bar Chart

Summarizes total usage per vehicle.

✔ Excel Workbook

Contains:

Summary sheet: identical to CSV but formatted for Excel users

Details sheet: all rows + flags (Is_Commute, Row_OK) and source file names

🧩 Function-by-Function Explanation
pick_input_csvs()

Identifies all relevant CSV files.

Prefers filenames containing "Mileage".

Prints out which files will be processed.

load_all_csvs(csv_paths)

Loads each CSV via pandas.

Adds a Source File column.

Strips whitespace from column names.

Stacks all files into one combined DataFrame.

normalize_column_names(df)

Maps varying column names to consistent internal ones:

"Vehicle" or "Vehicle Used" → "Vehicle"

"Start Mileage" → "Start Mileage"

"End Mileage" → "End Mileage"

"Mileage Type" → "Mileage Type"

Ensures all required columns exist.

load_and_prepare(df)

Cleans, converts, and organizes the data.

Computes miles.

Creates commute and validity flags.

Reorders columns for consistency.

Preserves all extra columns (like Date) for detailed reporting.

aggregate_by_vehicle(df)

Uses only valid rows.

Sums Business and Commute miles per vehicle.

Constructs a clear per-vehicle summary table.

save_outputs(df, summary, outdir)

Generates:

Summary CSV

Summary table image

Pie chart grid

Total miles bar chart

Excel workbook

Invalid-row report

main()

The orchestrator:

Find input files

Load + combine

Clean + prepare

Aggregate

Output reports

▶️ How to Run the Script
1. Place CSVs next to the script

All mileage logs should be in the same folder as mileage_process.py.

2. Run from terminal:
python mileage_process.py

3. Open mileage_outputs/

All charts, reports, and summaries will be inside.

👨‍💼 For Future Maintainers

This script is designed to be robust against inconsistent CSV formats.

If new mileage logs add new columns, the script will automatically include them in the Excel details tab.

The only critical fields are:

Start Mileage

End Mileage

Vehicle

Mileage Type

Any invalid rows are automatically quarantined in rows_with_issues.csv.

If updates are needed:

Additional visualizations can be added easily.

You can adjust the commute/business logic inside _is_commute.

You can change the file detection pattern in pick_input_csvs().

🏁 Summary

This script provides a fully automated, repeatable, and transparent workflow for processing mileage logs across multiple employees.
It is built for robustness and easy maintenance, and this README serves as both documentation and onboarding for new staff.

If improvements or modifications are needed, the code is well-structured and easy to extend.
