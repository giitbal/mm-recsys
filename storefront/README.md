# MM Shop

외부 쇼핑몰 템플릿을 실제 mm-recsys API와 시뮬레이터 상품에 연결한 로컬 데모입니다.

## 원본 템플릿

- 출처: https://github.com/Epic-Design-Labs/nextjs-ecommerce-starter
- 고정 커밋: `8618a0080492b157c5609ddd8b18c48440728e2d`
- Next.js + Tailwind CSS + shadcn/ui, upstream `package.json`과 README의 MIT 선언.
- [원본 README](UPSTREAM_README.md), [원본 파일·압축 해시](upstream.json), [고지](THIRD_PARTY_NOTICES.md).
- 홈의 hero/카테고리/상품 그리드, 상품 카드·이미지 갤러리, 상품 목록의 필터·정렬·페이지,
  장바구니 drawer/item, UI 컴포넌트와 테마를 가져왔습니다.
- 한국어 문구와 내비게이션, 데이터 저장소, 검색·추천, 행동 기록, 데모 구매, 운영 화면을 연결했습니다.
  원본의 예시 상품·리뷰·할인·가짜 로그인/결제 및 CMS 페이지는 서비스에 포함하지 않습니다.
  원본 상품 ID·이미지·가격은 API가 사용 중인 시뮬레이터 카탈로그를 그대로 사용합니다.

## Docker 실행

대시보드와 쇼핑몰에서 같은 상품 JPEG를 검색하고 표시합니다. full 카탈로그는 `data/full-illustrations-v1/images/`에 생성됩니다. SHA-256은 같은 데이터 폴더의 `image_manifest.json`에 기록됩니다. 가방은 종류별로 몸판 6종과 디테일 4종을 조합합니다.

저장소 루트에서 실행합니다. 새 데이터/모델은 기존 준비 절차로 생성하며 이미 준비된 경우 재사용합니다.

```bash
docker compose up --build -d
docker compose --profile storefront up -d --build --no-deps storefront
```

기본 배포가 꺼져 있으면 `docker compose --profile storefront up -d --build storefront`로 필요한 API와 Redis도 함께 시작합니다.

- 쇼핑몰: http://localhost:3000 (`STOREFRONT_PORT`로 변경)
- 검색: `/search` — 텍스트, 이미지, 두 입력을 함께 사용한 복합 검색.
- 추천: `/recommend` — 사용자 ID 선택 후 추천받기. ID를 바꾸면 장바구니도 초기화합니다.
- 상품: `/product/<product_id>` — 조회 기록, 장바구니 담기.
- 구매: `/checkout` — 실제 결제 없이 상품별 구매 이벤트 기록.
- 운영: `/operations` — 현재 API 준비·모델·신규 이벤트 및 배포 identity가 일치하는 A/B 결과.

기본 대시보드는 http://localhost:8501 에서 열립니다. CLI에서도 같은 API를 호출할 수 있습니다.

```bash
docker compose exec -T api-server demo search --query-text "검정 가방"
docker compose exec -T api-server demo recommend --user-id U000001
```

CT 워커·A/B 실행 명령은 저장소 README와 기존 CLI를 따릅니다. 운영 화면은 읽기 전용이며
관리자 reload/학습 API를 브라우저 프록시로 노출하지 않습니다. A/B 화면은 저장된 합성 실험 결과이며
방문자를 온라인 실험군에 배정하는 기능은 없습니다. CT의 학습·승격을 시연 클릭으로 보장하지 않습니다.

## 로컬 프론트엔드 개발

Node.js 24와 별도로 실행 중인 실제 mm-recsys API가 필요합니다.

```bash
cd storefront
npm ci --ignore-scripts
API_URL=http://127.0.0.1:8000 npm run dev -- --hostname 127.0.0.1
```

`API_URL`은 서버 전용입니다. 브라우저는 동일 출처의 `/api/live/...` 프록시만 사용합니다.
GET 경로는 상품·이미지·상태·추천으로, POST는 검색·event·feedback으로 제한합니다.
다른 출처의 POST, 관리 경로와 7MB 초과 본문을 거부합니다. 로컬 시연용이며 외부 공개 인증을 제공하지 않습니다.

## 데이터·이벤트 계약

- 카탈로그는 `cfg.paths.data_dir`의 `products.parquet`와 `split_manifest.json`으로 검증합니다.
  파일이나 fingerprint 오류는 503으로 표시하며 예시 상품으로 대체하지 않습니다.
- 상품 가격은 원화 원본 값입니다. 템플릿의 USD cents 나누기 100 규칙을 적용하지 않습니다.
- 추천 응답의 `X-Recommendation-Request-ID`를 상품 링크와 장바구니에 유지합니다.
  동일 사용자에 한해 조회/장바구니/구매에 전달하며 검색·카탈로그 탐색은 임의 노출에 귀속시키지 않습니다.
- 실패한 행동은 동일 event ID와 attribution으로 재시도합니다. 구매 도중 일부만 성공하면
  성공 상품만 장바구니에서 제거하고 나머지를 재시도할 수 있습니다.
- 장바구니 수량은 UI 합계용이며 학습 이벤트는 상품별 행동 한 건입니다. 재고·결제·배송 시스템은 아닙니다.
- 하트는 원본 템플릿의 브라우저 내 관심 표시이며 추천 학습 이벤트에 추가하지 않습니다.
- A/B는 데이터와 초기 모델 해시를 확인한 기존 결과만 표시합니다. 음의 효과·미측정을 그대로 표시합니다.
- CT는 현재 registry·journal 및 실행 로그를 읽습니다. 저장된 로그 시각과 현재 서비스 모델을 구분합니다.
  화면 새로고침은 학습을 실행하지 않습니다.
- 개별 요청의 API 처리 시간은 부하 테스트 p95와 다릅니다.

## 검증

```bash
npm --prefix storefront run typecheck
npm --prefix storefront run build
node --test storefront/tests/events.test.mjs
.venv/bin/python -m pytest -q tests/test_storefront.py tests/test_docker.py
STOREFRONT_URL=http://localhost:3000 node scripts/verify_storefront_browser.cjs
```

새 도안 쇼핑몰의 브라우저 검사는 `STOREFRONT_URL=http://localhost:13000`으로 실행합니다. 이미지별 체크섬과 데이터 재생성 결과는 [카탈로그 비교](../docs/results/experiments/A/illustrations_v1/catalog.json)와 [full 재현 결과](../docs/results/experiments/A/illustrations_v1/reproduction_full.json)에 기록했습니다.

브라우저 검증에는 설치된 Playwright Chromium이 필요합니다. 다른 설치를 재사용하려면
`PLAYWRIGHT_MODULE`과 `PLAYWRIGHT_BROWSERS_PATH`를 설정합니다.
이 검증은 실제 추천 요청과 소량의 조회·장바구니·구매 이벤트를 기록하며 학습을 강제하지 않습니다.

HTTP smoke는 기본 대시보드를 검사합니다. 쇼핑몰도 실행 중이면 `scripts/smoke_test.py --storefront-url http://storefront:3000`으로 두 UI를 검사합니다.
