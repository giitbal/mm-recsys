# 데이터 범위와 출처

## 현재 사용 상태 (2026-11-14)

사용자가 로컬 `학습 데이터셋 추천/`에 H&M 전체 ZIP, Retailrocket 이벤트·상품 속성 ZIP,
카테고리 트리, DeepFashion 이미지·주석을 준비했다. 이전의 미획득 상태는 현재 상태가 아니다.
사용자의 추가 활용 요청에 따라 다음 오프라인 실험을 구현했다.

| 출처 | 사용 목적 | 범위 |
|---|---|---|
| H&M | Multi-Stage 구매 추천 검증, 시뮬레이터 파라미터 교정 | 전체 거래로 시간 경계·train 교정 통계 산출, 고정 2,000명·전체 상품 추천 평가 |
| Retailrocket | Markov Chain 전이 확률 추정 | 전체 이벤트의 train에서 추정, valid/test에서 분포 차이 측정 |
| DeepFashion | CLIP 임베딩 품질 검증 | 암호 없는 Category/Attribute 공식 분할의 고정 이미지 표본 |
| 자체 시뮬레이터 | 기본 제출 경로 및 교정 효과 확인 | 기존 full 유지, 교정된 별도 설정·pilot 실행 |

실행 명령·평가 정의·데이터 누수 방지·측정 한계는 [실제 데이터 활용 문서](external_datasets.md),
실행 결과는 [외부 데이터 결과](results/external/v1/)에 있다. 원자료·이미지·모델은 GitHub나 Docker 이미지에 넣지 않는다.
데이터별 ID를 임의로 서로 연결하지 않는다. H&M 구매 이력에 노출 후 비클릭 정답을 만들어 붙이지 않는다.

공식 출처: [H&M](https://www.kaggle.com/competitions/h-and-m-personalized-fashion-recommendations),
[Retailrocket](https://www.kaggle.com/datasets/retailrocket/ecommerce-dataset),
[DeepFashion](https://mmlab.ie.cuhk.edu.hk/projects/DeepFashion.html).
DeepFashion의 비상업 연구·재배포 제한과 각 원배포 조건을 따른다. 일부 DeepFashion 이미지의
암호를 우회하지 않으며, 비암호 Category/Attribute 자료만 사용한다.

## 기본 평가 범위: RESOLVED_OPTIONAL (2026-10-16 결정 유지)

사용자가 전달한 강사 지시는 합성 데이터로 기본 개발과 필수 검증을 완료하고, 외부 실제
데이터셋은 추가 모델 검증에 사용한다는 것이다. [결정 기록](submission/dataset_scope.json)을 따른다.
이번 실제 데이터 사용은 그 후속 작업이며, 외부 데이터 표본 결과가 기존 합성 full acceptance를 대신하지 않는다.
교정된 full 데이터의 재학습·품질·Docker·A/B·CT는 새 실행 전까지 UNMEASURED다.

## 과거 기록

B11 당시에는 PDF p.7의 “필수 활용 데이터셋” 제목과 “활용할 수 있다” 본문이 함께 있어
UNRESOLVED로 기록했고 원자료를 획득하지 않았다. 2026-10-16 강사 지시 전달로
RESOLVED_OPTIONAL이 됐다. 이후 2026-11-14 사용자가 자료를 추가하고 세 가지 용도의 실제 활용을 요청했다.
CLIP checkpoint는 기존 고정 revision을 재사용하며 외부 클라우드 추론 API를 호출하지 않는다.
