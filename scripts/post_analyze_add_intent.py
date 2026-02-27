import json, sys

sys.path.insert(0, r"F:\graph-corag-clean\src")
from graphcorag.intent_router import route_intent


def iter_jsonl(p):
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


if __name__ == "__main__":
    in_p, out_p = sys.argv[1], sys.argv[2]
    with open(out_p, "w", encoding="utf-8") as out:
        for obj in iter_jsonl(in_p):
            text = obj.get("text", "")
            surfaces = obj.get("extracted_surfaces") or []
            intent, cues = route_intent(text, surfaces)
            obj["intent"] = intent
            obj["relation_hint"] = cues
            out.write(json.dumps(obj, ensure_ascii=False) + "\n")
