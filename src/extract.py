import hashlib, json, shutil, sys
from datetime import datetime, timezone
import pandas as pd
from config import RAW_SRC, RAW, DOCS, FILES, EXPECTED_RAW_ROWS


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def count_rows(csv_path):
    # header excluded; utf-8-sig so a BOM never counts as data
    return sum(len(c) for c in pd.read_csv(csv_path, dtype=str, encoding="utf-8-sig", chunksize=200_000))


def extract():
    RAW.mkdir(parents=True, exist_ok=True)
    DOCS.mkdir(parents=True, exist_ok=True)
    entries = []
    for key, f in FILES.items():
        src, dst = RAW_SRC / f["src"], RAW / f["src"]
        if src.resolve() != dst.resolve():
            shutil.copy2(src, dst)                   # raw files are copied, never edited
        csv_path = RAW / f["csv"]
        if dst.suffix.lower() == ".xlsx":            # really an Excel file despite the name
            pd.read_excel(dst, dtype=str).to_csv(csv_path, index=False, encoding="utf-8")
        entries.append({
            "key": key,
            "file": f["csv"],
            "converted_from": f["src"] if f["csv"] != f["src"] else None,
            "size_bytes": csv_path.stat().st_size,
            "sha256": sha256(csv_path),
            "row_count": count_rows(csv_path),
            "extracted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
    got = {e["row_count"] for e in entries}
    assert got == EXPECTED_RAW_ROWS, f"row counts {sorted(got)} != expected {sorted(EXPECTED_RAW_ROWS)}"
    (DOCS / "manifest.json").write_text(json.dumps(entries, indent=2))
    return entries


if __name__ == "__main__":
    try:
        for e in extract():
            print(f"{e['file']:28s} {e['row_count']:>9,} rows  {e['size_bytes']/1e6:7.1f} MB  OK")
    except AssertionError as err:
        print(f"CHECK FAILED: {err}", file=sys.stderr)
        sys.exit(2)
