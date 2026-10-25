#!/usr/bin/env python3
"""한국 특허 명세서 초안의 형식·일관성을 검사한다.

사용법:
  python3 -I check_spec.py specification.md [--claims claims.md] [--figures figures.md] [--json]

검사 항목:
  sections     필수 항목(【발명의 명칭】 … 【요약서】) 누락·순서
  paragraphs   [0001] 문단 번호 누락·중복·역순
  refnums      '구성명(110)' 형식 부호의 이름 충돌, 【부호의 설명】·도면 부호표와의 불일치
  figures      본문에서 언급한 '도 N'과 【도면의 간단한 설명】의 불일치
  support      청구항에 '상기'로 다시 나오는 용어가 발명의 설명(청구범위 앞)에 없음
  placeholders [시험 데이터 삽입 …] 같은 미완성 표시 개수
--claims를 주지 않으면 명세서 안의 【청구범위】를 쓴다.
"""
import argparse
import json
import re
import sys

SECTIONS = ["【발명의 명칭】", "【기술분야】", "【발명의 배경이 되는 기술】", "【해결하고자 하는 과제】", "【과제의 해결 수단】",
            "【발명의 효과】", "【도면의 간단한 설명】", "【발명을 실시하기 위한 구체적인 내용】", "【부호의 설명】",
            "【청구범위】", "【요약서】"]
PARTICLES = sorted(["으로부터", "로부터", "에서의", "에서는", "으로서", "로서", "에서", "에는", "으로", "까지", "부터", "보다",
                    "이며", "이고", "은", "는", "이", "가", "을", "를", "의", "에", "로", "와", "과", "도", "인"],
                   key=len, reverse=True)
REF_RE = re.compile(r"([가-힣A-Za-z][가-힣A-Za-z0-9 ]{0,20}?)\s?\((\d{2,4}[a-z']?)\)")


