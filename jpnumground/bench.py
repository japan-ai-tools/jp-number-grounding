"""Score on data/jp_number_grounding_cases_v1.jsonl.

python -m jpnumground.bench
The naive checker is what a quick script usually does: NFKC, take every run of ASCII digits
in the summary, drop commas, and flag it when that string is not in the source.
Cases and rules come from the same author: this is a regression suite, not proof.
"""
import json
import os
import re
import sys
import unicodedata

from .ground import check

CASES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data",
                     "jp_number_grounding_cases_v1.jsonl")


def load(path=CASES):
    with open(path, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def naive_has_problem(source, summary):
    src = unicodedata.normalize("NFKC", source).replace(",", "")
    nums = re.findall(r"\d+(?:\.\d+)?", unicodedata.normalize("NFKC", summary).replace(",", ""))
    return any(n not in src for n in nums)


def ours_problems(case):
    return sorted(p["normalized"] for p in check(case["source"], case["summary"])["problems"])


def score(cases=None):
    cases = cases or load()
    exact = sum(ours_problems(c) == sorted(c["expected_problems"]) for c in cases)
    ours_bool = sum((not ours_problems(c)) == (not c["expected_problems"]) for c in cases)
    naive_bool = sum(naive_has_problem(c["source"], c["summary"]) == bool(c["expected_problems"]) for c in cases)
    return {"cases": len(cases), "jp_number_grounding_exact": exact, "jp_number_grounding_flag": ours_bool,
            "naive_flag": naive_bool}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    cases = load()
    r = score(cases)
    print(json.dumps(r))
    for c in cases:
        got = ours_problems(c)
        if got != sorted(c["expected_problems"]):
            print("MISS", c["id"], c["category"], "expected", c["expected_problems"], "got", got)


if __name__ == "__main__":
    main()
