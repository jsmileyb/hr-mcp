"""Dynamic PTO accrual parsing utilities.

Parses the Employee Handbook markdown to extract:
 1. PTO accrual table (years -> hours per pay period & annual hours)
 2. Career Ladder Level (CLL) rule groups and their accrual patterns

The parser avoids hardcoding CLL lists so future handbook changes are picked
up automatically if the markdown bullet structure is preserved.

Current expected handbook snippet pattern (simplified):

 - Career Ladder Levels P7, P8, ... T8:
   - o Upon hire or promotion, employees will accrue 200 hours (five weeks) ...
 - Career Ladder Levels P5, P6, ... A4:
   - o Upon hire or promotion, employees in these levels will accrue PTO beginning at the eightyear incremental accrual rate (164.45) ... increase yearly up to a maximum of 200 hours ...
 - All other CLL's not identified above will begin at the 0-2 accrual rate.

Heuristics:
  * Any bullet starting with "- Career Ladder Levels" defines a group. We capture all tokens that look like alphanumeric CLL codes (e.g., P7, TP8, OR9, M1, A5, I6, T7).
  * We scan the following indented lines for keywords:
        "200 hours" -> fixed_200 group
        "164.45" or "eight" + "incremental" -> accelerated_164 group (start at 164.45, then follow table until capped at 200)
  * Fallback group for all others -> table group (base table values by years of service).

If the handbook wording changes, the detection relies only on these numeric
and phrase cues. Unknown groups will gracefully revert to table logic.
"""

from __future__ import annotations

import pathlib
import re
from typing import Dict, List, Any, Optional, Tuple

TABLE_HEADER_RE = re.compile(r"\|\s*Years of\s*\|.*Hours Per Pay Period", re.IGNORECASE)
TABLE_ROW_RE = re.compile(
    r"^\|\s*([0-9]+(?:-[0-9]+)?)\s*\|\s*([0-9.]+)\s*\(([^)]+)\).*?\|\s*([0-9]+)\s*\|\s*([0-9.]+)\s*\(([^)]+)\)")

CLL_TOKEN_RE = re.compile(r"\b([A-Z]{1,3}\d)\b")  # Accept e.g. TP7, OR9, M1, A6

class AccrualResult(Dict[str, Any]):
    pass

class ParsedAccrualData(Dict[str, Any]):
    """Container for cached parsing output."""
    pass

_CACHE: ParsedAccrualData | None = None


def load_markdown(path: str) -> str:
    return pathlib.Path(path).read_text(encoding="utf-8", errors="ignore")


def parse_table(md: str) -> List[Dict[str, Any]]:
    lines = md.splitlines()
    collecting = False
    rows: List[Dict[str, Any]] = []
    for line in lines:
        if not collecting and TABLE_HEADER_RE.search(line):
            collecting = True
            continue
        if collecting:
            m = TABLE_ROW_RE.search(line)
            if m:
                span1, hpp1, annual1, span2, hpp2, annual2 = m.groups()
                rows.append(_row_dict(span1, hpp1, annual1))
                rows.append(_row_dict(span2, hpp2, annual2))
            # Heuristic: stop once we have typical number of rows (<= 14)
            if len(rows) >= 14:
                break
    return rows


def _row_dict(span: str, hpp: str, annual: str) -> Dict[str, Any]:
    start, end = _parse_span(span)
    return {
        "years_range": (start, end),
        "hours_per_pay_period": float(hpp),
        "annual_hours": float(annual),
    }


def _parse_span(span: str) -> Tuple[int, int]:
    if "-" in span:
        a, b = span.split("-", 1)
        return int(a), int(b)
    return int(span), int(span)


