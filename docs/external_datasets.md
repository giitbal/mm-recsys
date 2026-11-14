# 실제 데이터셋 활용과 재현

PDF 7쪽의 용도에 따라 H&M은 Multi-Stage 추천 검증과 시뮬레이터 파라미터 교정,
Retailrocket은 Markov Chain 전이 확률 추정, DeepFashion은 CLIP 임베딩 품질 검증에 사용한다.
사용자가 2026-11-14 로컬에 추가한 원자료를 사용하며 외부 클라우드 추론 API는 호출하지 않는다.
암호화된 In-shop/Consumer-to-shop 사진은 이 실험의 입력이 아니다.

## 실행

아래의 기본 실행과 세 데이터셋 설명은 최초 v1 실험 범위다. 이후 H&M 재검증은 v2,
학습 규모·멀티모달 특징·전이 세분화·DeepFashion 확대 실험은 문서 끝의 expansion-v3를 따른다.

저장소 루트에서 다음을 실행한다. 원자료는 `학습 데이터셋 추천/`에 둔다.
설정은 `config/external_data.yaml`, 작업 데이터·모델은 `.team/external-data-v1/`,
요약 결과는 `docs/results/external/v1/`에 저장한다. 기존 합성 데이터와 서빙 모델은 바꾸지 않는다.

```bash
PYTHONHASHSEED=42 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 \
  ./.venv/bin/python -m src.external_data.run --task all
```

각 단계는 `--task inventory`, `prepare-hm`, `retailrocket`, `deepfashion`, `hm`, `calibrate`, `verify`로
실행할 수 있다. `hm`은 `prepare-hm` 이후, `calibrate`는 H&M 준비와 Retailrocket 분석 이후 실행한다.
표준 출력은 JSON 요약이며 진행 로그는 stderr다. 원자료·설정이 바뀌면 새 work_dir/results_dir를 사용한다.
첫 실행은 압축 해제, 전체 거래 CSV 두 번 순회, CLIP CPU 인코딩과 모델 학습 때문에 시간이 걸린다.
중단된 CSV 추출은 다시 수행하며 완료된 추출은 SHA256을 확인해 재사용한다.

교정된 시뮬레이터는 다음 설정으로 실행한다. `SCALE=full`은 새 full 경로를 사용한다.

```bash
CONFIG_PATH=.team/external-data-v1/calibrated_simulator.yaml SCALE=full \
  ./.venv/bin/python -m src.simulator.generate
```

이 명령은 5만 상품·1만 사용자·100만 이벤트를 새로 생성하는 명령이다.
외부 데이터 실험에서 자동 실행하는 것은 1,000상품·200사용자·10,000이벤트의 교정 확인용 pilot이다.
새 full 데이터의 모델 학습·전체 품질·Docker·A/B·CT 검증은 별도의 측정이며 기존 PASS를 재사용하지 않는다.

## H&M: 실제 구매 추천과 교정

- ZIP 안의 articles/customers/transactions_train/sample_submission CSV를 CRC 확인과 SHA256 기록을 거쳐 읽는다.
  이미지 경로와 상품 ID의 연결 여부는 전체 목록으로 확인한다. 이번 추천 실험은 기존 메타데이터 Item Tower를
  사용하므로 H&M 전체 이미지 인코딩은 하지 않는다. sample_submission은 형식 참고이며 정답이 아니다.
- 전체 거래의 일별 누적 건수로 8:1:1 경계를 정한다. 같은 날짜 거래는 같은 split에 속한다.
  cutoff는 이전 split의 마지막 날짜 끝으로 정해 그날의 모든 거래를 과거 이력으로 포함한다.
- 고객 전체 ID에서 seed42로 2,000명을 먼저 균등 추출한다. 활동량·test 구매량·성능으로 고르지 않는다.
  해당 고객의 모든 거래와 전체 105,542개 상품을 유지한다. 따라서 고객 표본 실험이며 전체 고객 평가가 아니다.
- 상품 후보는 cutoff까지 최초 구매가 관측된 상품 전체다. 최초 관측일은 실제 등록일의 대리값이며,
  미래 최초 관측 상품의 정답도 Recall 분모에 남긴다. 상품 메타데이터는 시점 정보 없는 스냅샷이라는 한계가 있다.
