#!/usr/bin/env python3
"""한국식 청구범위의 형식 오류를 찾는다.

사용법:
  python3 -I check_claims.py claims.md [--json]

입력 파일 안의 【청구항 N】 블록을 청구항으로 읽는다. 검사 항목:
  numbering      청구항 번호 누락·중복
  dependency     존재하지 않거나 뒤 번호를 인용, 다중 종속항이 다중 종속항을 인용
  antecedent     '상기 X'의 X가 같은 항 앞부분이나 인용 항에 없음(휴리스틱, 오탐 가능)
  unclear        불명확 표현(약, 대략, 바람직하게, 주로, 등, 필요에 따라 …)
  sentence       한 청구항에 문장이 둘 이상이거나 마침표로 끝나지 않음
  refnum         청구항 안의 도면 부호 괄호(권고)
  numeric        수치·단위 목록(측정 방법이 명세서에 정의됐는지 사람이 확인)
결과는 의심 목록이다. 오탐을 걸러 내는 일은 검사관이 정독으로 한다.
"""
import argparse
import json
import re
import sys

CLAIM_RE = re.compile(r"【청구항\s*(\d+)】(.*?)(?=【청구항\s*\d+】|【요약서】|^#{1,6}\s|\Z)", re.S | re.M)
PARTICLES = sorted(["으로부터", "로부터", "에서의", "에서는", "으로서", "로서", "으로써", "로써", "에서", "에는", "에도", "으로",
                    "에게", "까지", "부터", "보다", "이며", "이고", "이나", "와의", "과의", "은", "는", "이", "가", "을", "를",
                    "의", "에", "로", "와", "과", "도", "만", "인", "및"], key=len, reverse=True)
UNCLEAR = [
    (r"(?<![가-힣])약\s?\d", "약(수치 앞)"), (r"대략", "대략"), (r"바람직하", "바람직하게/바람직한"),
    (r"(?<![가-힣])주로(?![가-힣])", "주로"), (r"필요에\s?따라", "필요에 따라"), (r"적당한|적절한", "적당한/적절한"),
    (r"(?<![가-힣])특히(?![가-힣])", "특히"), (r"예를\s?들어|예컨대", "예시 표현"), (r"\s등(?=[\s,.;의을를이가과와]|$)", "등"),
    (r"정도(?![가-힣])", "정도"), (r"가량", "가량"), (r"(?<![가-힣])(고온|저온|고압|저압)(?![가-힣])", "기준 없는 고온/저온"),
]
NUM_RE = re.compile(r"\d+(?:\.\d+)?\s?(?:℃|°C|°|%|g/m²|g/m2|㎛|μm|um|mm|cm|N/\d+\s?mm|N|mN|초|분|시간|RH|kPa|MPa|ml|mL)")


def strip_particle(tok):
    tok = tok.strip(",.;:()[]")
    for p in PARTICLES:
        if tok.endswith(p) and len(tok) > len(p):
            return tok[: -len(p)]
    return tok


def parse_claims(text):
    claims = {}
    order = []
    for m in CLAIM_RE.finditer(text):
        n = int(m.group(1))
        body = re.sub(r"\s+", " ", m.group(2)).strip()
        if n in claims:
            claims.setdefault("_dups", []).append(n)
        claims[n] = body
        order.append(n)
    return claims, order


def deps_of(body):
    head = body[:120]
    refs = set()
    for a, b in re.findall(r"제\s?(\d+)\s?항\s?(?:내지|~|-)\s?제?\s?(\d+)\s?항", head):
        refs.update(range(int(a), int(b) + 1))
    refs.update(int(x) for x in re.findall(r"제\s?(\d+)\s?항", head))
    refs.update(int(x) for x in re.findall(r"청구항\s?(\d+)", head))
    multi = len(refs) > 1 or bool(re.search(r"중\s?어느\s?(한|하나의)\s?항", head))
    return sorted(refs), multi


