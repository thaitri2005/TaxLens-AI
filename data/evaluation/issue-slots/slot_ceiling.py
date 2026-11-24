"""Phase 1 of data/evaluation/issue-slots/plan.md: slot ceiling from the saved oracle run."""

import json

run = json.load(open("data/evaluation/runs/oracle-reviewed.json", encoding="utf-8"))
cases = run["cases"]


def found(case, B, q, s):
    issues = case.get("queries", [])
    slots = []  # (issue index, places)
    used = 0
    for j in range(len(issues)):
        if used + s > B - q:
            break
        slots.append(j)
        used += s
    q_eff = B - used
    out = []
    for p, base in enumerate(case["baseline_ranks"]):
        hit = base is not None and base <= q_eff
        hit = hit or any((r := issues[j]["ranks"][p]) is not None and r <= s for j in slots)
        out.append(hit)
    return out


def recall(fn):
    vals = [sum(fn(c)) / len(c["baseline_ranks"]) for c in cases]
    return round(sum(vals) / len(vals), 3)


result = {}
for B, splits in ((5, ((2, 1), (3, 1))), (8, ((4, 1), (3, 2)))):

    def base(c, B=B):
        return [r is not None and r <= B for r in c["baseline_ranks"]]

    result[f"B={B} question only"] = recall(base)
    for q, s in splits:

        def fn(c, B=B, q=q, s=s):
            return found(c, B, q, s)

        up = sum(sum(fn(c)) > sum(base(c)) for c in cases)
        down = sum(sum(fn(c)) < sum(base(c)) for c in cases)
        result[f"B={B} q={q} s={s}"] = f"{recall(fn)} (up {up}, down {down})"
print(json.dumps(result, indent=1))
