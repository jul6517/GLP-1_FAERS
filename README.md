# GLP-1 RA Safety Signals in FAERS

Disproportionality analysis (ROR / PRR) of GLP-1 receptor agonists (semaglutide, liraglutide,
dulaglutide, tirzepatide) vs. an SGLT2-inhibitor active comparator, using the FDA Adverse Event
Reporting System (FAERS), with LLM-assisted drug-name normalization and label extraction.

## Step 1 — Download and deduplicate FAERS

```bash
pip install -r requirements.txt
python run_step1.py --start 2023Q1 --end 2025Q2
```

Raw zips go to `data/raw/`, clean tables to `data/clean/` (Parquet). `data/` is not committed;
anyone can regenerate it with the command above.

**Deduplication** (follows the FDA FAERS README):
1. Stack DEMO across all quarters and drop exact duplicate rows.
2. For each `caseid`, keep the version with the latest `fda_dt`; break ties by highest `primaryid`.
3. Remove caseids listed in any quarter's DELETE file.
4. Filter DRUG / REAC / OUTC / INDI / THER / RPSR to the kept `primaryid`s.

Row counts after each step are written to `data/clean/dedup_stats.json` for the methods section.

`data/clean/drug_strings.csv` lists every unique (`drugname`, `prod_ai`) string with report counts
and a naive regex match (`baseline_match`). This is the input to the LLM normalization task and the
baseline it is evaluated against.

## Tests

```bash
python -m pytest -q
```

Tests use tiny synthetic FAERS-format zips, so they run offline.

## Roadmap
- [x] Step 1: download, parse, deduplicate
- [ ] Step 2: LLM drug-name normalization + gold-standard annotation + P/R/F1 vs. baseline
- [ ] Step 3: LLM extraction of adverse reactions from drug labels → MedDRA PTs
- [ ] Step 4: ROR / PRR with 95% CI, GLP-1 vs. SGLT2i comparator
- [ ] Step 5: Figures, notoriety-bias sensitivity analysis (by report period)
