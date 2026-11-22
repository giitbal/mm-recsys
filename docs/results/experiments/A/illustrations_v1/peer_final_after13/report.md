# 13번 수정 후 PDF 동료 평가 재검증

**27/27 통과.** 새 도안 50,000개·사용자 10,000명의 기본 Docker 배포에서 PDF 12~14쪽 질문을 다시 판정했다. 같은 체크포인트 v1.0으로 측정한 다양성 개선 후 full valid/test의 소스·모델·데이터 지문을 현재 API와 대조했다. 검색 품질·지연, 실제 API·브라우저, A/B, CT 실험은 이번 감사에서 실행했다. [원문 질문과 PDF 해시](questions.json) · [문항별 근거 해시](checklist.json) · [현재 지문](input_identity.json)

## A/B 결과

시드 42로 배정한 두 군에 각 5,000명이 속했다. 30일 동안 사용자당 매일 10개씩, 각 군에서 150만 회 노출했다. A는 학습 로그의 인기순, B는 새 정책이 적용된 전체 추천 파이프라인이다. 클릭률과 구매 전환율 모두 분모는 노출 수다. 한 사람의 반복 노출을 한 묶음으로 계산했다. 이전 실험과 사용자 배정·데이터·초기 모델이 같았고 대조군 사용자별 결과도 모두 같았다. [독립 통계 검산](ab_statistics.json) · [검증된 무손실 원자료](ab_full_archive.json)

| 합성 지표 | A | B | B−A | 차이의 95% 신뢰구간 | 상대 변화 | 양측 p |
|---|---:|---:|---:|---:|---:|---:|
| CTR | 25.0049% | 20.7599% | -4.2449%p | [-4.4036, -4.0863]%p | -16.98% | < 1×10⁻³²³ |
| CVR | 1.2253% | 0.8887% | -0.3367%p | [-0.3669, -0.3065]%p | -27.48% | 9.68e-106 |

이전 정책 실험의 인기순 대비 상대 변화는 CTR -17.37%, CVR -27.72%였다. 이번 실험의 통계 판정은 새 정책과 인기순의 차이에 대한 것이다. 이 구간으로 정책 개정 전후 차이의 유의성을 판단할 수는 없다. 실제 구매자 트래픽에서의 효과는 미측정이다. [이전 실험 검산](../peer_review_20261121/ab_statistics.json)

## CT 결과

