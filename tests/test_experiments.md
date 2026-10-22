# Test experiments

Each test was checked by deliberately breaking its rule in a temporary
copy of the code, confirming the test fails, then restoring the code
and confirming it passes again.

| # | Rule broken | Change made | Test that failed | After restore |
|---|---|---|---|---|
| 1 | Day-first dates | "dd/MM/yyyy" changed to "MM/dd/yyyy" in transform_categories | test_categories_day_first_and_code | 1 passed |
| 2 | Totals preserved | Added a filter dropping rows with count 1 or less in transform_regional | test_clean_row_counts[regional], test_clean_totals[regional], test_regional_total_matches_raw | 27 passed |
| 3 | Look-alike rows summed, not dropped | Replaced groupBy + sum with dropDuplicates(keys) in transform_regional | test_clean_totals[regional], test_regional_total_matches_raw, test_regional_sums_lookalike_rows_and_tidies_labels (row count test still passed, which is why totals are tested too) | 27 passed |
| 4 | No duplicate keys | Replaced groupBy + sum with plain return (no grouping) in transform_regional | test_no_duplicate_keys[regional], test_clean_row_counts[regional], test_regional_sums_lookalike_rows_and_tidies_labels (totals tests still passed: nothing was lost, only duplicates left in) | 27 passed |