def build_year_index(rows: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    idx: Dict[int, Dict[str, Any]] = {}
    for r in rows:
        a, b = r["years_range"]
        for year in range(a, b + 1):
            if year not in idx:
                idx[year] = r
    return idx


def parse_cll_groups(md: str) -> Dict[str, str]:
    """Return mapping of CLL token -> group type (fixed_200, accelerated_164).

    We scan bullet paragraphs. For each group bullet:
      * Extract tokens with CLL_TOKEN_RE.
      * Look for keywords in the bullet + its immediate indented lines.
    """
    groups: Dict[str, str] = {}
    lines = md.splitlines()
    n = len(lines)
    for i, line in enumerate(lines):
        if line.lstrip().startswith("- Career Ladder Levels"):
            block_text = [line]
            # include up to next 4 indented lines (bullets or tabs) as context
            for j in range(i + 1, min(i + 6, n)):
                nxt = lines[j]
                if nxt.startswith("-") and not nxt.lstrip().startswith("- o "):
                    # New top-level bullet encountered
                    break
                block_text.append(nxt)
            block_join = "\n".join(block_text)
            tokens = set(CLL_TOKEN_RE.findall(block_join))
            if not tokens:
                continue
            lowered = block_join.lower()
            group_type = None
            if "200 hours" in lowered:
                group_type = "fixed_200"
            elif "164.45" in lowered or ("eight" in lowered and "incremental" in lowered):
                group_type = "accelerated_164"
            if group_type:
                for t in tokens:
                    groups[t.upper()] = group_type
    return groups


def parse_handbook(path: str) -> ParsedAccrualData:
    md = load_markdown(path)
    rows = parse_table(md)
    idx = build_year_index(rows)
    cll_groups = parse_cll_groups(md)
    return ParsedAccrualData(
        rows=rows,
        year_index=idx,
        cll_groups=cll_groups,
    )


def get_parsed(path: str) -> ParsedAccrualData:
    global _CACHE
    p = pathlib.Path(path)
    if not p.exists():
        raise FileNotFoundError(path)
    if _CACHE is None:
        _CACHE = parse_handbook(str(p))
    return _CACHE


def classify_cll(cll: Optional[str], data: ParsedAccrualData) -> str:
    if not cll:
        return "table"
    cll_up = cll.upper()
    return data.get("cll_groups", {}).get(cll_up, "table")


def compute_accrual(years: int, cll: Optional[str], data: ParsedAccrualData) -> AccrualResult:
    years = max(0, int(years))
    group = classify_cll(cll, data)
    idx: Dict[int, Dict[str, Any]] = data["year_index"]

    def nearest_entry(y: int):
        if y in idx:
            return idx[y]
        prior = [k for k in idx.keys() if k <= y]
        if not prior:
            return None
        return idx[max(prior)]

    if group == "fixed_200":
        annual = 200.0
        return AccrualResult(
            annual_hours=annual,
            hours_per_pay_period=round(annual / 24, 2),
            basis=group,
        )
    if group == "accelerated_164":
        base = 164.45
        entry = nearest_entry(years)
        table_val = entry["annual_hours"] if entry else base
        annual = min(200.0, max(base, table_val))
        return AccrualResult(
            annual_hours=annual,
            hours_per_pay_period=round(annual / 24, 2),
            basis=group,
        )
    # table
    entry = nearest_entry(years)
    if not entry:
        return AccrualResult(annual_hours=None, hours_per_pay_period=None, basis="unknown")
    return AccrualResult(
        annual_hours=entry["annual_hours"],
        hours_per_pay_period=entry["hours_per_pay_period"],
        basis="table",
    )


def get_accrual(path: str, years: int, cll: Optional[str]) -> Dict[str, Any]:
    data = get_parsed(path)
    result = compute_accrual(years, cll, data)
    return {
        "input_years": years,
        "input_cll": cll,
        "parsed_group": classify_cll(cll, data),
        "result": result,
        "table_rows": data["rows"],
        "cll_groups": data["cll_groups"],
    }


if __name__ == "__main__":
    # Quick manual test (adjust path if needed)
    hb = pathlib.Path(__file__).parent.parent / ".source" / "marker" / "employee-handbook-markdown" / "employee-handbook.md"
    if hb.exists():
        print(get_accrual(str(hb), 5, "P5"))
    else:
        print("Handbook markdown not found:", hb)
