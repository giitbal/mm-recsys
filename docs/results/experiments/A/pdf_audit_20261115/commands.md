**이번 감사에서 사용한 명령과 실행 조건**

저장소 루트에서 실행했다. 표준 Compose에 `audit_harness/compose.yaml`의 쓰기 경로·포트 격리를 적용했다. 해당 파일의 절대 경로는 이 로컬 워크스페이스 기준이다. 명령을 다시 실행하면 로그·Redis 상태가 추가되므로 새 감사 경로와 프로젝트 이름을 사용해야 한다.

```bash
API_PORT=18000 DASHBOARD_PORT=18501 REDIS_PORT=16379 \
docker compose -p mm-recsys-audit-20261115 \
  -f docker-compose.yml -f .team/pdf-audit-20261115/compose.yaml build

API_PORT=18000 DASHBOARD_PORT=18501 REDIS_PORT=16379 \
docker compose -p mm-recsys-audit-20261115 \
  -f docker-compose.yml -f .team/pdf-audit-20261115/compose.yaml up -d --no-build

RUN_REDIS_TESTS=1 REDIS_HOST=127.0.0.1 REDIS_PORT=16379 CONFIG_PATH=config.yaml \
OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 .venv/bin/python -m pytest -q -rA \
  -p src.serving.pytest_support tests \
  --junitxml=docs/results/experiments/A/pdf_audit_20261115/pytest.xml

.venv/bin/python -m mypy --explicit-package-bases src dashboard scripts
.venv/bin/python -m pip check

docker exec mm-recsys-audit-20261115-api-server-1 \
  python scripts/verify_peer_review.py --api-url http://127.0.0.1:8000 \
  --output docs/results/experiments/A/pdf_audit_20261115/peer_review.json

# load_config만 사용하는 도구에는 실제 배포 설정 경로를 명시했다.
# 생략한 최초 실행의 KeyError는 mab.txt에 보존했다.
docker exec -e CONFIG_PATH=models/full-v44/.docker/config.yaml \
  mm-recsys-audit-20261115-api-server-1 \
  python scripts/verify_integration_mab.py --api-url http://127.0.0.1:8000 \
  --output docs/results/experiments/A/pdf_audit_20261115/mab_runtime_config.json

docker stop mm-recsys-audit-20261115-simulator-1
docker exec mm-recsys-audit-20261115-api-server-1 \
  python scripts/smoke_test.py --benchmark --api-url http://127.0.0.1:8000 \
  --output docs/results/experiments/A/pdf_audit_20261115/quality/smoke_full.json

# smoke PASS 후 valid, valid PASS 후 test. 같은 설정/소스/모델을 유지했다.
docker exec mm-recsys-audit-20261115-api-server-1 python -m docker.quality --split valid
docker exec mm-recsys-audit-20261115-api-server-1 python -m docker.quality --split test

SCALE=full PYTHONPATH=. OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 \
  .venv/bin/python .team/pdf-audit-20261115/reproduce.py

OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  .venv/bin/python -m src.ct.verify_ct \
  --work-dir .team/pdf-audit-20261115/ct-drill \
  --output docs/results/experiments/A/pdf_audit_20261115/ct_drill.json

SCALE=full PYTHONPATH=. PYTHONHASHSEED=42 \
OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  .venv/bin/python .team/pdf-audit-20261115/ab.py

.venv/bin/python .team/pdf-audit-20261115/semantic.py

FONTCONFIG_FILE="$PWD/.team/pdf-audit-20261115/fontconfig.xml" \
PLAYWRIGHT_BROWSERS_PATH=.team/pdf-audit-20261115/browsers \
  node .team/pdf-audit-20261115/browser.js
```

자동 CT는 `compose-ct.yaml`을 추가하고 simulator만 재기동했다. 60초 간격의 WAITING 두 번(신규80/166건, 임계치10,000)을 관측한 뒤 중지했다. 운영 모델 학습이나 승격은 발생하지 않았다. 소규모 CT drill의 승격과 구분한다.

realism-v4 무결성 검사는 기존 `scripts.run_realism_validation.verify()`를 사용했다. 해당 모듈의 `write_json`만 감사 경로의 `realism_verification.json`/`realism_temporal_coverage.json`으로 전달하여 이전 결과 파일은 수정하지 않았다. 원본 CSV·이미지·모델·동결 소스·12개 실행의 시간 인과성과 기존167개 결과 보존을 확인했다.

제출 검사 실패는 `scripts.check_submission.files_check(Path.cwd(), check_policy)`의 실제 실행 결과다. 과거 PASS를 복사하거나 검사 조건을 우회하지 않았다. 전체 pytest는 이미 실행했으므로 제출 wrapper로 동일 테스트를 중복 실행하지 않았다.

A/B 계산과 통계 검증은 완료됐지만 마지막 결과 복사가 컨테이너 소유권 때문에 실패했다. `ab_verification.json`의 PASS를 확인한 뒤 컨테이너 내부 `shutil.copyfile`로 동일 결과를 대시보드에 연결했다. 원본 실패는 `ab_test.txt`, 복사 성공은 `ab_dashboard_copy.txt`에 있다.

첫 브라우저 캡처는 차트 비동기 렌더링을 충분히 기다리지 않았고 브라우저 호스트에 한글 폰트가 없었다. `browser_initial/`에 그대로 보존했다. 후속 검사는 Plotly 렌더링을 기다리고 로컬 Windows의 Malgun 글꼴을 감사 전용 fontconfig로 읽었다. 서비스 CSS나 소스는 변경하지 않았다.

감사 소스 파일은 `audit_harness/`, 원본 실행 로그와 신규 측정은 이 디렉터리, 데이터·모델·원본 PDF 텍스트·브라우저 바이너리·폰트는 Git 제외 경로 `.team/pdf-audit-20261115/`에 있다.