- 고객 인구통계는 과거 시점의 값임을 증명할 수 없어 unknown으로 둔다. 실제 성별·페르소나를 추정해 채우지 않는다.
  상품 가격은 전체 train 거래의 상품별 평균과 train 전체 평균 대체값만 사용한다.
- 기존 TwoTower/TrainingDataset/FAISS/Evaluation을 사용해 train 학습, valid Recall@300으로 체크포인트를 선택한다.
  초기 HNSW가 valid 4명에 대해 후보 수를 채우지 못한 실패를 별도 보존한다. 탐색 가능한 부분 그래프가
  89개 벡터에 그쳐 efSearch를 전체 카탈로그 크기로 늘려도 해결되지 않았다.
  이제 이런 경우에만 같은 인덱스에 저장된 벡터로 cutoff 전체 카탈로그를 정확 검색해 300개를 채운다.
  추천 모델·정답·K를 바꾸지 않으며 exact refill 요청 수를 보고한다. 새 full API 지연은 미측정이다.
- 기존 DeepFM과 RankingEncoder를 구매 선호도 판별에 재사용한다. 구매 1개당 무작위 미관측 상품 4개이며,
  이는 비노출/비클릭의 정답이 아니다. 첫 출력만 구매 선호도 logits로 학습하고 두 번째 출력은 사용하지 않는다.
  순위 모델은 valid NDCG@50으로 선택하고, 선택·모델 해시를 저장한 다음 test를 평가한다.
- 전체 cutoff 카탈로그의 인기도 기준선과 Two-Tower 단독, 구매 DeepFM, 기존 Reranker 결과를 비교한다.
  DeepFM과 Reranker는 같은 Two-Tower 후보를 사용한다.
  MAB는 오프라인 무보상 상태이고 신규 상품은 최초 관측일 기준이다. 실제 A/B 효과나 출시일 보장은 아니다.
  다양성 불가능/위반 사용자 수를 숨기지 않는다. 진짜 CTR/CVR AUC는 `NOT_IDENTIFIABLE`이다.
  이번 오프라인 cold-start 점수는 train 인기도만 사용하며 실제 서비스의 최근 성장률 보정은 포함하지 않는다.
- 시뮬레이터 교정은 전체 train 거래의 지원 카테고리 구매 비율과 상대 가격 비율을 사용한다.
  기존 5개 대분류로 명확히 연결되는 상품만 교정에 쓰고 제외 건수를 보고한다. 추천 평가에는 이 제외를 적용하지 않는다.
  각 페르소나의 기존 선호와 실제 분포를 0.5씩 혼합해 차이를 유지한다. 정규화된 H&M 가격을 원화로 해석하지 않는다.
  여섯 페르소나의 비율·브랜드 충성도·인과적 가격 민감도는 이 자료만으로 알아낼 수 없으므로 기존 가정을 유지한다.

## Retailrocket: Markov 전이 추정

- 전체 이벤트를 시간순 8:1:1로 분할하고 동일 timestamp를 같은 split에 둔다.
- view/addtocart/transaction을 view/cart/purchase로 연결한다. 사용자별 연속 행동에서
  30분 이내의 다음 행동을 전이로 세고, 30분 무활동이 확인된 경우 exit로 센다.
- 같은 사용자의 같은 timestamp 이벤트 묶음은 순서를 알 수 없으므로 이 묶음에 닿는 전이는 제외한다.
  데이터/분할 종료까지 무활동 관측창이 확보되지 않은 마지막 이벤트를 exit로 단정하지 않는다.
- train의 3×4 전이 횟수에 셀당 1의 평활화를 적용한다. valid/test는 고정 행렬과의 total variation만 측정한다.
- 상품 속성 두 파일은 스키마·행 수·categoryid/available 레코드를 검증한다.
  전역 행동 전이에는 상품 속성이 필요 없어 조인하지 않는다. 카테고리별 모델은 향후 as-of 조인이 필요하다.
