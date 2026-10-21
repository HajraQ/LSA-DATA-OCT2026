# Data profile

## actual_duration.csv

- **Rows:** 137,793
- **Grain (what one row is):** appointments in one sub-ICB, on one day, in one actual-duration band
- **Grain key:** sub_icb_location_code, appointment_date, actual_duration
- **Key unique?** Yes (0 exact duplicate rows)
- **Date range:** 2021-12-01 to 2022-06-30

| column | type | nulls | distinct |
|---|---|---|---|
| sub_icb_location_code | object | 0 | 106 |
| sub_icb_location_ons_code | object | 0 | 106 |
| sub_icb_location_name | object | 0 | 106 |
| icb_ons_code | object | 0 | 42 |
| region_ons_code | object | 0 | 7 |
| appointment_date | datetime64[ns] | 0 | 212 |
| actual_duration | object | 0 | 7 |
| count_of_appointments | int64 | 0 | 7,611 |

## appointments_regional.csv

- **Rows:** 596,821
- **Grain (what one row is):** appointments in one ICB, in one month, for one status, staff type, mode and booking-wait band (sub-ICB columns removed, so rows can repeat: sum them, never drop)
- **Grain key:** icb_ons_code, appointment_month, appointment_status, hcp_type, appointment_mode, time_between_book_and_appointment
- **Key unique?** No (21,604 exact duplicate rows)
- **Date range:** 2020-01 to 2022-06

| column | type | nulls | distinct |
|---|---|---|---|
| icb_ons_code | object | 0 | 42 |
| appointment_month | object | 0 | 30 |
| appointment_status | object | 0 | 3 |
| hcp_type | object | 0 | 3 |
| appointment_mode | object | 0 | 5 |
| time_between_book_and_appointment | object | 0 | 8 |
| count_of_appointments | int64 | 0 | 22,807 |

## national_categories.csv

- **Rows:** 817,394
- **Grain (what one row is):** appointments in one sub-ICB, on one day, for one service setting, context type and national category
- **Grain key:** appointment_date, icb_ons_code, sub_icb_location_name, service_setting, context_type, national_category
- **Key unique?** Yes (0 exact duplicate rows)
- **Date range:** 2021-08-01 to 2022-06-30

| column | type | nulls | distinct |
|---|---|---|---|
| appointment_date | datetime64[ns] | 0 | 334 |
| icb_ons_code | object | 0 | 42 |
| sub_icb_location_name | object | 0 | 106 |
| service_setting | object | 0 | 5 |
| context_type | object | 0 | 3 |
| national_category | object | 0 | 18 |
| count_of_appointments | int64 | 0 | 9,957 |
| appointment_month | object | 0 | 11 |


## Five traps found (each confirmed against the data)

1. `actual_duration.csv.xlsx` is a real Excel file, not a CSV. Spark cannot read Excel, so it is converted to CSV with pandas during extract.
2. `national_categories.csv` starts with a byte-order mark, so the first column can load as `\ufeffappointment_date`. The BOM is stripped from the column names.
3. National dates are day-first text such as `02/08/2021` (2 August). The first number goes up to 31 and the middle number only to 12. Always parse with `dd/MM/yyyy`.
4. 21,604 rows in the regional file are exact copies of other rows. They are real appointments (the sub-ICB columns were removed), so they are summed, never dropped.
5. Booking-wait bands have double spaces (`15  to 21 Days`, `22  to 28 Days`, `8  to 14 Days`); staff type is `Other Practice staff` while the metadata says `Other Practice Staff`; alphabetical order puts `1 Day` before `Same Day`. Clean the labels and give the bands an explicit sort order.
