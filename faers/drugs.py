"""Study drug lists and a simple string-matching baseline.

The string matcher here is intentionally naive. It is the *baseline* that the
LLM drug-name normalizer will be compared against in the evaluation step.
"""

from __future__ import annotations

import re

import pandas as pd

# ingredient -> brand names / common variants (lowercase)
STUDY_DRUGS = {
    # GLP-1 receptor agonists (exposure)
    "semaglutide": ["semaglutide", "ozempic", "wegovy", "rybelsus"],
    "liraglutide": ["liraglutide", "victoza", "saxenda"],
    "dulaglutide": ["dulaglutide", "trulicity"],
    "tirzepatide": ["tirzepatide", "mounjaro", "zepbound"],  # GIP/GLP-1 dual agonist
    # SGLT2 inhibitors (active comparator)
    "empagliflozin": ["empagliflozin", "jardiance"],
    "dapagliflozin": ["dapagliflozin", "farxiga", "forxiga"],
    "canagliflozin": ["canagliflozin", "invokana"],
    "ertugliflozin": ["ertugliflozin", "steglatro"],
}
GLP1 = ["semaglutide", "liraglutide", "dulaglutide", "tirzepatide"]
SGLT2 = ["empagliflozin", "dapagliflozin", "canagliflozin", "ertugliflozin"]

_PATTERNS = {
    ing: re.compile(r"\b(" + "|".join(map(re.escape, names)) + r")\b")
    for ing, names in STUDY_DRUGS.items()
}


def baseline_match(text: str | None) -> list[str]:
    """Return study ingredients whose name/brand appears as a whole word in text."""
    if not isinstance(text, str):
        return []
    t = text.lower()
    return [ing for ing, pat in _PATTERNS.items() if pat.search(t)]


def unique_drug_strings(drug: pd.DataFrame) -> pd.DataFrame:
    """Collapse DRUG rows to unique (drugname, prod_ai) strings with report counts.

    This table is the input for the LLM normalization task: there are far fewer
    unique strings than rows, so we label/normalize each string once.
    """
    g = (
        drug.assign(drugname=drug["drugname"].fillna("").str.upper().str.strip(),
                    prod_ai=drug["prod_ai"].fillna("").str.upper().str.strip())
        .groupby(["drugname", "prod_ai"], as_index=False)
        .agg(n_rows=("primaryid", "size"), n_reports=("primaryid", "nunique"))
        .sort_values("n_reports", ascending=False)
        .reset_index(drop=True)
    )
    g["baseline_match"] = [
        ";".join(sorted(set(baseline_match(a) + baseline_match(b))))
        for a, b in zip(g["drugname"], g["prod_ai"])
    ]
    return g
