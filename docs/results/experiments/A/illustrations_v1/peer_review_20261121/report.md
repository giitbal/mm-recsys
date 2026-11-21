# PDF 동료 평가 27문항 검증

2026년 11월 21일 로컬 작업본과 새 도안 full 데이터에서 프로젝트 평가 계약 기준으로 **27/27문항 통과**했다. PDF 12~14쪽의 질문을 원문 순서로 세었다. 기능 14개, 설계·문서 6개, 핵심 기술 7개이며 MAB에 대한 두 질문은 각각 확인했다. [문항 원문·판정·SHA-256](checklist.json)

## 판정 범위

다양성은 현재 설정의 소분류, Ranking AUC는 사전 합의한 CTR AUC로 판정했다. PDF의 다양성 문항은 계층을 지정하지 않는다. 같은 Top 10을 중분류로 판단하면 30명 중 18명, 대분류로 판단하면 24명에게서 3연속 이상이 발생한다. 최대 10개까지 이어진 응답도 있었다. 중분류나 대분류까지 요구하면 13번은 미충족으로 총 26/27이다. CVR AUC는 0.53041이다. [카테고리별 반례](category_levels.json) · [정량 검산](quality_recheck.json)

API 94개, 대시보드 7개, 시뮬레이터 12개의 소스·설정·보고서 SHA-256을 각 배포 경로에서 읽어 현재 로컬 파일과 대조했다. 113개 서비스별 파일 대조가 모두 일치했다. [배포 파일 해시](deployment_sources.json)

호스트는 물리 8코어·설치 RAM 16GiB, Docker 엔진은 8 CPU·11.66GiB이며 API 컨테이너는 4 CPU·4GiB다. GPU 없이 서빙 Torch·FAISS·OMP·MKL 각 2스레드를 사용했다. 기본 시뮬레이터와 선택 쇼핑몰을 실행한 단일 배포에서 모드별 워밍업 10회 후 100회 직렬 HTTP 요청을 측정했다. CPU 허용 오차를 적용하기 전의 기준을 만족했다. [실행 환경](runtime.json) · [원시 시간 표본](live_benchmark.json)

품질 문항은 valid에서 동결한 동일 모델의 기존 full test 보고서와 내부 수치, 해시 및 원본 분할을 재검산했다. 이번 감사에서 전체 test 추론이나 30일 A/B 시뮬레이션을 다시 돌리지는 않았다. A/B는 사용자별 원자료에서 통계량을 다시 계산했다. API·Redis·브라우저, 실제 모델 재인코딩·점수·정렬, 설정 변경 생성과 저하 트리거는 이번 감사에서 실행했다. [최종 통합 근거](../final_integration/submission/checks.json) · [A/B 통계 재계산](ab_statistics.json)

## 기능 동작

