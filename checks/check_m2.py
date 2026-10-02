"""
Milestone 2 acceptance check for evals/scorer.py. You don't need to edit this file.

    python checks/check_m2.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from evals.scorer import results_match  # noqa: E402

CASES = [
    ("identical", [[1, "a"]], [[1, "a"]], False, True),
    ("different value", [[1, "a"]], [[2, "a"]], False, False),
    ("different row count", [[1], [2]], [[1]], False, False),
    ("order ignored when ordered=False", [[1], [2]], [[2], [1]], False, True),
    ("order matters when ordered=True", [[1], [2]], [[2], [1]], True, False),
    ("float tolerance", [[0.3]], [[0.1 + 0.2]], False, True),
    ("rounding to 2 decimals", [[12.3456]], [[12.35]], False, True),
    ("string case and spaces", [["SP "]], [["sp"]], False, True),
    ("empty vs empty", [], [], False, True),
    ("mixed types still sortable", [[None, 1], ["x", 2]], [["x", 2], [None, 1]], False, True),
]

failed = 0
failed_names = []
for name, gold, agent, ordered, expected in CASES:
    try:
        got = results_match(gold, agent, ordered=ordered)
    except Exception as e:  # noqa: BLE001
        got = f"crashed: {type(e).__name__}: {e}"
    ok = got == expected
    failed += not ok
    if not ok:
        failed_names.append(name)
    print(f"  {'✅' if ok else '❌'} {name}" + ("" if ok else f"  expected {expected}, got {got}"))

print(f"\n{len(CASES) - failed} passed, {failed} failed")
if "mixed types still sortable" in failed_names:
    print("Tip for 'mixed types': Python can't compare None with 'x'. Sort with key=lambda row: [str(c) for c in row].")
sys.exit(1 if failed else 0)
