## Week 3 decisions (load and automate)

- **Three fact tables, not one.** They have different grains and different date ranges (30, 11 and 7 months). One table would invent appointments that were never reported.
- **NHS codes are the keys.** Sub-ICB and ICB codes are real, stable identifiers, so no surrogate keys.
- **One date type everywhere.** Months are DATE (first day of the month, `month_start`) and days are DATE. The month partition folder name comes back as text from Parquet, so the load filters on `month_start` instead.
- **Sub-ICB code for the category fact is taken from the end of the location name** ("... ICB - 00L" gives 00L) in the load SQL, because the clean category data only carries the name.
- **dim_geography is built from the duration file** (it has ICB and region codes). Any sub-ICB found only in the category file is added with an empty region.
- **Band dimensions use a fixed list with a sort order** (Same Day first). A label not in the list fails check 6 or 7.
- **No GROUP BY or DISTINCT on facts in the load.** Look-alike regional rows were already summed in Week 2.
- **Idempotent load:** dimensions are rebuilt each run. Facts are loaded one month at a time as delete-then-insert inside one transaction.
- **Build in a temporary copy.** The real warehouse file is replaced only after all nine checks pass, so a failed run writes nothing.
- **Exit codes:** 0 loaded, 2 failed check, 1 crashed. Extract and transform raise AssertionError on a wrong number, which becomes exit 2.
- **One date format per file, stated once** (regional yyyy-MM, categories dd/MM/yyyy, duration yyyy-MM-dd HH:mm:ss). A wrong value fails loudly with examples.
- **Checks run before Parquet is written** (totals and the 295,692 regional row count), as well as after.
- **Check 9 stays at 90%, not 100%.** The duration file covers 90.9-92.2% of category appointments (lowest 90.9% in 2021-12). From metadata_nhs.txt: duration data only starts with December 2021; it is recorded differently by GP system suppliers (EMIS and TPP start and stop the clock at different moments); and appointments with a null duration, under 1 minute or over 60 minutes are grouped as "Unknown / Data Quality Issue". **Reason for the gap itself: TODO, still to be written.**
