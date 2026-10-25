# 워크플로 스크립트

Workflow 도구의 `script`에 그대로 넣는다. 사건마다 바뀌는 값은 모두 `args`로 넘긴다. 스크립트를 고쳐 다시 실행할 때는 보존된 스크립트 파일을 Edit한 뒤 `scriptPath`와 `resumeFromRunId`로 재개한다.

## 목차

1. A. patent-verify — 보고서 인용 문헌 대조(R 유형 2단계)
2. B. patent-search — 다기준 선행기술 검색(D 유형 2단계)
3. args 예시
4. 점검 목록

## A. patent-verify

에이전트 수: 묶음 수(기본 5) + 재확인 1 + 보충 과제 수 + 시장 1. 기본 10명 미만으로 맞춘다.

```javascript
export const meta = {
  name: 'patent-verify',
  description: '보고서 인용 문헌을 묶음별로 원문과 대조하고 미열람 문헌·보충 검색·시장 주장을 확인한다',
  phases: [
    { title: '대조', detail: '문헌 묶음별 서지·법적 상태·내용 대조' },
    { title: '재확인', detail: '불일치·확인 불가 판정을 다른 검증가가 반박 입장에서 다시 확인' },
    { title: '보충', detail: '미열람 문헌 확인, 보충 검색, 시장 주장 확인' },
  ],
}

const V = ['일치', '불일치', '불일치(범위 과장)', '확인 불가', '해당 없음']
const FIELD = { type: 'object', required: ['report', 'source', 'verdict'], properties: {
  report: { type: 'string' }, source: { type: 'string' }, verdict: { type: 'string', enum: V } } }
const VERIFY = { type: 'object', required: ['items'], properties: { items: { type: 'array', items: {
  type: 'object', required: ['number', 'overall', 'fields'], properties: {
    number: { type: 'string' }, url: { type: 'string' },
    overall: { type: 'string', enum: ['일치', '부분 불일치', '불일치', '확인 불가'] },
    fields: { type: 'object', properties: { country: FIELD, applicant: FIELD, year: FIELD, status: FIELD, content: FIELD } },
    status_raw: { type: 'string' }, expiration: { type: 'string' }, alive: { type: 'string', enum: ['존속', '소멸', '심사 중', '불명'] },
    correction: { type: 'string' }, note: { type: 'string' } } } } } }
const RECHECK = { type: 'object', required: ['items'], properties: { items: { type: 'array', items: {
  type: 'object', required: ['number', 'agree', 'recheck_overall', 'reason'], properties: {
    number: { type: 'string' }, agree: { type: 'boolean' },
    recheck_overall: { type: 'string', enum: ['일치', '부분 불일치', '불일치', '확인 불가'] },
    reason: { type: 'string' }, correction: { type: 'string' } } } } } }
const SEARCH = { type: 'object', required: ['axis', 'documents'], properties: {
  axis: { type: 'string' },
  queries: { type: 'array', items: { type: 'object', properties: {
    db: { type: 'string' }, query: { type: 'string' }, hits: { type: 'integer' }, reviewed: { type: 'integer' } } } },
  documents: { type: 'array', items: { type: 'object', required: ['number', 'relevance', 'summary'], properties: {
    number: { type: 'string' }, title: { type: 'string' }, applicant: { type: 'string' },
    priority_date: { type: 'string' }, status: { type: 'string' },
    relevance: { type: 'string', enum: ['X', 'Y', 'A', '해당 없음'] },
    matched_elements: { type: 'array', items: { type: 'string' } },
    location: { type: 'string' }, summary: { type: 'string' }, opened_fulltext: { type: 'boolean' } } } },
  task_results: { type: 'array', items: { type: 'object', properties: {
    task: { type: 'string' }, result: { type: 'string' }, impact: { type: 'string' } } } },
  not_accessible: { type: 'array', items: { type: 'object', properties: {
    number: { type: 'string' }, reason: { type: 'string' } } } } } }
const MARKET = { type: 'object', required: ['claims'], properties: { claims: { type: 'array', items: {
  type: 'object', required: ['id', 'statement', 'verdict'], properties: {
    id: { type: 'string' }, statement: { type: 'string' },
    verdict: { type: 'string', enum: ['확인', '불일치', '확인 불가'] },
    evidence: { type: 'string' }, source_url: { type: 'string' },
    source_type: { type: 'string' }, note: { type: 'string' } } } } } }

// 세션 시작 뒤 만든 사용자 정의 유형은 그 세션의 에이전트 목록에 없다. args.fallback이 true이면
// general-purpose로 띄우고 정의 파일을 먼저 읽게 한다. 모델은 정의 파일의 model 값과 같게 맞춘다.
const MODEL = { 'citation-verifier': 'sonnet', 'prior-art-searcher': 'sonnet', 'market-analyst': 'sonnet' }
const run = (type, prompt, opts) => args.fallback
  ? agent(`먼저 .claude/agents/${type}.md를 Read로 읽고 그 역할, 작업 원칙, 구조화 출력 규칙을 따른다.\n\n${prompt}`,
      { ...opts, agentType: 'general-purpose', model: MODEL[type] })
  : agent(prompt, { ...opts, agentType: type })

const ws = args.ws
const common = `원 보고서 본문: ${args.source}\n공개번호-등록번호 대응: ${args.linkMap}\n원문 JSON 저장 폴더: ${ws}/01_raw/ (다른 곳에 파일을 만들지 않는다)`

phase('대조')
// 대조와 보충은 서로 결과를 기다리지 않으므로 함께 시작한다.
const verifyBranch = () => pipeline(args.batches,
  b => run('citation-verifier', 
    `[서지 대조 묶음 ${b.id}] 보고서 절: ${b.section}\n${common}\n대상 번호 ${b.numbers.length}건: ${b.numbers.join(', ')}\n` +
    `절차: .claude/skills/prior-art-search/SKILL.md의 B절. 원문은 한 번에 가져온다:\n` +
    `python3 -I .claude/skills/prior-art-search/scripts/gpatents_fetch.py ${b.numbers.join(' ')} --out ${ws}/01_raw/batch_${b.id}.json --sleep 4\n` +
    `번호마다 원 보고서가 적은 국가·출원인·연도·핵심 내용·상태를 source에서 찾아 원문과 대조하라. ` +
    `보고서가 적지 않은 항목은 report='(기재 없음)', verdict='해당 없음'. 공개번호와 등록번호 쌍은 같은 출원인지 확인하라.`,
    { label: `대조:${b.id}`, phase: '대조', schema: VERIFY }),
  (r, b) => (r ? { batch: b.id, items: r.items } : null))

const supplementThunks = (args.searchTasks || []).map(t => () =>
  run('prior-art-searcher', `[보충 과제 ${t.key}]\n${common}\n${t.prompt}\n절차: .claude/skills/prior-art-search/SKILL.md의 A절.`,
    { label: `보충:${t.key}`, phase: '보충', schema: SEARCH }))
if ((args.marketClaims || []).length) {
  supplementThunks.push(() => run('market-analyst', 
    `[시장·상용화 주장 확인]\n원 보고서 본문: ${args.source}\n아래 주장마다 원 출처를 열어 확인하라.\n` +
    args.marketClaims.map(c => `${c.id}. ${c.statement}${c.url ? ' (보고서 출처: ' + c.url + ')' : ''}`).join('\n'),
    { label: '보충:시장', phase: '보충', schema: MARKET }))
}

const [verified, supplements] = await parallel([verifyBranch, () => parallel(supplementThunks)])

const ok = (verified || []).filter(Boolean)
const missingBatches = args.batches.filter(b => !ok.some(r => r.batch === b.id)).map(b => b.id)
if (missingBatches.length) log(`대조 실패 묶음 ${missingBatches.length}개: ${missingBatches.join(', ')}`)
const items = ok.flatMap(r => r.items.map(it => ({ ...it, batch: r.batch })))
const flagged = items.filter(it => it.overall !== '일치')
log(`대조 ${items.length}건 중 ${flagged.length}건이 불일치·부분 불일치·확인 불가`)

phase('재확인')
// 재확인은 불일치 항목 전체를 한 검증가가 본다. 1차 판정을 반박하는 입장에서 확인해 오판을 걸러 낸다.
let recheck = null
if (flagged.length) {
  recheck = await run('citation-verifier', 
    `[재확인] 아래 항목은 1차 대조에서 일치가 아니라고 판정됐다. 1차 판정이 틀렸을 가능성을 먼저 의심하고 원문을 다시 확인하라.\n` +
    `${common}\n1차 원문 JSON은 ${ws}/01_raw/batch_*.json에 있다. 번호 형식 문제로 확인 불가였다면 형식을 바꿔 스크립트를 다시 실행하라.\n` +
    `1차 판정에 동의하면 agree=true. 근거를 reason에 적어라.\n${JSON.stringify(flagged.map(f => ({ number: f.number, overall: f.overall, fields: f.fields, correction: f.correction })))}`,
    { label: '재확인', phase: '재확인', schema: RECHECK })
  if (!recheck) log('재확인 결과가 없다. 1차 판정만 남긴다.')
}

const sup = (supplements || []).filter(Boolean)
const searches = sup.filter(s => s.documents)
const market = sup.find(s => s.claims) || null
const supTotal = (args.searchTasks || []).length + ((args.marketClaims || []).length ? 1 : 0)
log(`보충 ${sup.length}/${supTotal}건 완료`)
return { items, flaggedCount: flagged.length, recheck, searches, market, missingBatches }
```

