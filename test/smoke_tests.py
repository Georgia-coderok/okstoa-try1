"""
Smoke tests for the Brain (agent). Run from the project root:

    python tests/smoke_tests.py

Each test asks a question and checks the result. Results are also saved to
eval/smoke_results.jsonl so you can compare runs over time.
"""

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brain_starter import answer  # noqa: E402


def has(text):
    return lambda r: r.get("answer") is not None and text.lower() in r["answer"].lower()


def is_null(r):
    return r.get("answer") is None


def verified(r):
    return r.get("verification", {}).get("ok", False)


TESTS = [
    # (name, question, list of (check_name, check_fn))
    ("lookup_en", "What is the fire rating of door D-214?",
     [("answer contains EI60", has("EI60")), ("citations verified", verified)]),
    ("lookup_fi", "Mikä on oven D-214 paloluokka?",
     [("answer contains EI60", has("EI60")), ("citations verified", verified)]),
    ("abstain_missing_data", "How many floors does the building have?",
     [("answer is null (no guessing)", is_null)]),
    ("abstain_unknown_tag", "What is the fire rating of door D-999?",
     [("answer is null (tag does not exist)", is_null)]),
    ("schedule_attr", "How wide is door D-214?",
     [("answer contains 1000", has("1000")), ("citations verified", verified)]),
]


def main():
    out_path = ROOT / "eval" / "smoke_results.jsonl"
    out_path.parent.mkdir(exist_ok=True)
    passed = failed = 0

    with out_path.open("a", encoding="utf-8") as f:
        for name, question, checks in TESTS:
            t0 = time.time()
            try:
                r = answer(question)
            except Exception as e:  # keep going if one test crashes
                r = {"answer": None, "error": repr(e)}
            dt = time.time() - t0

            results = [(cname, bool(fn(r))) for cname, fn in checks]
            ok = all(v for _, v in results) and "error" not in r
            passed += ok
            failed += not ok

            print(f"\n[{'PASS' if ok else 'FAIL'}] {name}  ({dt:.1f}s)")
            print(f"  Q: {question}")
            print(f"  A: {r.get('answer')}   confidence={r.get('confidence')}")
            for cname, v in results:
                print(f"     {'ok ' if v else 'XX '} {cname}")
            if "error" in r:
                print(f"     XX  error: {r['error']}")

            f.write(json.dumps({"ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                                "model": os.environ.get("BRAIN_MODEL", "default"),
                                "test": name, "ok": ok, "seconds": round(dt, 1),
                                "result": r}, ensure_ascii=False) + "\n")

    print(f"\n==== {passed} passed, {failed} failed  (saved to {out_path.relative_to(ROOT)}) ====")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()