| 번호 | PDF 쪽 | 질문 | 판정 | 확인 결과와 근거 |
|---:|---:|---|---|---|
| 1 | 12 | docker-compose up 명령으로 모든 컨테이너가 정상 시작되는가? | PASS | 기본 Compose 4개 서비스를 확인했다. 현재 기동 명령은 종료 코드 0이었다. 빈 디렉터리에서 처음 기동한 별도 기록에서도 네 서비스가 동작했다. 쇼핑몰은 선택 프로필이다. [runtime.json](runtime.json) · [cold_services.json](../final_integration/cold_services.json) · [cold_preparation.json](../final_integration/cold_preparation.json) |
| 2 | 12 | 검색 API, 추천 API, 대시보드가 각각 응답하는가? | PASS | 실제 텍스트·이미지·복합 검색과 추천이 응답했다. Chromium에서 대시보드의 검색, 추천, A/B 차트와 클릭 전후 비교까지 열었다. [live_benchmark.json](live_benchmark.json) · [browser.json](browser.json) · 로컬 화면 캡처 `browser_session.png` (브라우저 실행 시 생성) · [deployment_sources.json](deployment_sources.json) |
| 3 | 12 | 신규 사용자 요청 시 적절한 폴백 결과가 반환되는가? | PASS | 클릭 이력이 없는 신규 ID의 일반 추천 8개 점수가 학습 로그로 따로 계산한 인기도·최근 증가량 점수와 모두 일치했다. 나머지 2개는 탐색 슬롯이다. [cold_session.json](cold_session.json) · [live_peer.json](live_peer.json) |
| 4 | 13 | 추천 결과에 MAB Exploration 슬롯(is_exploration=true)이 포함되어 있는가? | PASS | 시드 42로 무작위 추출한 서로 다른 사용자 30명의 Top 10에 모두 is_exploration=true가 2개씩 있었다. [sample_30.json](sample_30.json) · [live_peer.json](live_peer.json) |
| 5 | 13 | 검색 API 응답 시간이 200ms 이내인가? | PASS | 실제 HTTP 왕복 p95는 텍스트 24.35ms, 이미지 105.98ms, 복합 90.71ms였다. 각 100건 중 200ms 초과는 0건이었다. [live_benchmark.json](live_benchmark.json) · [quality_recheck.json](quality_recheck.json) · [runtime.json](runtime.json) |
| 6 | 13 | 추천 API 응답 시간이 200ms 이내인가? | PASS | 추천 HTTP 왕복 p95는 34.56ms였다. 100건 모두 정상 응답했다. [live_benchmark.json](live_benchmark.json) · [quality_recheck.json](quality_recheck.json) |
| 7 | 13 | 리포트에 데이터 분할 방식(train/valid/test 비율)이 명시되어 있는가? | PASS | 실험 보고서에 시간순 분할 건수가 명시돼 있다. 실제 Parquet에서 800,000 / 100,000 / 100,000건과 시간 정렬, 세 구간 사이의 비중첩 및 해시를 확인했다. [quality_recheck.json](quality_recheck.json) · [data_audit.json](../default_full/data_audit.json) · [report.md](../report.md) · [README.md](../../../../../../README.md) |
| 8 | 13 | 검색 성능: MRR ≥ 0.55, NDCG@10 ≥ 0.50 달성 여부가 수치로 보고되었는가? | PASS | 동결 test 600개에서 MRR 0.93572 ≥ 0.55, nDCG@10 0.93063 ≥ 0.50이었다. 세 모드별 200개이며 독립 재생성한 인덱스 평가값도 일치했다. [quality_full_test.json](../final_integration/quality/quality_full_test.json) · [quality_recheck.json](quality_recheck.json) · [cold_search_quality.json](../final_integration/cold_search_quality.json) · [report.md](../../../../../submission/report.md) |
| 9 | 13 | 추천 성능: Recall@300 ≥ 0.30, HitRate@50 ≥ 0.20, NDCG@50 ≥ 0.08 달성 여부가 보고되었는가? | PASS | 전체 후보 카탈로그 기준 Recall@300 0.74579 ≥ 0.30, HitRate@50 0.66515 ≥ 0.20, nDCG@50 0.32991 ≥ 0.08이었다. 추천 정답을 가진 사용자 7,012명을 평가했다. [quality_full_test.json](../final_integration/quality/quality_full_test.json) · [quality_recheck.json](quality_recheck.json) · [report.md](../../../../../submission/report.md) |
| 10 | 13 | Ranking 모델: AUC ≥ 0.70 달성 여부가 보고되었는가? | PASS | 프로젝트가 사전 확정한 CTR 기준으로 AUC 0.96578 ≥ 0.70이었다. 클릭된 노출만 대상으로 측정한 별도 CVR AUC는 0.53041이다. [quality_full_test.json](../final_integration/quality/quality_full_test.json) · [quality_recheck.json](quality_recheck.json) · [contracts.md](../../../../../contracts.md) |
| 11 | 13 | Coverage ≥ 0.20 달성 여부가 보고되었는가? | PASS | 10,000명 Top 50에 등장한 고유 상품 18,724개 / 전체 상품 50,000개 = 0.37448 ≥ 0.20으로 검산했다. [quality_full_test.json](../final_integration/quality/quality_full_test.json) · [quality_recheck.json](quality_recheck.json) |
| 12 | 13 | Feature Store 피처 조회 시간이 10ms 이내인지 확인되었는가? | PASS | 실제 Redis에서 프로필과 클릭 이력을 조회했다. 100건 전부 적중했고 p95는 0.260ms였다. [quality_recheck.json](quality_recheck.json) · [live_benchmark.json](live_benchmark.json) |
| 13 | 13 | 동일 카테고리 상품이 연속 3개 이상 노출되지 않는가? (샘플 3건 이상 확인) | PASS | 현재 설정인 소분류로는 30명 전원 최장 2연속이다. 같은 응답에서 중분류로는 18명, 대분류로는 24명이 3연속 이상이었다. PDF는 적용할 계층을 특정하지 않는다. [category_levels.json](category_levels.json) · [sample_30.json](sample_30.json) · [recommend.yaml](../../../../../../config/recommend.yaml) |
| 14 | 13 | 신규 상품(등록 7일 이내)이 추천 결과에 포함되는가? | PASS | 30명 전원의 Top 10에 7일 이내 신상품이 1개씩 포함됐다. 시뮬레이터 기준일 2026-01-01 UTC와 각 상품의 실제 등록일을 대조했다. [sample_30.json](sample_30.json) · [live_peer.json](live_peer.json) |

