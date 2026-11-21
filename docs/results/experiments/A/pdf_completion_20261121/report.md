# PDF 요구사항 재검증 · 2026-11-21

로컬 기본 full 배포에서 11개 품질·지연 기준과 최소 후보 300개를 확인했다. 기본 대시보드와 별도 쇼핑몰에 Chromium으로 접속했고, 각 화면에서 실제 API를 호출했다. 최종 제출 검사는 [실행 영수증](submission/checks.json), [최종 집계](../../../final_acceptance.json), [요구사항별 매핑](../../../../submission/requirements.md)에서 확인할 수 있다.

| 지표 | PDF 기준 | full test 또는 실측 | 판정 |
|---|---:|---:|---|
| 검색 MRR | ≥ 0.55 | 0.9250 | PASS |
| 검색 NDCG@10 | ≥ 0.5 | 0.9250 | PASS |
| 후보 Recall@300 | ≥ 0.3 | 0.7458 | PASS |
| 랭킹 CTR AUC | ≥ 0.7 | 0.9658 | PASS |
| 추천 HitRate@50 | ≥ 0.2 | 0.6651 | PASS |
| 추천 NDCG@50 | ≥ 0.08 | 0.3299 | PASS |
| Coverage | ≥ 0.2 | 0.3745 | PASS |
| 검색 p95 (ms) | ≤ 200 | 119.6971 | PASS |
| 추천 p95 (ms) | ≤ 200 | 23.9157 | PASS |
| 후보 p95 (ms) | ≤ 100 | 4.8929 | PASS |
| Redis p95 (ms) | ≤ 10 | 0.3046 | PASS |

상품 50,000개·사용자 10,000명·이벤트 1,000,000건과 seed 42를 사용했다. 시간순 8/1/1로 나누고, 동결된 기본 v1.0에서 valid 후 test를 실행했다. Recall@300은 평가 시점의 전체 판매 가능 카탈로그를 대상으로 한 사용자별 미래 cart/purchase 재현율의 평균이다. HTTP는 단건 10회 준비 후 100회 실측이며 검색 세 모드 중 가장 느린 값을 사용했다. 검증용 시뮬레이터를 중지했고, 다른 검증 배포의 API와 시뮬레이터를 시간 측정 동안 일시 정지했다. [valid](quality_full_valid.json) · [동결](quality_selection_full.json) · [test와 베이스라인](quality_full_test.json) · [HTTP·Redis 표본](smoke_full.json) · [CPU 스레드](serving_runtime.json)

계약상 AUC 기준은 CTR에 적용한다. 별도로 측정한 CVR AUC는 0.5304였다. 최종 독립 후보 100회 측정에서 100ms 초과는 1회, 최대는 122.70ms였다. 실제 추천 HTTP 100회의 후보 단계 최대는 6.27ms였다. 검색·추천 HTTP 400건의 오류는 0건이었다. [개별 호출 원본](smoke_full.json)

시뮬레이터의 대시보드 기동 의존성을 복원하기 전 측정도 보관했다. 당시 검색·추천 p95는 107.32ms와 23.55ms였고, 독립 후보 호출 1회가 121.60ms였다. 제출 검사가 Compose 변경을 검출한 뒤 최종 이미지로 지연·valid·test를 모두 다시 실행했다. [이전 전체 측정](before_final_compose/quality_full_test.json) · [소스 불일치 원본](before_final_compose/submission_attempt.log)

