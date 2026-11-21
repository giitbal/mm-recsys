from __future__ import annotations

import base64
import json
from copy import deepcopy
import subprocess
import sys
from pathlib import Path

import pytest
import requests
import pandas as pd
import pyarrow as pa
from streamlit.testing.v1 import AppTest

import dashboard.data as data
from dashboard.formatting import display_value


def test_display_conversion_handles_timezone_rollover_without_mutating_values():
    original = dict(at='2026-11-11T18:07:08.123Z', other='2026-11-11T20:07:08+02:00',
        naive=pd.Timestamp('2026-11-11 18:07:08'), score=.9663299617,
        nested=[True, 300, None, 4.409705e-106], identifier='v1.0', date='2026-11-11',
        invalid='2026-99-99T00:00:00Z')
    before = deepcopy(original)
    shown = display_value(original)
    assert shown['at'] == shown['other'] == shown['naive'] == '2026-11-12 03:07:08 KST'
    assert shown['score'] == '1.0' and shown['nested'] == [True, 300, None, '4.4e-106']
    assert shown['identifier'] == 'v1.0' and shown['date'] == '2026-11-11'
    assert shown['invalid'] == original['invalid']
    assert display_value('2026-11-12T03:07:08+09:00') == shown['at']
    assert original == before


@pytest.fixture
def report():
    values = dict(mrr=.6, ndcg_at_10=.45, recall_at_300=.8, auc=.96, hit_rate_at_50=.4,
        ndcg_at_50=.2, coverage=.3, search_p95_ms=250., recommend_p95_ms=80., candidate_p95_ms=10., feature_p95_ms=.2)
    targets = dict(mrr=.55, ndcg_at_10=.5, recall_at_300=.3, auc=.7, hit_rate_at_50=.2,
        ndcg_at_50=.08, coverage=.2, search_p95_ms=200., recommend_p95_ms=200., candidate_p95_ms=100., feature_p95_ms=10.)
    rows = [dict(name=k, value=v, target=targets[k], status='PASS' if (v <= targets[k] if k.endswith('_ms') else v >= targets[k]) else 'FAIL',
                 direction='max' if k.endswith('_ms') else 'min', split='benchmark' if k.endswith('_ms') else 'valid') for k, v in values.items()]
    arms = {arm: dict(users=20, cvr=v, ctr=.2, exploration_rate=0. if arm == 'control' else .2)
            for arm, v in [('control', .02), ('treatment', .01)]}
    risks = {name: dict(control=.6, treatment=.5, z_p_value=.2, chi_square_p_value=.2, low_expected_counts=False)
             for name in ('any_click', 'any_purchase')}
    return dict(version=data.VERSION, scale='dev', split='valid', quality_status='FAIL', acceptance='UNMEASURED',
        data_counts=dict(products=1000, users=100, events=5000), metrics=rows, model_version='fixture-v1', identity={},
        search=dict(status='MEASURED', per_mode={mode: dict(mrr=.6, ndcg_at_10=.45) for mode in ('text', 'image', 'hybrid')},
            bm25=dict(text=dict(mrr=.4, ndcg_at_10=.3), hybrid=dict(mrr=.4, ndcg_at_10=.3), image=dict(status='UNMEASURED')),
            tradeoff=[dict(mode=mode, parameter='efSearch', requested_value=32, vector_p95_ms=1., mrr=.6, ndcg_at_10=.45)
                      for mode in ('text', 'image', 'hybrid')]),
        recommendation=dict(status='MEASURED', cohort=dict(total_users=100, truth_users=80, cold=10),
            metrics={name: dict(hit_rate_at_50=.4, ndcg_at_50=.2, coverage=.3) for name in ('train_popularity', 'two_tower', 'deepfm', 'full_pipeline')},
            classification=dict(cvr=dict(auc=None, auc_status='UNDEFINED_SINGLE_CLASS', samples=200, positives=0))),
        ab=dict(status='MEASURED', days=30, arms=arms, inference=dict(cvr=dict(relative_lift=-.5, difference_ci95=[-.02, -.001], z_p_value=.01), independent_user_risks=risks)))


