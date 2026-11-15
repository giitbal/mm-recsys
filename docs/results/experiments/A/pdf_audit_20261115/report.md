**PDF 전 범위 검증 보고서 — 2026-11-15**

이 저장소는 합성 쇼핑 행동을 생성하고, CLIP 검색과 Two-Tower → DeepFM → 재정렬 추천을 API·Redis·대시보드로 제공한다. PDF 14쪽 전체와 동료 평가 예제를 기준으로, 단일 요청·CPU·full 규모에서 검증했다.

**종합 판정: 모든 요구사항을 완벽히 충족한다고 판정할 수 없다.** 기존 full-v44의 핵심 기능·품질은 현재 코드로 재검증했으나, 최근 외부 데이터 교정 레시피는 기본 서비스에 반영되지 않았다. 제출 근거의 해시 불일치와 타입 힌트 누락도 실제 확인했다. PDF의 합성 시스템 요구와 사용자의 “교정 결과가 반영된 환경” 조건을 분리한다.

감사 HEAD: `70de88958340037b50b702f1f314d08e2e283e13`. 원본 PDF의 페이지 수·SHA는 [pdf_source.json](pdf_source.json), 실행 대상/전체 소스 해시는 [scope.json](scope.json)에 있다. 원본 소스·운영 config·기존 결과를 수정하거나 실험 모델을 승격하지 않았다.

**새로 실행한 검증**

- 전체 회귀: **519 passed**, 실제 격리 Redis 포함. 타입 검사: **157개 파일 PASS**. 의존성 검사 PASS. mypy 통과는 모든 함수의 annotation 완성을 뜻하지 않는다.
- 현재 소스로 Docker 이미지 빌드, 표준 준비 단계, API/Redis/대시보드/실시간 시뮬레이터 기동. 포트 18000/18501/16379, 모델·로그·Redis 쓰기는 감사용으로 격리했다.
- 상품 **50,000**, 고객 **10,000**, 이벤트 **1,000,000**, 노출 **2,254,172**. 시간순 train/valid/test **800,000/100,000/100,000**. 여섯 페르소나와 참조 무결성 PASS.
- 빈 경로에서 seed42로 full 데이터를 재생성해 8개 데이터/분할/이미지 manifest 파일 해시와 생성 fingerprint가 일치했다. 기존 full 모델은 무결성 확인 후 재사용했으며, 이번에 전체 모델을 처음부터 다시 학습한 것은 아니다.
- 실제 HTTP 동료 평가 14항목 PASS. 한국어 후드티·가방 이미지·가방 hybrid 예제는 각각 top10의 10개 모두 카탈로그 속성과 일치. 실제 Redis MAB 클릭/구매 보상·중복·세션 검증 PASS.
- Chromium 대시보드: **PASS**, 6탭·차트·검색·추천·클릭 전후 응답 확인. 스크린샷과 요청 오류는 [browser.json](browser.json)에 기록했다.
- CT: 자동 작업자의 60초 반복 모니터와 10,000건 임계치 대기 확인. 별도 실제 학습 drill은 400상품/24사용자/6,000이벤트, 임계치200으로 저하 알림·세 모델 학습·승격·유지·reload·롤백·손상 거부·중복 소비 방지 12항목 PASS. 초기 랭커를 의도적으로 약화한 fixture이며 운영 성능 개선 증거가 아니다.
- 외부 realism-v4: 원본 입력·12개 생성 세트·6개 학습 조건·모델/소스/이미지 해시와 기존 결과167개 보존 재검증 PASS. 기존 실험 결과를 재학습한 것은 아니다.

**현재 코드의 full test 수치**

valid를 먼저 실행해 변경 없는 설정/모델/소스를 동결한 뒤 test를 실행했다. 아래는 기존 full-v44에 대한 새 측정이며 교정된 realism-v4의 full 평가가 아니다. test에 맞춰 답·K·평가 코호트를 바꾸지 않았다.