- **운영 CT**. 기본 시뮬레이터의 로그 35,669건이 임계치 10,000건을 넘어 후보 v1.3를 학습했다. Two-Tower·DeepFM·세션 모델의 체크포인트와 해시를 재검산했다. 같은 시계열 valid에서 CTR AUC는 기존 0.965642, 후보 0.965277였고 차이는 -0.000365였다. 같은 비교에서 HitRate@50은 0.68891→0.69216, CTR logloss는 0.14400→0.14347였다. 승격에는 AUC 0.70 이상과 기존 대비 0.001 초과의 개선이 필요하다. 판정은 **기존 모델 유지**이고, 실제 API가 보고한 활성 모델은 v1.0다. [운영 판정과 양쪽 지표](ct_full.json) · [학습 가능 라벨](ct_eligibility.json)
- **새 로그 분할**. 이번 워터마크에서 들어온 로그 중 스냅샷에 포함된 건수는 35,669개였다. 시간순 분할에서 train 0, valid 0, test 35,669개였다. test 건수는 이벤트 ID 개수 차이로 계산했고 학습·승격에는 test 라벨을 사용하지 않았다. 트리거 로그 중 35,598건이 현재 API 컨테이너의 기동 전 기록이었다. 원본 데이터 전체를 80/10/10으로 다시 분할하면서 기존 이력의 학습 종료 시점도 이동했다. 이번 학습에서 새 정책에 대한 반응을 익혔다는 증거는 없다. [분할 검산](ct_folds.json) · [정책 배포 전후 로그 대조](ct_observation_window.json)
- **성능 저하 조건**. 격리된 저널과 실제 모니터에서 클릭·구매 없는 성숙 요청을 19→20건으로 늘렸다. 20건에서 경보 두 개가 발생하고 재학습 진입점을 호출했다. 19/20 경계 검사는 호출 지점에서 멈췄다. 추가로 400상품·24명·6,000행의 격리 환경에서 같은 성능 저하를 주자 세 모델을 실제로 학습·복원하고 v1.0을 유지했다. 운영 CT를 촉발한 사유는 신규 로그였다. [경계 검사](ct_degradation.json) · [성능 저하에 의한 실제 세 모델 학습](ct_degraded_retraining.json)
- **배포 후 관측**. 실제 시계로 1시간 귀속을 마친 v1.0 요청 464건의 CTR은 0.958%, 그중 Top 50 요청 160건의 HitRate는 32.500%였다. 새 정책 준비 시점 이후로 관측 기간을 제한한 모니터 판정은 ALERT (ctr_below_threshold)이고 기본 24시간 판정은 MEASURED였다. 기본 시뮬레이터와 검사 트래픽이 섞인 기록이다. [시각·분모·경보](ct_postdeployment_monitor.json)
- **승격·롤백 기능**. 별도 레지스트리에서 기준 랭커를 의도적으로 상수 출력으로 만들고, 실제 학습된 후보와 기본 승격 기준을 사용했다. 승격 후 HTTP 재로딩, 롤백 후 복귀를 확인했다. 운영 모델의 성적은 위 운영 CT 행에 기록했다. [격리 전체 생명주기 검사](ct_controlled_lifecycle_full.json)

## 동료 평가 27문항

### 기능 동작

