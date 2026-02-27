import csv, json, io, argparse, os


def load_overlay(path):
    with io.open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_kg(path):
    edges = set()
    with io.open(path, "r", encoding="utf-8") as f:
        rdr = csv.reader(f)
        for row in rdr:
            if len(row) != 3:
                continue
            h, r, t = [x.strip() for x in row]
            edges.add((h, r, t))
    return edges


def first_surface(overlay, eid):
    arr = overlay.get(eid) or []
    return arr[0] if arr else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--queries", required=True)
    ap.add_argument("--kg", required=True)
    ap.add_argument("--overlay", required=True)
    ap.add_argument("--out_csv", required=True)
    args = ap.parse_args()

    overlay = load_overlay(args.overlay)
    kg = load_kg(args.kg)

    rows = []
    with io.open(args.queries, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            q = json.loads(line)
            head, r1, t1, r2, t2 = (
                q["head"],
                q["rel1"],
                q["tail1"],
                q["rel2"],
                q["tail2"],
            )
            e1 = (head, r1, t1)
            e2 = (head, r2, t2)

            hs = first_surface(overlay, head)
            t1s = first_surface(overlay, t1)
            t2s = first_surface(overlay, t2)

            row = dict(
                qid=i,
                text=q["text"],
                head=head,
                head_surface=hs,
                head_surface_links=head if hs else "",
                head_surface_link_ok=bool(hs),
                rel1=r1,
                tail1=t1,
                tail1_surface=t1s,
                tail1_surface_links=t1 if t1s else "",
                tail1_surface_link_ok=bool(t1s),
                edge1_present=e1 in kg,
                rel2=r2,
                tail2=t2,
                tail2_surface=t2s,
                tail2_surface_links=t2 if t2s else "",
                tail2_surface_link_ok=bool(t2s),
                edge2_present=e2 in kg,
                both_edges_present=(e1 in kg and e2 in kg),
            )
            rows.append(row)

    os.makedirs(os.path.dirname(args.out_csv), exist_ok=True)
    with io.open(args.out_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    total = len(rows)
    both = sum(1 for r in rows if r["both_edges_present"])
    one = sum(
        1
        for r in rows
        if (r["edge1_present"] or r["edge2_present"]) and not r["both_edges_present"]
    )
    none = total - both - one
    print(f"[explain] wrote {total} rows -> {args.out_csv}")
    print(
        f"[KG support] total={total}  both={both}  one={one}  none={none}  both%={100.0*both/total:.1f}%"
    )


if __name__ == "__main__":
    main()