| 지표 | 새 측정값 | 기준 | 판정 |
|---|---:|---:|---|
| mrr | 0.925000 | 0.55 | PASS |
| ndcg_at_10 | 0.925000 | 0.5 | PASS |
| recall_at_300 | 0.745793 | 0.3 | PASS |
| auc | 0.965785 | 0.7 | PASS |
| hit_rate_at_50 | 0.665145 | 0.2 | PASS |
| ndcg_at_50 | 0.329914 | 0.08 | PASS |
| coverage | 0.374480 | 0.2 | PASS |
| search_p95_ms | 111.330475 | 200 | PASS |
| recommend_p95_ms | 22.319504 | 200 | PASS |
| candidate_p95_ms | 3.276589 | 100 | PASS |
| feature_p95_ms | 0.437049 | 10 | PASS |

별도 CVR AUC는 0.530408이다. AUC≥0.70은 사용자 확인된 계약에 따라 CTR에 적용하며, CVR 예측이 강하다는 뜻은 아니다. 후보 최소 개수는 300개다.

지연은 warmup10회 후 순차100회, 동시성1, CPU로 측정했다. 텍스트/이미지/hybrid HTTP p95는 각각 24.107/80.648/111.330ms다. API 컨테이너는 4CPU/4GiB 제한, API 추론 Torch/FAISS 각2 threads, OMP/MKL/OpenBLAS=2다. 별도 후보 벤치는4 threads로 측정했고 환경은 원본 JSON에 있다. 다른 프로젝트 스택과 시뮬레이터의 생성 부하를 멈춘 조건이다. Docker 엔진은8CPU·약11.66GiB로 PDF의 RAM16GB 최소 사양과 동일한 환경은 아니다. CPU ±50ms 허용을 사용하지 않고 원래 한도로 판정했다.

[test 원본](quality/quality_full_test.json) · [valid 원본](quality/quality_full_valid.json) · [HTTP 원시 표본](quality/smoke_full.json). fixed-origin 품질 평가의 메모리 저장소와 실제 Redis HTTP 검증은 서로 다른 측정이다.

**A/B 결과와 해석**

기존 full 모델과 50,000개 상품에서 popularity 대 full_pipeline, seed42, 500명/군×7일로 새 합성 실험을 했다. PDF의 5,000명/30일/+28% 예시는 필수 합격 숫자가 아니다. 사용자 단위 Z/Chi-square와 반복 노출을 고려한 95% CI를 재검산했다.

| 지표 | 인기순 | 전체 추천 | 상대 변화 | 차이 95% CI | p-value |
|---|---:|---:|---:|---|---:|
| CTR | 24.9743% | 20.7771% | -16.81% | [-4.9571, -3.4372]%p | 2.62096e-27 |
| CVR | 1.2229% | 0.9371% | -23.36% | [-0.4457, -0.1257]%p | 0.000464397 |

A/B 기능은 정상이다. 이 조건에서는 추천 우위를 입증하지 못했고 두 지표 모두 인기순보다 낮았다. 가상의 반응 함수에 대한 결과이며 실제 고객 CTR/CVR로 해석하지 않는다. 자연 CT 모니터는 귀속기간1시간이 지난 표본이 없어 UNMEASURED이며, 운영 모델 승격/개선은 주장하지 않는다.

**필수 조치 — 완전 충족/이번 결과 반영을 주장하기 전**

