#!/usr/bin/env python3
import json
import sys
from pathlib import Path
import argparse

STRIP_HTML_TYPES = {"SectionHeader", "Text"}
DROP_KEYS = {"polygon", "bbox"}

def transform(node):
    """
    Recursively:
      - remove keys in DROP_KEYS
      - if block_type in STRIP_HTML_TYPES, set html to ""
    """
    if isinstance(node, dict):
        # First, drop keys we don't want
        d = {k: v for k, v in node.items() if k not in DROP_KEYS}

        # Strip html for specific block types
        bt = d.get("block_type")
        if isinstance(bt, str) and bt in STRIP_HTML_TYPES and "html" in d:
            d["html"] = ""

        # Recurse into remaining values
        for k, v in list(d.items()):
            d[k] = transform(v)

        return d

    if isinstance(node, list):
        return [transform(item) for item in node]

    return node

def parse_args():
    p = argparse.ArgumentParser(
        description="Remove 'polygon'/'bbox' and clear html for SectionHeader/Text blocks."
    )
    p.add_argument("input", help="Path to the input JSON file.")
    p.add_argument("output", help="Path to write the cleaned JSON file.")
    p.add_argument("--indent", type=int, default=2,
                   help="Indent level for output JSON (default: 2). Use 0 for compact.")
    return p.parse_args()

def main():
    args = parse_args()
    in_path = Path(args.input)
    out_path = Path(args.output)

    if not in_path.exists():
        print(f"Error: input file not found: {in_path}", file=sys.stderr)
        sys.exit(1)

    try:
        with in_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: invalid JSON in {in_path}:\n  {e}", file=sys.stderr)
        sys.exit(1)

    cleaned = transform(data)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(cleaned, f, indent=None if args.indent == 0 else args.indent, ensure_ascii=False)

    print(f"Cleaned JSON written to: {out_path}")

if __name__ == "__main__":
    main()
