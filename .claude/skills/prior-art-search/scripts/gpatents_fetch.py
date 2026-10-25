#!/usr/bin/env python3
"""Google Patents 원문 페이지에서 서지·법적 상태·청구항 요약을 추출한다.

사용법:
  python3 -I gpatents_fetch.py US5960411A US6285999B1 ... [--out result.json] [--lang en|ko|ja]
  python3 -I gpatents_fetch.py --file numbers.txt --out result.json

- 번호는 Google Patents 공개번호 형식(국가코드+번호+종류코드)으로 넣는다. 예: KR101234567B1, JPH11123456A
- 결과는 JSON 배열. 각 항목의 fetch_status가 ok가 아니면 페이지를 찾지 못한 것이다.
- 법적 상태(status)와 예상 만료일은 Google이 추정한 값이다. 최종 판단은 각국 특허청 원부로 확인한다.
"""
import argparse
import html
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


def fetch(number, lang):
    url = f"https://patents.google.com/patent/{number}/{lang}"
    # 일부 macOS Python은 인증서 묶음이 없어 urllib가 SSL 검증에 실패한다. 시스템 curl을 먼저 쓴다.
    try:
        p = subprocess.run(["curl", "-sS", "-L", "-m", "40", "-A", UA, "-w", "\n%{http_code}", url],
                           capture_output=True, timeout=60)
        body, _, code = p.stdout.decode("utf-8", errors="replace").rpartition("\n")
        if p.returncode == 0:
            if code.strip() != "200":
                raise urllib.error.HTTPError(url, int(code.strip() or 0), "http", None, None)
            return url, body
    except FileNotFoundError:
        pass
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return url, r.read().decode("utf-8", errors="replace")


def text(s):
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def first(pattern, h, flags=re.S):
    m = re.search(pattern, h, flags)
    return text(m.group(1)) if m else None


def all_of(pattern, h, flags=re.S):
    seen, out = set(), []
    for m in re.finditer(pattern, h, flags):
        v = text(m.group(1))
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def parse(number, url, h, claim_chars):
    info = {"number": number, "url": url, "fetch_status": "ok"}
    info["title"] = first(r'<span itemprop="title">(.*?)</span>', h) or first(r"<title>(.*?)</title>", h)
    info["assignee_original"] = all_of(r'itemprop="assigneeOriginal"[^>]*>(.*?)</dd>', h)
    info["assignee_current"] = all_of(r'itemprop="assigneeCurrent"[^>]*>(.*?)</dd>', h)
    info["inventors"] = all_of(r'itemprop="inventor"[^>]*>(.*?)</dd>', h)
    info["priority_date"] = first(r'itemprop="priorityDate" datetime="([^"]+)"', h)
    info["filing_date"] = first(r'itemprop="filingDate" datetime="([^"]+)"', h)
    info["publication_date"] = first(r'itemprop="publicationDate" datetime="([^"]+)"', h)
    info["application_number"] = first(r'itemprop="applicationNumber">(.*?)</dd>', h)
    info["status"] = first(r'itemprop="legalStatusIfi"[^>]*>\s*<span itemprop="status">(.*?)</span>', h)
    info["anticipated_expiration"] = first(
        r'<time itemprop="date" datetime="([^"]+)">[^<]*</time>\s*<span itemprop="title">Anticipated expiration', h)
    events = []
    for m in re.finditer(
            r'<dd itemprop="events"[^>]*>\s*<time itemprop="date"[^>]*>([^<]*)</time>\s*<span itemprop="title">(.*?)</span>',
            h, re.S):
        events.append(f"{m.group(1).strip()} {text(m.group(2))}")
    info["events"] = events[:15]
    # 페이지 아래 Legal Events 표. 상단 status가 갱신되지 않은 문헌(Pending 표시)도 여기에
    # 거절사정(A02), 연차료 미납 말소(LAPS, CF01) 같은 실제 경과가 남아 있다.
    legal = []
    for row in re.findall(r'<tr itemprop="legalEvents"[^>]*>(.*?)</tr>', h, re.S):
        legal.append(text(row)[:240])
    info["legal_events"] = legal[-20:]
    abs_block = first(r'<section itemprop="abstract"[^>]*>(.*?)</section>', h)
    info["abstract"] = (abs_block or "").replace("Abstract", "", 1).strip()[:1200] or None
    claims_block = re.search(r'<section itemprop="claims"[^>]*>(.*?)</section>', h, re.S)
    if claims_block:
        cb = claims_block.group(1)
        info["claim_count"] = first(r'itemprop="count">(\d+)<', cb)
        ct = re.search(r'class="claim-text">(.*?)</div>\s*</div>', cb, re.S)
        claim1 = text(ct.group(1)) if ct else text(cb)
        info["claim1"] = claim1[:claim_chars]
    else:
        info["claim_count"], info["claim1"] = None, None
    info["cpc"] = all_of(r'itemprop="Code">([A-H]\d\d[A-Z]\s?\d+/\d+)<', h)[:12]
    info["cited_by_count"] = first(r"Cited By \((\d+)\)", h)
    info["family_note"] = first(r'<h2>Applications Claiming Priority \((\d+)\)</h2>', h)
    return info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("numbers", nargs="*")
    ap.add_argument("--file")
    ap.add_argument("--out")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--claim-chars", type=int, default=1500)
    ap.add_argument("--sleep", type=float, default=2.0)
    a = ap.parse_args()
    nums = list(a.numbers)
    if a.file:
        with open(a.file, encoding="utf-8") as f:
            nums += [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
    results = []
    for i, n in enumerate(nums):
        n = n.replace(" ", "").replace("-", "")
        try:
            url, h = fetch(n, a.lang)
            results.append(parse(n, url, h, a.claim_chars))
        except urllib.error.HTTPError as e:
            results.append({"number": n, "fetch_status": f"http_{e.code}",
                            "url": f"https://patents.google.com/patent/{n}/{a.lang}"})
        except Exception as e:  # 네트워크 오류는 항목별로 기록하고 다음 번호로 넘어간다
            results.append({"number": n, "fetch_status": f"error: {e}"})
        if i < len(nums) - 1:
            time.sleep(a.sleep)
    out = json.dumps(results, ensure_ascii=False, indent=2)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(out)
        ok = sum(1 for r in results if r.get("fetch_status") == "ok")
        print(f"{ok}/{len(results)} fetched -> {a.out}")
    else:
        print(out)


if __name__ == "__main__":
    sys.exit(main())