1. **교정 레시피와 full 서비스가 연결되지 않았다.** [config.yaml:14](../../../../../config.yaml#L14), [generate.py:32](../../../../../src/simulator/generate.py#L32). `SCALE=full`의 데이터/모델은 `full-v44`, realism은 비활성이다. 교정 실험은3,000/1,000/100,000이며 GRU session 파일3개와 검색 serving bundle이 없다([scope.json](scope.json)). 최소 조치는 별도 버전의 full 설정·데이터와 검색/후보/랭킹/세션 번들을 만들고 valid 동결→test→HTTP/CT/A/B를 검증한 후 연결하는 것이다. 미조치 시 이번 full PASS를 교정 결과의 운영 검증으로 사용할 수 없다. 이는 PDF의 외부 데이터 사용 자체 미이행과는 다르다.

2. **제출 문서의 근거 해시가 실제 파일과 다르다.** [requirements.json:237](../../../../submission/requirements.json#L237), [requirements.md:22](../../../../submission/requirements.md#L22). 실제 `files_check`가 `evidence changed or missing: docs/submission/dataset_scope.json`으로 실패했다([submission_files.json](submission_files.json)). acquisition_performed는 true인데 표는 여전히 미획득이고, 기록 SHA는 a767f33f…, 실제는116b7fd0…이다. 최소 조치는 최신 사용 범위와 측정 근거로 제출표/해시를 다시 생성하고 제출 검사·최종 집계를 재검증하는 것이다. 숫자만 PASS로 바꿔서는 안 된다.

3. **새 외부 데이터 주요 함수에 타입 힌트가 없다.** [expansion_retail.py:13](../../../../../src/external_data/expansion_retail.py#L13), 같은 파일 fit/predict/score/run 등. AST 검사에서11개 파일의 공개 함수46개에 인자 또는 반환 annotation 누락을 확인했다([python_audit.json](python_audit.json)). PDF p.9의 요구에 맞게 실제 입력/반환 타입을 명시하고 해당 코드 검사 범위를 강화하면 된다. 현재 mypy 설정은 annotation 없는 함수 전체를 검증하지 않으므로 PASS만으로 이 요구를 충족하지 않는다.

4. **외부 데이터 입력 보고서 경로가 코드에 고정돼 있다.** [realism_data.py:36](../../../../../src/external_data/realism_data.py#L36)은 H&M/Retailrocket의 이전 보고서를 docs/results/external/v1 아래에서 직접 읽는다. source_work/work_dir/results_dir을 설정해도 그 경로는 바뀌지 않는다. 입력 보고서를 다른 경로에 두고 기존 경로를 없앤 별도 작업 경로에서 FileNotFoundError를 재현했다([hardcoded_report_paths.json](hardcoded_report_paths.json)). 현재 원래 경로에서는 동작하나 PDF p.9의 파일 경로 설정 분리는 미완료다. 두 입력 보고서 경로를 설정으로 옮기는 것이 최소 수정이다. 기존 실험 동결값은 보존하고 변경 버전에서 검증해야 한다.

5. **공개 제출 저장소 main에 이번 로컬 결과가 없다.** [README.md:62](../../../../../README.md#L62)의 저장소는 공개 접근 가능하나 원격 main은 b159ee27…, 로컬은70de8895…이다. 그 사이 실제 데이터 활용 커밋4개가 있다([github.json](github.json)). 검증과 수정이 끝난 변경을 설명하고 프로젝트의 사용자 승인 절차로 push/PR해야 평가자가 같은 결과를 재현할 수 있다. 이번 감사에는 push/PR/병합을 수행하지 않았다. 제출 사이트의 URL 등록 여부도 로컬에서 확인할 수 없다.

**권장 조치**

6. **Docker 기본 설정으로 MAB 검증 스크립트가 잘못된 Redis 영역을 읽는다.** [verify_integration_mab.py:21](../../../../../scripts/verify_integration_mab.py#L21)은 load_config만 사용하지만 [runtime.py:31](../../../../../docker/runtime.py#L31)은 데이터 경로를 포함한 namespace를 추가한다. 실제 기본 호출은 KeyError: P000423으로 실패했고([mab.txt](mab.txt)), CONFIG_PATH=models/full-v44/.docker/config.yaml 지정 시 모든 검증이 통과했다([mab_runtime_config.json](mab_runtime_config.json)). 서비스 보상 로직의 실패가 아니다. 도구가 실제 runtime_config를 사용하게 하거나 명시 설정을 필수화하는 작은 수정이 필요하다.

**선택 개선**

7. **추천 전략의 우위는 별도 개선 과제다.** [ab_test.json](ab_test.json)의 합성 A/B에서 전체 추천 CTR/CVR은 인기순보다 낮다. realism-v4의 후보 Recall은 좋아졌지만 DeepFM NDCG는 악화한 기존 결과도 유지된다. 고정된 반응 모델과 valid 구간에서 후보·랭킹·재정렬·탐색을 나눠 비교하고, 선택 후 별도 평가로 확인하는 접근이 적절하다. PDF는 양의 A/B lift를 합격 조건으로 정하지 않으므로 이를 필수 기능 실패로 세지 않았다.

**페이지별 요구사항 대조**

PASS는 해당 행의 범위만 의미한다. VERIFIED_EXISTING은 기존 결과 확인, PARTIAL은 일부 미완료, OPTIONAL은 선택 항목이다. 상세 기계 판독표는 [requirements_matrix.json](requirements_matrix.json)에 있다.

| PDF 쪽 | 요구사항 | 판정 | 근거·범위 |
|---|---|---|---|
| 1–2 | 검색·추천·평가·시뮬레이터의 단일 시스템 | PASS | quality/smoke_full.json; browser.json; auto_ct_simulator.txt — 기존 full-v44 데이터/모델, 현재 코드, 격리 Compose |
| 1,6,9 | GitHub URL와 평가자 접근 | PARTIAL | github.json — 공개 접근 PASS. main에는 이번 데이터 활용 4개 커밋 미반영. 제출 사이트의 URL 제출 여부는 미검증 |
| 2 | 검색 POST, 세 가지 입력, 기본 top10, 필수 응답 필드 | PASS | quality/smoke_full.json; semantic_examples.json — JSON·multipart·422 검사 포함 |
| 2 | 추천 GET, 기본 top10, reason·탐색·단계별 시간·세션 필드 | PASS | quality/smoke_full.json; peer_review.json; pytest.xml — 실제 HTTP + 기본값 단위 검사 |
| 2,5 | 독립 API/대시보드/Redis/시뮬레이터 Compose 실행 | PASS | quality/preparation_full.json; docker_final_state.json; auto_ct_simulator.txt — 포트와 쓰기 경로 격리. 현재 소스로 이미지 새 빌드; 기존 모델 재사용 |
| 2,5 | 검색·추천·A/B 지표와 차트 | PASS | browser.json; browser_tab_1.png; browser_tab_2.png; browser_tab_3.png — 실제 Chromium 렌더링; HTTP health만으로 판정하지 않음 |
| 3 | 50,000개 상품과 텍스트·이미지·3단계 카테고리 | PASS | data_audit.json; data_reproduction.json — 실제 상품 50,000개, 이미지 생성 및 manifest 검증 |
| 3 | 10,000명 고객과 여섯 페르소나 | PASS | data_audit.json — 카테고리 선호·가격 민감도·전환 차이 및 브랜드 충성 검증 |
| 3 | 1,000,000개 search/view/cart/purchase 이벤트 | PASS | data_audit.json — 중복·참조·시간분할 검사. 노출 2,254,172개 별도 |
| 3,13 | 페르소나 비율·전이·카테고리의 config 변경 반영 | PASS | pytest.xml; data_audit.json — 실제 생성 함수로 설정 변경 테스트. full-v44 동일 seed 재생성도 일치 |
| 3,6 | seed42 및 시간순 80/10/10 재현성 | PASS | data_reproduction.json; data_audit.json — 빈 경로에서 현재 소스로 full 데이터 재생성. 모델 전체 재학습은 이번 범위 아님 |
| 3–4,14 | 실제 CLIP 텍스트/이미지 임베딩과 FAISS HNSW | PASS | quality/quality_full_test.json; quality/preparation_full.json; semantic_examples.json — 기존 full CLIP/인덱스 무결성 검사 후 실제 추론. mock encoder 측정 아님 |
| 4 | 검색 MRR≥0.55와 NDCG@10≥0.50 | PASS | quality/quality_full_test.json — 현재 코드의 test 재측정; valid 먼저 동결, test로 선택하지 않음 |
| 4,10 | 검색 p95≤200ms | PASS | quality/smoke_full.json — 모드별 warmup10 + 순차100; CPU 오차 완화 없이 원래 기준 적용 |
| 4,14 | Two-Tower 사용자 이력/프로필·상품 속성/가격·offline FAISS | PASS | quality/quality_full_test.json; pytest.xml — 모델/특징/인덱스 로딩 및 미래 정보 차단 테스트 |
| 4 | 후보 300개 이상·100ms 이내·Recall@300≥0.30 | PASS | quality/quality_full_test.json; quality/smoke_full.json — full catalog macro-user Recall; 정답·K·사용자 집합 변경 없음 |
| 4,14 | DeepFM CTR/CVR와 user/item/cross/context 특징 | PASS | quality/quality_full_test.json; pytest.xml — 기존 full 학습 모델로 재평가; CVR을 별도 보고 |
| 4 | Ranking AUC≥0.70 | PASS | quality/quality_full_test.json — docs/contracts.md의 사용자 확인에 따라 CTR AUC에 적용 |
| 4,13 | 동일 카테고리 3연속 방지·샘플 3사용자 이상 | PASS | peer_review.json; quality/quality_full_test.json — 실제 3사용자 top10 및 offline 전체 평가 top50 제약 검사 |
| 4,12 | 이력 5개 미만 인기+트렌딩 폴백 | PASS | peer_review.json — 이력 0개·4개 실제 API 검증 |
| 4,13–14 | MAB 1–2슬롯·신상품 7일 노출 | PASS | peer_review.json; mab_runtime_config.json — 슬롯과 신상품 검사 + 실제 Redis 보상 귀속/최대 보상/중복 방지 |
| 4–5,14 | GRU와 장기 선호 결합·실시간 클릭 반영 | PASS | peer_review.json; mab_runtime_config.json; browser.json; pytest.xml — GRU 모델 실제 로딩; Redis·API·브라우저 클릭 전후 응답 검사 |
| 5 | HitRate@50≥0.20·NDCG@50≥0.08·Coverage≥0.20 | PASS | quality/quality_full_test.json — fixed-origin full test. 실데이터 H&M 수치와 혼합하지 않음 |
| 5,10 | 추천 API p95≤200ms | PASS | quality/smoke_full.json — 기본 top10 HTTP; 품질 평가는 top50 |
| 5 | Redis 최근 조회·클릭 수 및 p95≤10ms | PASS | peer_review.json; mab_runtime_config.json; quality/smoke_full.json — 실제 별도 Redis 클라이언트 관측 |
| 5,14 | 두 전략 A/B 시뮬레이션 | PASS | ab_test.json; ab_verification.json — popularity/full_pipeline, 500명/군×7일, 기존 full 데이터/모델. 실제 서비스 온라인 실험 아님 |
| 5,14 | Chi-square/Z-test·p-value·95% CI | PASS | ab_verification.json; browser.json — 사용자 단위 군 배정과 반복 노출의 군집 분산 재계산; 양의 lift는 필수 요건 아님 |
| 5,12,14 | CT 주기적 HitRate/CTR 모니터와 저하 알림 | PASS | auto_ct_simulator.txt; ct_natural.jsonl; ct_drill.json — 60초 반복 실행 확인. 자연 관측은 성숙 표본 0; 임계치 알림은 통제된 fixture에서 실측 |
| 5,12,14 | 누적 로그 CT 트리거·학습·모델 버전 관리 | PASS | auto_ct_simulator.txt; ct_drill.json; pytest.xml — 실제 기본 임계치 10,000; drill 임계치200. 학습/승격/유지/reload/롤백 검증. 자연 운영 모델 개선은 미측정 |
| 5–6,9,13 | README 개요·아키텍처·실행, 실험 리포트 | PARTIAL | submission_files.json; ../../../../submission/requirements.md — 필수 문서 존재. 외부 데이터 범위의 기록 해시 불일치로 제출 검사 FAIL |
| 6 | Two-Tower random negative 1:4, Ranking 노출 비클릭 | PASS | pytest.xml; quality/quality_full_test.json — train-only sampling/label 및 cutoff 테스트, 기존 모델 metadata 확인. H&M 구매 proxy와 구분 |
| 6 | BM25·Two-Tower-only·인기순 baseline | PASS | quality/quality_full_test.json — 동일 정답·사용자·카탈로그에서 비교, 개선/악화 수치 모두 보존 |
| 6 | metrics.py 및 검색K10/추천K50, 정의·설정·개선율 보고 | PASS | quality/quality_full_test.json; ../../../../contracts.md; ../../../../submission/report.md — 정의/계산식/seed42/분할/비교 근거 존재 |
| 6–7 | 속성 자동 추출·MMR·ONNX·Thompson Sampling | OPTIONAL | ../../../../../config/recommend.yaml; ../../../../../src/search/text.py — 보너스. 전체 구현 완료를 주장하지 않으며 필수 실패로 계산하지 않음 |
| 7–8 | H&M: 다단계 추천 검증과 교정 | VERIFIED_EXISTING | ../../../external/expansion-v3/report.md; realism_verification.json — 10만 고객 학습·105,542개 상품 평가와 12개 교정 실험 존재. 이번에는 v4 입력/모델/데이터 해시 재검증; 전부 재학습하지 않음 |
| 7–8 | Retailrocket: Markov 전이 확률 추정 | VERIFIED_EXISTING | ../../../external/expansion-v3/retail_conditional.json; realism_verification.json — 전역/조건부 추정과 train/valid 선택 근거 존재. 조건부 프로필의 생성기 적용은 v4 valid에서 기각된 결과를 보존 |
| 7–8 | DeepFashion: CLIP 품질 검증 | VERIFIED_EXISTING | ../../../external/expansion-v3/deepfashion_expanded.json — 공식 분할 gallery10k·valid/test각5k, 카테고리/속성 평가. 이번에 CLIP 전체 재인코딩하지 않음 |
| 8–9 | Python/PyTorch/FastAPI/Streamlit/FAISS/transformers/redis-py/Compose | PASS | quality/smoke_full.json; pip_check.txt; browser.json — CPU에서 실제 실행. GPU 필수 아님 |
| 9 | 외부 클라우드 추론 API 없이 로컬 서비스 | PASS | scope.json; quality/smoke_full.json — 현재 캐시된 CLIP을 로컬 실행. 초기 의존성/모델 다운로드와 감사 중 공개 GitHub 조회는 별개 |
| 9 | 인증은 ID, 결제·배송·재고·Kafka는 범위 밖 | PASS | ../../../../../src/serving/main.py; pytest.xml — 요구 범위에 맞는 API/모듈 경계 |
| 9 | 하이퍼파라미터·경로 config 분리 | PARTIAL | hardcoded_report_paths.json; scope.json; pytest.xml — 주요 운영 설정은 분리. realism_data.py의 과거 입력 보고서 경로2개는 고정값이며 이전 경로를 없애면 재현 오류 |
| 9 | 주요 함수 타입 힌트 | FAIL | python_audit.json; mypy.txt — 외부 데이터 11개 파일의 공개 함수46개에서 인자/반환 일부 누락. mypy 기본 설정 PASS와 별개 |
| 9–10 | CPU 및 측정 하드웨어 조건 보고 | MEASURED | quality/smoke_full.json; docker_environment.json — Docker8CPU, 약11.66GiB 메모리, API4CPU/4GiB 제한. PDF 최소 RAM16GB 환경과 완전히 같지는 않음 |
| 10–12 | PDF 검색/추천/CT/A/B 예시의 실제 동작 | PASS | semantic_examples.json; peer_review.json; ct_drill.json; ab_test.json — 예시의 ID/문구/시간/+28%/p=.003 값 자체를 정답으로 요구하지 않음 |
| 13 | similarity→newest 전략 설정 변경 | PASS | pytest.xml — test_checklist_fixes에서 API·등록 모델 restart/reload·newest 후보 순서·cold fallback 검증; 이번 full Docker 정책 자체는 변경하지 않음 |
| 13–14 | 모듈 역할 분리·팀원 기여도 문서 | PASS | ../../../../submission/contributions.json; ../../../../../README.md — A/B/C 담당과 PR 문서 확인. 팀원의 설명 능력/최신 PR 상태 전체 재심사는 범위 밖 |
| 사용자 추가 조건 | 외부 데이터 교정 결과를 full 로컬 서비스에 반영 | NOT_INTEGRATED | scope.json; deployment.json; realism_verification.json — 기본 full-v44는 realism 비활성. v4는 3k/1k/100k 별도 실험이며 session·search serving bundle 없음 |
| 사용자 추가 목표 | 실제 사용자 추천 우위·운영 CT 개선 | UNMEASURED | ab_test.json; ct_natural.jsonl; ../../../external/realism-v4/report.md — 실데이터 offline 진단/분포 교정과 실제 서비스 성과는 별개. 이번 합성 A/B는 음의 효과 |

**검증의 한계와 원본 보존**

- 14쪽의 기능·수치·제약·예제·동료 평가를 대조했다. 학습자의 설명 능력, 법적 라이선스 전체 해석, 평가 사이트의 URL 제출은 코드 실행만으로 판정하지 않았다. GPU/Windows·다중 사용자 부하·장기 운영·빈 모델 캐시에서의 full 전체 재학습은 이번에 실행하지 않았다.
- 기존 full 모델을 현재 코드로 다시 평가한 결과다. 교정된 full 데이터의 CLIP/ANN/GRU 통합·품질·운영 승격은 UNMEASURED다. 외부 데이터 전체 재학습/재인코딩도 하지 않았다. 과거 독립 전체 재학습 기록은 과거 근거로 유지한다.
- 감사용 A/B는 계산·통계 검증을 완료한 뒤 컨테이너 소유 결과 폴더 복사에서 권한 오류가 났다. 계산을 반복하거나 숫자를 바꾸지 않고 해당 컨테이너에서 검증 완료 파일을 복사해 대시보드에 연결했다(ab_test.txt, ab_dashboard_copy.txt). 초기 mypy 인자는 모듈 경로 중복으로 실패했고 --explicit-package-bases로 올바르게 실행했다. 이러한 감사 실행상의 오류를 제품 결함으로 합산하지 않았다.
- 원본 config/Compose/final_acceptance와 운영 모델 registry 보존은 preservation.json으로 확인한다. 기존 data/.gitkeep 삭제와 미추적 Docker 결과도 보존했다. 최종 PASS 문서나 gate를 덮어쓰지 않았고 새 보고서/검증 근거만 별도 경로에 추가했다.
- 이 검증은 캐시를 사용하는 표준 기동 + 읽기 전용 원본 데이터 + 감사용 모델 복사에서 수행했다. 서비스 소스를 수정하지 않았다. 감사용 컨테이너는 종료했으며 기존 컨테이너/볼륨은 삭제하지 않았다.

**재확인 명령**

```bash
# 감사 시작 시점 소스 확인
git rev-parse HEAD
# 핵심 증거
cat docs/results/experiments/A/pdf_audit_20261115/requirements_matrix.json
cat docs/results/experiments/A/pdf_audit_20261115/quality/quality_full_test.json
# 서비스 소스 수정 후에는 새 결과 경로로 다시 측정해야 한다.
# 이번 사용 명령과 격리 설정은 commands.md 및 audit_harness/에 보존했다.
```
