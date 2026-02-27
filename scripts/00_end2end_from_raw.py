import os, sys, subprocess, argparse

p = argparse.ArgumentParser()
p.add_argument("--proj", required=True)
p.add_argument("--dict", required=True)
p.add_argument("--kg", required=True)
p.add_argument("--schema", required=True)
p.add_argument("--corpus", required=True)
p.add_argument("--raw", required=True)
p.add_argument("--outdir", required=True)
p.add_argument("--topk", type=int, default=80)
args = p.parse_args()

os.makedirs(args.outdir, exist_ok=True)
structured = os.path.join(args.outdir, "queries.structured.jsonl")

# 1) analyze raw → structured
subprocess.check_call(
    [
        sys.executable,
        os.path.join(args.proj, "scripts", "03_analyze_queries_sapbert.py"),
        "--dict",
        args.dict,
        "--input",
        args.raw,
        "--out",
        structured,
    ]
)

# 2) run hybrid
subprocess.check_call(
    [
        sys.executable,
        os.path.join(args.proj, "scripts", "rl", "scrape_run_verbose.py"),
        "--proj",
        os.path.join(args.proj, "hybridkg_minimal"),
        "--corpus",
        args.corpus,
        "--kg",
        args.kg,
        "--dict",
        args.dict,
        "--schema",
        args.schema,
        "--queries",
        structured,
        "--out",
        args.outdir,
        "--topk",
        str(args.topk),
        "--min_constraints",
        "1",
        "--mode",
        "both",
        "--bm25_mod_path",
        os.path.join(args.proj, "src", "hybridkg", "text_retriever.py"),
        "--dense_mod_path",
        os.path.join(args.proj, "src", "hybridkg", "dense_retriever.py"),
        "--kg_mod_path",
        os.path.join(args.proj, "src", "hybridkg", "kg_loader.py"),
    ]
)
print("Done. Output dir:", args.outdir)
