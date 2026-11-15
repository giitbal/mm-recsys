# 교정 레시피 기반 full 통합 검증

상품 50,000개·사용자 10,000명·이벤트 1,000,000건의 교정 데이터를 새로 생성하고 전체 의존 모델을 재학습했다. valid 품질은 PASS, 동결 test 품질은 PASS다. 이는 B11 최종 제출 승인이나 기본 배포 승격을 뜻하지 않는다.

다만 CVR AUC는 0.5052이고, 합성 A/B의 CTR/CVR 상대 변화는 각각 -39.56% / -54.90%다. 실행과 오프라인 품질 기준 통과를 추천 전략의 효과 개선이나 PDF 전체 최종 합격으로 해석하면 안 된다.

## 실행과 데이터 출처

- H&M 카테고리·상대가격, Retailrocket 전역 Markov 전이·활동량·행동 간격의 동결된 realism-v4 결합 레시피를 사용했다. 조건부 전이는 기존 valid에서 탈락하여 적용하지 않았다.
- seed 42, 시간 분할 80/10/10, 전체 카탈로그 Recall@300, 사용자 10,000명 coverage 집합과 기존 기준을 유지했다. test 결과를 이용한 레시피·K·정답·코호트 수정은 없다.
- CLIP 고정 가중치로 새 임베딩과 세 검색 인덱스를 생성했다. Two-Tower/DeepFM/GRU는 새 데이터에서 학습하고 valid로 checkpoint를 선택했다. 필수 모델 파일 12개와 데이터 fingerprint 일치 확인.
- 기존 full-v44 및 소규모 realism-v4 산출물은 보존했다. 새 데이터·모델은 `.team/realism-full-20261115/`의 전용 경로에 있다.
- 데이터 fingerprint: `21ed7437e9e8f7d9f63afd37b6979d219e896ce12b6e863b846d1edc7e873b3f`.
- [재현 설정과 명령](README.md), [동결 출처](plan.json), [데이터 감사](data_audit.json), [재생성 일치](data_reproduction.json), [모델 출처](model_provenance.json).

## 최종 test 측정

이전 full-v44는 직전 감사에서 같은 서비스 소스로 측정한 값이다. 생성 데이터와 정답이 다르므로 두 열의 차이는 교정의 인과적 성능 향상을 증명하지 않는다.

| 지표 | 기존 full-v44 | 교정 full | 기준 | 판정 |
|---|---:|---:|---:|---|
| mrr | 0.925000 | 0.938333 | ≥ 0.55 | PASS |
| ndcg_at_10 | 0.925000 | 0.938333 | ≥ 0.5 | PASS |
| recall_at_300 | 0.745793 | 0.744233 | ≥ 0.3 | PASS |
| auc | 0.965785 | 0.968465 | ≥ 0.7 | PASS |
| hit_rate_at_50 | 0.665145 | 0.635979 | ≥ 0.2 | PASS |
| ndcg_at_50 | 0.329914 | 0.316974 | ≥ 0.08 | PASS |
| coverage | 0.374480 | 0.328720 | ≥ 0.2 | PASS |
| search_p95_ms | 111.330475 | 103.952606 | ≤ 200 | PASS |
| recommend_p95_ms | 22.319504 | 24.164433 | ≤ 200 | PASS |
| candidate_p95_ms | 3.276589 | 4.329209 | ≤ 100 | PASS |
| feature_p95_ms | 0.437049 | 0.277812 | ≤ 10 | PASS |

CTR AUC는 0.968465다(관측 노출 224,704건). CVR AUC는 0.505248다(관측 클릭 56,176건, 구매 양성 247건). 품질 기준의 AUC는 계약상 CTR이며, 낮은 CVR AUC는 별도 한계로 남는다.

동일 교정 test에서 단계별 비교:

| 전략 | HR@50 | NDCG@50 | Coverage |
|---|---:|---:|---:|
| train_popularity | 0.098413 | 0.026035 | 0.001000 |
| two_tower | 0.507937 | 0.170914 | 0.465340 |
| deepfm | 0.665608 | 0.362381 | 0.415000 |
| full_pipeline | 0.635979 | 0.316974 | 0.328720 |

평가 집합 10,000명 중 정답이 있는 사용자는 945명, 없는 사용자는 9,055명이다. Coverage에는 10,000명을 모두 포함한다. cold 300명의 test 정답은 0건이다. 시점상 이용 가능한 상품은 48,574개이며, 미래 출시 정답 상품 10개는 정답에서 지우지 않았다.

## 기능 검증과 제한