- search와 여섯 페르소나의 정답은 없으므로 기존 search/exit 재시작 가정을 유지한다.
  실제 생성기에 교정 설정을 넣고 pilot의 관측 전이를 다시 계산해 현실과의 차이를 보고한다.
  페르소나별 구매 오즈 조정 때문에 기본 행렬과 최종 생성 분포가 완전히 같지는 않다.

## DeepFashion: 고정 CLIP의 의미적 품질

- 암호 없는 Category/Attribute `img-008.zip`과 coarse 카테고리 주석, 공식 분할을 사용한다.
  공식 289,222개 이미지 경로를 확인하고 주석 외 파일은 평가하지 않는다.
- 공식 train에서 gallery 1,000장, valid/test에서 query 각 1,000장을 seed42로 고정 추출한다.
  클래스별 성능이나 정답 유무를 보고 표본을 바꾸지 않는다. 대표성 한계가 있는 표본 결과다.
- 기존 고정 revision CLIPEncoder와 동일 RGB/정규화 경로를 사용한다. 미세조정하지 않는다.
  50개 카테고리를 고정 영어 프롬프트로 인코딩해 zero-shot top1/top5, macro 정확도, class MRR/NDCG@10을 측정한다.
  train 최빈 카테고리 기준선도 보고한다.
- 다른 split의 gallery 이미지를 검색해 동일 카테고리를 relevance로 삼는다. 동일 SHA256 사진은 제외하고,
  gallery에 정답이 없는 query도 0점으로 유지한다. 유사 사진 중복 여부와 세부 속성은 미검토다.
- 이는 CLIP의 실제 사진 의미 표현 검증이다. 동일 상품 식별 평가, 전체 DeepFashion 평가,
  PDF의 5만 상품 검색 acceptance 또는 API 지연 측정을 대신하지 않는다.

## 결과와 범위

`inventory.json`, `hm_data.json`, `hm_candidate_training.json`, `hm_selection.json`,
`hm_recommendation.json`, `retailrocket.json`, `deepfashion.json`, `calibration.json`에 실행 근거를 남긴다.
`status=PASS`는 해당 분석/실행 완료이며 품질 임계값 충족을 뜻하지 않는다. `acceptance=UNMEASURED`를 유지한다.
모든 원자료·파생 데이터·모델·개별 사용자 기록은 Git/Docker 빌드에서 제외한다. 집계 결과와 코드만 제출한다.