## 코드 구조·설계·문서

| 번호 | PDF 쪽 | 질문 | 판정 | 확인 결과와 근거 |
|---:|---:|---|---|---|
| 15 | 13 | 전체 코드를 수정하지 않고, config나 전략 패턴으로 로직을 교체할 수 있는가? | PASS | 동일 full 모델과 사용자에 YAML의 recommend.scoring.strategy만 바꿨다. 유사도순과 최신순의 결과가 달라졌고, 최신순 10개 모두 카탈로그 최종 등록일 상품이었다. 기존 재정렬 제약도 활성 상태였다. [strategies.json](strategies.json) · [verified_mechanisms.xml](verified_mechanisms.xml) · [recommend.yaml](../../../../../../config/recommend.yaml) |
| 16 | 13 | config 파일 수정만으로 시뮬레이터가 변경된 설정을 반영하는가? | PASS | 임시 YAML 두 개로 정식 생성 CLI를 두 번 실행했다. 120명 중 두 페르소나는 18→30명, 24→12명으로 바뀌었고 새 중·소분류 상품은 0→11개였다. 각각 상품 450장과 이벤트 4,000건을 생성했다. [simulator_yaml.json](simulator_yaml.json) · [verified_mechanisms.xml](verified_mechanisms.xml) |
| 17 | 13 | 역할 분리: simulator, search, recommendation, serving 모듈이 폴더로 분리되어 있는가? | PASS | src/simulator, src/search, src/recommendation, src/serving에 패키지와 기능별 진입점이 각각 있다. [generate.py](../../../../../../src/simulator/generate.py) · [service.py](../../../../../../src/search/service.py) · [service.py](../../../../../../src/recommendation/service.py) · [main.py](../../../../../../src/serving/main.py) |
| 18 | 13 | 문서화: README.md에 실행 방법과 아키텍처가 설명되어 있는가? | PASS | README에 기본 Compose 명령, 접속 주소, 구성요소 표 및 시뮬레이터→검색/추천→API 흐름도가 있다. [README.md](../../../../../../README.md) · [runtime.json](runtime.json) · [browser.json](browser.json) |
| 19 | 13 | README 또는 기획서에 팀원별 역할 분담이 명시되어 있는가? | PASS | README의 역할 표에 이제원(공통·검색·Docker), 박정욱(추천), 박채영(플랫폼·평가·CT)이 명시돼 있다. [README.md](../../../../../../README.md) · [contributions.json](../../../../../submission/contributions.json) |
| 20 | 14 | 개인별 주요 기여 영역(구현 모듈, 문서 작성 등)이 요약되어 있는가? | PASS | 세 사람의 주요 구현·문서 기여, 역할별 인계 문서와 PR 목록을 확인했다. 공개 PR은 보고서의 역할 분담과 연결되며 미게시 변경의 개인별 작성자는 이번에 확인하지 않았다. [contributions.json](../../../../../submission/contributions.json) · [A.md](../../../../../contributions/A.md) · [B.md](../../../../../contributions/B.md) · [C.md](../../../../../contributions/C.md) |

## 핵심 기술 원리

