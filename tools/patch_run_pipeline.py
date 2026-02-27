import re, sys, io, os

rp = r"F:\graph-corag-clean\scripts\pipeline\run_pipeline.py"
with open(rp, "r", encoding="utf-8") as f:
    src = f.read()

# (A) Add new CLI arguments after --run_tag if not already present
if "--corpus" not in src:
    pattern = r'(parser\.add_argument\(\s*"--run_tag"[^)]*\)\s*)'
    addition = (
        r"\1\n"
        r'    parser.add_argument("--corpus", required=True)\n'
        r'    parser.add_argument("--dict", required=True)\n'
        r'    parser.add_argument("--overlay", required=True)\n'
        r'    parser.add_argument("--schema", required=True)\n'
        r'    parser.add_argument("--bm25_mod_path", required=True)\n'
        r'    parser.add_argument("--dense_mod_path", required=True)'
    )
    src, n = re.subn(pattern, addition, src, flags=re.MULTILINE)
    if n == 0:
        print(
            "WARNING: Could not find anchor after --run_tag; arguments may already exist.",
            file=sys.stderr,
        )

# (B) Replace the subprocess.run([...]) block to forward all required args
new_call = """
    subprocess.run([
        "python", "scripts/run_hybrid.py",
        "--corpus", args.corpus,
        "--kg", args.kg_csv,
        "--dict", args.dict,
        "--overlay", args.overlay,
        "--schema", args.schema,
        "--queries", qpath,
        "--out", args.out_dir,
        "--bm25_mod_path", args.bm25_mod_path,
        "--dense_mod_path", args.dense_mod_path
    ], check=True)
""".strip()

src, n2 = re.subn(
    r'subprocess\.run\(\[\s*?"python",\s*"scripts\/run_hybrid\.py"[\s\S]*?\]\s*,\s*check=True\)',
    new_call,
    src,
    flags=re.MULTILINE,
)
if n2 == 0:
    print(
        "WARNING: Could not replace subprocess.run(...) block; it may already be patched.",
        file=sys.stderr,
    )

with open(rp, "w", encoding="utf-8") as f:
    f.write(src)

print("Patched:", rp)
