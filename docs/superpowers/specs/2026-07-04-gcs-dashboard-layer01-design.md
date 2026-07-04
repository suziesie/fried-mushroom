# GCS 대시보드 탭 ↔ 실 layer 01 배선 (#111 설계)

날짜: 2026-07-04 · 범위: `infra/log/log_server.py` + `infra/dashboard/static/gcs.js`

## 목적

대시보드 GCS 탭은 layer 01 미구현 시점 설계라 운용자가 mission_brief 를 수동
조립하는 mock 이다(`gcs.js`: "layer 01 미구현 대체 UI"). layer 01(`src/gcs`) +
`mission_pipeline` 이 머지됐으므로, 실 layer 01(`assemble_draft`)을 `/gcs/*` 에 배선한다.
#102-107(온보드 02-07 패널 실데이터화)의 GCS 측 짝.

## 백엔드 (`infra/log/log_server.py`)

- **import**: `from gcs.layer_01_info_center.run import assemble_draft` — `run_cycle`
  가드와 동일하게 실패 시 `/gcs/assemble` 만 503.
- **`POST /gcs/assemble`** `{set_mission}` →
  - `draft = assemble_draft(set_mission)` → `{draft_brief, signal_cards, warnings}`.
  - `correlation_id` 생성(기존 시퀀스 카운터 재사용).
  - 허브에 gcs 레이어 로그 publish: 요약 1건(`layer="gcs"`, `"01 임무브리핑 조립 · 카드 N · 경고 M"`)
    + 경고당 1건(`level="warn"`).
  - 반환 `{draft_brief, signal_cards, warnings, correlation_id}`.
- **`GET /gcs/set-missions`** — `examples/set_mission_{tag}.json` 스캔 →
  `[{tag, sortie_id, mission_context}]`.
- **`GET /gcs/set-mission/{tag}`** — 태그 1건 set_mission json (태그 sanitize/404).
- **`/gcs/run`** — body 에 optional `correlation_id` 수용 → 있으면 재사용(GCS 조립 →
  온보드 사이클 로그 연결). 기존 `{raw, mission_brief}` 계약 하위호환.
  `draft_brief` 는 6-필드 MissionBrief 이므로 그대로 `/gcs/run` 에 투입 가능.
  운용자가 run 을 누르는 행위 = 승인(HITL 게이트).

## 프런트 (`gcs.js`, 최소 배선)

"미구현" 주석 제거. set-missions 로드 → `POST /gcs/assemble` → 카드·경고·draft
표시. 풍부한 리뷰 패널 UX 는 범위 밖(후속).

## fixture

`examples/set_mission_{recon,strike}.json` 을 이 브랜치에 포함(main 미머지 상태 대비
self-contained). recon(정찰/저격조), strike(타격/leaflet).

## 데이터 흐름

```
UI → GET /gcs/set-missions → recon 선택
   → POST /gcs/assemble {set_mission} → {draft_brief, cards, warnings, correlation_id=C}
       (허브에 gcs 레이어 엔트리, corr=C)
   → 운용자 카드·경고 검토 → POST /gcs/run {raw, mission_brief=draft_brief, correlation_id=C}
       → 온보드 사이클 로그(corr=C) → 대시보드가 조립+사이클 연결 표시
```

## 에러 처리

- layer 01 import 실패 → `/gcs/assemble` 503(로그 스트림/`/gcs/run` 은 기동 유지).
- set_mission 필수필드 누락 → `assemble_brief` ValueError → 400.
- 잘못된 태그 → 404(경로 sanitize).

## 테스트 (`infra/log/test_gcs_endpoints.py`, TDD)

- `POST /gcs/assemble` recon → 200 + draft_brief(6필드) + signal_cards + warnings + correlation_id.
- assemble → 허브 backlog 증가, 엔트리 `layer="gcs"` + 동일 correlation_id.
- spare 불일치 set_mission → warnings 에 spare 경고.
- `GET /gcs/set-missions` → recon/strike tag 목록.
- `GET /gcs/set-mission/{tag}` → set_mission json; 잘못된 태그 404.
- `/gcs/run` 에 correlation_id 전달 → 재사용(반환 correlation_id 일치).

## 범위 밖

풍부한 리뷰 패널 UI, `finalize` ts 스탬핑 API(run=승인으로 대체), 실 NLP 모델.