def offline(*args, **kwargs):
    return dict(ok=False, status_code=None, data=None, error='fixture: API unavailable')


def test_large_ct_log_reads_latest_utf8_records_and_preserves_invalid_count(tmp_path):
    path = tmp_path / 'ct_log.jsonl'
    with path.open('wb') as stream:
        stream.write(b'x' * 11_000_000 + b'\n')
        for i in range(120):
            stream.write((json.dumps(dict(index=i, message='학습 관측'), ensure_ascii=False) + '\n').encode())
        stream.write(b'\xff\n{"partial":')
    result = data.ct_log(tmp_path, limit=102)
    assert result['status'] == 'MEASURED' and not result['truncated']
    assert result['invalid_lines'] == 2
    assert [row['index'] for row in result['rows']] == list(range(20, 120))
    assert result['rows'][-1]['message'] == '학습 관측'
    path.write_bytes(b'x' * 11_000_000)
    assert data.ct_log(tmp_path)['truncated']
    with pytest.raises(ValueError):
        data.ct_log(tmp_path, limit=0)


@pytest.mark.parametrize('api_url,public_url,expected', [
    ('http://api-server:8000', '', 'http://localhost:19000'),
    ('http://api-server:8000', 'https://demo.example/api/', 'https://demo.example/api'),
    ('http://localhost:18000', '', 'http://localhost:18000'),
])
def test_browser_link_uses_public_address_without_changing_http_transport(tmp_path, monkeypatch, api_url, public_url, expected):
    (tmp_path / 'config.yaml').write_text('paths: {results_dir: results}\n')
    monkeypatch.setenv('CONFIG_PATH', str(tmp_path / 'config.yaml'))
    monkeypatch.setenv('API_URL', api_url)
    monkeypatch.setenv('PUBLIC_API_URL', public_url)
    monkeypatch.setenv('API_PORT', '19000')
    config = data.settings(tmp_path)
    assert config['api_url'] == api_url
    assert config['public_api_url'] == expected


def test_test_report_is_preferred_and_integration_receipt_is_visible(tmp_path, monkeypatch, report):
    (tmp_path / 'evaluation_dev_valid.json').write_text(json.dumps(report))
    report.update(split='test', integration=dict(stage='INTEGRATE', status='UNMEASURED'))
    (tmp_path / 'evaluation_dev_test.json').write_text(json.dumps(report))
    monkeypatch.setenv('RESULTS_DIR', str(tmp_path))
    monkeypatch.setattr(data, 'api_call', offline)
    app = AppTest.from_file('dashboard/app.py', default_timeout=20).run()
    assert not app.exception
    assert app.selectbox[0].value.name == 'evaluation_dev_test.json'
    assert any(item.label == '최종 통합 검사 근거' for item in app.expander)
    assert next(m.value for m in app.metric if m.label == '최종 종합 품질') == 'UNMEASURED'


def test_missing_full_test_falls_back_to_full_valid_before_dev(tmp_path, monkeypatch, report):
    (tmp_path / 'evaluation_dev_test.json').write_text(json.dumps(dict(report, split='test')))
    (tmp_path / 'evaluation_full_valid.json').write_text(json.dumps(dict(report, scale='full')))
    monkeypatch.setenv('RESULTS_DIR', str(tmp_path))
    monkeypatch.setenv('SCALE', 'full')
    monkeypatch.setattr(data, 'api_call', offline)
    app = AppTest.from_file('dashboard/app.py', default_timeout=20).run()
    assert not app.exception
    assert app.selectbox[0].value.name == 'evaluation_full_valid.json'


