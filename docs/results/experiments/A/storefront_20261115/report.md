# 외부 쇼핑몰 템플릿 실제 연동 검증 — 2026-11-15

## 결과와 범위

- 구현: Epic Design Labs의 Next.js + Tailwind + shadcn/ui 쇼핑몰 템플릿을 고정 커밋으로 도입했다.
  출처·원본 해시·MIT 고지는 `storefront/`에 보관한다. 홈/카테고리/상품 카드/그리드/갤러리/장바구니 구성을 재사용했다.
- 상품: 실제 API가 사용하는 시뮬레이터의 50,000개 상품, 이미지, 원화 가격을 연결했다.
  기존 full-realism-v4 데이터·모델을 사용했으며 기본 full-v44 설정을 교체하거나 데이터를 재생성하지 않았다.
- 런타임 통합: 검색 3종, 추천, 상품 조회, 장바구니, 데모 구매, A/B·CT 상태, 모바일 메뉴 검증 PASS.
- 최종 품질 acceptance: **UNMEASURED**. 이번 변경은 UI·연동 검증이며 신규 학습/온라인 A/B/승격/부하 p95 측정이 아니다.

## 실제 실행

- 쇼핑몰: http://localhost:13000
- API: http://localhost:18020
- 선택 실행한 Streamlit: http://localhost:18520
- Compose 프로젝트: `mm-recsys-storefront`
- Frontend image: `sha256:1fe80f06bb70d2e5b0057a4a160fa5e51acb7ec6c22a1be27ebdeb10292d8c59`
- API는 기존 검증 이미지에 현재 `src/`, `dashboard/`를 읽기 전용 마운트했고,
  변경한 HTTP smoke 스크립트는 컨테이너에 복사해 실행했다. API 이미지를 완전히 새로 빌드한 검증은 아니다.
- 현재 결과 경로는 이 폴더의 로컬 `runtime/full`이다. 기존 배포의 A/B·CT 로그를 복사해
  저장된 측정으로 표시하며 현재 API의 data/model identity와 대조한다. 과거 증거를 덮어쓰지 않았다.
- 루트 기본 실행은 `docker compose up --build -d`이며 http://localhost:3000 을 제공한다.
  기본 배포 설정(full-v44)은 그대로다. 현재 검증 주소 13000은 기존 realism full 산출물 재사용 환경이다.

## 실행 근거

| 검증 | 결과 | 근거 |
|---|---|---|
| API/기존 dashboard/CT traffic 회귀 | 50 PASS | `pytest.xml` |
| Docker/팀 워크플로/PR 규칙 회귀 | 78 PASS | `workflow_pytest.xml` |
| 두 Python 실행의 고유 테스트 수 | 109 | JUnit classname+name 집합 합산; 중복 제외 |
| 프론트엔드 이벤트 재시도·사용자 귀속 | 2 PASS | `node --test storefront/tests/events.test.mjs` |
| TypeScript·Next.js 프로덕션 빌드 | PASS | `npm run typecheck`, `npm run build`, Docker 빌드 |
| 변경 Python mypy | PASS (3 files) | storefront API, smoke, evidence verifier |
| 실제 Chromium | PASS, page/console 오류 0 | `browser/browser.json` |
| 실제 CT SQLite 원장 | 3건 일치, 후속 세션 이력 일치 | `journal_verification.json` |
| 실제 HTTP smoke | PASS, Streamlit 검사 생략·쇼핑몰 검사 PASS | `http_smoke.json` |
| 기존 CLI 검색 | 실제 10개 결과 반환 | `cli_search.txt` |
| 선택 실행 Streamlit | `/_stcore/health` → 200 `ok` | Docker healthy 상태와 실제 HTTP 확인 |
| 실제 컨테이너 Python 소스 | 현재 작업 파일 hash 일치 | `container_sources.json` |

브라우저 검증은 route mock을 사용하지 않았다. 화면의 상품 이미지도 API 상품 이미지 경로에서 읽었다.
추천에서 선택한 `P000003`의 view/cart/purchase를 동일 request ID로 전송했고 실제 CT DB에서 확인했다.
후속 추천의 `recent_clicks`에 같은 상품이 있으며 `session_interest=sweatshirt`를 반환했다.
관찰된 API 처리 시간은 개별 요청 값으로, p95 성능 검증으로 해석하지 않는다.

## 발견 후 수정한 문제와 실패 기록

1. 상품 정렬에서 `product_id`가 index와 column에 동시에 있어 pandas 오류가 발생했다.
   정렬용 frame의 index를 초기화해 해결했고 페이지/필터/순서/가격 테스트가 통과했다.
2. 최초 회귀 실행에서 기본 Redis 호스트 `redis`를 호스트 OS가 해석하지 못했다.
   검증용 Redis의 `127.0.0.1:16395`를 명시한 재실행이 통과했다. 서비스의 쓰기 오류 처리는 바꾸지 않았다.
3. 첫 Chromium 실행은 Docker 내부 포트와 외부 포트를 혼동한 same-origin 검사 때문에 검색이 403이었다.
   브라우저 Host와 Origin을 비교하도록 수정했다. 다른 출처의 POST 및 관리자 경로 거부도 브라우저에서 검증했다.
   최초 실패는 `attempts/browser_port_origin_failure.json`에 보존했다.
4. WORKFLOW 소유권에 Docker Compose를 추가하는 시도는 기존 역할 계약 테스트에 실패했다.
   해당 설정 변경을 되돌려 기존 단계 소유권을 유지했다. 실패는 `attempts/workflow_scope_rejected.xml`에 남겼다.
   이 작업은 기존 단계 실행 지시가 아닌 별도 UI 요청으로 처리했고 단계 gate/자동 커밋을 변경하지 않았다.

## 제한과 보존

- A/B는 현재 데이터·초기 모델과 일치하는 저장된 합성 결과다. 음의 lift도 그대로 표시한다.
  온라인 방문자 배정이나 새로운 A/B 실험을 구현·실행한 결과가 아니다.
- CT는 현재 활성 모델 v1.0, 신규 이벤트와 실제 로그를 조회한다. 재학습/승격을 이번에 실행하지 않았다.
- 장바구니는 사용자 선택과 같은 브라우저 세션에 저장한다. 구매 재시도는 같은 event ID를 사용한다.
  데모 구매는 결제·배송·재고 예약이 없으며 상품별 구매 이벤트다.
- 실제 데이터·이미지·학습 파일은 버전 관리 대상이 아니다. 실행 증거용 스크린샷도 로컬에만 남겼다.
- 기존 `data/.gitkeep` 삭제 및 사용자의 `docs/results/docker` 미추적 결과는 건드리지 않았다.
- 커밋·원격 푸시·PR 생성은 하지 않았다. 기존 정해진 역할/단계 및 승인 규칙을 바꾸지 않았다.