| 번호 | PDF 쪽 | 질문 | 판정 | 확인 결과와 근거 |
|---:|---:|---|---|---|
| 21 | 14 | 멀티모달 임베딩: CLIP으로 텍스트/이미지가 동일 벡터로 변환되어 검색에 사용되는가? | PASS | 고정된 동일 CLIP 체크포인트로 상품 8개의 텍스트·이미지를 각각 재인코딩했다. 512차원 단위벡터가 인덱싱 원본과 일치했다. 후드티 텍스트, 갈색 가방 이미지, 가방 복합 검색에서 각각 Top 10 모두 관측 속성이 일치했다. [clip.json](clip.json) · [semantic_examples.json](semantic_examples.json) |
| 22 | 14 | Two-Tower 구조: User/Item Tower가 분리되고, Item 임베딩이 FAISS에 저장되어 있는가? | PASS | 분리된 두 Tower의 MLP와 사용자 벡터 검색을 확인했다. 50,000개인 FAISS 인덱스에서 상품 32개를 복원해 Item Tower 출력과 비교한 최대 차이는 0이었다. [trained_models.json](trained_models.json) · [cold_candidate_training.json](../final_integration/cold_candidate_training.json) |
| 23 | 14 | Ranking 모델: DeepFM 또는 Wide&Deep으로 Feature Interaction이 학습되는가? | PASS | 학습된 DeepFM의 FM 계수 두 개가 초기값 1에서 0.04014, 0.02187로 바뀌었다. 복제한 모델에서 FM 항을 끈 로짓 차이가 수작업으로 합산한 모든 필드 쌍의 상호작용과 일치했다. [trained_models.json](trained_models.json) · [verified_mechanisms.xml](verified_mechanisms.xml) · [cold_ranking_training.json](../final_integration/cold_ranking_training.json) |
| 24 | 14 | MAB 탐색: Exploration 슬롯이 추천 결과에 포함되어 있는가? | PASS | 탐색 표시된 상품의 요청 ID로 클릭·중복 클릭·구매를 보냈다. epsilon-greedy의 해당 Redis arm에 누적 보상이 2.0→2.2→2.2→3.0으로 반영됐다. [mab_arm.json](mab_arm.json) · [sample_30.json](sample_30.json) · [mab.py](../../../../../../src/recommendation/mab.py) |
| 25 | 14 | 세션 기반 추천: 현재 세션 클릭이 추천에 실시간 반영되는가? | PASS | 동일 사용자가 추가 클릭 없이 다시 요청했을 때 일반 추천 8개의 ID·점수는 같았다. 백팩 3개를 클릭하자 다음 요청의 세션 관심이 hoodie→backpack으로 바뀌고, 일반 추천 8개 중 7개가 교체됐다. GRU를 결합한 벡터 차이도 확인했다. [cold_session.json](cold_session.json) · [trained_models.json](trained_models.json) · [browser.json](browser.json) |
| 26 | 14 | A/B 테스트: 통계적 유의성 검정(p-value, 신뢰구간)이 구현되었는가? | PASS | 무작위 배정한 군당 5,000명·30일의 사용자별 원본으로 양측 p값과 사용자 군집 95% CI를 독립 검산했다. CTR 차이 −4.3424%p [−4.5132, −4.1716], CVR 차이 −0.3397%p [−0.3701, −0.3092]로 둘 다 p<0.001이었다. [ab_statistics.json](ab_statistics.json) · [ab_acceptance_full.json](../full_ab_ct/ab_acceptance_full.json) |
| 27 | 14 | CT 파이프라인: 성능 저하 시 재학습 트리거 로직이 구현되었는가? | PASS | 기본 임계치에서 후속 반응 없는 성숙 요청 19건은 대기, 20건은 CTR·HitRate 경보와 함께 학습 진입점 호출 1회였다. 신규 이벤트는 0건이고 동일 관측 재호출은 억제됐다. 이 검사는 학습 진입점에서 멈췄다. 별도의 실제 운영 재학습은 신규 로그 10,054건으로 발동해 v1.0을 유지했다. [ct_degradation.json](ct_degradation.json) · [verified_mechanisms.xml](verified_mechanisms.xml) · [ct_full.json](../full_ab_ct/ct_full.json) |

## 재현 명령

아래 명령은 저장소 루트에서 실행한다. 실행 시점의 MAB 상태와 기기 부하에 따라 상품 ID와 측정 시간은 달라질 수 있다.

```bash
docker compose up -d
docker compose exec -T api-server python scripts/verify_peer_review.py --output /tmp/peer-recheck.json
docker compose exec -T api-server python scripts/smoke_test.py --benchmark --output /tmp/peer-audit/smoke.json
SCALE=full PYTHONPATH=. .venv/bin/python scripts/check_submission.py --verify-existing --require-ready --output-dir docs/results/experiments/A/illustrations_v1/final_integration/submission
```

관련 설정·학습·세션·CT 회귀 22개가 통과했다. 첫 격리 실행은 TestClient 단계에서 대기해 중단하고 로컬 소켓이 가능한 환경에서 다시 확인했다. 실제 모델 진단은 정렬 기본값의 기록 키, MAB 진단은 알고리즘 이름 키, CT 진단은 콜백 반환 형식을 수정한 뒤 각각 새로 수행한 결과를 사용했다. 서비스 소스와 평가 기준은 그대로 두었다. [회귀 실행 로그](verified_mechanisms.log)

A/B에서 개인화 추천의 CTR·CVR은 인기순보다 낮았다. 운영 CT 후보는 승격 기준에 미달했고, 통제 환경의 승격·롤백은 별도로 검증돼 있다. 이 두 결과는 통계 검정 구현 및 저하 트리거 구현을 묻는 26·27번과 함께 확인할 수 있다. [운영·통제 CT 구분](../full_ab_ct/ct_acceptance_full.json)
