## National categories file (national_categories.csv)
- Header starts with an invisible byte-order mark (\ufeffappointment_date). Handled by reading with a declared schema with clean column names. Rows affected: none.
- Parsed appointment_date with dd/MM/yyyy (day-first). Why: 02/08/2021 is 2 August, not 8 February. Check: month of appointment_date equals appointment_month on every row.
- Added sub_icb_code, taken from the end of sub_icb_location_name ("... ICB - 00L" -> "00L"). Original name column kept.

## Actual duration file (actual_duration.csv.xlsx)
- File is really Excel despite the name; converted to CSV with pandas in the extract step.
- Parsed appointment_date and added appointment_month (yyyy-MM). Why: needed to partition the Parquet output by month.
## Testing
- Tests run against the saved Parquet output, not just the in-memory data. Why: this catches problems in what was actually written.
- Clean output was written to local disk for the test run. Why: Google Drive dropped files when Spark wrote many small partition folders, which left empty folders and made the tests error out.