# Decision log

Every change made to the data, and why. Raw files are never edited;
all changes happen in the transform step, so the clean data can always
be rebuilt from raw.

## Regional file (appointments_regional.csv)
- Collapsed repeated spaces in label columns (e.g. "15  to 21 Days" -> "15 to 21 Days"). Why: the same label was written two ways, which breaks grouping. Rows affected: none removed, only labels changed.
- Changed "Other Practice staff" to "Other Practice Staff". Why: matches the metadata spelling so there is one value.
- Added month_start (date) beside appointment_month; original kept. Why: real dates sort and filter correctly.
- Grouped by every descriptive column and summed count_of_appointments: 596,821 -> 295,692 rows, total unchanged at 742,804,525. Why: rows identical apart from the count are real separate appointments, so summing keeps them. Dropping them would lose appointments.
- Tested the alternative: dropping look-alike rows with dropDuplicates keeps the row count at 295,692 but the total falls far below 742,804,525, so appointments are lost. The row-count test did not catch this, but the totals tests did. Summing is the only approach that keeps both the row count and the total correct.

## National categories file (national_categories.csv)
- Header starts with an invisible byte-order mark (\ufeffappointment_date). Handled by reading with a declared schema with clean column names. Rows affected: none.
- Parsed appointment_date with dd/MM/yyyy (day-first). Why: 02/08/2021 is 2 August, not 8 February. Check: month of appointment_date equals appointment_month on every row.
- Added sub_icb_code, taken from the end of sub_icb_location_name ("... ICB - 00L" -> "00L"). Original name column kept.

## Actual duration file (actual_duration.csv.xlsx)
- File is really Excel despite the name; converted to CSV with pandas in the extract step.
- Parsed appointment_date and added appointment_month (yyyy-MM). Why: needed to partition the Parquet output by month.

## Output format
- Clean data written as Parquet, partitioned by appointment_month, for all three datasets. Why: smaller files, types preserved, and monthly queries only read the folders they need. Write mode is overwrite so re-running gives identical output.

## Testing
- Tests run against the saved Parquet output, not just the in-memory data. Why: this catches problems in what was actually written.
- Clean output was written to local disk for the test run. Why: Google Drive dropped files when Spark wrote many small partition folders, which left empty folders and made the tests error out.