| 번호 | PDF 질문 | 판정 | 측정·근거 |
|---:|---|---|---|
| 1 | docker-compose up 명령으로 모든 컨테이너가 정상 시작되는가? | PASS | 기본 Compose 기동 명령이 성공했고 Redis·API·대시보드·시뮬레이터가 실행 중이었다. 쇼핑몰은 별도 프로필이다. [runtime.json](runtime.json) |
| 2 | 검색 API, 추천 API, 대시보드가 각각 응답하는가? | PASS | 검색 3모드·추천 HTTP 응답, Chromium 대시보드의 검색·추천·A/B 차트와 실제 클릭 후 비교를 확인했다. [smoke.json](smoke.json) · [browser.json](browser.json) · 로컬 화면 캡처 `browser_session.png` (브라우저 실행 시 생성) |
| 3 | 신규 사용자 요청 시 적절한 폴백 결과가 반환되는가? | PASS | 신규 사용자 일반 추천 8개의 점수가 학습 로그로 다시 계산한 인기·최근 상승 점수와 일치했다. [cold_session.json](cold_session.json) |
| 4 | 추천 결과에 MAB Exploration 슬롯(is_exploration=true)이 포함되어 있는가? | PASS | 서로 다른 30명의 Top 10 모두 is_exploration=true인 상품이 2개였다. [sample_30.json](sample_30.json) · [measurement.json](measurement.json) |
| 5 | 검색 API 응답 시간이 200ms 이내인가? | PASS | PDF 10쪽의 10회 워밍업·100회 직렬 기준으로 HTTP p95는 텍스트 48.05, 이미지 122.07, 복합 135.91ms였다. 검색 요청 총 300건 중 200ms 초과 1건, 전체 최대 226.19ms였다. [measurement.json](measurement.json) · [smoke.json](smoke.json) |
| 6 | 추천 API 응답 시간이 200ms 이내인가? | PASS | 추천 HTTP 왕복 p95 59.54ms, 100회 중 최대 85.36ms였다. [measurement.json](measurement.json) · [smoke.json](smoke.json) |
| 7 | 리포트에 데이터 분할 방식(train/valid/test 비율)이 명시되어 있는가? | PASS | 제출 보고서에 시간순 80/10/10이 명시됐다. 실제 80만·10만·10만 행, 파일 해시, 정렬과 시간 경계의 비중첩을 재검산했다. [report.md](../../../../../submission/report.md) · [measurement.json](measurement.json) |
| 8 | 검색 성능: MRR ≥ 0.55, NDCG@10 ≥ 0.50 달성 여부가 수치로 보고되었는가? | PASS | 모드별 200개, 총 600개의 동결 test 질의에서 MRR 0.93572와 nDCG@10 0.93063를 재측정했다. [cold_search_test.json](search/cold_search_test.json) · [cold_search_freeze.json](search/cold_search_freeze.json) |
| 9 | 추천 성능: Recall@300 ≥ 0.30, HitRate@50 ≥ 0.20, NDCG@50 ≥ 0.08 달성 여부가 보고되었는가? | PASS | 현재 배포와 동결 지문이 일치한 13번 수정 후 full test에서 Recall@300 0.74579, HitRate@50 0.66443, nDCG@50 0.32928였다. 미래 정답이 있는 사용자는 7,012명이다. [full_test.json](../peer13_all_levels/full_test.json) · [input_identity.json](input_identity.json) · [measurement.json](measurement.json) |
| 10 | Ranking 모델: AUC ≥ 0.70 달성 여부가 보고되었는가? | PASS | 사전 확정한 CTR AUC 기준에서 0.96578였다. 별도로 계산한 CVR AUC는 0.53041였다. [full_test.json](../peer13_all_levels/full_test.json) · [contracts.md](../../../../../contracts.md) |
| 11 | Coverage ≥ 0.20 달성 여부가 보고되었는가? | PASS | 전체 사용자 1만 명의 Top 50에 등장한 고유 상품 19,158개 / 전체 50,000개 = 0.38316. [full_test.json](../peer13_all_levels/full_test.json) · [measurement.json](measurement.json) |
| 12 | Feature Store 피처 조회 시간이 10ms 이내인지 확인되었는가? | PASS | 배포 Redis의 프로필·이력 조회 100회 모두 적중했고 p95는 0.436ms였다. [smoke.json](smoke.json) · [measurement.json](measurement.json) |
| 13 | 동일 카테고리 상품이 연속 3개 이상 노출되지 않는가? (샘플 3건 이상 확인) | PASS | 실제 Top 10 표본 30명에서 대·중·소분류 모두 위반 0명. 동결 test 1만 명의 Top 50에서도 위반과 수량 부족이 각각 0건이었다. [measurement.json](measurement.json) · [native_peer.json](native_peer.json) · [full_test.json](../peer13_all_levels/full_test.json) · [report.md](../peer13_all_levels/report.md) |
| 14 | 신규 상품(등록 7일 이내)이 추천 결과에 포함되는가? | PASS | 실제 30명 전원과 test 1만 명 전원에게 각 기준일 당시 등록 7일 이내 상품이 포함됐다. [sample_30.json](sample_30.json) · [measurement.json](measurement.json) · [full_test.json](../peer13_all_levels/full_test.json) |

### 코드 구조·설계·문서