def test_four_tabs_charts_and_metric_tables_match_json(tmp_path, monkeypatch, report):
    path = tmp_path / 'evaluation_dev_valid.json'
    path.write_text(json.dumps(report))
    monkeypatch.setenv('RESULTS_DIR', str(tmp_path))
    monkeypatch.setattr(data, 'api_call', offline)
    app = AppTest.from_file('dashboard/app.py', default_timeout=20).run()
    assert not app.exception
    assert [tab.label for tab in app.tabs] == ['검색', '추천', 'A/B 실험', '시스템', 'EDA·구매 이력', '상품·CLIP']
    assert len(app.get('plotly_chart')) == 5
    metrics = {m.label: m.value for m in app.metric}
    assert metrics['측정 기준 판정'] == 'FAIL' and metrics['최종 종합 품질'] == 'UNMEASURED'
    assert metrics['CVR 상대 lift'] == '-50.0%' and metrics['API 연결'] == '연결 안 됨'
    observed = {}
    for frame in app.dataframe:
        df = frame.value
        if '측정값' in df:
            observed.update({row['지표']: (row['측정값'], row['판정']) for row in df.to_dict('records')})
    from dashboard.app import LABELS
    assert len(observed) == len(report['metrics'])
    for row in report['metrics']:
        assert observed[LABELS[row['name']]] == (row['value'], row['status'])
    spec = json.loads(app.get('plotly_chart')[0].proto.spec)
    assert spec['data'][0]['y'] == [.6, .6, .6]
    assert spec['data'][1]['y'] == [.4, None, .4]
    assert spec['layout']['annotations'][0]['text'] == '기준 0.55'
    assert spec['layout']['yaxis']['tickformat'] == '.1f'
    assert spec['layout']['yaxis']['hoverformat'] == '.1f'
    shown = pa.ipc.open_stream(app.dataframe[0].proto.styler.display_values).read_all().to_pandas()
    assert shown['측정값'].tolist() == ['0.6', '0.5']
    assert shown['기준'].tolist() == ['0.55', '0.5']


def test_absent_and_malformed_results_render_without_fake_values(tmp_path, monkeypatch):
    monkeypatch.setenv('RESULTS_DIR', str(tmp_path))
    monkeypatch.setattr(data, 'api_call', offline)
    for content in (None, '{not JSON}', '{"version":"old"}'):
        if content is not None:
            (tmp_path / 'evaluation_dev_valid.json').write_text(content)
        app = AppTest.from_file('dashboard/app.py', default_timeout=20).run()
        assert not app.exception and len(app.tabs) == 6
        assert not app.get('plotly_chart')
        assert all(m.label not in ('측정 기준 판정', 'Control CVR') for m in app.metric)


def test_demos_use_shared_http_contract_and_empty_search_is_local(tmp_path, monkeypatch):
    monkeypatch.setenv('RESULTS_DIR', str(tmp_path))
    calls = []
    def api(url, method, route, **kwargs):
        calls.append((method, route, kwargs))
        if route == '/api/search':
            return dict(ok=True, data=dict(search_type='text', latency_ms=2., total_count=100,
                        results=[dict(product_id='p1', name='shirt', score=.8, price=1000)]))
        if route == '/api/recommend':
            return dict(ok=True, data=dict(recommendations=[dict(product_id='p2', score=.7, reason='popular')],
                        pipeline_latency=dict(total_ms=3.), session_context=dict(session_interest=None)))
        return offline()
    monkeypatch.setattr(data, 'api_call', api)
    app = AppTest.from_file('dashboard/app.py', default_timeout=20).run()
    next(b for b in app.button if b.label == '검색 실행').click().run()
    assert not any(route == '/api/search' for _, route, _ in calls)
    app.text_input(key='query_text').set_value(' black shirt ')
    next(b for b in app.button if b.label == '검색 실행').click().run()
    assert next(kwargs['payload'] for _, route, kwargs in calls if route == '/api/search') == dict(query_text='black shirt', top_k=10)
    next(b for b in app.button if b.label == '추천 실행').click().run()
    assert next(kwargs['params'] for _, route, kwargs in calls if route == '/api/recommend') == dict(user_id='U000001', top_n=10)
    assert not app.exception
    image = b'fixture image bytes; server validates decoding'
    assert base64.b64decode(data.search_payload('', image, 10)['query_image']) == image
    assert data.search_payload('shirt', image, 10)['query_text'] == 'shirt'
    with pytest.raises(ValueError):
        data.search_payload('', None, 10)