## B. patent-search

에이전트 수: 검색 기준 수(기본 4) + 누락 점검 1 + 추가 검색(최대 2). 기본 7명.

```javascript
export const meta = {
  name: 'patent-search',
  description: '발명 구성 요소를 여러 검색 기준으로 나눠 선행기술을 찾고 누락 점검 뒤 추가 검색한다',
  phases: [
    { title: '검색', detail: '키워드·분류·출원인·인용 추적 기준별 검색' },
    { title: '누락 점검', detail: '쓰지 않은 기준과 빠진 구성을 찾는다' },
    { title: '추가 검색', detail: '누락 점검이 제안한 기준으로 한 번 더 검색' },
  ],
}

const SEARCH = { type: 'object', required: ['axis', 'documents'], properties: {
  axis: { type: 'string' },
  queries: { type: 'array', items: { type: 'object', properties: {
    db: { type: 'string' }, query: { type: 'string' }, hits: { type: 'integer' }, reviewed: { type: 'integer' } } } },
  documents: { type: 'array', items: { type: 'object', required: ['number', 'relevance', 'summary'], properties: {
    number: { type: 'string' }, title: { type: 'string' }, applicant: { type: 'string' },
    priority_date: { type: 'string' }, status: { type: 'string' },
    relevance: { type: 'string', enum: ['X', 'Y', 'A', '해당 없음'] },
    matched_elements: { type: 'array', items: { type: 'string' } },
    location: { type: 'string' }, summary: { type: 'string' }, opened_fulltext: { type: 'boolean' } } } } } }
const GAPS = { type: 'object', required: ['axes'], properties: { axes: { type: 'array', items: {
  type: 'object', required: ['key', 'prompt', 'reason'], properties: {
    key: { type: 'string' }, prompt: { type: 'string' }, reason: { type: 'string' } } } } } }

// 세션 시작 뒤 만든 사용자 정의 유형은 그 세션의 에이전트 목록에 없다. args.fallback이 true이면
// general-purpose로 띄우고 정의 파일을 먼저 읽게 한다. 모델은 정의 파일의 model 값과 같게 맞춘다.
const MODEL = { 'citation-verifier': 'sonnet', 'prior-art-searcher': 'sonnet', 'market-analyst': 'sonnet' }
const run = (type, prompt, opts) => args.fallback
  ? agent(`먼저 .claude/agents/${type}.md를 Read로 읽고 그 역할, 작업 원칙, 구조화 출력 규칙을 따른다.\n\n${prompt}`,
      { ...opts, agentType: 'general-purpose', model: MODEL[type] })
  : agent(prompt, { ...opts, agentType: type })

const base = `발명 요약: ${args.invention}\n구성 요소: ${args.elements.join(' / ')}\n기준일: ${args.cutoff}\n` +
  `원문 JSON 저장 폴더: ${args.ws}/01_raw/\n절차: .claude/skills/prior-art-search/SKILL.md의 A절.`
const runAxis = (ax, ph) => run('prior-art-searcher', `[검색 기준 ${ax.key}]\n${base}\n${ax.prompt}`,
  { label: `${ph}:${ax.key}`, phase: ph, schema: SEARCH })

phase('검색')
// 중복 제거와 누락 점검은 모든 기준의 결과가 있어야 하므로 여기서는 동기화한다.
const first = (await parallel(args.axes.map(ax => () => runAxis(ax, '검색')))).filter(Boolean)
log(`검색 기준 ${args.axes.length}개 중 ${first.length}개 완료`)

const seen = new Map()
const merge = rs => rs.flatMap(r => r.documents.map(d => ({ ...d, axis: r.axis }))).forEach(d => {
  const prev = seen.get(d.number)
  if (!prev) seen.set(d.number, { ...d, axes: [d.axis] })
  else if (!prev.axes.includes(d.axis)) prev.axes.push(d.axis)
})
merge(first)

phase('누락 점검')
const gaps = await run('prior-art-searcher', 
  `[누락 점검] 아래 검색 결과를 보고, 쓰지 않은 검색 기준, 어떤 문헌에도 대응되지 않은 구성 요소, 열지 않은 핵심 문헌을 찾아 ` +
  `추가 검색 기준을 최대 ${args.maxExtra ?? 2}개 제안하라. 더 할 것이 없으면 빈 배열.\n${base}\n` +
  `수행한 기준: ${first.map(r => r.axis).join(', ')}\n찾은 문헌: ${JSON.stringify([...seen.values()].map(d => ({ n: d.number, r: d.relevance, e: d.matched_elements })))}`,
  { label: '누락 점검', phase: '누락 점검', schema: GAPS })

phase('추가 검색')
const extraAxes = (gaps?.axes || []).slice(0, args.maxExtra ?? 2)
if (gaps && gaps.axes.length > extraAxes.length) log(`제안된 추가 기준 ${gaps.axes.length - extraAxes.length}개는 상한 때문에 실행하지 않았다`)
const extra = extraAxes.length
  ? (await parallel(extraAxes.map(ax => () => runAxis(ax, '추가 검색')))).filter(Boolean) : []
const before = seen.size
merge(extra)
log(`추가 검색으로 새 문헌 ${seen.size - before}건`)
return { documents: [...seen.values()], axesRun: [...first, ...extra].map(r => r.axis),
  queries: [...first, ...extra].flatMap(r => (r.queries || []).map(q => ({ ...q, axis: r.axis }))), gaps: gaps?.axes || [] }
```

