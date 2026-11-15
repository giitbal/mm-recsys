"""Run/report realism-v4, preserving the rejected high-density diagnostic."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
import yaml

from src.common.artifacts import file_hash, write_json
from src.external_data.realism_run import plan, tune, evaluate, train_models, check_selection, simulate, measure


def publish_reports(out: Path) -> None:
    """Only aggregate JSON evidence belongs in Git, never model weights or caches."""
    names=['candidate_training.json','frozen.json','ranking_labels_dev.json','ranking_selection_dev.json',
           'ranking_test.json','ranking_training_dev.json','ranking_valid.json','result.json']
    for folder in (out/'models').glob('*'):
        if not folder.is_dir(): continue
        destination=out/'training_reports'/folder.name;destination.mkdir(parents=True,exist_ok=True)
        for name in names:
            source=folder/name;target=destination/name
            if not source.exists():continue
            if target.exists() and file_hash(target)!=file_hash(source):
                raise ValueError(f'changed frozen training evidence: {target}')
            shutil.copyfile(source,target)


def run() -> None:
    spec, work, out = plan(); tune()
    try:
        evaluate()
    except ValueError as error:
        # This optional density stress test is beyond the 12 frozen primary runs.
        message = 'realism event times exceed configured window; choose a larger window or lower density'
        if str(error) != message or not (out/'density_control_baseline.json').exists() or len(list((out/'runs').glob('*.json'))) != 12:
            raise
        write_json(out/'density_control_combined_failure.json',dict(status='FAIL',events=500000,users=spec['users'],
            products=spec['products'],seed=spec['evaluation_seeds'][0],window_days=spec['purchase_window_days'],
            error=str(error),interpretation='Timestamp guard rejected the optional high-density run. No invalid data published; frozen primary recipes unchanged.'))
    for name in ['baseline','combined']:
        path=out/f'density_250k_{name}.json'
        if path.exists(): continue
        cfg=yaml.safe_load((work/'recipes'/f'{name}.yaml').read_text());cfg['seed']=spec['evaluation_seeds'][0]
        cfg['simulator']['n_events']=250000
        actual=measure(cfg,*simulate(cfg))
        write_json(path,dict(name=name,events=250000,actual=actual,
            scope='Matched additional density diagnostic; no recipe/model reselection'))
    train_models()
    publish_reports(out)


def verify() -> dict:
    spec, work, out=plan();check_selection()
    old=json.loads((out/'previous_evidence.json').read_text())
    assert all(file_hash(Path(p))==h for p,h in old['hashes'].items()), 'previous evidence changed'
    inputs=json.loads((out/'inputs.json').read_text())
    assert all(file_hash(Path(p))==h for p,h in inputs['source_hashes'].items()), 'source CSV changed'
    assert all(file_hash(Path(p))==h for p,h in inputs['cache_hashes'].items()), 'prepared reference changed'
    assert file_hash(Path(spec['source_expansion'])/'hm_data/users.json')==inputs['cohort_hash']
    assert file_hash(work/'behavior_profile.json')==file_hash(out/'behavior_profile.json')
    runs=list((out/'runs').glob('*.json'));assert len(runs)==12
    temporal=[]
    for path in runs:
        r=json.loads(path.read_text());root=work/'runs'/path.stem
        assert file_hash(root/'config.yaml')==r['config_sha256']
        manifest=json.loads((root/'data/split_manifest.json').read_text())
        assert manifest['generation_fingerprint']==r['data_fingerprint']
        assert all(file_hash(root/'data'/p)==h for p,h in manifest['file_hashes'].items())
        images=json.loads((root/'data/image_manifest.json').read_text())
        assert all(file_hash(root/'data'/p)==h for p,h in images.items())
        frame=pd.read_parquet(root/'data/events.parquet')
        products=pd.read_parquet(root/'data/products.parquet',columns=['product_id','created_at'])
        joined=frame[frame.product_id.notna()].merge(products,on='product_id',validate='many_to_one')
        assert len(joined)==int(frame.product_id.notna().sum()) and (joined.timestamp>=joined.created_at).all()
        exposures=pd.read_parquet(root/'data/impressions.parquet')
        assert not exposures.duplicated(['request_id','product_id']).any()
        exposed=exposures.merge(products,on='product_id',validate='many_to_one')
        assert len(exposed)==len(exposures) and (exposed.exposed_at>=exposed.created_at).all()
        assert frame.event_id.is_unique and frame.timestamp.is_monotonic_increasing
        assert set(frame.loc[frame.event_type=='view','impression_id'])<=set(exposures.impression_id)
        cfg=yaml.safe_load((root/'config.yaml').read_text());end=pd.Timestamp(cfg['simulator']['reference_time'])
        temporal.append(dict(run=path.stem,first=str(frame.timestamp.min()),last=str(frame.timestamp.max()),
            trailing_empty_days=(end-frame.timestamp.max()).total_seconds()/86400))
    models=list((out/'training_reports').glob('*/result.json'));assert len(models)==6
    for path in models:
        frozen=json.loads((path.parent/'frozen.json').read_text())
        assert frozen['source_hashes']==json.loads((out/'selection.json').read_text())['source_hashes']
        assert all(file_hash(Path(p))==h for p,h in frozen['model_hashes'].items())
    for name in ['catalog_control_3000.json','catalog_control_105542.json','density_control_baseline.json',
                 'density_control_combined_failure.json','density_250k_baseline.json','density_250k_combined.json']:
        assert (out/name).exists(),name
    def reject(value): raise ValueError(f'nonfinite JSON: {value}')
    for p in out.rglob('*.json'): json.loads(p.read_text(),parse_constant=reject)
    write_json(out/'temporal_coverage.json',dict(runs=temporal,
        limitation='All measurements use fixed windows. Generator reserves time for ongoing sessions, leaving an empty tail; this remains a temporal-realism limitation, especially at higher density.'))
    result=dict(status='PASS',acceptance='UNMEASURED',primary_runs=12,trained_model_conditions=6,
        previous_artifacts_preserved=len(old['hashes']),frozen_sources_verified=True,
        data_and_image_hashes_verified=True,raw_input_hashes_verified=True,actual_event_and_impression_causality_verified=True,
        rejected_diagnostics=['500000 events / 1000 users / 28 days combined profile exceeded timestamp window'],
        scope='Integrity and execution verification; not a claim that every behavior improved or full acceptance passed')
    write_json(out/'verification.json',result)
    return result


def report() -> None:
    _,_,out=plan()
    comparison=json.loads((out/'comparison.json').read_text())['aggregate']
    targets=json.loads((out/'targets.json').read_text())
    selection=json.loads((out/'selection.json').read_text())
    lines=['# 가격·행동 현실성 후속 실험 — realism-v4','',
        '가격·활동량·행동 간격은 개선됐다. 세션 길이는 개선되지 않았고, 반복 구매·취향 집중에는 큰 잔여 차이가 있다. 조건별 전이 적용과 고밀도 생성의 실패도 보존했다. 운영 설정/모델 승격과 full acceptance는 수행하지 않았다.','',
        '## 비교 계약과 실행','',
        '- 기존 v3 동시 교정 레시피를 기준으로 가격만 / 행동만 / 결합을 비교했다. 각 조건은 상품 3,000개·사용자 1,000명·이벤트 100,000건, seed 42/43/44다.',
        '- H&M 가격은 전체 고객 중 매핑 가능한 카테고리의 거래를 사용하고 양쪽 상대가격 분모를 동일하게 정의했다. 구매 행동은 기존에 고정한 10만 고객을 사용한다. 구매는 28일·사용자-상품-날짜 단위이며 같은 날 중복은 재구매가 아니다.',
        '- Retailrocket은 14일·조회/장바구니/구매만 사용한다. 세션은 30분 비활동으로 재구성한다. 경계 미완료 세션과 모호한 동시각 간격은 분리 집계한다. 세션 내 구매율은 노출 기반 CVR이 아니다.',
        '- 가격/행동 파라미터는 real train에서만 추정했다. seed 41로 valid에서 선택하고 소스·설정·레시피를 동결했다. real test는 v1-v3에서 이미 확인했으므로 독립 holdout으로 주장하지 않는다.',
        f'- 선택: 가격 `{selection["price_selected"]}`, 행동 `{selection["behavior_selected"]}`, 결합 가격 `{selection["combined_selected"]}`. 추천 점수는 레시피 선택에 사용하지 않았다.','',
        '## 실제 test 통계와의 거리 (3 seed 평균)','',
        '모든 오차는 작을수록 좋다. ± 표준편차와 train/valid 수치는 comparison.json에 있다. 이전 v3와는 가격 분모·기간·비교 기준이 달라 수치를 직접 이어 붙이면 안 된다.','',
        '| 조건 | 가격 평균 MAE | 가격 분위수 MAE | 카테고리 TV | 활동량 상위10% 비중 오차 | 세션 구매율 오차 | 세션 길이 오차 | 행동 간격 오차 |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    keys=['price_mae','price_quantile_mae','category_tv','activity_top10_error','session_purchase_error','session_length_error','gap_error']
    for name in ['baseline','price','behavior','combined']:
        lines.append('| '+name+' | '+' | '.join(f'{comparison[name]["test"][key]["mean"]:.6f}' for key in keys)+' |')
    lines+=['','분위수는 10/25/50/75/90%다. 길이·간격 오차는 각 분위수의 절대 차이를 실제 분위수(최소 분모 1)로 나눈 평균이다. 가격은 카테고리별 평균/분위수 차이를 균등 평균한다. 실제 통계와 합성 통계의 표본 수 차이는 남아 있다.',
        '활동량 목적함수는 상위 10%의 이벤트 점유율이다. 고정된 사용자/이벤트 수 때문에 사용자당 이벤트 수의 전체 분포가 맞았다는 뜻은 아니다. 101개 분위수 근사의 극단값 영향과 사용자당 밀도 차이도 남는다.','',
        '| 세션 관측창 | 활동 사용자당 이벤트 중앙값 | 이벤트 90% 분위수 | 상위 10% 이벤트 비중 |',
        '|---|---:|---:|---:|']
    session_rows=[('Retailrocket test',targets['test']['session'])]
    for name in ['baseline','combined']:
        r=json.loads((out/'runs'/f'42-{name}.json').read_text())
        session_rows.append((f'seed42 {name}',r['actual']['session']))
    for name,s in session_rows:
        a=s['activity'];lines.append(f'| {name} | {a["counts_quantiles"][2]:.2f} | {a["counts_quantiles"][4]:.2f} | {a["top10_share"]:.4f} |')
    lines+=['',
        '## 구매 행동과 통제 실험','',
        '| 조건 | 반복 구매율 | 2–4회 구매 그룹 반복률 | 5회 이상 구매 사용자 카테고리 집중도 (명) | 전반/후반 카테고리 TV (명) |',
        '|---|---:|---:|---:|---:|']
    rows=[('H&M test',targets['test']['purchase'])]
    for name in ['baseline','combined']:
        r=json.loads((out/'runs'/f'42-{name}.json').read_text())
        rows.append((f'100k events {name}',r['actual']['purchase']))
        r=json.loads((out/f'density_250k_{name}.json').read_text())
        rows.append((f'250k events {name}',r['actual']['purchase']))
    for size in [3000,105542]:
        r=json.loads((out/f'catalog_control_{size}.json').read_text())
        rows.append((f'catalog {size} baseline',r['actual']['purchase']))
    def number(value): return '미측정' if value is None else f'{value:.4f}'
    for name,r in rows:
        repeat=r['repeat_by_activity'].get('2-4',{}).get('rate')
        lines.append(f'| {name} | {number(r["repeat_rate"])} | {number(repeat)} | {number(r["category_concentration"])} ({r["category_concentration_users"]}) | {number(r["half_window_category_tv"])} ({r["half_window_users"]}) |')
    lines+=['','반복률은 활동량 구성에 민감하다. 구매 횟수별 수치와 표본 수를 함께 봐야 한다. 작은 카탈로그·고정 선호·인기 편중의 영향이 남으며, 상품 수 통제에서도 seed 하나의 표본 차이를 인과효과로 단정하지 않는다. 취향 변화 TV는 관측 구매 구성 변화이며 잠재 취향 자체의 변화가 아니다. 소수 사용자 결과는 불확실하다.','',
        '## 채택하지 않은 변경과 한계','',
        '- 조건별 전이: `activity_timing_transition`은 실제 로그 예측 개선만으로 채택하지 않았다. 생성 시 세션 길이·구매 도달 비율이 악화돼 valid 목적함수에서 탈락했다. 관련 pilot JSON을 보존했다.',
        '- 고밀도: 500,000 이벤트/1,000 사용자/28일 결합 조건은 시간 범위 초과 검사가 거부했다. 잘못된 시간을 잘라내거나 유효한 결과로 저장하지 않았다. 250,000 이벤트의 양쪽 조건으로 추가 진단했으며 이는 100k 본 실험과 별도다.',
        '- 초기 시간 배치: 모든 간격에 최댓값을 예약하던 pilot에서 후반 관측이 부족했다. 동결 전에 평균 간격 예약과 실제 범위 초과 거부로 수정했다. initial_timing_failure/에 이전 측정과 오류를 남겼다.',
        '- 시간 예약에 따른 끝부분의 무이벤트 구간은 남는다. temporal_coverage.json에 각 실행의 실제 마지막 시각과 빈 기간을 기록했다. 활동량/세션 분포 일부의 개선이 전체 시계열 현실성을 보장하지 않는다.',
        '- H&M의 실제 출시일·가격 인과효과·브랜드 충성도·persona·노출 CTR/CVR은 식별하지 않았다. 가격은 거래 가격 분포이며 원화 환산이나 정가 복원이 아니다.',
        '- H&M 고객과 Retailrocket 방문자는 서로 다른 모집단이다. 두 데이터의 통계를 합친 레시피가 하나의 실제 서비스의 결합 행동 분포를 재현한다는 보장은 없다. 특히 방문 밀도·구매 빈도를 동시에 맞췄다고 주장하지 않는다.',
        '- 파라미터는 101개 분위수로 근사한 집계다. 개인별 실사용 로그 복제 또는 원본 고객 프로필 주입을 하지 않았다.','',
        '## 새 데이터에서 재학습한 추천 품질','',
        '기존/결합 × seed 3개에서 Two-Tower와 DeepFM을 새로 학습했다. 후보 5 epoch·랭커 3 epoch 상한, valid 체크포인트 선택 후 test 평가다. 조건마다 생성 정답이 달라 실제 사용자 추천 개선으로 해석하면 안 된다.','',
        '| 조건 | test Recall@300 평균 | test DeepFM NDCG@50 평균 |','|---|---:|---:|']
    quality={}
    for name in ['baseline','combined']:
        records=[json.loads(p.read_text()) for p in (out/'training_reports').glob(f'*-{name}/result.json')]
        recall=float(np.mean([r['candidate']['recall_at_300'] for r in records]))
        ndcg=float(np.mean([r['ranking']['deepfm']['ndcg_at_50'] for r in records]))
        quality[name]=dict(runs=len(records),recall_at_300=recall,deepfm_ndcg_at_50=ndcg)
        lines.append(f'| {name} | {recall:.6f} | {ndcg:.6f} |')
    write_json(out/'quality_summary.json',quality)
    lines+=['','## 검증·적용 범위·재현','',
        'regression.txt와 typecheck.txt가 실제 회귀 검사 기록이다. verification.json은 12개 데이터/이미지 세트, 6개 학습 조건, 동결 소스/모델/입력 해시와 기존 167개 결과 보존을 검증한다. 테스트 통과는 전체 품질 합격이 아니다.',
        '기본 운영 설정과 기존 데이터/모델은 교체하지 않았다. `simulator.realism`은 opt-in이며 기존 v3 설정의 100,000 이벤트 동일성을 별도 확인했다. 소스 변경 전 v3 동결 검증은 당시 commit에서 재현해야 한다.','',
        '```bash','OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 .venv/bin/python scripts/run_realism_validation.py --run',
        '# 이미 완료된 산출물의 해시와 결과만 확인', '.venv/bin/python scripts/run_realism_validation.py','```','',
        '원본/파생 데이터·이미지·모델은 .team/에 보관하고 커밋하지 않는다. 학습 집계 JSON만 training_reports/에 공개하며 실행 중 models/의 JSON 사본은 Git에서 제외한다. 실행 환경은 environment.json에 있으며 CUDA·Windows·Docker·온라인 A/B·운영 승격·full acceptance는 이번에 검증하지 않았다.','']
    (out/'report.md').write_text('\n'.join(lines))


def main() -> None:
    parser=argparse.ArgumentParser();parser.add_argument('--run',action='store_true')
    if parser.parse_args().run:run()
    result=verify();report();print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
