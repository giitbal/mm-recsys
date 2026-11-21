# 쇼핑몰 카탈로그의 상품 도안 교체

같은 상위 24개 상품을 반환한 ‘검정 가방’ 검색에서 기본판은 서로 다른 JPEG 2개를, 새 쇼핑몰은 14개를 표시했다. 24개 모두 HTTP로 내려받은 파일의 SHA-256이 상품 메타데이터와 일치하며, 전체 카탈로그의 이미지 해시와 상품 순서도 배포한 CLIP 임베딩 manifest와 일치한다. [검색 응답 및 이미지 대조](storefront_search.json) · [기본판 실측](default_regression/search_black_bags.json)

| 측정 대상 | 기본 v4.4 | illustrations-v1 |
|---|---:|---:|
| 상품 이미지 파일 | 50,000 | 50,000 |
| 서로 다른 JPEG 콘텐츠 | 256 | 3,134 |
| 검정 레귤러핏 토트백 47개 안의 서로 다른 JPEG | 2 | 20 |
| 같은 토트백 상품쌍의 외곽선 IoU 중앙값 | 1.000 | 0.716 |

가방은 백팩·토트백·크로스백마다 몸판 6종과 포켓·패널 4종을 조합한다. 실루엣에 상품 ID나 브랜드 문자를 쓰지 않는다. 옷·신발·소품도 종류에 따라 재단선, 소매, 밑창, 장식이 달라진다. 같은 도안을 여러 상품이 쓸 수 있다. [카탈로그와 측정 방법](catalog.json) · [실행 중인 생성기와 설정 해시](deployed_artwork_sources.json)

## PDF 데이터와 평가

seed 42로 상품 50,000개, 사용자 10,000명, 페르소나 6종, 이벤트 1,000,000건을 생성했다. JPEG 50,000개는 모두 224×224 RGB다. 이미지 이외의 상품 메타데이터와 사용자·이벤트·노출, 시간순 분할 800,000/100,000/100,000건은 기본판과 일치한다. 독립된 빈 경로에서 같은 설정으로 한 번 더 생성해 manifest와 기록 파일 전체의 해시가 일치했다. [데이터 감사](data_audit.json) · [full 재현 결과](reproduction_full.json)

| 지표 | 기준 | valid | 동결 test |
|---|---:|---:|---:|
| 검색 MRR | ≥ 0.55 | 0.9402 | 0.9357 |
| 검색 NDCG@10 | ≥ 0.5 | 0.9345 | 0.9306 |
| 후보 Recall@300 | ≥ 0.3 | 0.7490 | 0.7458 |
| 랭킹 CTR AUC | ≥ 0.7 | 0.9666 | 0.9658 |
| 추천 HitRate@50 | ≥ 0.2 | 0.6893 | 0.6651 |
| 추천 NDCG@50 | ≥ 0.08 | 0.3670 | 0.3299 |
| 추천 Coverage | ≥ 0.2 | 0.3904 | 0.3745 |
| 검색 p95 (ms) | ≤ 200 | 86.8685 | 86.8685 |
| 추천 p95 (ms) | ≤ 200 | 20.6661 | 20.6661 |
| 후보 p95 (ms) | ≤ 100 | 3.6433 | 3.6433 |
| 피처 조회 p95 (ms) | ≤ 10 | 0.2761 | 0.2761 |

각 split에서 텍스트·이미지·복합 쿼리를 200개씩 평가했다. 정답은 관측 가능한 상품 속성과 시간 cutoff로 정의했다. 이미지 단독 test는 MRR 0.8972, NDCG@10 0.8819였다. 전체 카탈로그에서 후보 300개와 추천 상위 50개를 평가했다. 검색 BM25와 추천 기준 모델의 성적, 개선율과 계산 대상은 원본 보고서에 있다. [valid](quality_full_valid.json) · [동결 기록](quality_selection_full.json) · [test](quality_full_test.json)

지연은 쇼핑몰·API·Redis만 실행한 상태에서 모드마다 10회 예열 후 직렬 HTTP 요청 100회로 측정했다. 표의 지연은 같은 HTTP 측정값을 두 품질 보고서가 공유한다. 동시에 기본판 검사를 진행한 첫 측정도 보존했다. [단독 배포 측정](smoke_full.json) · [실행 조건](latency_conditions.json) · [동시 배포 측정](smoke_parallel_full.json)

## 쇼핑몰과 기본 제출판

새 도안 쇼핑몰은 빈 데이터·모델 경로에서 준비를 완료했고, 재기동 시 같은 산출물을 재사용했다. Chromium에서 세 가지 검색, 상품 조회, 추천에서 장바구니와 구매 이벤트까지의 귀속, 모바일 화면을 검사했다. 새 데이터 버전의 A/B 효과와 CT 승격 실험은 미측정이다. [최초 준비](preparation_full.json) · [재기동](preparation_reused.json) · [브라우저 결과](browser.json) · [실행 명령](../../../../../storefront/README.md)

기본 제출판은 기존 성능·A/B·CT 원본에 현 소스의 기본 설정 재생성 및 배포 검사를 연결했다. 재학습한 세 모델의 가중치와 후보 FAISS 인덱스 본체가 기존 기본판과 일치했다. 모델 메타데이터에는 설정 fingerprint 차이가 남아 있다. 실제 Redis를 포함해 532개 회귀 검사를 통과했다. [기존 기본판 판정](default_regression/previous_default_acceptance.json) · [새 재현 근거](default_regression/fresh_reproduction_full.json) · [모델별 해시 대조](default_regression/model_comparison.json) · [최종 제출 검사](default_regression/submission/checks.json)