공식 출처: [H&M](https://www.kaggle.com/competitions/h-and-m-personalized-fashion-recommendations),
[Retailrocket](https://www.kaggle.com/datasets/retailrocket/ecommerce-dataset),
[DeepFashion](https://mmlab.ie.cuhk.edu.hk/projects/DeepFashion.html).
DeepFashion 비상업 연구·재배포 제한과 H&M 원배포 조건을 따르며 원본 이미지를 GitHub에 올리지 않는다.

## H&M 재검증 v2 (2026-11-14)

[재검증 보고서](results/external/hm-v2/report.md)는 같은 v1 코호트·카탈로그·시간 분할을 유지하고
학습 횟수, 정확/ANN 검색, 전체 train 인기도·최근 판매량을 분리 비교한다.
실행은 `.venv/bin/python -m src.external_data.hm_revisit --task all`이며
`config/external_hm_v2.yaml`의 새 작업·결과 경로를 사용한다. v1 실행이 선행돼야 한다.
최대 20 epoch 중 valid 기준 9번째를 선택했고 14번째에서 조기 종료했다.
valid에서 가장 좋았던 것은 신경망 가중치 0인 30일 판매량 기준선이다.
같은 test Recall@300은 0.061304지만 독립 holdout 검증이나 딥러닝 문제 해결로 주장하지 않는다.

## 여섯 가지 추가 실험 expansion-v3 (2026-11-14)

설정은 `config/external_expansion.yaml`, 원자료에서 만든 데이터·모델·임베딩은
`.team/external-expansion-v3/`, 집계 결과는 `docs/results/external/expansion-v3/`에 저장한다.
v1 입력 준비가 선행돼야 한다. [측정 보고서](results/external/expansion-v3/report.md)의
학습 곡선, 동일 후보 단계별 비교, 교정 분포 거리와 CLIP 오분류를 함께 확인한다.

1. H&M 학습 고객을 2천 → 2만 → 10만 명으로 확대한다. 기존 평가 고객과 카탈로그,
   시간 경계·정답·K=300은 유지하고 추가 고객은 정답을 보기 전에 균등 추출한다.
2. 전체 상품의 텍스트와 실제 이미지를 고정 CLIP으로 인코딩한다. train 시점 가용 상품만으로
   fit한 PCA 64차원을 사용해 메타데이터 / 텍스트 추가 / 텍스트·이미지 추가를 비교한다.
   원본 512차원 벡터를 보존하고 이미지 누락 상품은 제거하지 않는다.
3. 각 조건의 같은 후보 300개에서 Two-Tower / 인기도 / 구매 선호 DeepFM / 재정렬을
   비교한다. 최종 설정은 valid에서 선택하고 모델·소스 해시를 고정한 뒤 test를 평가한다.
4. 기존 / H&M만 / Retailrocket만 / 둘 다 교정한 시뮬레이터를 각각 seed 42·43·44로
   생성하고 모델을 새로 학습한다. 실행당 3천 상품·1천 사용자·10만 이벤트를 사용한다.
5. Retailrocket의 과거 시점 카테고리와 이전 활동량별 Markov 모델을 추정한다.
   평활화는 valid NLL로 선택하며 미관측 조건은 전역 확률로 보완한다.
6. DeepFashion gallery 1만 장과 valid/test 각 5천 장으로 확대한다. 카테고리별 성능과
   혼동, 같은 카테고리 이미지 검색, 1천 속성의 AP를 측정한다.

```bash
PYTHONHASHSEED=42 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 \
  ./.venv/bin/python -m src.external_data.expansion_run --task all

./.venv/bin/python -m src.external_data.expansion_run --task verify
```

완료한 단계는 기록과 해시를 확인해 재사용한다. 동일 작업 경로를 여러 프로세스에서 중복 실행하지
않으며 설정을 바꾸는 새 실험은 work/results 경로도 새 버전으로 지정한다.
H&M test는 앞서 본 구간이므로 후속 탐색 결과다. 시뮬레이터 조건별 정답도 서로 달라
합성 점수 상승을 실제 추천 개선으로 해석하지 않는다. 실행 완료와 품질 목표 달성을 구분하며
full acceptance·서빙 지연·온라인 A/B·운영 모델 승격은 이 실험 범위에 포함하지 않는다.

실측 test Recall@300은 metadata 기준 2천/2만/10만 명에서 각각
0.017706/0.023124/0.028820이었다. 10만 명에 텍스트를 더하면 0.043885,
이미지까지 더하면 0.059892였고, valid에서 선택한 멀티모달 모델의 최종 NDCG@50은
0.015305, test 다양성 위반은 0명이었다. 같은 후보에서 인기도 NDCG는 0.013747,
DeepFM은 0.015075였다. 2만 명 metadata 조건의 test 제약 위반 3명과
멀티모달 조건의 valid 제약 위반 1명은 별도 기록에 남겼다.

기존 v2의 전체 train 거래 기반 30일 인기도 기준선은 같은 test Recall 0.061304,
최종 NDCG 0.006575였다. 이번 모델은 최종 순위 품질이 높아졌지만 후보 Recall은 아직
이 기준선을 넘지 못했다. 학습 정보량도 달라 동일 데이터량의 모델 대조로 해석하지 않는다.
데이터 식별자와 출처 해시를 대조한 [이전 결과 비교](results/external/expansion-v3/historical_comparison.json)를 참조한다.

시뮬레이터 12회 실험에서는 카테고리·행동 전이 분포가 가까워졌으나, 두 자료를 함께
교정한 상대 가격 MAE는 0.354558에서 0.463777로 악화됐다. 현재 가격 교정식은 추가 개선이 필요하다.
Retailrocket 조건부 전이의 test NLL은 0.727838에서 0.668306으로 낮아졌다.
DeepFashion 2만 장 평가의 test Top-1/Top-5는 34.42%/75.40%, 속성 macro AP는
0.051748이었다. 평가 가능한 test 카테고리는 43/50개, 속성은 913/1,000개다.
