import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

PAGE_ID_RE = re.compile(r'<span id="page-(\d+)-0"></span>')
SECTION_HDR_RE = re.compile(r'^##\s+<span id="page-(\d+)-0"></span>(.+)$')

@lru_cache(maxsize=1)
def build_page_map(markdown_path: str) -> Dict[str, int]:
    """Parse the markdown file and map normalized section title -> page number.
    Normalization: lowercase, strip punctuation & extra spaces.
    """
    path = Path(markdown_path)
    if not path.exists():
        return {}
    text = path.read_text(encoding='utf-8', errors='ignore')
    lines = text.splitlines()
    mapping: Dict[str, int] = {}
    for line in lines:
        m = SECTION_HDR_RE.match(line.strip())
        if m:
            page = int(m.group(1))
            title = m.group(2)
            norm = normalize_title(title)
            if norm and norm not in mapping:
                mapping[norm] = page
    return mapping

def normalize_title(t: str) -> str:
    t = re.sub(r'<.*?>', '', t)  # remove any residual html
    t = re.sub(r'[^A-Za-z0-9 ]+', ' ', t)
    return re.sub(r'\s+', ' ', t).strip().lower()

PTO_KEY_TERMS = [
    'paid time off (pto)',
    'attendance and time off: paid time off (pto)',
    'pto benefit accrual',
    'pto accrual'
]


def find_pto_pages(markdown_path: str) -> List[int]:
    mapping = build_page_map(markdown_path)
    pages = []
    for term in PTO_KEY_TERMS:
        p = mapping.get(term)
        if p is not None:
            pages.append(p)
    return sorted(set(pages))

def find_section_pages(markdown_path: str, keywords: List[str]) -> List[int]:
    mapping = build_page_map(markdown_path)
    out = []
    for k in keywords:
        p = mapping.get(k.lower())
        if p is not None:
            out.append(p)
    return sorted(set(out))
