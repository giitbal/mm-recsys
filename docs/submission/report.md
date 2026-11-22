# PDF 요구사항 재현 보고서

<!-- latest-start -->
## 2026-11-21 · PDF 2·4·7절 검토

| 절 | 검토 결과 | 근거 |
|---|---|---|
| 2. 최종 결과물 | 3종 검색·개인화 추천 기본값 10개와 필수 JSON 필드, 기본 대시보드·차트, 기본 Compose 네 서비스와 실시간 로그를 확인했다. 쇼핑몰은 별도 프로필로 실행한다. | [기본 HTTP 응답](../results/experiments/A/illustrations_v1/integration_current/default_api_contract.json) · [브라우저](../results/experiments/A/illustrations_v1/integration_current/dashboard/browser.json) · [독립 기동](../results/experiments/A/illustrations_v1/integration_current/cold_services.json) |
| 4. 기능 요구사항 | 시뮬레이터·검색·세 단계 추천·세션·Redis·합성 A/B·CT와 평가 프로토콜을 대조했다. 측정값과 기준선은 아래 표에 담았다. | [항목별 구현·테스트·측정](requirements.md) · [재학습](../results/experiments/A/illustrations_v1/integration_current/ct_full.json) |
| 7. 제약사항 | CPU 전용 로컬 추론, 지정 라이브러리와 Docker·Redis, ID 기반 시연, 설정 분리·주요 함수 타입, 직렬 p95 조건을 확인했다. 사전학습 가중치와 의존성 레이어를 재사용해 빈 데이터·모델 경로에서 재현했다. | [측정 환경](../results/experiments/A/illustrations_v1/integration_current/hardware.json) · [full 재현](../results/experiments/A/illustrations_v1/integration_current/fresh_reproduction_full.json) · [전체 검사](../results/experiments/A/illustrations_v1/integration_current/preflight/evidence.json) |
| 2·4·7절의 원격 제출 | 공개 저장소가 익명 접근 가능하다. 아래 Git 트리 대조는 PR 발행 전 검사 시점의 기록이다. 실제 반영 커밋과 시각은 [통합 PR의 병합 기록](https://github.com/k-pang-2026/mm-recsys/pulls?q=is%3Apr+head%3Afeat%2Fintegration+sort%3Aupdated-desc)에서 확인할 수 있다. | [공개 Git 트리 대조](../results/experiments/A/illustrations_v1/integration_current/submission/publication.json) · [공개 저장소](https://github.com/k-pang-2026/mm-recsys) |

### 품질과 성능

모드별 검색 점수·인덱스 설정·속도 실험, 추천 기준선의 절대값·랭킹 라벨 수, A/B 검정식·신뢰구간은 각 실험 보고서에서 확인할 수 있다. [검색](../search_report.md) · [추천](../recommend_report.md) · [A/B](../ab_test_report.md) · [실행과 재현](reproduction.md)

시드 42로 상품 50,000개, 사용자 10,000명, 행동 1,000,000건을 생성했다. 이벤트 시간순 80/10/10 분할로 train에서만 학습하고 valid에서 고정한 뒤 test를 평가했다. 후보는 전체 카탈로그에서 찾는다. Two-Tower는 양성당 랜덤 음성 4개를 사용하고, DeepFM은 실제 합성 노출에서 귀속 시간이 지난 비클릭을 CTR 음성으로 사용한다. [데이터·페르소나 검사](../results/experiments/A/illustrations_v1/integration_current/cold_data_audit.json) · [후보 학습](../results/experiments/A/illustrations_v1/integration_current/cold_candidate_training.json) · [랭킹 학습·라벨](../results/experiments/A/illustrations_v1/integration_current/cold_ranking_training.json) · [valid 동결](../results/experiments/A/illustrations_v1/integration_current/release_quality/quality_selection_full.json)

| 지표 | 실측 | 기준 |
|---|---:|---:|
| 검색 MRR / nDCG@10 | 0.93572 / 0.93063 | ≥0.55 / ≥0.50 |
| 후보 최솟값 / Recall@300 | 300 / 0.74579 | ≥300 / ≥0.30 |
| DeepFM CTR AUC | 0.96578 | ≥0.70 |
| HitRate@50 / nDCG@50 / Coverage | 0.66443 / 0.32928 / 0.38316 | ≥0.20 / ≥0.08 / ≥0.20 |
| 검색 p95 텍스트 / 이미지 / 복합 | 26.48 / 105.13 / 119.31 ms | 각각 ≤200 ms |
| 추천 / 후보 / Redis p95 | 31.93 / 14.46 / 0.35 ms | ≤200 / ≤100 / ≤10 ms |

검색은 각 모드 200개씩 총 600쿼리의 평균이다. MRR은 최초 정답 순위 역수의 평균, nDCG는 순위 할인을 적용한 DCG/이상적 DCG다. Recall은 사용자별 상위 300개에 들어온 정답 비율, HitRate는 정답이 하나 이상 포함된 사용자 비율이다. 두 값은 test 정답이 있는 7,012명을 사용한다. Coverage는 10,000명에게 추천한 고유 상품 수/50,000이다. AUC는 양성의 점수가 음성보다 높을 확률(동점 0.5)이다. CVR AUC는 0.53041다. 프로젝트의 합의된 0.70 기준은 CTR AUC에 적용한다. [원시 지표](../results/experiments/A/illustrations_v1/integration_current/release_quality/quality_full_test.json) · [평가 계약](../contracts.md) · [계산 코드](../../src/evaluation/metrics.py)

개선율은 (제안−기준)/기준 × 100이다. 같은 텍스트가 있는 쿼리에서 BM25의 MRR·nDCG는 1.0이며, CLIP 텍스트는 두 지표 모두 -6.0%, 복합은 -3.0%다. 이미지 단독에는 BM25 입력 텍스트가 없다. 독립 HNSW 재생성 후 동일 프로토콜의 test MRR은 0.93572, nDCG@10은 0.93063였다. [검색 모드·BM25](../results/experiments/A/illustrations_v1/integration_current/release_quality/quality_full_test.json) · [독립 인덱스 test](../results/experiments/A/illustrations_v1/integration_current/cold_search_test.json)

| 추천 기준선 대비 상대 변화 | HitRate@50 | nDCG@50 | Coverage |
|---|---:|---:|---:|
| 인기순 | +878.78% | +2070.62% | +38216.00% |
| Two-Tower 단독 | +25.17% | +99.48% | -29.32% |
| DeepFM까지 | -3.56% | -13.76% | -9.83% |

세 카테고리 레벨 모두에서 10,000명의 Top-50에 같은 카테고리가 3개 연속 나온 사례는 0건이었다. 모든 사용자에게 MAB 탐색 슬롯이 2개씩 있었고 등록 7일 이내 상품이 1개 이상 포함됐다. 신규 사용자 이력 5건 기준과 실제 세션 클릭 반영은 HTTP·Redis로 검사했다. [전체 사용자 분포](../results/experiments/A/illustrations_v1/peer13_all_levels/full_test.json) · [신규 사용자·세션](../results/experiments/A/illustrations_v1/peer_final_after13/cold_session.json) · [실제 세션·보상](../results/experiments/A/illustrations_v1/integration_current/mab_full.json)

### A/B와 CT

아래 운영 CT 수치는 배포 저널의 이벤트 순번 120,223까지 처리한 후보 v1.4를 기준으로 한다. 이후 자동 학습은 계속된다. 현재 활성 모델과 최근 판정은 기본 API의 `GET /api/storefront/operations` 응답에서 `ct.active`와 `ct.logs`로 확인할 수 있다.

각 군 5,000명 × 30일의 합성 A/B에서 인기순 → 개인화 CTR은 25.0049% → 20.7599%, CVR은 1.2253% → 0.8887%였다. 두 차이의 95% 신뢰구간은 각각 [−4.4036, −4.0863]%p, [−0.3669, −0.3065]%p다. 상대 변화는 −16.98%, −27.48%다. 실험·통계·차트 요구는 충족했고 실제 고객 대상 효과는 미측정이다. [p값과 검정 방법](../ab_test_report.md) · [현재 정책·설정 해시](../results/experiments/A/illustrations_v1/integration_current/ab_recipe_alignment.json)

운영 CT는 SQLite 잠금으로 첫 시도가 중단됐다. 로컬 저널을 WAL로 전환한 뒤 신규 이벤트 63,812건이 임계값을 넘어 재학습을 시작했다. 결합 스냅샷의 시간순 train 896,169건으로 3개 모델을 다시 학습했다. 같은 valid에서 CTR AUC 0.96303470 → 0.96343080, HitRate@50 0.67538 → 0.67719였다. CTR AUC 절대 개선량은 +0.00039610이고 승격 기준은 +0.001 초과다. 후보 **v1.4 RETAINED**, 활성 **v1.0**다. 신규 로그의 시간순 분할 위치는 train 0, valid 0, test 63,812건이다. 이번 신규 로그 전체가 시간상 test에 배치되어 이 구간의 클릭·구매 라벨은 후보 학습이나 승격 결정에 사용되지 않았다. 다음 독립 구간에서도 44,786건으로 재학습이 다시 시작됐다. 별도 full 배포에서 동일 후보와 상수 기준 모델로 실제 승격·HTTP 재로딩·롤백을 검사했다. 성숙한 관측에서 CTR·HitRate가 임계값 아래로 떨어졌을 때 경보와 성능 저하 재학습 트리거가 발생하는 경우도 확인했다. [임계값 저하 시연](../results/experiments/A/illustrations_v1/peer_final_after13/ct_degraded_retraining.json) [잠금 재현](../results/experiments/A/illustrations_v1/integration_current/ct_contention.json) · [운영 CT](../results/experiments/A/illustrations_v1/integration_current/ct_full.json) · [통제 실험](../results/experiments/A/illustrations_v1/integration_current/ct_controlled_lifecycle_full.json)

### 실행 환경과 정리

기존 활성 모델은 학습 잠금이 잡힌 상태에서도 해시를 검증해 API를 기동한다. 독립 Compose에서도 잠금을 실제로 잡고 HTTP 준비 응답을 확인했다. [재기동 검증](../results/experiments/A/illustrations_v1/integration_current/cold_bootstrap_recheck.json) · [수정 전 오류](../results/experiments/A/illustrations_v1/integration_current/preflight/bootstrap_lock_before.txt)

Windows 호스트 물리 8코어, 메모리 16,758,542,336바이트, WSL2 Docker 엔진 8 vCPU·약 11.66 GiB이며 API 제한은 4 CPU·4 GiB다. GPU를 사용하지 않았다. HTTP 모드별·후보·Redis마다 10회 예열 후 100회 직렬 호출의 p95를 다시 계산했다. 대시보드는 기본 8501, 선택 쇼핑몰은 3000에서 실행한다. 쇼핑몰의 구매는 사용자 ID에 귀속되는 시뮬레이션 이벤트다. [환경](../results/experiments/A/illustrations_v1/integration_current/hardware.json) · [벤치마크 조건과 서비스 복귀](../results/experiments/A/illustrations_v1/integration_current/deployment_benchmark.json) · [원시 지연](../results/experiments/A/illustrations_v1/integration_current/release_quality/smoke_full.json)

쇼핑몰 11개 Next.js 진입점과 TypeScript import 그래프, 테스트·Docker·문서 참조를 확인해 도달하지 않는 템플릿 컴포넌트 19개와 주문·결제·배송 타입, 미사용 직접 의존성 두 개를 제거했다. 상품 이미지의 로딩 오류 대체, 실제 구매 이벤트, 테스트 fixture와 원본 라이선스 및 성능 이력은 검토한 용도로 사용한다. [삭제 파일과 SHA-256](../results/experiments/A/illustrations_v1/integration_current/storefront_cleanup.json) · [쇼핑몰 브라우저](../results/experiments/A/illustrations_v1/integration_current/storefront/browser.json) · [검색 링크와 이미지 대체](../results/experiments/A/illustrations_v1/integration_current/storefront/cleanup_browser.json)
<!-- latest-end -->

## 이전 실행 기록

아래 수치는 이전 정책·생성기에서 얻은 측정값이다. 현재 제출 수치와 원본 해시는 문서 맨 위의 2026-11-21 검토에 있다.

기본 실행과 쇼핑몰 모두 `illustrations-v1` 상품과 독립 검색 쿼리를 사용한다. 새 도안의 full test와 합성 A/B 실측은 [대시보드 기준 보고서](dashboard/evaluation_full_test.json)에 기록한다. 새 데이터의 전체 통합 판정은 [현재 판정](../results/final_acceptance.json)을 따른다.

상품 50,000개·사용자 10,000명·이벤트 1,000,000건으로 valid를 동결한 후 test에서 품질·지연 11개 기준을 통과했다. MRR 0.93572, nDCG@10 0.93063, Recall@300 0.74579, 검색 p95 최댓값 112.37ms를 기록했다. [full test 원본](../results/experiments/A/illustrations_v1/default_full/quality_full_test.json) · [독립 재생성](../results/experiments/A/illustrations_v1/default_full/reproduction_full.json) · [대시보드·API·쇼핑몰 이미지 대조](../results/experiments/A/illustrations_v1/default_full/catalog_check.json)

새 도안 상품으로 사용자 5,000명씩 무작위 배정해 모의 30일 동안 인기순과 개인화 추천을 비교했다. 각 군 노출은 1,500,000건이었다. CTR은 25.0049% → 20.6625%(-17.37%, p < 0.001), CVR은 1.2253% → 0.8857%(-27.72%, p < 0.001)였다. CVR의 분모는 추천 노출 수다. [A/B 통계 검산](../results/experiments/A/illustrations_v1/full_ab_ct/ab_acceptance_full.json)

운영 API와 시뮬레이터에서 신규 이벤트 10,054건을 관측해 재학습을 시작했다. 전체 스냅샷을 시간순으로 나눠 후보·랭킹·세션 모델을 학습했다. 동일한 시간순 valid에서 CTR AUC는 0.966133695 → 0.965839790(-0.000293905)였다. 승격 조건은 후보 AUC ≥ 0.70과 기존 모델 대비 개선 > 0.001이다. 후보 v1.1 판정은 **RETAINED**, API가 제공한 모델은 **v1.0**이다. [운영 CT 판정](../results/experiments/A/illustrations_v1/full_ab_ct/ct_full.json) · [배포 API 응답](../results/experiments/A/illustrations_v1/full_ab_ct/ct_http_after.json)

신규 이벤트의 시간순 위치는 train 0건, valid 0건, test 10,054건이다. test 구간 건수는 전체에서 train·valid를 빼서 확인했다. [신규 이벤트 분포](../results/experiments/A/illustrations_v1/full_ab_ct/ct_new_event_folds.json)

동일 후보와 AUC 0.5의 상수 초기 모델을 사용한 별도 full API에서는 승격·교체·롤백 순으로 추천 응답 6건이 모두 HTTP 200이었다. 기본 대시보드에서 30일 A/B 차트 2개를, 쇼핑몰 운영 화면에서 같은 실험과 배포 모델을 확인했다. [브라우저 검증](../results/experiments/A/illustrations_v1/full_ab_ct/live_browser.json) · [통제 시연](../results/experiments/A/illustrations_v1/full_ab_ct/ct_controlled_lifecycle_full.json)

독립 복제본에 현재 작업 소스를 반영하고 빈 데이터·모델·결과 디렉터리에서 기본 Compose 네 서비스를 기동했다. 지정된 CLIP 사전학습 캐시와 Docker 의존성 레이어는 재사용했다. 상품 이미지 50,000장의 개별 해시와 검색·추천 산출물을 동결 측정과 대조했다. 동일 벡터로 생성한 세 HNSW 인덱스의 이웃 연결은 달랐다. 재생성한 인덱스에서 동일한 600개 test 쿼리를 평가해 MRR 0.93572, nDCG@10 0.93063를 확인했다. [독립 검색 재측정](../results/experiments/A/illustrations_v1/final_integration/cold_search_quality.json) · [Docker 재현](../results/experiments/A/illustrations_v1/final_integration/fresh_reproduction_full.json) · [최종 제출 검사](../results/experiments/A/illustrations_v1/final_integration/submission/checks.json)

아래는 이전 도안의 제출 이력이다. [이전 PDF 통합 검사](../results/experiments/A/pdf_completion_20261121/report.md)

## 2026-11-12 리팩터링 검증

당시 소스에서 full valid를 동결한 뒤 test를 새로 실행해 **품질·지연 11개 기준을 모두 통과했다.**
상품 50,000개·사용자 10,000명·이벤트 1,000,000건, K=300, 정답·사용자 집합·기준은 유지했다.
당시 통합 판정은 [게시 직전 검사 결과](../results/experiments/A/final_validation_20261112/release/submission/checks.json)와 [당시 집계 사본](../results/experiments/A/pdf_completion_20261121/previous_acceptance.json)을 따른다.
KST·소수 한 자리 표시의 전체 회귀·배포 소스 검증은 release 기록을, 아래 full 모델·품질 측정은 보존한 실행 기록을 따른다.
품질 통과와 A/B 개선, 실제 CT 승격, 원격 게시 여부를 구분한다.

## 데이터와 재현

- seed 42, 노출 2,254,172건, 시간순 train/valid/test 80/10/10, fixed-origin 평가.
- fingerprint: `2df9b64e07e3b2aad48c967c4c8d3d8b04883dd19279896bb374c4f9926ad7d8`.
- 새 빈 데이터·모델 경로에서 생성·감사·CLIP·FAISS·세 모델 학습·Redis 준비 6단계를 모두 통과했다.
  단계 실행 시간 합은 1651.5초이며, 독립 재생성의 기록 파일 8개는 원본과 해시가 같다.
- pinned CLIP 다운로드 캐시와 Docker 의존성 레이어는 재사용했다. 원격 새 클론 검증은 아니다.
- 최초 실행은 데이터·인덱스·학습 후 Redis 준비에서 timeout으로 실패했다.
  프로필 교체의 제한된 멱등 재시도를 추가한 뒤 새 빈 경로에서 전체 과정을 다시 검증했다.
  후속 회귀 검사에서 Redis 예외 import가 기본 ConnectionError를 가리는 문제도 수정했다.
  이 수정은 학습·데이터·준비 알고리즘을 바꾸지 않으며, 수정 후 실제 Redis·API와 전체 회귀·품질을 다시 검증했다.

근거: [빈 경로 재현](../results/experiments/A/final_validation_20261112/fresh_reproduction_full.json), [데이터 동일성](../results/experiments/A/final_validation_20261112/data_reproduction_full.json),
[최초 실패와 재검증 설명](../results/experiments/A/final_validation_20261112/verification_attempts.json).

## 품질과 속도

| 지표 | valid | test / 별도 benchmark | 기준 | 판정 |
|---|---:|---:|---:|---|
| mrr | 0.945000 | 0.925000 | ≥0.55 | PASS |
| ndcg_at_10 | 0.945000 | 0.925000 | ≥0.5 | PASS |
| recall_at_300 | 0.748963 | 0.745793 | ≥0.3 | PASS |
| auc | 0.966648 | 0.965785 | ≥0.7 | PASS |
| hit_rate_at_50 | 0.689281 | 0.665145 | ≥0.2 | PASS |
| ndcg_at_50 | 0.366957 | 0.329914 | ≥0.08 | PASS |
| coverage | 0.390440 | 0.374480 | ≥0.2 | PASS |
| search_p95_ms | 77.677496 | 77.677496 | ≤200 | PASS |
| recommend_p95_ms | 18.924133 | 18.924133 | ≤200 | PASS |
| candidate_p95_ms | 3.350916 | 3.350916 | ≤100 | PASS |
| feature_p95_ms | 0.245390 | 0.245390 | ≤10 | PASS |

Recall@300은 전체 카탈로그의 사용자별 미래 cart/purchase 정답에 대한 macro 평균이다.
Coverage는 고정 전체 10,000명의 Top-50 합집합/전체 50,000개다.
관측 cutoff와 train-only 학습을 유지하고 valid에서 선택한 설정으로 test를 한 번 평가했다.
BM25·인기도·Two Tower 등 기존 baseline과 비교 프로토콜도 유지했다.
AUC ≥0.70은 CTR 기준이다. CVR AUC는 별도 진단값이며 높은 구매 예측력을 주장하지 않는다.

지연은 aarch64 CPU의 단일 API 배포에서 10회 예열 후 100회 순차 요청으로 측정했다.
API 4GiB/4CPU, 추론 Torch/FAISS·OMP/MKL/OpenBLAS 2스레드, pinned FP32 CLIP 조건이다.
모든 측정 구간에서 simulator를 중지하고 다른 학습 컨테이너를 일시 정지했다가 복구했다.
Docker 전체 RAM은 약 11.66GiB였다. 다른 하드웨어와 동시 학습 중 지연으로 일반화하지 않는다.
검색 p95는 text 19.817ms, image 73.177ms, hybrid 77.677ms이며 최댓값으로 판정했다.

원본: [valid](../results/experiments/A/final_validation_20261112/quality_full_valid.json), [동결](../results/experiments/A/final_validation_20261112/quality_selection_full.json),
[test](../results/experiments/A/final_validation_20261112/quality_full_test.json), [HTTP 지연](../results/experiments/A/final_validation_20261112/smoke_full.json), [실행 조건](../results/experiments/A/final_validation_20261112/latency_conditions.json).

## 결과 예시와 한 명령 시연

실행 가이드는 [README](../../README.md)와 [재현 절차](reproduction.md)를 따른다.
`docker compose up --build -d` 후 `demo examples`로 검색·클릭·추천·A/B·CT를 실행한다.
이번에는 20명/군·2일로 전체 명령 연결을 확인하고, full 5,000명/군·30일 A/B를 별도 재측정했다.
기본 A/B 설정은 바꾸지 않았다. 상품·가격·점수·시간을 PDF의 참고 숫자로 고정 출력하지 않는다.
실제 한국어 텍스트·이미지·하이브리드 상품 의미, API 스키마, 422/413, 세션·Redis 귀속,
다양성·신규 상품·cold-start 및 브라우저 여섯 탭을 검증했다.

근거: [예시 의미](../results/experiments/A/final_validation_20261112/pdf_examples.json), [동료 평가](../results/experiments/A/final_validation_20261112/peer_review.json),
[HTTP·Redis](../results/experiments/A/final_validation_20261112/mab_full.json), [브라우저](../results/experiments/A/final_validation_20261112/browser_basic/browser.json),
[한 명령 시연](../results/experiments/A/final_validation_20261112/demo_examples_verified.json).
최종 집계 게시 후 화면 검증은 [browser_final](../results/experiments/A/final_validation_20261112/browser_final/browser.json)에 별도 기록한다.

## A/B 결과

| 지표 | Control | Treatment | 상대 변화 |
|---|---:|---:|---:|
| CTR | 25.0049% | 20.6625% | −17.37% |
| CVR | 1.2253% | 0.8857% | −27.72% |

각 군 5,000명·30일·top10, 150만 노출의 합성 실험이다.
CVR 차이 −0.339667%p, 사용자 군집 95% CI [−0.370099, −0.309234]%p, Z 검정 p=4.409705e−106이다.
통계 검산 PASS는 treatment 개선을 뜻하지 않는다.
고정 노출의 점수 순서인 오프라인 AUC와 각 정책이 생성한 새 노출의 A/B 반응은 평가 대상이 다르다.
원인별 ablation은 수행하지 않았으므로 음의 효과를 특정 단계 탓으로 단정하지 않는다.

이전 동일 데이터 실험과 사용자 배정·클릭·구매·통계는 같았다.
다만 treatment 노출 150만 건 중 1건의 상품 배분이 달라 완전 동일성 비교는 FAIL로 보존했다.
모든 상품 노출의 비트 단위 동등성을 주장하지 않는다.
근거: [통계 검산](../results/experiments/A/final_validation_20261112/ab_acceptance_full.json), [무손실 원본](../results/experiments/A/final_validation_20261112/ab_full_archive.json),
[동일성 비교의 실패 범위](../results/experiments/A/final_validation_20261112/ab_regression_detail.json).

## 실제 CT와 통제 시연

기존 배포 원장의 미처리 로그 **13,404건**으로 실제 재학습을 실행했다.
이번 학습은 `src.ct.retrain_trigger --train`의 1회 감시 호출이며 자동 worker가 직접 수행한 학습으로 표기하지 않는다.
기본 Compose의 자동 CT worker 기동과 공유 잠금 연결은 [별도 기록](../results/experiments/A/final_validation_20261112/automatic_ct_startup.txt)으로 확인했다.
후보 v1.2의 세 모델 학습·checkpoint 재로딩·동일 valid 평가는 모두 통과했다.
CTR AUC는 **0.966114654 → 0.966329962**, 개선 폭 **0.000215308**로 원래 최소 개선 0.001 미만이다.
따라서 **RETAINED**, 운영 v1.0 유지가 정상 판정이다. 중복 호출은 WAITING, 신규 로그 0건이었다.

재학습 스냅샷에는 누적 원장 이벤트 116,908건이 들어 있다.
원장 이벤트의 시간순 위치는 train 0, valid 5,372, test 111,536건이다.
이는 이번 트리거 13,404건의 분할 수가 아니다. 최신 로그를 임의로 train으로 옮기거나 CT test 정답을 열지 않았다.
새 snapshot cutoff에 따라 기존 base 이벤트가 train으로 이동할 수 있다.

운영 승격과 별개로, 동일한 실제 후보와 full 데이터·동일 guard를 사용한 별도 registry에서
초기 ranker를 상수 AUC 0.5로 두고 실제 승격·HTTP 모델 교체·롤백을 검증했다.
6개 HTTP 응답이 모두 200이며 운영 registry는 바뀌지 않았다.
통제 시연 PASS를 운영 모델의 개선·승격으로 해석하지 않는다.

기본 자동 CT는 로그 10,000건 또는 성숙한 활성 모델 성능 저하로 감지한다.
성숙한 train/valid 라벨이 부족하면 WAITING_FOR_LABELS로 대기하며 원래 시간순·귀속 조건을 지킨다.
입력·모델·설정이 같으면 불필요한 재시도를 억제하고, A/B와 CT는 공유 잠금으로 순차 실행한다.

근거: [실제 CT](../results/experiments/A/final_validation_20261112/ct_full.json), [학습](../results/experiments/A/final_validation_20261112/ct_training_sources_full.json),
[시간순 위치](../results/experiments/A/final_validation_20261112/ct_new_observation_folds.json), [분리된 라이프사이클 검증](../results/experiments/A/final_validation_20261112/ct_acceptance_full.json).

## 코드 품질과 범위

중복 데이터·모델 읽기, 불필요한 DataFrame 왕복과 전체 카탈로그 복사, CT 전체 로그 읽기를 줄였다.
재시도 상태·SQLite 시간 인덱스·선택 분할 라벨·공개 함수 타입을 보강했다.
상세 전후 측정은 [리팩터링 기록](../results/experiments/A/resource_refactor_20261112.md)에 보존한다.
전체 pytest·실제 Redis·mypy·의존성·공개 함수 검사와 근거 해시는 [최종 checker](../results/experiments/A/final_validation_20261112/release/submission/checks.json)가 판정한다.
이 문서만으로 미실행 검사를 PASS로 간주하지 않는다.

H&M·Retailrocket·DeepFashion은 [사용자가 전달한 강사 결정](dataset_scope.json)에 따라 획득했고 추가 검증에 사용했다. [데이터별 평가 결과](../external_datasets.md)
실제 사용자 효과, 다른 하드웨어·GPU, 여러 배포의 동시 학습 용량, 외부 제출은 이번 검증 범위가 아니다.
기존 역할 기여·PR은 [원본](contributions.json)을 유지한다. 원격 게시·CI·병합은 GitHub PR 기록으로 별도 확인한다.
