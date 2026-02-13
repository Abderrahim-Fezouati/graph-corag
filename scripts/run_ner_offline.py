# -*- coding: utf-8 -*-
"""
run_ner_offline.py
------------------
Runs BC5CDR NER over passages and preserves document IDs.
"""

import json
import spacy
import argparse


def load_jsonl(path):
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--model", default="en_ner_bc5cdr_md")
    args = p.parse_args()

    print(f"[INFO] Loading spaCy model: {args.model}")
    nlp = spacy.load(args.model)

    with open(args.output, "w", encoding="utf-8") as out:
        for ex in load_jsonl(args.input):
            doc_id = ex.get("id") or ex.get("doc_id")
            text = ex.get("text", "")

            doc = nlp(text)
            ents = [
                {
                    "text": ent.text,
                    "label": ent.label_,
                    "start": ent.start_char,
                    "end": ent.end_char,
                }
                for ent in doc.ents
            ]

            out.write(json.dumps({
                "id": doc_id,
                "text": text,
                "ents": ents,
            }) + "\n")

    print(f"[DONE] wrote NER JSONL -> {args.output}")


if __name__ == "__main__":
    main()
