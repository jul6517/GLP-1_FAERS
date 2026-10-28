"""Tests on tiny synthetic FAERS-format zips (no network needed)."""

import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pandas as pd

from faers.dedup import deduplicate_demo
from faers.download import quarter_range
from faers.drugs import baseline_match
from faers.load import read_deleted_caseids, read_table

ROOT = Path(__file__).resolve().parents[1]

DEMO_HDR = "primaryid$caseid$caseversion$i_f_code$event_dt$mfr_dt$init_fda_dt$fda_dt$rept_cod$auth_num$mfr_num$mfr_sndr$lit_ref$age$age_cod$age_grp$sex$e_sub$wt$wt_cod$rept_dt$to_mfr$occp_cod$reporter_country$occr_country"
DRUG_HDR = "primaryid$caseid$drug_seq$role_cod$drugname$prod_ai$val_vbm$route$dose_vbm$cum_dose_chr$cum_dose_unit$dechal$rechal$lot_num$exp_dt$nda_num$dose_amt$dose_unit$dose_form$dose_freq"


def demo_row(pid, cid, ver, fda_dt):
    return f"{pid}${cid}${ver}$F$$${fda_dt}${fda_dt}$EXP$$$$$50$YR$$F$Y$$$$$MD$US$US"


def drug_row(pid, cid, seq, name, ai):
    return f"{pid}${cid}${seq}$PS${name}${ai}$1$SUBCUTANEOUS$$$$$$$$$$$$"


def make_zip(path: Path, tag: str, demo, drug, reac, deleted=None, trailing_dollar=False):
    end = "$" if trailing_dollar else ""
    files = {
        f"ASCII/DEMO{tag}.txt": [DEMO_HDR] + demo,
        f"ASCII/DRUG{tag}.txt": [DRUG_HDR] + drug,
        f"ASCII/REAC{tag}.txt": ["primaryid$caseid$pt$drug_rec_act"] + reac,
        f"ASCII/OUTC{tag}.txt": ["primaryid$caseid$outc_cod"] + [f"{r.split('$')[0]}${r.split('$')[1]}$HO" for r in demo],
        f"ASCII/INDI{tag}.txt": ["primaryid$caseid$indi_drug_seq$indi_pt"],
        f"ASCII/THER{tag}.txt": ["primaryid$caseid$dsg_drug_seq$start_dt$end_dt$dur$dur_cod"],
        f"ASCII/RPSR{tag}.txt": ["primaryid$caseid$rpsr_cod"],
    }
    with zipfile.ZipFile(path, "w") as zf:
        for name, lines in files.items():
            zf.writestr(name, "\n".join(l + end for l in lines) + "\n")
        if deleted:
            zf.writestr(f"Deleted/DELETE{tag}.txt", "\n".join(deleted) + "\n")


def build_fixture(raw: Path):
    raw.mkdir(parents=True)
    # Case 100: v1 in 24Q1, follow-up v2 in 24Q2 -> keep v2 (1002).
    # Case 200: two versions same fda_dt -> keep higher primaryid.
    # Case 300: deleted in 24Q2 -> dropped.
    # Case 400: only in 24Q2.
    make_zip(raw / "faers_ascii_2024q1.zip", "24Q1",
             demo=[demo_row(1001, 100, 1, 20240110), demo_row(2001, 200, 1, 20240115),
                   demo_row(2002, 200, 2, 20240115), demo_row(3001, 300, 1, 20240120)],
             drug=[drug_row(1001, 100, 1, "OZEMPIC", "SEMAGLUTIDE"),
                   drug_row(2001, 200, 1, "MOUNJARO 5MG", "TIRZEPATIDE"),
                   drug_row(2002, 200, 1, "MOUNJARO 5MG", "TIRZEPATIDE"),
                   drug_row(3001, 300, 1, "JARDIANCE", "EMPAGLIFLOZIN")],
             reac=["1001$100$Nausea$", "2001$200$Pancreatitis$", "2002$200$Pancreatitis$",
                   "3001$300$Ketoacidosis$"],
             trailing_dollar=True)
    make_zip(raw / "faers_ascii_2024q2.zip", "24Q2",
             demo=[demo_row(1002, 100, 2, 20240501), demo_row(4001, 400, 1, 20240502)],
             drug=[drug_row(1002, 100, 1, "OZEMPIC", "SEMAGLUTIDE"),
                   drug_row(4001, 400, 1, "SEMAGLUTIDE COMPOUNDED", "")],
             reac=["1002$100$Nausea$", "1002$100$Gastroparesis$", "4001$400$Vomiting$"],
             deleted=["300"])


def test_quarter_range():
    assert quarter_range("2023Q3", "2024Q2") == ["2023Q3", "2023Q4", "2024Q1", "2024Q2"]


def test_read_handles_trailing_dollar_and_deleted(tmp_path):
    build_fixture(tmp_path / "raw")
    demo = read_table(tmp_path / "raw" / "faers_ascii_2024q1.zip", "DEMO")
    assert not any(c.startswith("unnamed") for c in demo.columns)
    assert len(demo) == 4
    assert read_deleted_caseids(tmp_path / "raw" / "faers_ascii_2024q2.zip") == {"300"}


def test_dedup_rules():
    demo = pd.DataFrame({
        "primaryid": ["1001", "1002", "2001", "2002", "3001"],
        "caseid":    ["100", "100", "200", "200", "300"],
        "fda_dt":    ["20240110", "20240501", "20240115", "20240115", "20240120"],
    })
    out, stats = deduplicate_demo(demo, {"300"})
    assert sorted(out["primaryid"]) == ["1002", "2002"]
    assert stats["after_latest_version_per_case"] == 3


def test_baseline_match():
    assert baseline_match("OZEMPIC 1MG PEN") == ["semaglutide"]
    assert baseline_match("Mounjaro") == ["tirzepatide"]
    assert baseline_match("SEMAGLUTIDE/B12 compounded") == ["semaglutide"]
    assert baseline_match("OZEMPC") == []  # misspelling: baseline misses, LLM should catch


def test_end_to_end(tmp_path):
    build_fixture(tmp_path / "raw")
    out = tmp_path / "clean"
    subprocess.run([sys.executable, str(ROOT / "run_step1.py"), "--start", "2024Q1", "--end", "2024Q2",
                    "--skip-download", "--raw-dir", str(tmp_path / "raw"), "--out-dir", str(out)],
                   check=True, cwd=ROOT)
    demo = pd.read_parquet(out / "demo.parquet")
    assert sorted(demo["primaryid"]) == ["1002", "2002", "4001"]
    reac = pd.read_parquet(out / "reac.parquet")
    assert set(reac["primaryid"]) == {"1002", "2002", "4001"}
    assert len(reac) == 4
    stats = json.loads((out / "dedup_stats.json").read_text())
    assert stats["demo_rows_raw"] == 6
    assert stats["after_removing_deleted_cases"] == 3
    strings = pd.read_csv(out / "drug_strings.csv", keep_default_na=False)
    assert "SEMAGLUTIDE COMPOUNDED" in set(strings["drugname"])