def chain_text(n, claims, deps, seen=None):
    seen = seen or set()
    if n in seen or n not in claims:
        return ""
    seen.add(n)
    return " ".join(chain_text(p, claims, deps, seen) for p in deps.get(n, ([], False))[0]) + " " + claims[n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    text = open(a.path, encoding="utf-8").read()
    claims, order = parse_claims(text)
    dups = claims.pop("_dups", [])
    issues = []

    def add(kind, claim, msg, severity="보정 사유"):
        issues.append({"kind": kind, "claim": claim, "severity": severity, "message": msg})

    if not claims:
        print("청구항(【청구항 N】)을 찾지 못했다.", file=sys.stderr)
        return 2
    nums = sorted(claims)
    for d in dups:
        add("numbering", d, "청구항 번호 중복", "출원 불가")
    for i in range(1, max(nums) + 1):
        if i not in claims:
            add("numbering", i, "청구항 번호 누락", "출원 불가")

    deps = {n: deps_of(claims[n]) for n in nums}
    for n in nums:
        refs, multi = deps[n]
        for r in refs:
            if r not in claims:
                add("dependency", n, f"존재하지 않는 제{r}항 인용", "출원 불가")
            elif r >= n:
                add("dependency", n, f"자기 이후 번호 제{r}항 인용")
        if multi:
            for r in refs:
                if r in deps and deps[r][1]:
                    add("dependency", n, f"다중 종속항이 다중 종속항(제{r}항)을 인용(시행령 제5조)")
            if re.search(r"제\s?\d+\s?항\s?및\s?제", claims[n][:120]):
                add("dependency", n, "두 항 이상 인용을 '및'으로 씀. 택일('또는', '중 어느 한 항')로 써야 함")

    for n in nums:
        body = claims[n]
        parents = " ".join(chain_text(p, claims, deps) for p in deps[n][0])
        for m in re.finditer(r"상기\s+", body):
            toks = body[m.end():].split()[:3]
            prior = parents + " " + body[: m.start()]
            prior_plain = re.sub(r"상기\s+", " ", prior)
            matched = None
            for k in (3, 2, 1):
                if len(toks) < k:
                    continue
                cand = " ".join(toks[: k - 1] + [strip_particle(toks[k - 1])]).strip()
                if len(cand) >= 1 and cand in prior_plain:
                    matched = cand
                    break
            if not matched:
                add("antecedent", n, f"'상기 {' '.join(toks)}'의 선행 근거를 찾지 못함(오탐 가능)")
        for pat, label in UNCLEAR:
            for m in re.finditer(pat, body):
                s = max(0, m.start() - 15)
                add("unclear", n, f"불명확 표현 '{label}': …{body[s:m.end() + 15]}…")
        stripped = body.rstrip()
        if not stripped.endswith("."):
            add("sentence", n, "마침표로 끝나지 않음")
        inner = re.sub(r"\d\.\d", "", stripped[:-1])
        if re.search(r"[가-힣)]\.\s+\S", inner):
            add("sentence", n, "한 청구항 안에 문장이 둘 이상으로 보임")
        for m in re.finditer(r"[가-힣]\s?\((\d{2,4}[a-z']?)\)", body):
            add("refnum", n, f"도면 부호 괄호 ({m.group(1)}) 사용", "권고")
        nums_found = sorted(set(x.strip() for x in NUM_RE.findall(body)))
        if nums_found:
            add("numeric", n, "수치 한정: " + ", ".join(nums_found) + " → 측정 방법 정의 확인", "확인")

    summary = {}
    for i in issues:
        summary[i["severity"]] = summary.get(i["severity"], 0) + 1
    tree = {n: deps[n][0] for n in nums}
    if a.json:
        print(json.dumps({"claims": len(nums), "tree": tree, "summary": summary, "issues": issues},
                         ensure_ascii=False, indent=2))
    else:
        print(f"청구항 {len(nums)}개, 독립항: {[n for n in nums if not deps[n][0]]}")
        print("종속 관계:", ", ".join(f"{n}←{deps[n][0]}" for n in nums if deps[n][0]))
        print("요약:", summary)
        for i in issues:
            print(f"- [{i['severity']}] 청구항 {i['claim']} {i['kind']}: {i['message']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
