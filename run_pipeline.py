import argparse, json, os, shutil, subprocess, sys, time, traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))


class CheckFailed(Exception):
    pass


def parse_args():
    p = argparse.ArgumentParser(description="Run extract, transform, load and checks in order.")
    p.add_argument("--raw", help="folder for the raw copies (default data/raw)")
    p.add_argument("--out", help="folder for the clean Parquet (default data/clean)")
    return p.parse_args()


def main():
    args = parse_args()
    if args.raw:
        os.environ["LSA_RAW"] = str(Path(args.raw).resolve())
    if args.out:
        os.environ["LSA_CLEAN"] = str(Path(args.out).resolve())
    import duckdb
    import config, load, checks          # imported after the paths are set

    config.DOCS.mkdir(parents=True, exist_ok=True)
    log_file = config.DOCS / "pipeline_log.txt"

    def log(message):
        print(message, flush=True)
        with open(log_file, "a") as f:
            f.write(f"{datetime.now().isoformat(timespec='seconds')}  {message}\n")

    def run_script(name):
        result = subprocess.run([sys.executable, str(ROOT / "src" / name)])
        if result.returncode == 2:
            raise CheckFailed(f"{name} stopped by a failed check")
        if result.returncode != 0:
            raise RuntimeError(f"{name} crashed (exit code {result.returncode})")

    started = time.time()
    try:
        t = time.time()
        run_script("extract.py")
        manifest = json.loads((config.DOCS / "manifest.json").read_text())
        rows = " / ".join(f"{e['row_count']:,}" for e in manifest)
        log(f"extract   OK   {rows}   ({time.time() - t:.0f}s)")

        t = time.time()
        run_script("transform.py")
        summary = json.loads((config.DOCS / "transform_summary.json").read_text())
        regional = next(r for r in summary if r["key"] == "regional")
        log(f"transform OK   {regional['rows']:,} regional rows   {regional['total']:,} appointments   ({time.time() - t:.0f}s)")

        # Build in a temporary copy. The real warehouse is replaced only if every check passes.
        t = time.time()
        final = config.WAREHOUSE_DB
        building = final.with_name("warehouse_building.duckdb")
        final.parent.mkdir(parents=True, exist_ok=True)
        if building.exists():
            building.unlink()
        if final.exists():
            shutil.copy2(final, building)
        totals = load.load_all(building)
        log(f"load      OK   3 facts, 5 dimensions   ({time.time() - t:.0f}s)")

        con = duckdb.connect(str(building))
        try:
            results = checks.run_checks(con)
        finally:
            con.close()
        checks.write_report(results)
        for r in results:
            log(f"  check {r['check']} {r['status']}: {r['detail']}")
        passed = sum(r["status"] == "PASS" for r in results)
        if passed != len(results):
            building.unlink()
            raise CheckFailed(f"{len(results) - passed} of {len(results)} quality checks failed; warehouse left unchanged")
        os.replace(building, final)
        log(f"checks    OK   {passed}/{len(results)} passed")
        log("warehouse: " + "; ".join(f"{k} rows={v['rows']:,} total={v['total']:,}" for k, v in totals.items() if k.startswith("fact_")))
        log(f"done in {time.time() - started:.0f}s, exit 0")
        return 0
    except CheckFailed as err:
        log(f"STOPPED: {err}")
        return 2
    except Exception as err:
        log(f"CRASHED: {type(err).__name__}: {err}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
