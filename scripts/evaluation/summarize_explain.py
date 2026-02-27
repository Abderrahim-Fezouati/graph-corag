import csv, argparse, io


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--explain_csv", required=True)
    args = ap.parse_args()

    rows = list(csv.DictReader(io.open(args.explain_csv, "r", encoding="utf-8")))
    total = len(rows)
    both = sum(1 for r in rows if r["both_edges_present"] == "True")
    e1 = sum(1 for r in rows if r["edge1_present"] == "True")
    e2 = sum(1 for r in rows if r["edge2_present"] == "True")
    link_ok = sum(
        1
        for r in rows
        if r["head_surface_link_ok"] == "True"
        and r["tail1_surface_link_ok"] == "True"
        and r["tail2_surface_link_ok"] == "True"
    )

    print(f"[summary] queries={total}")
    print(f"          both_edges_present={both} ({both/total:.1%})")
    print(f"          edge1_present={e1}  edge2_present={e2}")
    print(f"          full_entity_link_ok={link_ok} ({link_ok/total:.1%})")


if __name__ == "__main__":
    main()
