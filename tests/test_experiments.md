# Test experiments

Each test was checked by deliberately breaking its rule in a temporary
copy of the code, confirming the test fails, then restoring the code
and confirming it passes again.

| # | Rule broken | Change made | Test that failed | After restore |
|---|---|---|---|---|
| 1 | Day-first dates | "dd/MM/yyyy" changed to "MM/dd/yyyy" in transform_categories | test_categories_day_first_and_code | 1 passed |