def strip_particle(tok):
    tok = tok.strip(",.;:()[]")
    for p in PARTICLES:
        if tok.endswith(p) and len(tok) > len(p):
            return tok[: -len(p)]
    return tok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--claims")
    ap.add_argument("--figures")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    spec = open(a.path, encoding="utf-8").read()
    issues = []

    def add(kind, msg, severity="보정 사유"):
        issues.append({"kind": kind, "severity": severity, "message": msg})

    # sections
    pos = []
    for s in SECTIONS:
        i = spec.find(s)
        if i < 0:
            add("sections", f"{s} 없음", "출원 불가" if s in ("【발명의 명칭】", "【청구범위】", "【요약서】") else "보정 사유")
        else:
            pos.append((i, s))
    if [s for _, s in sorted(pos)] != [s for _, s in pos]:
        add("sections", "필수 항목 순서가 서식과 다름: " + " → ".join(s for _, s in sorted(pos)))

    claims_start = spec.find("【청구범위】")
    desc = spec[:claims_start] if claims_start > 0 else spec

    # paragraphs
    paras = [int(x) for x in re.findall(r"\[(\d{4})\]", desc)]
    seen = set()
    for i, p in enumerate(paras):
        if p in seen:
            add("paragraphs", f"[{p:04d}] 중복")
        seen.add(p)
        if i and p != paras[i - 1] + 1 and p not in paras[:i]:
            add("paragraphs", f"[{paras[i - 1]:04d}] 다음이 [{p:04d}]", "권고")
    if not paras:
        add("paragraphs", "문단 번호 [0001] 형식이 없음", "권고")

    # refnums
    body_end = spec.find("【부호의 설명】")
    body = spec[:body_end] if body_end > 0 else desc
    used = {}
    for name, num in REF_RE.findall(body):
        name = strip_particle(name.strip().split()[-1]) if name.strip() else name
        used.setdefault(num, set()).add(name)
    for num, names in sorted(used.items()):
        if len(names) > 1:
            add("refnums", f"부호 {num}에 이름이 여럿: {sorted(names)}")
    listed = {}
    if body_end > 0:
        seg = spec[body_end: claims_start if claims_start > body_end else len(spec)]
        for num, name in re.findall(r"(\d{2,4}[a-z']?)\s?[:：]\s?([^\s,，]+(?:\s[^\s\d,，:：]+)?)", seg):
            listed[num] = name.strip()
    for num in sorted(set(used) - set(listed)):
        add("refnums", f"본문 부호 {num}({sorted(used[num])[0]})이 【부호의 설명】에 없음")
    for num in sorted(set(listed) - set(used)):
        add("refnums", f"【부호의 설명】 {num}({listed[num]})이 본문에 쓰이지 않음", "권고")
    if a.figures:
        fig = open(a.figures, encoding="utf-8").read()
        fig_nums = set(re.findall(r"(?<![\d.])(\d{3}[a-z']?)(?![\d.])", fig))
        for num in sorted(set(used) - fig_nums):
            add("refnums", f"본문 부호 {num}이 도면 부호표 파일에 없음")
        # 역방향: 도면 문서의 【부호의 설명】 블록에 있는데 명세서에 없거나 이름이 다른 부호
        fb = fig.find("【부호의 설명】")
        if fb >= 0:
            fig_listed = {}
            for line in fig[fb:].splitlines()[1:]:
                m = re.match(r"\s*(\d{2,4}[a-z']?)\s*[:：]\s*(.+?)\s*$", line)
                if m:
                    fig_listed[m.group(1)] = m.group(2)
                elif fig_listed and (not line.strip() or line.strip().startswith("```")):
                    break
            for num in sorted(set(fig_listed) - set(listed)):
                add("refnums", f"도면 부호표의 {num}({fig_listed[num]})이 명세서 【부호의 설명】에 없음")
            for num in sorted(set(fig_listed) & set(listed)):
                if fig_listed[num].split()[0] != listed[num].split()[0]:
                    add("refnums", f"부호 {num} 이름 불일치: 도면 '{fig_listed[num]}' / 명세서 '{listed[num]}'")

    # figures
    brief_s = spec.find("【도면의 간단한 설명】")
    brief_e = spec.find("【발명을 실시하기 위한 구체적인 내용】")
    if brief_s >= 0:
        brief = spec[brief_s: brief_e if brief_e > brief_s else len(spec)]
        # '온도 40℃', '각도 30°'처럼 '도'로 끝나는 단어와 수치를 도면 번호로 읽지 않도록,
        # '도' 앞이 한글이 아니고 번호 뒤가 단위 기호가 아닌 경우만 도면 언급으로 센다.
        fig_re = r"(?<![가-힣])도\s?(\d+[a-z]?)(?![\d.℃°%])"
        declared = set(re.findall(fig_re + r"\s?(?:은|는)", brief))
        mentioned = set(re.findall(fig_re, spec[brief_e:] if brief_e > 0 else ""))
        for f in sorted(mentioned - declared, key=lambda x: (len(x), x)):
            add("figures", f"본문에 도 {f}가 나오나 【도면의 간단한 설명】에 없음")
        for f in sorted(declared - mentioned, key=lambda x: (len(x), x)):
            add("figures", f"도 {f}가 본문 상세 설명에서 언급되지 않음", "권고")

    # support
    ctext = open(a.claims, encoding="utf-8").read() if a.claims else (spec[claims_start:] if claims_start > 0 else "")
    # 청구항 파일에 작성 메모나 대비표가 함께 있으면 그 안의 인용문을 청구항으로 읽지 않도록
    # 【청구항 N】 블록만 남긴다. 블록은 다음 【청구항】, Markdown 제목, 구분선에서 끝난다.
    blocks = re.findall(r"【청구항\s*\d+】.*?(?=【청구항\s*\d+】|\n#{1,6}\s|\n---|\Z)", ctext, re.S)
    if blocks:
        ctext = "\n".join(blocks)
    # 첫 어절이 조사로 끝나면 한 단어 용어, 아니면 다음 어절까지 이어진 복합 명사로 본다.
    terms = {}
    for m in re.finditer(r"상기\s+(\S+)(?:\s+(\S+))?", ctext):
        r1, r2 = m.group(1).strip(",.;"), (m.group(2) or "").strip(",.;")
        s1 = strip_particle(r1)
        if s1 != r1:
            cands = [c for c in (s1, r1) if len(c) >= 2]
        else:
            s2 = strip_particle(r2) if r2 else ""
            cands = [f"{r1} {s2}", f"{r1}{s2}"] if s2 else [r1]
        if cands:
            terms.setdefault(cands[0], cands)
    desc_plain = re.sub(r"\s+", " ", desc)
    for t, cands in sorted(terms.items()):
        if not any(c in desc_plain for c in cands):
            add("support", f"청구항 용어 '{t}'가 발명의 설명에 같은 표현으로 없음(오탐 가능)")

    # placeholders
    ph = re.findall(r"\[((?:시험 데이터 삽입|확인 필요|실시 형태 보충 필요|시험 후 확정|시험 후 기재|발명자 확인|T0 후 확정)[^\]]*)\]", spec)
    if ph:
        add("placeholders", f"미완성 표시 {len(ph)}개: " + ", ".join(sorted(set(p.split(':')[0] for p in ph))), "확인")

    summary = {}
    for i in issues:
        summary[i["severity"]] = summary.get(i["severity"], 0) + 1
    if a.json:
        print(json.dumps({"summary": summary, "issues": issues, "refnums_used": {k: sorted(v) for k, v in used.items()},
                          "refnums_listed": listed}, ensure_ascii=False, indent=2))
    else:
        print("요약:", summary)
        for i in issues:
            print(f"- [{i['severity']}] {i['kind']}: {i['message']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
