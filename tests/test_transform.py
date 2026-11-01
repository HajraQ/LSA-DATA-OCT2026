import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import pandas as pd
import pytest
from config import CLEAN, EXPECTED_TOTALS, EXPECTED_REGIONAL_ROWS_AFTER_AGG, FILES


@pytest.fixture(scope="session", params=list(FILES))
def t(request):
    df = pd.read_parquet(CLEAN / request.param)
    cnt = [c for c in df.columns if "count" in c]
    assert len(cnt) == 1
    for c in df.columns:
        if str(df[c].dtype) == "category":
            df[c] = df[c].astype(str)
    return request.param, df, cnt[0]


def test_total_matches_expected(t):
    key, df, cnt = t
    assert int(df[cnt].sum()) == EXPECTED_TOTALS[key]


def test_counts_are_positive_whole_numbers(t):
    key, df, cnt = t
    assert pd.api.types.is_integer_dtype(df[cnt])
    assert (df[cnt] > 0).all()


def test_no_nulls_in_count_or_month(t):
    key, df, cnt = t
    assert df[cnt].notna().all()
    assert df["month_start"].notna().all()


def test_no_bom_in_column_names(t):
    key, df, cnt = t
    assert not any("\ufeff" in c or c.startswith("\u00ef\u00bb\u00bf") for c in df.columns)


def test_dates_are_day_first(t):
    key, df, cnt = t
    pairs = [(c[: -len("_date")], c) for c in df.columns if c.endswith("_date") and c[: -len("_date")] in df.columns]
    assert pairs, "no parsed date column found"
    for orig, parsed_col in pairs:
        s = df[orig].astype(str)
        mask = s.str.match(r"^\d{2}/\d{2}/\d{4}$")
        if mask.any():
            parsed = pd.to_datetime(df.loc[mask, parsed_col])
            assert (parsed.dt.day == s[mask].str[:2].astype(int)).all()
            assert (parsed.dt.month == s[mask].str[3:5].astype(int)).all()
    ms = pd.to_datetime(df["month_start"])
    assert (ms.dt.day == 1).all()
    assert ms.min() >= pd.Timestamp("2020-01-01") and ms.max() <= pd.Timestamp("2022-12-31")


def test_labels_are_tidy(t):
    key, df, cnt = t
    for c in df.columns:
        if c == cnt or c.endswith("_date") or c in ("month_start", "month"):
            continue
        s = df[c].dropna().astype(str)
        assert not s.str.contains("  ").any(), f"double space in {c}"
        assert (s == s.str.strip()).all(), f"stray whitespace in {c}"
        assert not (s == "Other Practice staff").any(), f"bad spelling in {c}"


def test_month_partitions_exist(t):
    key, df, cnt = t
    folders = [p.name for p in (CLEAN / key).glob("month=*")]
    assert len(folders) == df["month"].nunique() > 0


def test_regional_rows_unique_and_summed(t):
    key, df, cnt = t
    if key != "regional":
        pytest.skip("regional only")
    assert not df.drop(columns=[cnt]).duplicated().any()
    assert len(df) == EXPECTED_REGIONAL_ROWS_AFTER_AGG
