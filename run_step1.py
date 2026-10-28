"""Step 1: download FAERS quarters, deduplicate, and save clean tables.

Usage:
    python run_step1.py --start 2023Q1 --end 2025Q2
    python run_step1.py --start 2023Q1 --end 2025Q2 --skip-download   # zips already in data/raw

Outputs (data/clean/):
    demo.parquet, drug.parquet, reac.parquet, outc.parquet, indi.parquet, ther.parquet, rpsr.parquet
    drug_strings.csv     unique drug name strings + counts (input for the LLM task)
    dedup_stats.json     row counts at each cleaning step (report these in your methods)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from faers.dedup import deduplicate_demo, filter_to_primaryids
from faers.download import download_quarter, quarter_range
from faers.drugs import unique_drug_strings
from faers.load import TABLES, read_deleted_caseids, read_table

ROOT = Path(__file__).resolve().parent


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", required=True, help="first quarter, e.g. 2023Q1")
    ap.add_argument("--end", required=True, help="last quarter, e.g. 2025Q2")
    ap.add_argument("--raw-dir", type=Path, default=ROOT / "data" / "raw")
    ap.add_argument("--out-dir", type=Path, default=ROOT / "data" / "clean")
    ap.add_argument("--skip-download", action="store_true")
    args = ap.parse_args()

    quarters = quarter_range(args.start, args.end)
    zips = []
    for q in quarters:
        if args.skip_download:
            year, n = q.split("Q")
            zips.append(args.raw_dir / f"faers_ascii_{year}q{n}.zip")
        else:
            zips.append(download_quarter(q, args.raw_dir))

    # 1. Read every quarter's tables and stack them.
    tables: dict[str, list[pd.DataFrame]] = {t: [] for t in TABLES}
    deleted: set[str] = set()
    for q, z in zip(quarters, zips):
        print(f"[read] {q}")
        for t in TABLES:
            df = read_table(z, t)
            df["quarter"] = q
            tables[t].append(df)
        deleted |= read_deleted_caseids(z)
    stacked = {t: pd.concat(dfs, ignore_index=True) for t, dfs in tables.items()}

    # 2. Deduplicate on DEMO, then filter every other table to the kept report versions.
    # 'quarter' differs between re-exports of the same row, so exclude it from exact-dup checks.
    demo_q = stacked["DEMO"][["primaryid", "quarter"]].drop_duplicates("primaryid", keep="last")
    demo, stats = deduplicate_demo(stacked["DEMO"].drop(columns="quarter"), deleted)
    demo = demo.merge(demo_q, on="primaryid", how="left")
    keep = set(demo["primaryid"])
    stats["n_quarters"] = len(quarters)
    stats["n_deleted_caseids_listed"] = len(deleted)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    demo.to_parquet(args.out_dir / "demo.parquet", index=False)
    for t in TABLES:
        if t == "DEMO":
            continue
        clean = filter_to_primaryids(stacked[t].drop(columns="quarter"), keep)
        stats[f"{t.lower()}_rows_raw"] = len(stacked[t])
        stats[f"{t.lower()}_rows_clean"] = len(clean)
        clean.to_parquet(args.out_dir / f"{t.lower()}.parquet", index=False)
        if t == "DRUG":
            strings = unique_drug_strings(clean)
            strings.to_csv(args.out_dir / "drug_strings.csv", index=False)
            stats["unique_drug_strings"] = len(strings)

    (args.out_dir / "dedup_stats.json").write_text(json.dumps(stats, indent=2))
    print(json.dumps(stats, indent=2))
    print(f"[done] clean tables in {args.out_dir}")


if __name__ == "__main__":
    main()
