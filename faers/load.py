"""Read the '$'-delimited tables out of a FAERS quarterly zip.

Each zip contains (names vary slightly in case between quarters):
  ascii/DEMO24Q1.txt  demographics, one row per report version (primaryid)
  ascii/DRUG24Q1.txt  drugs listed on each report
  ascii/REAC24Q1.txt  reactions, coded as MedDRA Preferred Terms
  ascii/OUTC24Q1.txt  outcomes (death, hospitalization, ...)
  ascii/INDI24Q1.txt  indications
  ascii/THER24Q1.txt  therapy dates
  ascii/RPSR24Q1.txt  report sources
  deleted/DELETE24Q1.txt  caseids the FDA has removed (newer quarters only)
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import pandas as pd

TABLES = ["DEMO", "DRUG", "REAC", "OUTC", "INDI", "THER", "RPSR"]

# Only the columns we need downstream; keeps memory manageable for DRUG/REAC.
KEEP_COLS = {
    "DEMO": ["primaryid", "caseid", "caseversion", "i_f_code", "event_dt", "init_fda_dt",
             "fda_dt", "rept_cod", "age", "age_cod", "sex", "wt", "wt_cod",
             "occp_cod", "reporter_country", "occr_country"],
    "DRUG": ["primaryid", "caseid", "drug_seq", "role_cod", "drugname", "prod_ai",
             "route", "dose_vbm", "dose_amt", "dose_unit", "dose_form", "nda_num"],
    "REAC": ["primaryid", "caseid", "pt", "drug_rec_act"],
    "OUTC": ["primaryid", "caseid", "outc_cod"],
    "INDI": ["primaryid", "caseid", "indi_drug_seq", "indi_pt"],
    "THER": ["primaryid", "caseid", "dsg_drug_seq", "start_dt", "end_dt"],
    "RPSR": ["primaryid", "caseid", "rpsr_cod"],
}


def _find_member(zf: zipfile.ZipFile, table: str) -> str | None:
    """Locate e.g. 'ascii/DRUG24Q1.txt' regardless of folder/file case."""
    pat = re.compile(rf"(^|/){table}\d{{2}}Q[1-4]\.txt$", re.IGNORECASE)
    hits = [n for n in zf.namelist() if pat.search(n)]
    return hits[0] if hits else None


def read_table(zip_path: Path, table: str) -> pd.DataFrame:
    """Read one FAERS table from a quarterly zip as all-string columns."""
    with zipfile.ZipFile(zip_path) as zf:
        member = _find_member(zf, table)
        if member is None:
            raise FileNotFoundError(f"{table} not found in {zip_path.name}")
        raw = zf.read(member)

    # FAERS files are mostly ASCII but occasionally contain latin-1 bytes.
    text = raw.decode("latin-1")
    df = pd.read_csv(
        io.StringIO(text),
        sep="$",
        dtype=str,
        keep_default_na=False,
        na_values=[""],
        quoting=3,          # csv.QUOTE_NONE: free-text fields contain stray quotes
        on_bad_lines="warn",
    )
    df.columns = [c.strip().lower() for c in df.columns]
    # Some older quarters have a trailing '$' -> an empty unnamed column.
    df = df.loc[:, ~df.columns.str.startswith("unnamed")]

    wanted = [c for c in KEEP_COLS.get(table, df.columns) if c in df.columns]
    df = df[wanted].copy()
    for c in df.columns:
        df[c] = df[c].str.strip()
    return df


def read_deleted_caseids(zip_path: Path) -> set[str]:
    """Return caseids listed in the quarter's DELETE file (empty set if none)."""
    with zipfile.ZipFile(zip_path) as zf:
        member = _find_member(zf, "DELETE")
        if member is None:
            return set()
        text = zf.read(member).decode("latin-1")
    return {tok for tok in re.split(r"[\s$,]+", text) if tok.isdigit()}
