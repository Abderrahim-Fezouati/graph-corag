from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dict", dest="dict_path", required=True)
    ap.add_argument("--overlay", dest="overlay_path", required=True)
    ap.add_argument(
        "--allow_overlay_new_keys",
        action="store_true",
        help="Allow overlay keys not present in base dict.",
    )
    return ap.parse_args()


def _as_str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        raise TypeError(f"Expected list[str], got {type(value).__name__}")
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise TypeError(f"Expected string alias, got {type(item).__name__}")
        s = item.strip()
        if s:
            out.append(s)
    return out


def main() -> None:
    args = parse_args()
    dict_path = Path(args.dict_path)
    overlay_path = Path(args.overlay_path)

    base = json.loads(dict_path.read_text(encoding="utf-8"))
    overlay = json.loads(overlay_path.read_text(encoding="utf-8"))
    if not isinstance(base, dict) or not isinstance(overlay, dict):
        raise TypeError("Both dict and overlay files must be JSON objects")

    base_norm: dict[str, list[str]] = {}
    overlay_norm: dict[str, list[str]] = {}

    for kg_id, aliases in base.items():
        if not isinstance(kg_id, str):
            raise TypeError("Base dict keys must be strings")
        base_norm[kg_id] = sorted(set(_as_str_list(aliases)), key=str.casefold)
    for kg_id, aliases in overlay.items():
        if not isinstance(kg_id, str):
            raise TypeError("Overlay keys must be strings")
        vals = sorted(set(_as_str_list(aliases)), key=str.casefold)
        if vals:
            overlay_norm[kg_id] = vals

    if not args.allow_overlay_new_keys:
        missing = sorted(set(overlay_norm) - set(base_norm))
        if missing:
            raise AssertionError(
                f"Overlay has {len(missing)} keys absent from base dict. "
                f"Examples: {missing[:10]}"
            )

    overlap_keys: list[str] = []
    overlap_total = 0
    for kg_id, aliases in overlay_norm.items():
        base_aliases = set(base_norm.get(kg_id, []))
        inter = base_aliases.intersection(aliases)
        if inter:
            overlap_keys.append(kg_id)
            overlap_total += len(inter)

    if overlap_keys:
        raise AssertionError(
            f"Overlay intersects base aliases for {len(overlap_keys)} keys "
            f"({overlap_total} overlapping aliases). Examples: {overlap_keys[:10]}"
        )

    top20 = sorted(
        ((kg_id, len(vals)) for kg_id, vals in overlay_norm.items()),
        key=lambda x: (-x[1], x[0]),
    )[:20]

    total_aliases_base = sum(len(v) for v in base_norm.values())
    total_aliases_overlay = sum(len(v) for v in overlay_norm.values())

    print(f"dict_keys={len(base_norm)}")
    print(f"overlay_keys={len(overlay_norm)}")
    print(f"total_aliases_base={total_aliases_base}")
    print(f"total_aliases_overlay={total_aliases_overlay}")
    print("top_overlay_kg_ids:")
    for kg_id, n in top20:
        print(f"  {kg_id}\t{n}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # pragma: no cover
        print(f"[validate_dict_overlay] FAIL: {e}", file=sys.stderr)
        raise
