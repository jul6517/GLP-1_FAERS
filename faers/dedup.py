"""Deduplicate FAERS reports.

FAERS stores every *version* of a case as its own row (primaryid = caseid + caseversion).
Follow-up reports for the same case appear again, often in later quarters. Counting
them all would inflate ROR/PRR, so we keep one version per case.

Rule (follows the FDA FAERS README):
  1. For each caseid, keep the row with the latest fda_dt.
  2. If fda_dt ties, keep the highest primaryid.
  3. Drop caseids that appear in any quarter's DELETE file.
The other tables are then filtered to the kept primaryids.
"""

from __future__ import annotations

import pandas as pd


def deduplicate_demo(demo: pd.DataFrame, deleted_caseids: set[str]) -> tuple[pd.DataFrame, dict]:
    """Return one DEMO row per caseid, plus a dict of counts for the methods section."""
    stats = {"demo_rows_raw": len(demo)}

    d = demo.copy()
    # Exact duplicate rows occur when the same version is re-exported in two quarters.
    d = d.drop_duplicates()
    stats["after_exact_dup_removal"] = len(d)

    d["_fda_dt"] = pd.to_numeric(d["fda_dt"], errors="coerce")
    d["_pid"] = pd.to_numeric(d["primaryid"], errors="coerce")
    d = d.sort_values(["caseid", "_fda_dt", "_pid"], na_position="first")
    d = d.drop_duplicates(subset="caseid", keep="last")
    stats["after_latest_version_per_case"] = len(d)

    d = d[~d["caseid"].isin(deleted_caseids)]
    stats["after_removing_deleted_cases"] = len(d)

    return d.drop(columns=["_fda_dt", "_pid"]).reset_index(drop=True), stats


def filter_to_primaryids(df: pd.DataFrame, keep_ids: set[str] | pd.Series) -> pd.DataFrame:
    """Keep rows of a child table (DRUG/REAC/...) belonging to kept report versions."""
    return df[df["primaryid"].isin(keep_ids)].drop_duplicates().reset_index(drop=True)
