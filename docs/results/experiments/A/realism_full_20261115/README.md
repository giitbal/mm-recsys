**교정 레시피의 full 통합 검증**

realism-v4에서 valid로 선택하고 동결한 결합 레시피를 상품50,000·사용자10,000·이벤트1,000,000으로 확장한다. 기존 full-v44와 별도 데이터·모델·Redis·결과 경로에서 실행한다. 완료 판정과 수치는 report.md 및 summary.json을 따른다. plan.json의 RUNNING은 완료가 아니다.

- H&M의 카테고리/상대가격 교정, Retailrocket의 전역 Markov 전이와 활동량·행동 간격 파라미터를 유지한다.
- `realism.transition: false`는 valid에서 채택하지 않은 활동량 조건부 전이를 뜻한다. `simulator.transitions`의 Retailrocket 기반 전역 전이는 적용한다.
- 생성 시드42, 시간 분할80/10/10, 전체 카탈로그 Recall@300 및 기존 품질 기준을 유지한다.
- CLIP은 같은 고정 가중치로 새 카탈로그의 임베딩/인덱스를 구축한다. Two-Tower·DeepFM·GRU는 새 데이터에서 학습한다. 각 최대20 epoch와 기존 early stopping을 적용하며 checkpoint는 valid에서 선택한다.
- 실행 결과가 나쁜 경우에도 레시피·정답·K·평가 코호트를 test 결과에 맞춰 바꾸지 않는다. valid가 기준 미달이면 동일 설정을 동결한 진단 test로 기록하며 미달을 그대로 보존한다.
- A/B 기능 검사는 이전 감사와 같은500명/군×7일이다. full 카탈로그·모델을 사용하되 기본5,000명/군×30일 실행을 뜻하지 않는다. CT 생명주기 drill은 교정 레시피의 별도400상품/24사용자/6,000이벤트 검증이며, 자연 운영 모델 개선과 구분한다.

설정: [full_realism_v4.yaml](../../../../../config/full_realism_v4.yaml). 원래 교정 설정의 출처/해시는 plan.json과 frozen_calibration_check.json에 있다.

저장소 루트에서 재현하는 기본 Docker 명령:

```bash
API_PORT=18010 DASHBOARD_PORT=18511 REDIS_PORT=16389 \
docker compose -p mm-recsys-realism-full-20261115 \
  -f docker-compose.yml -f docker/compose.realism-full.yaml up -d --build
```

첫 실행은 데이터를 생성하고 세 추천 모델을 학습하므로 준비까지 시간이 걸린다. `/health`는 생존, `/ready`는 모델 준비를 표시한다. 기본 API 8000/대시보드8501과 구분하여 이 실행은18010/18511을 사용한다.

이번 실행은 직전 감사에서 현재 소스로 빌드한 동일 이미지와 로컬 HF 캐시를 재사용했다. 실제 실행 오버라이드는 `.team/realism-full-20261115/compose.yaml`에 보존한다. 공개 Compose는 이미지 빌드와 캐시 준비를 포함한 재현용이다. 서비스 소스의 실행본 일치는 별도 hash 증거로 확인한다.

원본/파생 데이터·이미지·모델·임시 학습 산출물은 `.team/realism-full-20261115/`에 있으며 Git에 포함하지 않는다. 컨테이너 안의 `data/full-realism-v4`, `models/full-realism-v4`는 그 전용 디렉터리로 연결된다. 이 설정은 기본 운영 레시피의 자동 교체나 승격을 뜻하지 않는다.

서비스가 준비된 뒤 같은 배포를 검사하는 명령:

```bash
dc() {
  API_PORT=18010 DASHBOARD_PORT=18511 REDIS_PORT=16389 \
  docker compose -p mm-recsys-realism-full-20261115 \
    -f docker-compose.yml -f docker/compose.realism-full.yaml "$@"
}
curl --fail http://localhost:18010/ready
# 지연 시간 측정에 배경 이벤트 생성이 섞이지 않도록 정지한다.
dc stop simulator
dc exec -T api-server python scripts/verify_peer_review.py \
  --api-url http://127.0.0.1:8000 \
  --output docs/results/experiments/A/realism_full_20261115/peer_review.json
dc exec -T -e CONFIG_PATH=models/full-realism-v4/.docker/config.yaml \
  api-server python scripts/verify_integration_mab.py \
  --output docs/results/experiments/A/realism_full_20261115/mab.json
dc exec -T api-server python scripts/smoke_test.py --benchmark \
  --output docs/results/experiments/A/realism_full_20261115/quality/smoke_full.json
dc exec -T api-server python -m docker.quality --split valid
dc exec -T api-server python -m docker.quality --split test
dc exec -T api-server python scripts/demo.py ab --users-per-group 500 --days 7 \
  --output docs/results/experiments/A/realism_full_20261115/ab_test.json
dc exec -T api-server python scripts/demo.py ct --json \
  --output docs/results/experiments/A/realism_full_20261115/ct_natural.jsonl
```

valid 품질 기준을 충족한 경우에만 기본 품질 명령이 test용 선택 기록을 만든다. 실패한 valid를 임의로 PASS로 바꾸지 않는다. 이미 저장된 증거를 보존하려면 재실행 전에 결과 폴더를 별도 보관한다. 위 A/B와 CT 명령은 모델 identity가 같은 실행용 결과 폴더에도 표시용 결과를 저장한다.
