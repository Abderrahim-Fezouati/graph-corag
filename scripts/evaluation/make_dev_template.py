import json, random, argparse, io, os


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--queries", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--n", type=int, default=200)
    args = ap.parse_args()

    qs = [json.loads(x) for x in io.open(args.queries, "r", encoding="utf-8")]
    sample = qs[: args.n] if len(qs) <= args.n else random.sample(qs, args.n)
    for i, j in enumerate(sample, 1):
        j_out = {
            "qid": i,
            "text": j["text"],
            "head": j["head"],
            "rel1": j["rel1"],
            "tail1": j["tail1"],
            "rel2": j["rel2"],
            "tail2": j["tail2"],
            "support_gold": "",  # fill with: text | kg | both | none
            "notes": "",
        }
        print(json.dumps(j_out, ensure_ascii=False))
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    # we print to stdout; caller redirects into the file


if __name__ == "__main__":
    main()
