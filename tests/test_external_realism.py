from __future__ import annotations

import copy
import numpy as np
import pandas as pd
import pytest

from src.common.config import load_config
from src.external_data.calibration import calibrated_config, correct_price_ranges
from src.external_data.realism_metrics import price_stats, purchase_stats, session_stats
from src.external_data.realism_behavior import validate, conditional_rows
from src.simulator.catalog import make_catalog
from src.simulator.users import make_users
from src.simulator.events import make_events
from src.simulator.generate import generate, generation_identity


def profile():
    return dict(version='realism-v4', activity=True, timing=True, transition=True,
                activity_quantiles=[1, 2, 5, 10], within_gap_quantiles=[10, 30, 120],
                activity_thresholds=[5,20], session_seconds=1800,
                transitions=[[[.3,.3,.1,.3],[.1,.1,.5,.3],[.2,.1,.1,.6]]]*3)


def test_price_correction_removes_existing_skew_and_preserves_recipe():
    cfg={'simulator':{'category_price_ranges':{'a':[10000,30000],'b':[20000,60000]}}}
    original=copy.deepcopy(cfg)
    result=correct_price_ranges(cfg,{'a':1,'b':1.5},{'a':1,'b':2},1)
    assert result['simulator']['category_price_ranges']['b']==[15000,45000]
    assert cfg==original
    with pytest.raises(ValueError): correct_price_ranges(cfg,{'a':1},{'a':1},1)
    with pytest.raises(ValueError): correct_price_ranges(cfg,{'a':1,'b':float('nan')},{'a':1,'b':2})


def test_price_denominator_uses_same_mapped_transaction_population():
    frame=pd.DataFrame({'category':['a','a','b',None],'price':[1,1,4,100]})
    result=price_stats(frame)
    assert result['rows']==3 and result['relative_means']=={'a':.5,'b':2.}
    assert sum(result['shares'][k]*r for k,r in result['relative_means'].items())==pytest.approx(1)


def test_purchase_same_day_duplicates_are_not_false_repeats():
    start=pd.Timestamp('2020-01-01',tz='UTC');end=start+pd.Timedelta(days=28)
    frame=pd.DataFrame({'user_id':['u']*4,'product_id':['a','a','a','b'],
                        'timestamp':[start,start,start+pd.Timedelta(days=2),start+pd.Timedelta(days=3)],'category':['tops']*4})
    result=purchase_stats(frame,start,end,['u','inactive'])
    assert result['repeat_rate']==pytest.approx(1/3)
    assert result['activity']['events']==3 and result['activity']['users']==2
    assert result['repurchase_gap_days']==[2.]*5


def test_sessions_censor_edges_and_exclude_ambiguous_gap_pairs():
    start=pd.Timestamp('2020-01-01',tz='UTC');end=start+pd.Timedelta(hours=4)
    f=pd.DataFrame({'user_id':['u']*6,'event':['view','view','cart','purchase','view','view'],
                    'timestamp':start+pd.to_timedelta([0,4000,4060,4060,9000,14390],unit='s'),'row_id':range(6)})
    r=session_stats(f,start,end)
    assert r['sessions']==4 and r['complete_sessions']==2 and r['censored_sessions']==2
    assert r['tied_event_rows']==2 and r['within_gap_seconds'] is None
    assert r['purchase_rate']==.5


def test_conditional_transition_uses_prior_observable_activity():
    p=profile();p['transitions'][0]=[[1,0,0,0]]*3;p['transitions'][1]=[[0,0,0,1]]*3
    validate(p)
    assert conditional_rows(p,np.array([4,5]),'view').tolist()==[[1,0,0,0],[0,0,0,1]]
    p['transitions'][0][0]=[1,1,0,0]
    with pytest.raises(ValueError): validate(p)


def test_opt_in_generator_preserves_causality_versions_and_reproducibility(tmp_path):
    cfg=load_config();cfg['simulator'].update(n_products=450,n_users=120,n_events=4000,realism=profile())
    first=generate(cfg,tmp_path/'first');second=generate(cfg,tmp_path/'second')
    assert first['file_hashes']==second['file_hashes']
    assert first['generator_version']=='4.5.0-realism'
    events=pd.read_parquet(tmp_path/'first/events.parquet');products=pd.read_parquet(tmp_path/'first/products.parquet')
    exposed=pd.read_parquet(tmp_path/'first/impressions.parquet')
    joined=events[events.product_id.notna()].merge(products[['product_id','created_at']])
    assert (joined.timestamp>=joined.created_at).all()
    assert not exposed.duplicated(['request_id','product_id']).any()
    assert events.timestamp.max()<pd.Timestamp(cfg['simulator']['reference_time'])
    assert len(events)==4000
    counts=events.groupby('user_id').size()
    assert counts.max()>counts.median()*1.5
    del cfg['simulator']['realism']
    assert generation_identity(cfg)['generator']=='4.4.0'


def test_zero_transition_remains_zero_with_conditional_profile():
    cfg=load_config();p=profile();p['transitions']=[[[0,1,0,0],[0,0,0,1],[0,0,0,1]]]*3
    cfg['simulator'].update(n_products=450,n_users=120,n_events=4000,realism=p)
    rng=np.random.default_rng(3);products=make_catalog(cfg,rng);users=make_users(cfg,rng)
    events,_=make_events(cfg,products,users,rng)
    assert 'purchase' not in set(events.event_type)


def test_report_runner_only_recovers_documented_optional_density_failure(tmp_path, monkeypatch):
    import importlib.util
    import json
    from pathlib import Path
    spec=importlib.util.spec_from_file_location('realism_report_runner',Path('scripts/run_realism_validation.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    output=tmp_path/'out';output.mkdir();(output/'runs').mkdir()
    for i in range(12):(output/'runs'/f'{i}.json').write_text('{}')
    for name in ['density_control_baseline.json','density_250k_baseline.json','density_250k_combined.json']:
        (output/name).write_text('{}')
    monkeypatch.setattr(module,'plan',lambda:({'users':1000,'products':3000,'evaluation_seeds':[42],'purchase_window_days':28},tmp_path,output))
    monkeypatch.setattr(module,'tune',lambda:None)
    monkeypatch.setattr(module,'publish_reports',lambda out:None)
    trained=[];monkeypatch.setattr(module,'train_models',lambda:trained.append(True))
    def expected_failure():
        raise ValueError('realism event times exceed configured window; choose a larger window or lower density')
    monkeypatch.setattr(module,'evaluate',expected_failure)
    module.run()
    assert trained==[True]
    assert json.loads((output/'density_control_combined_failure.json').read_text())['status']=='FAIL'
    def unexpected_failure():raise ValueError('changed source')
    monkeypatch.setattr(module,'evaluate',unexpected_failure)
    with pytest.raises(ValueError,match='changed source'):module.run()
    assert trained==[True]


def test_public_training_reports_exclude_weights_and_preserve_frozen_results(tmp_path):
    import importlib.util
    from pathlib import Path
    spec=importlib.util.spec_from_file_location('realism_report_publisher',Path('scripts/run_realism_validation.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    source=tmp_path/'models/42-baseline';source.mkdir(parents=True)
    (source/'result.json').write_text('{}');(source/'weights.pt').write_bytes(b'weights')
    module.publish_reports(tmp_path)
    destination=tmp_path/'training_reports/42-baseline'
    assert [p.name for p in destination.iterdir()]==['result.json']
    (source/'result.json').write_text('{"changed":true}')
    with pytest.raises(ValueError,match='changed frozen'):module.publish_reports(tmp_path)
