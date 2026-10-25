#!/usr/bin/env python3
"""보고서(PDF·텍스트·Markdown)에서 특허 공개번호와 Google Patents 링크를 뽑아 목록을 만든다.

사용법:
  python3 -I extract_patent_refs.py report.pdf --out refs.json [--text-out source.txt]
  python3 -I extract_patent_refs.py report.md --out refs.json

- PDF는 링크 주석(URI)과 본문 텍스트를 함께 읽는다. 링크 주석이 번호 오인식보다 정확하다.
- 결과: [{"number", "sources": ["link"|"text"], "pages": [..], "contexts": ["앞뒤 문장"...]}]
- 번호 형식만 보고 뽑으므로, 보고서가 번호를 잘못 적었으면 잘못된 번호가 그대로 나온다. 원문 존재 여부는 gpatents_fetch.py로 확인한다.
"""
import argparse
import json
import re
import sys

# 국가코드 + (일본 연호 S/H) + 숫자 + 종류코드
NUM_RE = re.compile(
    r"\b(?:(?P<cc>KR|JP|US|CN|EP|WO|DE|FR|GB|CA|TW|AU)\s?(?P<era>[SH])?(?P<num>\d[\d/,]{4,14}\d)\s?(?P<kind>[A-Z]\d?))\b")


def norm(cc, era, num, kind):
    return f"{cc}{era or ''}{num.replace(',', '').replace('/', '')}{kind}"


def read_pdf(path):
    pages, links = [], []
    try:
        import pypdf
    except ImportError:
        sys.exit("pypdf가 필요하다: pip install pypdf")
    r = pypdf.PdfReader(path)
    for i, p in enumerate(r.pages, 1):
        pages.append((i, p.extract_text() or ""))
        for a in p.get("/Annots") or []:
            o = a.get_object()
            act = o.get("/A")
            if act and act.get("/URI"):
                links.append((i, str(act["/URI"])))
    return pages, links


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--out")
    ap.add_argument("--text-out", help="추출한 본문 텍스트를 저장할 경로")
    a = ap.parse_args()

    if a.path.lower().endswith(".pdf"):
        pages, links = read_pdf(a.path)
    else:
        with open(a.path, encoding="utf-8") as f:
            pages, links = [(1, f.read())], []

    refs = {}

    def add(number, source, page, ctx=None):
        r = refs.setdefault(number, {"number": number, "sources": [], "pages": [], "contexts": [], "urls": []})
        if source not in r["sources"]:
            r["sources"].append(source)
        if page not in r["pages"]:
            r["pages"].append(page)
        if ctx and ctx not in r["contexts"] and len(r["contexts"]) < 4:
            r["contexts"].append(ctx)

    for page, url in links:
        m = re.search(r"patents\.google\.com/patent/([A-Z]{2}[A-Z]?\d+[A-Z]\d?)", url)
        if m:
            add(m.group(1), "link", page)
            refs[m.group(1)]["urls"].append(url) if url not in refs[m.group(1)]["urls"] else None
    for page, txt in pages:
        flat = re.sub(r"\s+", " ", txt)
        for m in NUM_RE.finditer(flat):
            n = norm(m.group("cc"), m.group("era"), m.group("num"), m.group("kind"))
            s, e = max(0, m.start() - 80), min(len(flat), m.end() + 120)
            add(n, "text", page, flat[s:e].strip())

    if a.text_out:
        with open(a.text_out, "w", encoding="utf-8") as f:
            for page, txt in pages:
                f.write(f"\n\n===== page {page} =====\n{txt}")
    out = sorted(refs.values(), key=lambda r: (min(r["pages"]), r["number"]))
    data = json.dumps(out, ensure_ascii=False, indent=2)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(data)
        print(f"{len(out)} refs ({sum('link' in r['sources'] for r in out)} with links) -> {a.out}")
    else:
        print(data)


if __name__ == "__main__":
    main()
