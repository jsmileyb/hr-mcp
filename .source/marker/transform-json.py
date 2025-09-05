#!/usr/bin/env python3
import argparse, json, re, html, sys
from typing import Any

STRIP_HTML_TYPES = {"SectionHeader", "Text"}
DROP_KEYS = {"polygon", "bbox", "section_hierarchy"}

def strip_tags_preserve_text(s: str) -> str:
    if not isinstance(s, str):
        return s
    # Remove script/style blocks if they exist
    s = re.sub(r'<\s*(script|style)[^>]*>.*?<\s*/\s*\1\s*>', ' ', s, flags=re.I|re.S)
    # Replace tags with space
    s = re.sub(r'<[^>]+>', ' ', s)
    # Decode HTML entities (&nbsp;, &amp;, etc.)
    s = html.unescape(s)
    # Collapse whitespace
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def transform(node: Any) -> Any:
    if isinstance(node, dict):
        new_dict = {}
        for k, v in node.items():
            if k in DROP_KEYS:
                continue  # strip polygon and bbox
            if k == "html" and node.get("block_type") in STRIP_HTML_TYPES:
                new_dict[k] = strip_tags_preserve_text(v)
            else:
                new_dict[k] = transform(v)
        return new_dict
    elif isinstance(node, list):
        return [transform(item) for item in node]
    else:
        return node

def main():
    ap = argparse.ArgumentParser(
        description="Remove 'polygon'/'bbox' keys and strip HTML tags (preserve text) from SectionHeader/Text."
    )
    ap.add_argument("input", help="Path to input JSON file")
    ap.add_argument("output", help="Path to output JSON file")
    ap.add_argument("--indent", type=int, default=2,
                   help="Indent level for output JSON (default: 2). Use 0 for compact.")
    args = ap.parse_args()

    try:
        with open(args.input, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON in {args.input}: {e}", file=sys.stderr)
        sys.exit(1)

    cleaned = transform(data)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, ensure_ascii=False,
                  indent=None if args.indent == 0 else args.indent)

    print(f"✅ Cleaned JSON written to {args.output}")

if __name__ == "__main__":
    main()
