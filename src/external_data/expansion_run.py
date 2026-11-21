"""Reproduce or verify all six external-data experiments without replacing production."""
import argparse,json,subprocess,sys
from pathlib import Path
from src.common.artifacts import file_hash,fingerprint,write_json
from src.external_data.expansion_common import plan


def training_coverage(spec: dict, work: Path, results: Path) -> list[dict]:
    import pandas as pd
    from src.recommendation.datasets import read_data,cutoff_for
    data=read_data(Path(spec['source_work'])/'hm','valid')
    truth=[set(g.product_id) for _,g in data['valid'].groupby('user_id')]
    eligible=set(data['products'].loc[data['products'].created_at<=cutoff_for(data,'valid'),'product_id'])
    source=json.loads((results/'hm_data.json').read_text());observed=set();active=0;rows=[]
    for shard in source['shards']:
        frame=pd.read_parquet(shard['path'],columns=['product_id','user_id'])
        observed.update(frame.product_id);active+=frame.user_id.nunique()
        size=(shard['number']+1)*spec['shard_users']
        if size in spec['training_sizes']:
            assert observed<=eligible
            rows.append(dict(selected_users=size,active_train_users=int(active),observed_products=len(observed),
                valid_unobserved_truth_pairs=sum(len(t-observed) for t in truth),
                valid_unavailable_truth_pairs=sum(len(t-eligible) for t in truth),
                valid_eligible_unobserved_truth_pairs=sum(len((t&eligible)-observed) for t in truth),
                valid_total_truth_pairs=sum(len(t) for t in truth),
                valid_unobserved_macro_fraction=sum(len(t-observed)/len(t) for t in truth)/len(truth)))
    write_json(results/'hm_training_coverage.json',dict(status='PASS',rows=rows,scope='diagnostic only; no users or truth filtered'))
    return rows


def verify(spec: dict, work: Path, results: Path) -> None:
    selection=json.loads((results/'hm_selection.json').read_text())
    assert selection['spec_fingerprint']==fingerprint(spec)
    for group in ['source_hashes','report_hashes','model_hashes','embedding_hashes']:
        assert all(file_hash(Path(p))==h for p,h in selection[group].items()),group
    expected=[(size,'metadata') for size in spec['training_sizes']]+[(selection['feature_training_size'],v) for v in ['text','multimodal']]
    hm=[]
    for size,variant in expected:
        for split in ['valid','test']:
            value=json.loads((results/f'hm_{split}_{size}_{variant}.json').read_text())
            assert value['candidate']['candidate_count_min']==value['candidate']['candidate_count_max']==300
            assert value['evaluation_users']==(643 if split=='valid' else 710)
            assert value['empty_target_users']==(1357 if split=='valid' else 1290)
            assert all(file_hash(Path(p))==h for p,h in value['model_hashes'].items())
            assert set(value['stages'])=={'two_tower','same_candidates_popularity','deepfm','reranked'}
            hm.append(value)
    data=json.loads((results/'hm_data.json').read_text());tensors=json.loads((results/'hm_tensors.json').read_text())
    for report in [data,tensors]:assert all(file_hash(Path(p))==h for p,h in report['hashes'].items())
    simulator=json.loads((results/'simulator_comparison.json').read_text())
    assert simulator['runs']==4*len(spec['simulator']['seeds']) and set(simulator['conditions'])=={'original','hm','retailrocket','both'}
    for p in (results/'simulator').glob('*/selection.json'):
        r=json.loads(p.read_text());assert all(file_hash(Path(k))==h for k,h in r['model_hashes'].items())
    retail=json.loads((results/'retail_conditional.json').read_text())
    assert len(retail['test'])==4 and all(file_hash(Path(p))==h for p,h in retail['model_hashes'].items())
    deep=json.loads((results/'deepfashion_expanded.json').read_text())
    assert deep['counts']==dict(train=spec['deepfashion']['gallery_images'],val=spec['deepfashion']['queries_per_split'],test=spec['deepfashion']['queries_per_split'])
    assert all(file_hash(Path(p))==h for p,h in deep['embedding_hashes'].items())
    training_coverage(spec,work,results)
    write_json(results/'verification.json',dict(status='PASS',acceptance='UNMEASURED',completed_requested_experiments=[1,2,3,4,5,6],
        plan_fingerprint=fingerprint(spec),hm_variants=len(expected),simulator_runs=simulator['runs'],
        report_hashes={str(p):file_hash(p) for p in sorted(results.rglob('*.json')) if p.name!='verification.json'},
        limitations=['H&M test interval previously inspected; exploratory follow-up','100k selected training customers, not all source customers',
        'simulator comparison is 3k products/1k users/100k events, not full acceptance','frozen CLIP sample benchmark, not identity retrieval',
        'no serving latency, online A/B or production model promotion']))
    print('Verified all six requested experiments',flush=True)