- **기본 화면**. 빈 실행 결과에서 검색과 추천 차트 각각 1개, A/B에 관측 비율 및 효과 크기·95% 신뢰구간·p-value 차트 2개를 확인했다. 제출 보고서의 측정 출처를 표시하며, 실제 배포의 결과를 생성하면 해당 평가 파일과 검증된 A/B를 우선 표시한다. [빈 결과 경로](dashboard_initial_effects.json) · [실제 평가·A/B 선택](dashboard_live_test_ab.json) · [브라우저와 세션 확인](dashboard_verified/browser.json)
- **쇼핑몰**. 별도 프로필 명령이 기존 API 컨테이너를 유지했다. 텍스트·이미지·복합 검색, 추천, 동일 추천 요청에 귀속한 상품 조회·장바구니·구매, 모바일 화면을 검사했다. [실행 명령](storefront_command.json) · [브라우저](storefront_browser/browser.json)
- **PDF 예시 및 동료 평가**. 검정 오버핏 후드티와 갈색 가방 이미지·복합 검색에서 상위 10개 상품의 속성을 대조했다. 기본 계약, 세션·탐색·다양성·콜드스타트 등 14개 동료 평가 항목을 확인했다. [상품별 결과](pdf_examples.json) · [동료 평가](peer_review.json) · [실제 Redis 귀속](mab_full.json) · [한 명령 검색→추천→A/B→통제 CT](demo_examples_verified.json)
- **CT CLI 경로**. 모델 상위 폴더를 읽기 전용으로 마운트한 첫 시연은 CT 작업 경로에서 중단됐다. 격리 학습에 설정된 모델 디렉터리를 사용하도록 수정하고 동일 시나리오를 다시 실행했다. [최초 실행의 검색·세션·A/B](demo_examples/) · [수정 후 CT 원본](demo_examples_retry/ct_drill.json)
- **재현**. 빈 경로의 데이터 생성, 감사, CLIP, FAISS, 세 모델 학습, Redis 준비를 실제 실행했다. 현재 기본 배포 데이터와 새로 생성한 데이터의 매니페스트와 기록 파일 해시가 일치했다. 기존 고정 CLIP 다운로드 캐시와 Docker 의존성 레이어를 재사용했다. [시작 상태](initial.json) · [준비](fresh_preparation.json) · [데이터 동일성](data_reproduction_full.json) · [기본 네 서비스와 자동 CT](fresh_services.json) · [빈 폴더 설치](scaffold.json) · [최종 이미지와 설치본 해시](reference_package.json) · [새로 학습한 배포의 기본 차트](published_browser.json)
- **A/B**. 이번 100명/군·7일 합성 실험의 CVR 상대 변화는 -24.72%였다(p=0.1027). PDF 12쪽의 +28%는 출력 예시다. 제출 규모 5,000명/군·30일 실험은 11월 12일 기록을 복원해 데이터·모델·소스 해시를 대조했다. 당시 CTR은 -17.37%, CVR은 -27.72%였다. 실제 고객 효과는 미측정이다. [이번 통계 재검산](ab_check_verification.json) · [full A/B](../final_validation_20261112/ab_acceptance_full.json)
- **CT**. 통합 검사에서 시뮬레이터 시작 로그의 변경을 검출했다. 기본 서비스 의존성에 대시보드 준비를 복원하고 기존 CT 수집기 그대로 이미지를 다시 빌드했다. 최종 기본 스택에서 자동 수집과 워커 기동을 확인했다. full 재학습·승격 심사·롤백은 11월 12일 실측 기록의 원본, 모델, 소스와 승인 조건을 재검산했다. 당시 신규 로그 13,404건으로 재학습했고 운영 v1.0을 유지했다. 승격·HTTP 재로딩·롤백은 별도 통제 실험에서 검증했다. [분리된 CT 실측](../final_validation_20261112/ct_acceptance_full.json)
- **코드·외부 데이터**. 공개 함수 타입, 경로를 옮긴 외부 데이터 실험 입력, 빈 폴더 설치, 체크섬, 의존성, 실제 Redis 회귀를 검사했다. H&M·Retailrocket·DeepFashion의 활용 기록을 제출 문서에 반영했다. [코드 검사](local_checks.json) · [전체 회귀](submission/pytest.txt) · [외부 데이터 실험](../../../../external_datasets.md)

대상은 현재 로컬 작업본이다. 공개 저장소의 기존 기여 PR과 평가자 접근을 재확인했다. 이 변경의 원격 게시와 과제 플랫폼 제출은 별도 절차다. [저장소 확인](submission/repository.json) · [통합 검사에서 발견한 CT 소스 불일치](before_simulator_dependency/submission_preflight.txt) · [수정 전 감사와 당시 실패](../pdf_audit_20261121/report.md)