def test_dashboard_is_standalone_and_does_not_import_model_libraries():
    command = 'import sys; import dashboard.app; assert "torch" not in sys.modules; assert "faiss" not in sys.modules; print("standalone PASS")'
    result = subprocess.run([sys.executable, '-c', command], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_result_path_safety_nonfinite_values_and_read_only_io(tmp_path, monkeypatch, report):
    root = tmp_path / 'results'
    root.mkdir()
    path = root / 'evaluation_dev_valid.json'
    path.write_text(json.dumps(report))
    outside = tmp_path / 'outside.json'
    outside.write_text(json.dumps(report))
    with pytest.raises(ValueError, match='경로'):
        data.read_report(outside, root)
    for bad in (float('nan'), float('inf'), True):
        report['metrics'][0]['value'] = bad
        path.write_text(json.dumps(report))
        with pytest.raises(ValueError):
            data.read_report(path, root)
    report['metrics'][0]['value'] = .6
    path.write_text(json.dumps(report))
    (root / 'ct_log.jsonl').write_text('{"fixture":true}\ninvalid\n')
    def no_write(*args, **kwargs):
        raise AssertionError('dashboard must not write result files')
    monkeypatch.setattr(Path, 'write_text', no_write)
    monkeypatch.setattr(Path, 'write_bytes', no_write)
    assert data.read_report(path, root)['scale'] == 'dev'
    assert data.ct_log(root)['invalid_lines'] == 1


def test_api_unavailable_is_explicit(monkeypatch):
    def fail(*args, **kwargs):
        raise requests.ConnectionError('fixture outage')
    monkeypatch.setattr(requests.Session, 'request', fail)
    response = data.api_call('http://localhost:1', 'GET', '/health')
    assert not response['ok'] and response['status_code'] is None and response['data'] is None
    with pytest.raises(ValueError):
        data.api_call('http://localhost:1', 'POST', '/api/admin/reload')


def test_live_model_version_and_nested_ct_logs_are_distinct_from_saved_measurement(tmp_path, monkeypatch, report):
    (tmp_path / 'evaluation_dev_valid.json').write_text(json.dumps(report))
    (tmp_path / 'ct_log.jsonl').write_text(json.dumps(dict(event='promoted', scope='controlled_fixture',
        version='v1.1', at='2026-11-11T18:07:08.123Z', comparison=dict(candidate=dict(ctr_auc=.9)), hashes=dict(candidate='abc'))) + '\n' +
        json.dumps(dict(event='rollback', version='v1.0')) + '\n')
    monkeypatch.setenv('RESULTS_DIR', str(tmp_path))
    def api(url, method, route, **kwargs):
        return dict(ok=True, data=dict(status='ok' if route == '/health' else 'ready', model_version='v1.1'))
    monkeypatch.setattr(data, 'api_call', api)
    app = AppTest.from_file('dashboard/app.py', default_timeout=20).run()
    assert not app.exception
    assert {m.label: m.value for m in app.metric}['현재 모델 버전'] == 'v1.1'
    assert any('fixture-v1' in caption.value for caption in app.caption)
    assert any('controlled_fixture' in caption.value for caption in app.caption)
    frame = next(df.value for df in app.dataframe if 'event' in df.value)
    assert frame['comparison.candidate.ctr_auc'].iloc[0] == .9
    assert frame['at'].iloc[0] == '2026-11-11T18:07:08.123Z'
    element = next(df for df in app.dataframe if 'event' in df.value)
    shown = pa.ipc.open_stream(element.proto.styler.display_values).read_all().to_pandas()
    assert shown['at'].iloc[0] == '2026-11-12 03:07:08 KST'
    assert shown['comparison.candidate.ctr_auc'].iloc[0] == '0.9'


def test_packaged_report_renders_charts_then_prefers_new_runtime_measurement(tmp_path, monkeypatch, report):
    reference = Path('docs/submission/dashboard/evaluation_full_test.json').resolve()
    monkeypatch.setenv('DASHBOARD_REFERENCE_REPORT', str(reference))
    monkeypatch.setenv('RESULTS_DIR', str(tmp_path))
    monkeypatch.setenv('SCALE', 'full')
    monkeypatch.setattr(data, 'api_call', offline)
    app = AppTest.from_file('dashboard/app.py', default_timeout=20).run()
    assert not app.exception and app.selectbox[0].value == reference
    assert all(tab.get('plotly_chart') for tab in app.tabs[:3])
    assert any('새 도안 카탈로그에서 측정한' in item.value for item in app.info)
    archived = json.loads(reference.read_text())
    chart = json.loads(app.tabs[2].get('plotly_chart')[1].proto.spec)
    for trace in chart['data']:
        estimate = archived['ab']['inference'][trace['x'][0].lower()]
        assert trace['y'] == pytest.approx([100 * estimate['difference']])
        assert trace['customdata'][0] == pytest.approx([100 * bound for bound in estimate['difference_ci95']])
        p_value = estimate['z_p_value']
        assert trace['text'] == ['p < 0.001' if p_value < .001 else f'p = {p_value:.3f}']

    report.update(scale='full', ab={'status': 'UNMEASURED'})
    live = tmp_path / 'evaluation_full_valid.json'
    live.write_text(json.dumps(report))
    with pytest.raises(ValueError, match='제출 보고서'):
        data.read_reference(live)
    app.run()
    assert not app.exception and app.selectbox[0].value == live
    assert next(metric.value for metric in app.metric if metric.label == '측정 기준 판정') == 'FAIL'
    assert not app.tabs[2].get('plotly_chart')
    report.update(data_fingerprint=archived['data_fingerprint'])
    report['recommendation']['models'] = archived['recommendation']['models']
    live.write_text(json.dumps(report))
    app.run()
    assert any('현재 배포의 A/B 측정 전' in item.value for item in app.tabs[2].caption)


def test_reference_compares_data_search_and_active_recommender(tmp_path):
    from dashboard.assets import reference_identity
    from src.common.artifacts import file_hash, write_json
    models, results = tmp_path / 'models', tmp_path / 'results'
    write_json(tmp_path / 'split_manifest.json', {'generation_fingerprint': 'same'})
    write_json(results / 'deployment.json', dict(data_fingerprint='same', data_dir=str(tmp_path),
                                                model_dir=str(models), search_subdir='search'))
    write_json(models / 'registry.json', {'active': 'v1.0'})
    bundles = {}
    for kind, folder in [('candidate', ''), ('ranking', 'ranking'), ('session', 'session')]:
        bundles[kind] = {'hashes': {'weights': kind}}
        write_json(models / 'v1.0' / folder / 'meta.json', bundles[kind])
    search = {'embeddings': {'fingerprint': 'e', 'files': {'text.npy': 'vector-hash'}},
              'index': {'fingerprint': 'i', 'files': {'text.faiss': 'index-hash'}}}
    for key, directory in [('embeddings', 'embeddings'), ('index', 'indexes')]:
        identity = search[key]['fingerprint']
        write_json(models / 'search' / f'{directory}_current.json', {'fingerprint': identity})
        write_json(models / 'search' / directory / identity / 'manifest.json', search[key])
    report = dict(model_version='v1.0', data_fingerprint='same', search={'models': search},
                  identity={'data_manifest_sha256': file_hash(tmp_path / 'split_manifest.json')},
                  recommendation={'models': bundles})
    assert '일치합니다' in reference_identity(report, results)
    index_manifest = models / 'search/indexes/i/manifest.json'
    write_json(index_manifest, {'fingerprint': 'i', 'files': {'text.faiss': 'rebuilt-index-hash'}})
    assert '검색 파일 해시는 제출 기준과 다릅니다' in reference_identity(report, results)
    write_json(index_manifest, search['index'])
    from src.common.artifacts import fingerprint
    recipe = {'candidate': {'max_grad_norm': 10.0}}
    expected_index = {'config_fingerprint': fingerprint({'candidate': {}}), 'index_sha256': 'same-index'}
    report['recommendation']['models']['index'] = expected_index
    bundles['candidate']['hashes']['index_manifest.json'] = 'legacy-manifest'
    write_json(models / 'registry.json', {'active': 'v1.0', 'versions': {'v1.0': {'config': {'recommend': recipe}}}})
    index_path = models / 'v1.0/index_manifest.json'
    active_index = dict(expected_index, config_fingerprint=fingerprint(recipe))
    for digest, expected_text in [('different-index', '추천 모델 산출물은 제출 기준과 다릅니다'), ('same-index', '일치합니다')]:
        write_json(index_path, dict(active_index, index_sha256=digest))
        write_json(models / 'v1.0/meta.json', {'hashes': {**bundles['candidate']['hashes'], 'index_manifest.json': file_hash(index_path)}})
        assert expected_text in reference_identity(report, results)
    write_json(models / 'search/indexes_current.json', {'fingerprint': 'other'})
    assert '검색 번들은 제출 기준과 다릅니다' in reference_identity(report, results)
    write_json(models / 'registry.json', {'active': 'v2.0'})
    assert '활성 모델 버전' in reference_identity(report, results)
    report['data_fingerprint'] = 'other'
    assert '다른 데이터' in reference_identity(report, results)

def test_changed_reranking_policy_marks_old_measurements(tmp_path):
    from dashboard.assets import different_recommendation_policy
    from src.common.artifacts import write_json
    sources = {'src/recommendation/reranking.py':'new'}
    report = {'identity':{'source_hashes':dict(sources)}}
    write_json(tmp_path/'deployment.json', {'recommendation_policy_sources':sources})
    assert not different_recommendation_policy(report, tmp_path)
    report['identity']['source_hashes']['src/recommendation/reranking.py'] = 'old'
    assert different_recommendation_policy(report, tmp_path)


def test_ab_display_requires_the_deployed_reranking_policy(tmp_path):
    from dashboard.assets import ab_result
    from src.common.artifacts import write_json

    data = tmp_path / 'data'
    models = tmp_path / 'models'
    policy = {'src/recommendation/reranking.py': 'current'}
    write_json(data / 'split_manifest.json', {'generation_fingerprint': 'same'})
    write_json(tmp_path / 'deployment.json', dict(data_dir=str(data), model_dir=str(models),
               data_fingerprint='same', recommendation_policy_sources=policy))
    bundles = {k: {'hashes': {'weights': k}} for k in ('candidate', 'ranking', 'session')}
    for kind, subdir in [('candidate', ''), ('ranking', 'ranking'), ('session', 'session')]:
        write_json(models / 'v1.0' / subdir / 'meta.json', bundles[kind])
    write_json(tmp_path / 'ab_test.json', dict(status='PASS', identity=dict(
        data_fingerprint='same', bundle_metadata=bundles, source_hashes={next(iter(policy)): 'old'})))
    assert ab_result(tmp_path) is None
    report = dict(ab=dict(status='MEASURED', run_id='current-run'), data_fingerprint='same',
                  identity=dict(source_hashes=policy), recommendation=dict(models=bundles))
    write_json(tmp_path / 'evaluation_full_test.json', report)
    assert ab_result(tmp_path)['run_id'] == 'current-run'
    report['recommendation']['models']['ranking'] = {'hashes': {'weights': 'other'}}
    write_json(tmp_path / 'evaluation_full_test.json', report)
    assert ab_result(tmp_path) is None