## args 예시

A. patent-verify

```json
{
  "ws": "_workspace/shoe-sole",
  "source": "_workspace/shoe-sole/00_input/source.txt",
  "linkMap": "_workspace/shoe-sole/00_input/link_map.md",
  "batches": [
    { "id": "B1", "section": "밑창 돌기 패턴", "numbers": ["KR101234567B1", "JPH11123456A"] }
  ],
  "searchTasks": [
    { "key": "미열람", "prompt": "원 보고서 '미열람 문헌 확인' 절의 항목을 하나씩 확인하라 …" }
  ],
  "marketClaims": [
    { "id": "M1", "statement": "A사는 2021년 6월 이중 경도 밑창 채택을 발표했다", "url": "…" }
  ]
}
```

B. patent-search

```json
{
  "ws": "_workspace/{case}",
  "invention": "발명 한 줄 요약",
  "elements": ["C1 …", "C2 …"],
  "cutoff": "YYYY-MM-DD",
  "axes": [
    { "key": "키워드", "prompt": "국문·영문·일문·중문 동의어로 …" },
    { "key": "분류", "prompt": "IPC/CPC … F-term …" },
    { "key": "출원인", "prompt": "주요 기업 …" },
    { "key": "인용", "prompt": "핵심 문헌의 인용·피인용 …" }
  ],
  "maxExtra": 2
}
```

## 점검 목록

- `meta`는 리터럴만 쓴다.
- `Date.now()`, `Math.random()`, 인자 없는 `new Date()`를 쓰지 않는다. 기준일은 `args.cutoff`로 넘긴다.
- `parallel()`·`pipeline()` 결과에는 `.filter(Boolean)`을 적용하고, 빠진 수를 `log()`로 알린다.
- `phase()` 제목과 `meta.phases`의 `title`이 같다. 병렬 단계 안에서는 `opts.phase`를 쓴다.
- 검증가·검색가의 출력 파일 경로는 `_workspace/{case}/01_raw/` 아래다.
- Google Patents를 읽는 에이전트가 동시에 3명 이상이면 스크립트 호출에 `--sleep 4` 이상을 넣는다. 묶음 4개와 보충 3개를 함께 돌린 첫 실행(2026-10-25)에서 503 차단이 세 번 났다.
- 반환값이 크므로 메인은 알림의 출력 파일을 `01_raw/workflow_result.json`으로 복사해 쓴다.