def report(spec: dict, work: Path, results: Path) -> None:
    read=lambda name:json.loads((results/name).read_text())
    selection=read('hm_selection.json');data=read('hm_data.json')
    variants=[(s,'metadata') for s in spec['training_sizes']]+[(selection['feature_training_size'],v) for v in ['text','multimodal']]
    lines=['# 외부 데이터 추가 실험 1–6 — expansion-v3','',
        '지정한 여섯 실험을 실제 실행했다. 실행 완료와 모델 품질 목표 충족은 구분한다. 종합 acceptance는 UNMEASURED다.','',
        '## 1. H&M 학습 규모 확대','',
        '원래 평가 사용자 2,000명, 전체 상품 105,542개, 시간 경계·미래 정답·K=300을 유지했다. ',
        '추가 고객은 구매량이나 정답을 보기 전에 균등 추출했다. 1,000명 단위로 기존 TrainingDataset의 1:4 음성 표본과 엄격한 과거 이력을 저장했다.',
        'H&M은 seed 42 한 번의 실행이며 규모별 epoch 상한은 같다. 고객이 늘면 optimizer 갱신 횟수도 늘어나므로 데이터량과 추가 학습량의 효과가 함께 포함된다.',
        '상품 가격·범주 어휘 등 v1 전처리는 고정했다. 고객 수는 모델 학습 상호작용의 범위를 뜻하며 모든 전처리 통계의 고객 수를 제한한 비교는 아니다.',
        '기존 v1/v2와 미니배치 순서·샤드별 난수열은 다르며, v3 내 모든 규모·특징 조건에는 같은 입력과 규칙을 적용했다.','',
        '| 선정 고객 | train 구매가 있는 고객 | train 구매 건수 | 관측 상품 | valid 정답의 train 미관측 비율 |','|---|---:|---:|---:|---:|']
    coverage={r['selected_users']:r for r in read('hm_training_coverage.json')['rows']}
    for size in spec['training_sizes']:
        c=coverage[size]
        lines.append(f"| {size:,} | {c['active_train_users']:,} | {data['training_events'][str(size)]:,} | {c['observed_products']:,} | {c['valid_unobserved_truth_pairs']/c['valid_total_truth_pairs']:.2%} |")
    largest=coverage[max(spec['training_sizes'])]
    lines+=['',f"가장 큰 학습 코호트에서 미관측 valid 정답 {largest['valid_unobserved_truth_pairs']:,}건 중 {largest['valid_unavailable_truth_pairs']:,}건은 평가 cutoff에 아직 가용하지 않은 상품이다. 가용하지만 해당 코호트 train에서 미관측인 정답은 {largest['valid_eligible_unobserved_truth_pairs']:,}건이다. 미래 상품 정답은 분모에 그대로 남으며 고객 수 확대만으로 이 시점 제약을 해결할 수 없다."]
    lines+=['','## 2–3. 상품 특징과 추천 단계 비교','',
        '메타데이터만, 메타데이터+고정 CLIP 상품명·설명, 메타데이터+텍스트+이미지를 비교했다.',
        '전체 상품의 텍스트와 존재하는 이미지를 인코딩했다. 누락 이미지는 0 벡터로 표시하고 상품·정답을 제거하지 않았다.',
        '상품명·설명·이미지는 시점 정보 없는 원본 스냅샷이다. 최초 관측 구매일을 등록일 대리값으로 사용하며 과거 콘텐츠 가용성을 증명한 것은 아니다.',
        'CPU 학습에서는 CLIP 원본 512차원을 train 시점에 가용한 상품만으로 fit한 PCA 64차원으로 투영한다. 원본 벡터는 보존하며 세부 정보 손실 가능성이 있다. 분산 보존율은 hm_content_projection.json에 기록한다.',
        '특징 실험의 학습 규모는 metadata 모델의 valid Recall로 선택했다. 같은 규모의 구매 선호 DeepFM을 특징 조건 간 공유해 후보 개선이 후속 순위에서 유지되는지도 확인했다.',
        'DeepFM은 CTR/CVR 모델이 아닌 구매 대 무작위 미관측 상품 판별 모델이다. 후보·랭커는 각 valid 지표로 체크포인트를 선택했고 최종 설정은 valid 재정렬 NDCG로 선택했다.','',
        '| 고객/특징 | valid Recall@300 | test Recall@300 | test Two-Tower NDCG@50 | 동일 후보 인기도 | DeepFM | 재정렬 | Coverage@50 |','|---|---:|---:|---:|---:|---:|---:|---:|']
    for size,variant in variants:
        v=read(f'hm_valid_{size}_{variant}.json');t=read(f'hm_test_{size}_{variant}.json');s=t['stages']
        lines.append(f"| {size:,}/{variant} | {v['candidate']['recall_at_300']:.6f} | {t['candidate']['recall_at_300']:.6f} | {s['two_tower']['ndcg_at_50']:.6f} | {s['same_candidates_popularity']['ndcg_at_50']:.6f} | {s['deepfm']['ndcg_at_50']:.6f} | {s['reranked']['ndcg_at_50']:.6f} | {s['reranked']['coverage_at_50']:.6f} |")
    lines+=['',f"valid 선택 결과: `{selection['selected_report']}`.",
        '같은 test 구간을 이전에 확인했으므로 후속 탐색 결과이며 새로운 독립 holdout 성능으로 주장하지 않는다. test가 좋아 보이는 설정으로 다시 선택하지 않았다.','',
        '| 고객/특징 | test 다양성 불가능 | test 제약 위반 |','|---|---:|---:|']
    for size,variant in variants:
        t=read(f'hm_test_{size}_{variant}.json');d=t['reranking']
        lines.append(f"| {size:,}/{variant} | {d['infeasible_diversity_users']} | {d['violating_users']} |")
    sim=read('simulator_comparison.json')
    lines+=['','## 4. 시뮬레이터 교정 전후','',
        '기존/H&M만/Retailrocket만/둘 다 교정의 네 조건을 seed 42·43·44로 생성하고 각각 후보·랭킹 모델을 새로 학습했다.',
        '각 실행은 상품 3,000개·사용자 1,000명·이벤트 100,000건이다. 조건별 생성 정답이 다르므로 추천 점수 차이는 해당 합성 환경의 난이도 변화이며 실제 H&M 품질 향상의 증거가 아니다.',
        '분포 거리는 작을수록 실제 train 통계에 가깝다. ±는 세 seed의 표본 표준편차이며 API 지연이나 full acceptance를 측정한 것이 아니다.','',
        '| 조건 | 카테고리 TV | 상대가격 MAE | view 전이 TV | cart 전이 TV | purchase 전이 TV | test Recall@300 | DeepFM NDCG@50 |','|---|---:|---:|---:|---:|---:|---:|---:|']
    for name,row in sim['conditions'].items():
        columns=[f"{row[k]['mean']:.5f} ± {row[k]['std']:.5f}" for k in ['category_tv','relative_price_mae','view_tv','cart_tv','purchase_tv','recall_at_300','deepfm_ndcg_at_50']]
        lines.append('| '+name+' | '+' | '.join(columns)+' |')
    lines+=['','현재 가격 교정식은 기존 카테고리 가격 범위에 H&M 상대 가격을 곱한다. 기존 상대 가격 차이에 대한 보정계수와는 다르므로, 이미 비싼 카테고리의 차이를 더 키울 수 있다. 가격 MAE 감소 여부는 위 실측으로 판단해야 한다.']
    retail=read('retail_conditional.json')
    lines+=['','## 5. Retailrocket 전이 세분화','',
        '상품 속성은 행동 시각보다 엄격히 앞선 최신 categoryid로 연결하고, 활동량도 같은 시각을 제외한 이전 이벤트 수만 센다.',
        '같은 timestamp의 순서 모호성·세션 종료·경계 검열 정의를 기존 전역 전이 집계와 대조했다. 미관측 그룹은 train 전역 확률로 축소하며 평가에서 제거하지 않는다.',
        '카테고리, 활동량, 두 조건의 결합을 비교하고 평활화 강도를 valid NLL로 선택했다.','',
        '| 방법 | 평활화 강도 | test NLL | test Brier |','|---|---:|---:|---:|']
    for r in retail['test']:lines.append(f"| {r['method']} | {r['alpha']} | {r['metrics']['nll']:.6f} | {r['metrics']['brier']:.6f} |")
    lines+=['',f"선택: `{retail['selected']['method']}`, alpha={retail['selected']['alpha']}.",
        '카테고리별 확률은 익명 Retailrocket 상품 분류 기준이다. 이를 H&M 또는 시뮬레이터 의류 분류에 임의 대응시키지 않았다.','',
        '## 6. DeepFashion 확대 평가와 실패 유형','',
        '공식 train gallery 10,000장, valid/test 각각 5,000장을 평가했다. 기존 1,000장 표본을 각 집합에 포함했고 결과에 따라 재추출하지 않았다.',
        '고정 CLIP의 50개 카테고리와 1,000개 속성 프롬프트를 사용했다. 이미지 검색은 같은 카테고리를 정답으로 삼고 바이트가 같은 사진은 제외한다.',
        '속성은 ±1 주석을 평가하며 0은 unknown으로 제외한다. 양성/음성이 모두 있는 속성의 AP를 평균한다. 사진이나 사람의 식별 정확도가 아니다.','',
        '| split | 최빈 분류 기준선 | Top-1 | Top-5 | macro 정확도 | 이미지 MRR@10 | 이미지 NDCG@10 | 속성 macro AP | 상수점수 속성 AP |','|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    deep=read('deepfashion_expanded.json')
    for split,r in deep['metrics'].items():
        values=[r[k] for k in ['majority_accuracy','zero_shot_top1','zero_shot_top5','macro_category_accuracy','image_category_mrr_at_10','image_category_ndcg_at_10','attribute_macro_ap','attribute_constant_macro_ap']]
        lines.append('| '+split+' | '+' | '.join(f'{v:.6f}' for v in values)+' |')
    lines+=['','카테고리 macro는 표본에서 관측된 분류의 평균이다. 속성 AP는 양성·음성이 모두 관측된 속성의 평균이다.','']
    for split,r in deep['metrics'].items():lines.append(f"- {split}: 관측 카테고리 {len(r['per_category'])}/50개, 평가 가능한 속성 {r['evaluated_attributes']}/1,000개")
    lines+=['','test에서 가장 많은 카테고리 혼동:','']
    for r in deep['metrics']['test']['confusions'][:10]:lines.append(f"- {r['actual']} → {r['predicted']}: {r['count']}장")
    lines+=['','test 표본이 20장 이상인 카테고리 중 정확도가 낮은 항목:','']
    for r in sorted((r for r in deep['metrics']['test']['per_category'] if r['queries']>=20),key=lambda r:r['accuracy'])[:5]:
        lines.append(f"- {r['category']}: 정확도 {r['accuracy']:.2%}, {r['queries']}장")
    lines+=['','test 양성·음성이 각각 50장 이상인 속성 중 AP가 낮은 항목:','']
    for r in sorted((r for r in deep['metrics']['test']['attributes'] if min(r['positives'],r['negatives'])>=50),key=lambda r:r['ap'])[:5]:
        lines.append(f"- {r['attribute']}: AP {r['ap']:.6f}, 상수점수 AP {r['constant_score_ap']:.6f}, 양성 {r['positives']}장")
    lines+=['','위 목록은 표본 수를 함께 보여 주는 오류 분석이다. 전체 macro 지표에서는 희소 카테고리·속성을 성능에 따라 제외하지 않는다.']
    lines+=['','## 재현과 제한','',
        f'설정: `config/external_expansion.yaml`. 파생 데이터·모델·개별 기록 경로는 `{work}/`이다.',
        'v1 입력 준비가 선행돼야 하며, 새 실험에는 설정의 work/results 경로를 함께 새 버전으로 지정한다. 동일 경로의 작업을 동시에 실행하지 않는다.','',
        '```bash','PYTHONHASHSEED=42 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 \\',
        '  ./.venv/bin/python -m src.external_data.expansion_run --task all','',
        './.venv/bin/python -m src.external_data.expansion_run --task verify','```','',
        'CPU 모델 학습·CLIP 추론을 독립 작업과 병행했다. 기록된 실행 시간은 격리된 성능 벤치마크가 아니다.',
        '100만 명 이상 전체 H&M 고객 학습, 신규 독립 holdout, 시뮬레이터 full acceptance, 운영 지연·온라인 A/B·모델 승격은 수행하지 않았다.',
        '실행 근거는 이 폴더의 JSON들과 `simulator/`의 12개 조건별 기록, 해시 대조는 `verification.json`에 있다.']
    (results/'report.md').write_text('\n'.join(lines)+'\n')


def main() -> None:
    parser=argparse.ArgumentParser();parser.add_argument('--task',choices=['all','verify'],default='all');args=parser.parse_args()
    spec,work,results=plan()
    if args.task=='all':
        steps=[('hm_data.json','expansion_data',[]),('hm_tensors.json','expansion_hm',['--task','tensors']),
            (f"hm_valid_{max(spec['training_sizes'])}_metadata.json",'expansion_hm',['--task','scales']),
            ('hm_embeddings.json','expansion_embeddings',[]),('hm_selection.json','expansion_hm',['--task','features']),
            ('hm_test_complete.json','expansion_hm',['--task','test']),
            ('simulator_comparison.json','expansion_simulator',[]),('retail_conditional.json','expansion_retail',[]),
            ('deepfashion_expanded.json','expansion_deepfashion',[])]
        for marker,module,extra in steps:
            if (results/marker).exists():continue
            subprocess.run([sys.executable,'-m','src.external_data.'+module,*extra],check=True)
            if marker=='hm_test_complete.json':write_json(results/marker,dict(status='PASS',selection_sha256=file_hash(results/'hm_selection.json')))
    verify(spec,work,results)
    report(spec,work,results)

if __name__=='__main__':main()