| 번호 | PDF 질문 | 판정 | 측정·근거 |
|---:|---|---|---|
| 15 | 전체 코드를 수정하지 않고, config나 전략 패턴으로 로직을 교체할 수 있는가? | PASS | 같은 모델·사용자에서 YAML의 scoring.strategy만 바꾸자 결과가 바뀌었다. 최신순 Top 10 모두 실제 최종 등록일 상품이었다. [strategies.json](strategies.json) |
| 16 | config 파일 수정만으로 시뮬레이터가 변경된 설정을 반영하는가? | PASS | 시뮬레이터 정식 CLI를 임시 YAML 두 개로 실행했다. 각 450개 상품·120명에서 trendsetter가 18→30명, 새 카테고리 상품이 0→11개가 됐다. [simulator_yaml.json](simulator_yaml.json) |
| 17 | 역할 분리: simulator, search, recommendation, serving 모듈이 폴더로 분리되어 있는가? | PASS | 시뮬레이터·검색·추천·서빙 모듈의 독립 패키지와 진입점을 확인했다. [generate.py](../../../../../../src/simulator/generate.py) · [service.py](../../../../../../src/search/service.py) · [service.py](../../../../../../src/recommendation/service.py) · [main.py](../../../../../../src/serving/main.py) |
| 18 | 문서화: README.md에 실행 방법과 아키텍처가 설명되어 있는가? | PASS | README에 아키텍처 흐름도, 기본 실행 명령과 접속 주소가 있다. [README.md](../../../../../../README.md) |
| 19 | README 또는 기획서에 팀원별 역할 분담이 명시되어 있는가? | PASS | README 역할 표와 기여 목록에 팀원 3명의 이름·담당 영역이 있다. [README.md](../../../../../../README.md) · [contributions.json](../../../../../submission/contributions.json) |
| 20 | 개인별 주요 기여 영역(구현 모듈, 문서 작성 등)이 요약되어 있는가? | PASS | A·B·C별 구현 모듈, 문서, 연결된 PR 목록과 개별 기여 문서를 확인했다. [contributions.json](../../../../../submission/contributions.json) · [A.md](../../../../../contributions/A.md) · [B.md](../../../../../contributions/B.md) · [C.md](../../../../../contributions/C.md) |

### 핵심 기술

| 번호 | PDF 질문 | 판정 | 측정·근거 |
|---:|---|---|---|
| 21 | 멀티모달 임베딩: CLIP으로 텍스트/이미지가 동일 벡터로 변환되어 검색에 사용되는가? | PASS | 8개 상품의 두 모달리티를 재인코딩했다. 512차원 공통 공간의 저장 벡터와 일치했다. 후드티 텍스트·갈색 가방 이미지·가방 복합 검색은 각 Top 10 모두 요청 속성에 맞았다. [clip.json](clip.json) · [semantic_examples.json](semantic_examples.json) |
| 22 | Two-Tower 구조: User/Item Tower가 분리되고, Item 임베딩이 FAISS에 저장되어 있는가? | PASS | Two-Tower의 분리된 인코더와 5만 상품 FAISS를 확인했다. 표본 32개의 실제 Item Tower 출력과 인덱스 복원 벡터 최대 절대 차이는 0이었다. [trained_models.json](trained_models.json) |
| 23 | Ranking 모델: DeepFM 또는 Wide&Deep으로 Feature Interaction이 학습되는가? | PASS | DeepFM의 학습된 FM 계수와 해당 항을 비활성화한 로짓 차이를 관측했다. 모든 필드 쌍의 상호작용을 손으로 합산한 값과 일치했다. [trained_models.json](trained_models.json) |
| 24 | MAB 탐색: Exploration 슬롯이 추천 결과에 포함되어 있는가? | PASS | 실제 탐색 상품의 request ID로 피드백을 보냈다. Redis 보상이 클릭·중복 클릭·구매 순으로 4.0→4.2→4.2→5.0로 바뀌었다. [mab_arm.json](mab_arm.json) · [sample_30.json](sample_30.json) |
| 25 | 세션 기반 추천: 현재 세션 클릭이 추천에 실시간 반영되는가? | PASS | 추가 클릭 없는 재요청에서 일반 추천 ID·점수는 같았다. 백팩 3회 클릭 후 관심이 hoodie→backpack으로 바뀌고 일반 추천 8개 중 7개가 교체됐다. [cold_session.json](cold_session.json) · [browser.json](browser.json) · [trained_models.json](trained_models.json) |
| 26 | A/B 테스트: 통계적 유의성 검정(p-value, 신뢰구간)이 구현되었는가? | PASS | 인기순 대조군과 새 추천 정책군을 각각 5,000명씩 30일간 시뮬레이션했다. 1만 명의 사용자별 원자료에서 양측 p값과 사용자 군집 95% 신뢰구간을 독립 검산했다. [ab_statistics.json](ab_statistics.json) · [ab_acceptance_full.json](ab_acceptance_full.json) · [ab_full_archive.json](ab_full_archive.json) |
| 27 | CT 파이프라인: 성능 저하 시 재학습 트리거 로직이 구현되었는가? | PASS | 성숙한 Top 50 요청 19건에서 대기했다. 20건째 실제 CTR·HitRate 경보가 발동했고 신규 로그가 0건인 상태에서 재학습 진입점을 1회 호출했다. 같은 상태의 재호출은 억제됐다. 별도 400상품 시험에서 성능 저하만으로 실제 세 모델의 학습·체크포인트 복원·버전 판정까지 완료했다. [ct_degradation.json](ct_degradation.json) · [ct_degraded_retraining.json](ct_degraded_retraining.json) · [ct_full.json](ct_full.json) · [ct_candidate_training_full.json](ct_candidate_training_full.json) · [ct_ranking_training_full.json](ct_ranking_training_full.json) · [ct_session_training_full.json](ct_session_training_full.json) |

