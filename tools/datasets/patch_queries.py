import json, sys, os

inp = sys.argv[1]
out = sys.argv[2]
cnt_in, cnt_out = 0, 0

with open(inp, "r", encoding="utf-8") as fin, open(out, "w", encoding="utf-8") as fout:
    for line in fin:
        line = line.strip()
        if not line:
            continue
        cnt_in += 1
        rec = json.loads(line)
        intent = rec.get("intent")
        rel = rec.get("gt_rel")

        # Fix 1: ADVERSE_EFFECT uses disease tail2
        if intent == "yesno" and rel == "ADVERSE_EFFECT":
            if (not rec.get("tail1")) and rec.get("tail2"):
                rec["tail1"] = rec["tail2"]

        # Fix 2: expand list queries into multiple yesno
        if intent == "list":
            head = rec.get("head")
            tails = rec.get("tails") or []
            for t in tails:
                r2 = dict(rec)
                r2["intent"] = "yesno"
                r2["tail1"] = t
                if r2.get("gt_rel") == "ADVERSE_EFFECT":
                    r2["tail2"] = t
                    r2["tail1"] = ""
                r2["text"] = (
                    f"Check if {t} relates to {head} via {r2.get('gt_rel','REL')}?"
                )
                r2.pop("tails", None)
                fout.write(json.dumps(r2, ensure_ascii=False) + "\n")
                cnt_out += 1
        else:
            fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
            cnt_out += 1

print(f"Patched from {cnt_in} input lines to {cnt_out} output lines")