- 회귀 테스트 519개, 실패 0개, 오류 0개, skip 0개. 실제 Redis를 사용했고 테스트 자체의 표준 fixture 설정을 유지했다. 교정 full 실행 검증은 별도다.
- mypy 157개 파일과 pip 의존성 검사를 통과했다. 기존 부분 타입 주석 누락이 전부 해소됐다는 뜻은 아니다.
- 실제 HTTP·Redis 동료 평가 14개, MAB 6개, PDF 검색 예제 3개, 브라우저 6개 탭과 검색·추천·클릭 비교를 검사했다. 개별 결과는 summary.json의 checks와 각 JSON에 있다.
- 지연 시간: 단일 Docker 배포, API 4 CPU/4GiB, CPU FP32, serving Torch/FAISS 2스레드, OMP/MKL/OpenBLAS 2, 10회 warmup + 100회 순차 요청. 동시 부하/타 장비 성능은 미측정이다. 후보 오프라인 벤치의 스레드 조건은 해당 원본 JSON을 따른다.
- A/B: full 카탈로그·새 모델, 군당 500명×7일. 공통 합성 반응식으로 두 전략을 비교했으며 실제 사용자 실험이 아니다. CTR/CVR 분모는 원본에 명시한다. A/B의 PASS는 결과 계산·검증 통과이며 treatment 우월성을 뜻하지 않는다.

| A/B 지표 | Control | Treatment | 상대 변화 | 차이 95% CI | p-value |
|---|---:|---:|---:|---|---:|
| ctr | 0.427657 | 0.258457 | -39.56% | [-0.18040312109701093, -0.1579968789029891] | 1.44176e-192 |
| cvr | 0.035286 | 0.015914 | -54.90% | [-0.022298689834210923, -0.016444167308646226] | 1.80447e-38 |

- CT: 교정 레시피의 400상품·24사용자·6,000이벤트 격리 drill에서 실제 3모델 학습·승격·유지·reload·rollback·중복 방지를 검증했다. 초기 랭커를 약화한 통제 fixture이므로 full 운영 모델의 자연스러운 개선으로 해석하지 않는다. 자연 full CT의 상태는 ct_natural.jsonl을 별도로 따른다.
- 실제 full CT 모니터: UNMEASURED, mature 요청 0건. 실제 트리거: WAITING, 신규 로그 37건 / 기준 10000건. 자연 full 재학습·승격 성과는 미측정이다. [원본 트리거](ct_trigger.jsonl).
- 구매 예측 CVR AUC, A/B 방향성, 세션 길이·반복 구매 현실성에는 한계가 남는다. full 품질 통과와 실제 서비스 효과는 구분해야 한다.
- cold 사용자는 전체 평가 집합에 포함된다. 해당 split에 cold 정답이 없는 경우 cold 품질은 미측정이며, HTTP cold-start 동작 PASS로 이를 대체하지 않는다. 단계별 표에서 재정렬이 DeepFM보다 낮은 지표는 그대로 보존한다.
- 제출 파일 검사는 `docs/submission/dataset_scope.json`의 기존 증거 해시 불일치로 FAIL이다. 앞선 PDF 감사의 문서·주석·원격 반영 관련 미완료 사항도 이번 실행으로 해결됐다고 주장하지 않는다.
- DeepFashion의 기존 CLIP 품질 검증을 재사용했고 CLIP 가중치는 바꾸지 않았다. 이번 작업은 교정된 합성 데이터의 전체 의존 파이프라인 검증이다.

## full에서의 현실성 거리

기존에 동결한 외부 데이터 통계와 비교한 기술적 거리다. 외부 test는 이전 작업에서 이미 관찰했으므로 독립 holdout으로 주장하지 않으며 이번 결과로 재선택하지 않았다. 작은 실험과 분포가 완전히 같거나 실제 서비스의 결합 행동을 재현했다는 뜻도 아니다.

| 지표 | 외부 test 기준 거리 |
|---|---:|
| price_mae | 0.166989 |
| price_quantile_mae | 0.188017 |
| category_tv | 0.233000 |
| activity_top10_error | 0.026596 |
| session_purchase_error | 0.000270 |
| session_length_error | 0.300000 |
| gap_error | 0.148432 |
| behavior_objective | 0.118825 |

[원본 품질 결과](quality/quality_full_test.json) · [A/B](ab_test.json) · [브라우저](browser.json) · [CT drill](ct_drill.json) · [자연 CT](ct_natural.jsonl) · [실행 명령/종료 코드](execution.json) · [이전 PDF 전수 감사](../pdf_audit_20261115/report.md)

기본 서비스는 자동 교체하지 않았다. 새 검증 서비스: API http://localhost:18010/docs, 대시보드 http://localhost:18511. 측정 후 시뮬레이터는 정지했고 자동 CT 학습은 비활성화한 상태다.