## 적용 범위와 남은 차이

1. **제출용 최종 통합 기록은 이전 버전이다.** 변경 전 제출 검사에는 현재 작업본과 다른 입력 해시가 5개 있었다. 기존 검사 명령이 처음 감지한 차이는 `dashboard/app.py`였다. 제출본을 현행화하려면 새 정책의 품질·A/B·CT 근거로 제출용 통합 검사와 대시보드 게시물을 다시 생성·검증해야 한다. 기존 제출 기록을 현재 릴리스의 PASS로 인용하면 두 버전을 혼동하게 된다. A/B 제출 문서 맨 위에는 이전 실험 수치가 있다. [기존 A/B 제출 보고서](../../../../../ab_test_report.md) [해시 차이](measurement.json) · [제출 검사 위치](../../../../../../scripts/check_submission.py) · [대시보드 정책 표시](../peer13_all_levels/dashboard.json)
2. **측정 조건**. 기본 배포 한 세트와 선택 쇼핑몰이 켜진 상태에서 워밍업 10회 뒤 100개 직렬 요청을 측정했다. 운영 CT가 동시에 실행됐다. PDF 10쪽은 p95 기준을 제시한다. 실제로 복합 검색 1회가 200ms를 넘었다. 이번 측정 범위는 기본 시뮬레이션·로컬 HTTP이며 다중 동시 사용자 부하는 별도다. [실행 환경](runtime.json) · [원시 시간](smoke.json)
3. **근거의 시점**. 검색 성능은 이번에 valid·test를 실행했다. 추천 성능과 538개 전체 테스트는 13번 수정 직후의 실행을 사용했다. 추천에는 현재 컨테이너의 전체 동결 지문과 모델 SHA를 다시 대조했고, 실제 API의 30명 다양성은 이번에도 새로 요청했다. [현행 지문과 대조](input_identity.json) · [동결 추천 결과](../peer13_all_levels/full_test.json) · [전체 테스트](../peer13_all_levels/pytest.xml)

## 재확인 명령

기본 Compose가 실행 중인 저장소 루트에서 아래 명령으로 실제 API의 동료 평가, 운영 모델 상태, 동일 규모 A/B를 확인할 수 있다. A/B 예시는 별도 결과 경로를 쓰며 기본 운영 CT와 순서대로 실행된다.

```bash
docker compose exec -T api-server python scripts/verify_peer_review.py --output /tmp/peer-audit.json
curl -fsS http://localhost:8000/health
docker compose run --rm --no-deps --pull never -e RUNTIME_RESULTS_DIR=docs/results/docker/peer-repeat -T api-server demo ab --users-per-group 5000 --days 30
```
