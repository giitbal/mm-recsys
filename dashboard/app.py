"""Evaluation room (Figma design 2026-11-19): saved measurements by tab; demos call the HTTP API."""
from __future__ import annotations

import math
from pathlib import Path
import statistics
import sys

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dashboard.data import (REQUIREMENTS, api_call, bundles, ct_log, read_json, read_report, search_payload,
                            settings)
from dashboard.explore import catalog_section, data_tab, product_cards
from dashboard.assets import ab_result
from dashboard.formatting import display_frame, display_value
from dashboard.style import BASE, CSS, GRAY, INDIGO, ORANGE, TEAL, baseline, chart

TABS = ['개요', '데이터', '검색', '추천', 'A/B', '시스템']
SECTIONS = {
    '개요': [('과제 기능 4가지', 'features'), ('요구사항 50개', 'requirements'), ('동료 평가 질문 → 확인할 곳', 'peer-review'),
           ('한계', 'limits')],
    '데이터': [('평가 프로토콜: 시간 분할', 'protocol'), ('페르소나 6개 비교', 'personas'), ('카탈로그와 이벤트', 'catalog'),
            ('무결성 검사', 'integrity'), ('사용자 구매 원장', 'ledger'), ('외부 데이터셋 검증 (선택 과제: 학습 데이터셋 추천)', 'external')],
    '검색': [('같은 쿼리로 비교한 검색 품질', 'search-quality'), ('ANN 설정의 속도-정확도 (valid 진단)', 'ann'),
           ('모드별 HTTP 응답 시간', 'search-http'), ('상품과 CLIP 벡터', 'clip')],
    '추천': [('베이스라인 비교', 'baselines'), ('후보 생성 Recall과 랭킹 AUC', 'recall-auc'), ('코호트와 재정렬 제약', 'cohorts')],
    'A/B': [('사용자 단위 A/B 실험', 'ab'), ('표본', 'ab-sample'), ('오프라인 지표와 온라인(합성 A/B) 지표가 어긋나는 이유', 'offline-online')],
    '시스템': [('응답 시간', 'latency'), ('저장된 응답 시간 측정 (지표마다 자기 축)', 'latency-samples'), ('측정 조건', 'conditions'),
            ('CT: 모니터 · 재학습 판정 · 버전', 'ct')],
}
LABELS = dict(mrr='MRR', ndcg_at_10='NDCG@10', recall_at_300='Recall@300', auc='CTR AUC',
    hit_rate_at_50='HitRate@50', ndcg_at_50='NDCG@50', coverage='Coverage',
    search_p95_ms='검색 HTTP p95', recommend_p95_ms='추천 HTTP p95',
    candidate_p95_ms='후보 생성 p95', feature_p95_ms='Redis 조회 p95')
HELP = dict(mrr='첫 정답 순위의 역수 평균', ndcg_at_10='상위 10개 안에서 정답이 높은 순위에 있을수록 커지는 점수',
    recall_at_300='후보 300개 안에 미래 정답이 들어간 비율', auc='클릭 예측의 순서 정확도 (0.5 = 무작위)',
    hit_rate_at_50='추천 50개 안에 미래 정답이 하나라도 있는 사용자 비율', ndcg_at_50='추천 50개 안 정답 순위 가중 점수',
    coverage='전체 카탈로그 중 한 번이라도 추천된 상품 비율', search_p95_ms='단건 요청 100회 중 95번째로 느린 응답 (가장 느린 모드)',
    recommend_p95_ms='단건 요청 100회 중 95번째로 느린 응답', candidate_p95_ms='사용자 벡터 계산과 FAISS 후보 300개 검색 시간',
    feature_p95_ms='최근 조회·프로필 조회 시간')
GROUPS = [('검색 품질', ('mrr', 'ndcg_at_10')),
          ('추천 품질', ('recall_at_300', 'auc', 'hit_rate_at_50', 'ndcg_at_50', 'coverage')),
          ('응답 시간', ('search_p95_ms', 'recommend_p95_ms', 'candidate_p95_ms', 'feature_p95_ms'))]
STATUS = dict(PASS='통과', FAIL='미달', UNMEASURED='미측정', MEASURED='측정됨')
PERCENT = {'recall_at_300', 'hit_rate_at_50', 'coverage'}
MODES = [('text', '텍스트'), ('image', '이미지'), ('hybrid', '하이브리드')]
PIPELINES = dict(train_popularity='인기순', two_tower='Two-Tower 단독', deepfm='DeepFM 단독', full_pipeline='전체 파이프라인')


def fmt(name: str, value) -> str:
    if value is None:
        return '미측정'
    if name.endswith('_ms'):
        return f'{value:.1f}ms'
    return f'{value:.1%}' if name in PERCENT else f'{value:.3f}'


def margin(row: dict) -> str:
    """How far a measured value clears its target, in the words the design uses."""
    value, target = row.get('value'), row['target']
    if value is None:
        return '미측정'
    if row['name'].endswith('_ms'):
        return f'기준보다 {target / value:.1f}배 빠름' if value else '측정값 0'
    return f'기준의 {value / target:.1f}배'


def target_text(row: dict) -> str:
    unit = 'ms' if row['name'].endswith('_ms') else ''
    return f"{'≤' if row['name'].endswith('_ms') else '≥'} {row['target']:g}{unit}"


def metric_table(report: dict, names: tuple[str, ...] | None = None) -> pd.DataFrame:
    return pd.DataFrame([dict(지표=LABELS.get(row['name'], row['name']), 측정값=fmt(row['name'], row['value']),
        기준=target_text(row), 판정=STATUS.get(row['status'], row['status']), 평가구간=row['split'])
        for row in report.get('metrics', []) if names is None or row['name'] in names])


def table(frame: pd.DataFrame, **kwargs) -> None:
    st.dataframe(frame, hide_index=True, use_container_width=True, **kwargs)


def section(tab: str, index: int, title: str | None = None) -> None:
    name, anchor = SECTIONS[tab][index]
    st.subheader(title or name, anchor=anchor)


def summary(rows: list[dict]) -> str:
    passed = sum(row['status'] == 'PASS' for row in rows)
    splits = ', '.join(sorted({row['split'] for row in rows}))
    return f"{'모두 통과' if passed == len(rows) else f'{passed}/{len(rows)} 통과'} · {splits} 분할"


# ── 개요 ─────────────────────────────────────────────────────────────────────
def overview_tab(report: dict, bundle: dict | None, config: dict) -> None:
    rows = report.get('metrics', [])
    if not rows:
        st.info('평가 결과가 없습니다.')
        return
    passed = sum(row['status'] == 'PASS' for row in rows)
    measured = [row for row in rows if row['value'] is not None and row['value'] > 0]
    st.markdown(f"## 과제 수치 기준 {len(rows)}개를 모두 넘었습니다." if passed == len(rows)
                else f'## 과제 수치 기준 {len(rows)}개 중 {passed}개를 넘었습니다.')
    if measured:
        ratio = lambda row: row['target'] / row['value'] if row['name'].endswith('_ms') else row['value'] / row['target']
        tight = min(measured, key=ratio)
        st.markdown(f"여유가 가장 적은 항목은 {LABELS.get(tight['name'], tight['name'])}({margin(tight)})입니다.")
    with st.container(key='verdict'):
        a, b, c = st.columns(3)
        a.metric('측정 기준 판정', STATUS.get(report['quality_status'], report['quality_status']))
        b.metric('측정 지표', f"{sum(row['value'] is not None for row in rows)}/{len(rows)}")
        c.metric('최종 종합 품질', STATUS.get(report['acceptance'], report['acceptance']))
    st.caption(f'측정 기준 판정은 수치 기준 {len(rows)}개, 최종 종합 품질은 그 결과와 필수 통합 검사를 함께 본 판정입니다. '
               '값은 원본 JSON 그대로입니다.')
    by_name = {row['name']: row for row in rows}
    for title, names in GROUPS:
        group = [by_name[name] for name in names if name in by_name]
        if not group:
            continue
        st.markdown(f'**{title}** · {summary(group)}')
        for column, row in zip(st.columns(len(group)), group):
            with column.container(border=True):
                st.metric(LABELS[row['name']], fmt(row['name'], row['value']), help=HELP.get(row['name']))
                st.caption(f"{target_text(row)} · {margin(row)}" + ('' if row['status'] == 'PASS' else f" · {STATUS.get(row['status'])}"))
    with st.expander(f'수치 기준 {len(rows)}개 표로 보기'):
        table(metric_table(report))
    integration = report.get('integration')
    if integration:
        with st.expander('최종 통합 검사 근거'):
            checks = integration.get('checks', {})
            if checks:
                table(pd.DataFrame([dict(검사=name, 판정=STATUS.get(row.get('status'), row.get('status')), 근거=row.get('source', '—'))
                                    for name, row in checks.items()]))
            st.json(display_value(integration))
    requirements = read_json(config['results_dir'] / REQUIREMENTS, config['results_dir'])
    features(requirements, integration or {})
    requirement_sections(requirements)
    section('개요', 3)
    for line in report.get('limitations', []):
        st.markdown(f'- {line}')


def features(requirements: dict | None, integration: dict) -> None:
    section('개요', 0)
    if not requirements:
        st.info('요구사항 점검 결과(requirements.json)가 없습니다.')
        return
    status = {row['id']: STATUS.get(row['status'], row['status']) for row in requirements['requirements']}
    checks = integration.get('checks', {})
    check = lambda name: STATUS.get(checks.get(name, {}).get('status'), '미측정') if checks else '미측정'
    rows = [('검색 API', ['S2'], check('api_schemas')), ('추천 API', ['R13'], check('api_schemas')),
            ('Streamlit 대시보드', ['A3', 'U4'], '해당 없음'), ('Docker Compose', ['F2', 'F3'], check('docker_reproduction'))]
    table(pd.DataFrame([dict(기능=name, 요구ID=', '.join(ids), 요구사항판정=' / '.join(status.get(i, '미측정') for i in ids), 통합검사=result)
                        for name, ids, result in rows]))
    with st.expander('근거'):
        st.caption(f"요구사항 점검 {display_value(requirements.get('generated_at'))} 실행 기준 · 통합 검사는 이 결과 묶음의 integration.checks")
        st.json(display_value({key: requirements.get(key) for key in ('scope', 'interpretation', 'data_fingerprint')}))


def requirement_sections(requirements: dict | None) -> None:
    if not requirements:
        return
    items = requirements['requirements']
    section('개요', 1, f'요구사항 {len(items)}개')
    passed = sum(row['status'] == 'PASS' for row in items)
    st.caption(f"{passed}/{len(items)} 통과 · 점검 시각 {display_value(requirements.get('generated_at'))} · 이 결과 묶음과 다른 실행일 수 있습니다.")
    table(pd.DataFrame([dict(ID=row['id'], 요구사항=row['requirement'], 판정=STATUS.get(row['status'], row['status']),
                             근거=row.get('evidence', '—')) for row in items]), height=420)
    review = requirements.get('peer_review', {})
    if review:
        section('개요', 2)
        text = {row['id']: row['requirement'] for row in items}
        table(pd.DataFrame([dict(질문=question, 판정=STATUS.get(row['status'], row['status']), 요구ID=', '.join(row['requirements']),
                                 확인할곳=' / '.join(text.get(i, i) for i in row['requirements'])) for question, row in review.items()]))


# ── 검색 ─────────────────────────────────────────────────────────────────────
def view_mode(key: str) -> str:
    # A horizontal radio drawn as a segmented control (style.py); AppTest cannot drive st.segmented_control in 1.41.
    return st.radio('보기', ['측정 결과', '직접 해보기'], key=key, horizontal=True, label_visibility='collapsed')


def search_tab(report: dict, bundle: dict | None, config: dict) -> None:
    if view_mode('search_view') == '직접 해보기':
        search_demo(config)
        return
    search = report.get('search', {})
    if search.get('status') != 'MEASURED':
        st.info('검색 품질이 아직 측정되지 않았습니다.')
        return
    targets = {row['name']: row for row in report.get('metrics', [])}
    section('검색', 0)
    mrr, target = search.get('primary', {}).get('mrr'), targets.get('mrr', {}).get('target')
    lines = []
    if mrr is not None and target:
        lines.append(f"CLIP 검색 MRR은 {mrr:.3f}로 기준({target:g})보다 {'높습니다' if mrr >= target else '낮습니다'}.")
    behind = [(label, search['per_mode'][mode]['mrr'] / search['bm25'][mode]['mrr'] - 1) for mode, label in MODES
              if search['bm25'].get(mode, {}).get('mrr') and search['per_mode'][mode]['mrr'] < search['bm25'][mode]['mrr']]
    if behind:
        lines.append(f"다만 {'·'.join(label for label, _ in behind)} 모드에서는 BM25가 더 높았습니다"
                     f"(CLIP의 BM25 대비 MRR {', '.join(f'{label} {lift:+.1%}' for label, lift in behind)}).")
    if lines:
        st.markdown(f"**{' '.join(lines)}**")
    st.caption('MRR — 첫 정답 순위의 역수 평균 · NDCG@10 — 상위 10개 안에서 정답이 높은 순위에 있을수록 커지는 점수')
    queries = search.get('primary', {}).get('queries')
    columns = st.columns(2)
    for column, key in zip(columns, ('mrr', 'ndcg_at_10')):
        clip = [search['per_mode'][mode][key] for mode, _ in MODES]
        bm25 = [search['bm25'].get(mode, {}).get(key) for mode, _ in MODES]
        fig = go.Figure()
        fig.add_bar(name='CLIP', x=[label for _, label in MODES], y=clip, marker_color=INDIGO,
                    text=[f'{v:.3f}' for v in clip], textposition='outside')
        fig.add_bar(name='BM25', x=[label for _, label in MODES], y=bm25, marker_color=GRAY,
                    text=[f'{v:.3f}' if v is not None else 'BM25 해당 없음' for v in bm25], textposition='outside')
        row = targets.get(key)
        primary = search.get('primary', {}).get(key)
        title = f'CLIP {LABELS[key]}' + (f' {primary:.3f}' if primary is not None else '')
        if row:
            baseline(fig, row['target'], f"기준 {row['target']:g}")
            if primary is not None:
                title += f" · {margin(dict(row, value=primary))}"
        if queries:
            title += f' (쿼리 {queries}개)'
        chart(fig, title, 330, legend=True).update_yaxes(range=[0, 1.15], tickformat='.1f')
        column.plotly_chart(fig, use_container_width=True)
        with column.expander('표로 보기'):
            table(pd.DataFrame(dict(모드=[label for _, label in MODES], CLIP=clip, BM25=bm25)))
    st.caption('이미지 단독 질의에는 BM25가 적용되지 않습니다(“BM25 해당 없음”, 0이 아님).')
    agreement = {label: search['per_mode'][mode].get('ann_vs_exact') for mode, label in MODES}
    if any(agreement.values()):
        with st.expander('ANN 인덱스와 exact 검색의 일치(품질 지표와 별개)'):
            table(pd.DataFrame([dict(모드=label, k=row.get('k'), 질의=row.get('queries'), 정답겹침=row.get('label_overlap_recall'),
                                     점수일치=row.get('exact_score_tie_aware_agreement')) for label, row in agreement.items() if row]))
    ann_section(search, bundle, config)
    http_section(report)
    st.divider()
    section('검색', 3)
    catalog_section(config)


def ann_section(search: dict, bundle: dict | None, config: dict) -> None:
    section('검색', 1)
    rows = search.get('tradeoff') or []
    if not rows and bundle and (bundle['folder'] / 'quality_full_valid.json').is_file():
        # The test report never tunes ANN; show the paired valid diagnosis from the same bundle.
        try:
            rows = read_report(bundle['folder'] / 'quality_full_valid.json', config['results_dir'])['search'].get('tradeoff') or []
        except (OSError, ValueError, KeyError) as error:
            st.warning(f'valid 진단을 읽을 수 없습니다: {error}')
    if not rows:
        st.info('이 결과 묶음에는 ANN 설정 탐색(valid 진단)이 없습니다.')
        return
    speeds = [row['vector_p95_ms'] for row in rows]
    same = all(len({row['mrr'] for row in rows if row['mode'] == mode}) <= 1 for mode, _ in MODES)
    title = (f'ANN 설정 {len(rows)}개 모두 정확도가 같았고 속도만 {min(speeds):.2f}~{max(speeds):.2f}ms 사이에서 달라졌습니다(valid 진단)'
             if same else f'ANN 설정 {len(rows)}개의 정확도와 속도 (valid 진단)')
    fig = go.Figure()
    for (mode, label), color, symbol in zip(MODES, (INDIGO, TEAL, ORANGE), ('circle', 'square', 'diamond')):
        values = sorted((row for row in rows if row['mode'] == mode), key=lambda row: row['vector_p95_ms'])
        fig.add_scatter(name=label, x=[row['vector_p95_ms'] for row in values], y=[row['mrr'] for row in values],
                        mode='lines+markers', line=dict(color=color, width=2.5), marker=dict(symbol=symbol, size=10),
                        customdata=[f"{row['parameter']}={row['requested_value']}" for row in values],
                        hovertemplate='%{customdata}<br>p95 %{x:.3f}ms · MRR %{y:.3f}<extra></extra>')
    chart(fig, title, 380, legend=True).update_xaxes(title='벡터 검색 p95 (ms)')
    fig.update_layout(margin_b=80, legend_y=-0.32)
    st.plotly_chart(fig, use_container_width=True)
    with st.expander('표로 보기'):
        table(pd.DataFrame([dict(모드=dict(MODES)[row['mode']], 설정=f"{row['parameter']}={row['requested_value']}",
                                 MRR=row['mrr'], NDCG10=row['ndcg_at_10'], 벡터검색p95ms=row['vector_p95_ms']) for row in rows]))
    st.caption('인코딩·HTTP 시간을 뺀 벡터 검색 시간이라 API 응답 시간 판정에는 쓰지 않습니다.')


def http_section(report: dict) -> None:
    section('검색', 2)
    modes = report.get('api', {}).get('modes', {})
    rows = [(label, modes[mode]) for mode, label in MODES if mode in modes]
    if not rows:
        st.info('모드별 HTTP 응답 시간이 측정되지 않았습니다.')
        return
    target = next((row['target'] for row in report.get('metrics', []) if row['name'] == 'search_p95_ms'), None)
    worst = max(rows, key=lambda item: item[1]['http']['p95_ms'])
    fig = go.Figure()
    for (label, row), color, pattern in zip(rows, (INDIGO, TEAL, ORANGE), ('', '/', '.')):
        fig.add_bar(x=[label], y=[row['http']['p95_ms']], marker=dict(color=color, pattern=dict(shape=pattern)),
                    text=[f"{row['http']['p95_ms']:.1f}ms"], textposition='outside', name=label)
    title = f"가장 느린 {worst[0]} 모드 p95 {worst[1]['http']['p95_ms']:.1f}ms"
    if target:
        baseline(fig, target, f'기준 {target:g}ms')
        inside = worst[1]['http']['p95_ms'] <= target
        title = f"가장 느린 {worst[0]} 모드도 p95 {worst[1]['http']['p95_ms']:.1f}ms로 기준 {target:g}ms {'안' if inside else '초과'}"
    title += f" (모드당 단건 {worst[1].get('requests', '?')}회)"
    chart(fig, title, 320).update_yaxes(range=[0, max(target or 0, worst[1]['http']['p95_ms']) * 1.12])
    st.plotly_chart(fig, use_container_width=True)
    with st.expander('표로 보기'):
        table(pd.DataFrame([dict(모드=label, p50ms=row['http']['p50_ms'], p95ms=row['http']['p95_ms'], p99ms=row['http']['p99_ms'],
                                 요청=row.get('requests'), 오류=row.get('errors')) for label, row in rows]))
    st.caption('검색 HTTP p95 — 단건 요청 중 95번째로 느린 응답 시간(가장 느린 모드) · 원시 표본 분포는 시스템 탭에 있습니다.')


def search_demo(config: dict) -> None:
    with st.form('search_demo'):
        text = st.text_input('검색어', placeholder='예: black shirt', key='query_text')
        image = st.file_uploader('이미지 · 선택', type=['png', 'jpg', 'jpeg'], key='query_image')
        count = st.number_input('검색 결과 수', 1, 100, 10, key='search_top_k')
        submit = st.form_submit_button('검색 실행')
    if submit:
        try:
            payload = search_payload(text, image.getvalue() if image is not None else None, int(count))
        except ValueError as error:
            st.warning(str(error))
            return
        response = api_call(config['api_url'], 'POST', '/api/search', payload=payload, timeout=config['api_timeout'])
        if response['ok']:
            body = response['data']
            st.session_state['search_response'] = body
            st.caption(f'{body["search_type"]} · {body["latency_ms"]:.1f}ms · 후보 {body["total_count"]:,}개')
            st.dataframe(display_frame(pd.DataFrame(body['results'])), hide_index=True, use_container_width=True)
        else:
            st.warning(response['error'])
    if 'search_response' in st.session_state:
        product_cards(st.session_state['search_response']['results'], config, 'search')


# ── 추천 ─────────────────────────────────────────────────────────────────────
def recommendation_tab(report: dict, bundle: dict | None, config: dict) -> None:
    if view_mode('recommend_view') == '직접 해보기':
        recommend_demo(config)
        return
    rec = report.get('recommendation', {})
    if rec.get('status') != 'MEASURED':
        st.info('추천 평가가 아직 없습니다.')
        return
    metrics, lift = rec.get('metrics', {}), rec.get('relative_lift', {})
    names = dict(hit_rate_at_50='HitRate@50', ndcg_at_50='NDCG@50', coverage='Coverage')
    lines = []
    if lift.get('train_popularity') and all(v > 0 for v in lift['train_popularity'].values()):
        lines.append('전체 파이프라인은 인기순보다 세 지표 모두 높습니다.')
    lower = [f"{PIPELINES[base]}보다는 {'·'.join(f'{names[k]} {v:+.1%}' for k, v in values.items() if v < 0)}"
             for base, values in lift.items() if base != 'train_popularity' and any(v < 0 for v in values.values())]
    if lower:
        lines.append(f"그러나 {', '.join(lower)} 낮습니다. 원인은 따로 측정하지 않았습니다.")
    if lines:
        st.markdown(f"**{' '.join(lines)}**")
    ann = rec.get('candidate', {}).get('ann_two_tower', {})
    full = metrics.get('full_pipeline', {})
    auc = rec.get('classification', {}).get('ctr', {}).get('auc')
    products = report.get('data_counts', {}).get('products')
    count = ann.get('candidate_count_max')
    stages = [('카탈로그', f'{products:,}' if products else '—', '전체 상품'),
              ('후보 생성', f'{count} ({count / products:.1%})' if count and products else '—',
               f"놓치지 않기 · Recall@300 {ann['recall_at_300']:.1%}" if 'recall_at_300' in ann else '놓치지 않기'),
              ('랭킹', f'{count}' if count else '—', f'순서만 바꿈 · CTR AUC {auc:.3f}' if auc is not None else '순서만 바꿈'),
              ('최종', '50', f"재정렬 후 · HitRate@50 {full['hit_rate_at_50']:.1%}" if 'hit_rate_at_50' in full else '재정렬 후')]
    for column, (title, value, note) in zip(st.columns(4), stages):
        with column.container(border=True):
            st.markdown(f'**{title}**')
            st.markdown(f'### {value}')
            st.markdown(f'<div class="stage-note">{note}</div>', unsafe_allow_html=True)
    st.caption('후보 생성은 넓은 그물(Recall), 랭킹은 위쪽 정밀도(AUC), 최종은 다양성·신상품 탐색 규칙을 적용한 결과입니다.')
    section('추천', 0)
    targets = {row['name']: row['target'] for row in report.get('metrics', [])}
    order = [name for name in PIPELINES if name in metrics]
    definitions = dict(hit_rate_at_50='HitRate@50 — 추천 50개 안에 미래 정답이 하나라도 있는 사용자 비율',
                       ndcg_at_50='NDCG@50 — 추천 50개 안 정답 순위 가중 점수',
                       coverage='Coverage — 전체 카탈로그 중 한 번이라도 추천된 상품 비율')
    for column, key in zip(st.columns(3), names):
        values = [metrics[name][key] for name in order]
        percent = key in PERCENT
        best = PIPELINES[order[max(range(len(order)), key=values.__getitem__)]]
        shown = (f'{full[key]:.1%}' if percent else f'{full[key]:.3f}') if key in full else '미측정'
        fig = go.Figure(go.Bar(y=[PIPELINES[name] for name in order], x=values, orientation='h',
            marker_color=[INDIGO if name == 'full_pipeline' else GRAY for name in order],
            text=[f'{v:.1%}' if percent else f'{v:.3f}' for v in values], textposition='outside'))
        if key in targets:
            baseline(fig, targets[key], f'기준 {targets[key]:g}', horizontal=False)
        chart(fig, f'{names[key]} · 전체 파이프라인 {shown}<br>가장 높은 것은 {best}', 330)
        fig.update_yaxes(autorange='reversed').update_xaxes(tickformat='.0%' if percent else '.2f', range=[0, max(values) * 1.3 or 1])
        column.plotly_chart(fig, use_container_width=True)
        with column.expander('표로 보기'):
            table(pd.DataFrame(dict(방법=[PIPELINES[name] for name in order], 값=values)))
        column.caption(definitions[key])
    if lift:
        st.markdown('**전체 파이프라인의 베이스라인 대비 개선율** (음수는 그대로 표시)')
        table(pd.DataFrame([{'비교 대상': PIPELINES[base], **{names[k]: f'{v:+.1%}' for k, v in values.items()}}
                            for base, values in lift.items()]))
    if full:
        st.caption(f"정답 사용자 {full.get('truth_users', 0):,}명 · Coverage 분모 사용자 {full.get('coverage_users', 0):,}명 · k=50 · "
                   '동일 사용자·정답·카탈로그')
    recall_section(rec)
    cohort_section(rec)


def recall_section(rec: dict) -> None:
    section('추천', 1)
    candidate, baselines = rec.get('candidate', {}), rec.get('candidate_baselines', {})
    users = candidate.get('ann_two_tower', {}).get('macro_users')
    rows = [('Two-Tower ANN (운영)', candidate.get('ann_two_tower', {})), ('Two-Tower exact', candidate.get('exact_flat_ip', {})),
            ('인기순 후보', baselines.get('train_popularity', {})), ('관측 이력 프로필 후보', baselines.get('observed_history_profile', {}))]
    left, right = st.columns(2)
    with left:
        found = [(name, row) for name, row in rows if 'recall_at_300' in row]
        if found:
            table(pd.DataFrame([dict(방법=name, Recall300=f"{row['recall_at_300']:.1%}", 사용자=f"{row.get('macro_users', users) or 0:,}")
                                for name, row in found]))
        if candidate.get('ann_agreement_at_300') is not None:
            st.caption(f"ANN과 exact top300 일치율 {candidate['ann_agreement_at_300']:.1%} (분모: exact 결과, 정답 아님)")
    classification = rec.get('classification', {})
    with right:
        a, b = st.columns(2)
        for column, key, label in ((a, 'ctr', 'CTR AUC · 기준 대상'), (b, 'cvr', 'CVR AUC · 별도 보고')):
            row = classification.get(key, {})
            with column.container(border=True):
                st.metric(label, f"{row['auc']:.3f}" if row.get('auc') is not None else '미측정')
                unit, positive = ('노출', '클릭') if key == 'ctr' else ('클릭 노출', '구매')
                st.caption(f"{unit} {row.get('samples', 0):,} · {positive} {row.get('positives', 0):,}")
        st.caption('기준 0.7은 CTR AUC에만 적용합니다(사용자 확인 2026-11-07). CVR AUC는 기준 없이 그대로 보고합니다.')
        cvr = classification.get('cvr', {})
        if cvr and cvr.get('auc') is None:
            st.info(f"CVR AUC 미정의: {cvr.get('auc_status')} · 클릭 노출 {cvr.get('samples', 0):,}개, 구매 양성 {cvr.get('positives', 0):,}개")


def cohort_section(rec: dict) -> None:
    section('추천', 2)
    cohort = rec.get('cohort', {})
    values = [('평가 사용자', cohort.get('total_users')), ('정답 있는 사용자', cohort.get('truth_users')),
              ('이력 있음 (정답)', cohort.get('warm'), cohort.get('warm_truth')),
              ('이력 적음 (정답)', cohort.get('cold'), cohort.get('cold_truth'))]
    for column, item in zip(st.columns(4), values):
        label, value, *truth = item
        shown = '—' if value is None else f'{value:,}' + (f' ({truth[0]:,})' if truth and truth[0] is not None else '')
        column.metric(label, shown)
    groups = rec.get('candidate', {}).get('ann_two_tower', {}).get('cohorts', {})
    names = dict(all='전체', cold='이력 적음(cold)', warm='이력 있음(warm)', no_history='이력 없음', rare_target='드문 상품이 정답',
                 new_target='신상품이 정답', unavailable_target='정답이 카탈로그에 없음', repeat_purchase='재구매가 정답')
    if groups:
        table(pd.DataFrame([dict(코호트=names.get(key, key), 사용자=f"{row['users']:,}",
                                 Recall300=f"{row['recall_at_300']:.1%}" if row.get('recall_at_300') is not None else '미측정 (사용자 0)')
                            for key, row in groups.items()]))
        st.caption('이력 적음·이력 없음처럼 사용자가 적은 코호트의 값은 변동이 큽니다.')
    if 'feasible_constraint_violations' in rec:
        st.markdown(f"**재정렬 제약 위반 {rec['feasible_constraint_violations']}건** (같은 카테고리 3개 연속 금지·신상품·탐색 슬롯, "
                    f"만족할 수 없는 후보 풀도 {rec.get('infeasible_candidate_pools', 0)}개)")
    if rec.get('label_diagnostics'):
        with st.expander('랭킹 라벨 진단 (CTR·CVR 분모)'):
            st.json(display_value(rec['label_diagnostics']))
    with st.expander('근거'):
        st.json(display_value({key: rec.get(key) for key in ('models', 'contract', 'session_scope', 'cutoff')}))


def recommend_demo(config: dict) -> None:
    with st.form('recommend_demo'):
        uid = st.text_input('사용자 ID', value='U000001', key='user_id')
        count = st.number_input('추천 결과 수', 1, 100, 10, key='recommend_top_n')
        submit = st.form_submit_button('추천 실행')
    if submit:
        if not uid.strip():
            st.warning('사용자 ID를 입력하세요.')
            return
        response = api_call(config['api_url'], 'GET', '/api/recommend', params=dict(user_id=uid.strip(), top_n=int(count)),
                            timeout=config['api_timeout'])
        if response['ok']:
            body = response['data']
            st.session_state['recommend_response'] = (uid.strip(), response)
            st.dataframe(display_frame(pd.DataFrame(body['recommendations'])), hide_index=True, use_container_width=True)
            st.caption(f'파이프라인 {body["pipeline_latency"]["total_ms"]:.1f}ms · 세션 관심사 {body["session_context"]["session_interest"] or "없음"}')
        else:
            st.warning(response['error'])
    if 'recommend_response' in st.session_state:
        selected_uid, response = st.session_state['recommend_response']
        product_cards(response['data']['recommendations'], config, 'recommend', selected_uid, response)


# ── A/B ──────────────────────────────────────────────────────────────────────
def ab_tab(report: dict, bundle: dict | None, config: dict) -> None:
    ab = report.get('ab', {})
    try:
        ab = ab_result(config['results_dir']) or ab
    except (OSError, ValueError, KeyError) as error:
        st.error(f'A/B 데이터 확인 실패: {error}')
    section('A/B', 0)
    if ab.get('status') != 'MEASURED':
        st.info(ab.get('reason', 'A/B 실험 결과가 없습니다.'))
        return
    control, treatment = ab['arms']['control'], ab['arms']['treatment']
    st.markdown('**Control: 인기순 (popularity)** vs **Treatment: 전체 파이프라인 (full_pipeline)**')
    st.caption(f"합성 실험 · 사용자 {control['users']:,}명/군 · {ab['days']}일 · seed={ab.get('seed', '저장된 실험 근거 참조')} · "
               '사용자 단위 무작위 배정, 반복 노출은 사용자 cluster로 묶음')
    arms = ['Control · 인기순', 'Treatment · 전체 파이프라인']
    impressions = (control.get('impressions') or 0) + (treatment.get('impressions') or 0)
    columns = st.columns(2)
    for column, key, label, denominator in ((columns[0], 'ctr', 'CTR', '클릭 / 노출'), (columns[1], 'cvr', 'CVR', '구매 / 노출')):
        values = [control.get(key), treatment.get(key)]
        fig = go.Figure(go.Bar(x=arms, y=values, marker_color=[GRAY, INDIGO], width=.55,
                               text=[f'{v:.1%}' if v is not None else '미측정' for v in values], textposition='outside'))
        title = f"{label}: 인기순 {values[0]:.1%} → 전체 파이프라인 {values[1]:.1%}" if None not in values else label
        if impressions:
            title += f' (노출 {impressions:,}건)'
        chart(fig, title, 330).update_yaxes(tickformat='.1%', range=[0, (max(v or 0 for v in values) * 1.25) or 1])
        column.plotly_chart(fig, use_container_width=True)
        with column.expander('표로 보기'):
            table(pd.DataFrame(dict(군=arms, 값=values)))
        column.caption(f'{label} = {denominator} · control이 0이면 상대 변화는 정의되지 않습니다.')
    inference = ab.get('inference', {})
    st.markdown('**차이와 95% 신뢰구간** (0을 가로지르지 않으면 5% 수준에서 차이가 있다는 뜻)')
    columns = st.columns(2)
    for column, key, label in ((columns[0], 'ctr', 'CTR'), (columns[1], 'cvr', 'CVR')):
        row = inference.get(key, {})
        ci = row.get('difference_ci95')
        difference = row.get('difference')
        if difference is None and None not in (control.get(key), treatment.get(key)):
            difference = treatment[key] - control[key]
        if ci is None or difference is None:
            column.info(f'{label} 차이 신뢰구간이 저장되지 않았습니다.')
            continue
        span = max(abs(ci[0]), abs(ci[1])) * 100 * 1.25
        fig = go.Figure(go.Scatter(x=[difference * 100], y=[label], mode='markers', marker=dict(color=INDIGO, size=12),
            error_x=dict(type='data', symmetric=False, array=[(ci[1] - difference) * 100], arrayminus=[(difference - ci[0]) * 100],
                         color=INDIGO, thickness=2.5, width=8)))
        fig.add_vline(x=0, line_dash='dash', line_color=BASE, annotation_text='차이 0', annotation_position='top')
        chart(fig, f'{label} 차이 {difference * 100:+.2f}%p · 95% CI [{ci[0] * 100:+.2f}%p, {ci[1] * 100:+.2f}%p]', 220)
        fig.update_xaxes(range=[-span, span], ticksuffix='%', title='전체 파이프라인 − 인기순 (%p)')
        column.plotly_chart(fig, use_container_width=True)
        with column.expander('표로 보기'):
            table(pd.DataFrame([dict(지표=label, 차이pp=difference * 100, 하한pp=ci[0] * 100, 상한pp=ci[1] * 100,
                                     p=row.get('z_p_value'), 방법=row.get('method'))]))
        lift, p = row.get('relative_lift'), row.get('z_p_value')
        direction = '낮습니다' if difference < 0 else '높습니다'
        p_text = '계산 가능한 최솟값보다 작음(사실상 0)' if p == 0 else (f'{p:.1e}' if p is not None else '미측정')
        significant = p is not None and p < .05
        column.markdown(f"{label}: 전체 파이프라인이 인기순보다 {abs(difference) * 100:.2f}%p {direction}"
                        f"{f'(상대 {lift:+.1%})' if lift is not None else ''}. p={p_text} → 5% 수준에서 "
                        f"{'유의한 차이' if significant else '유의하지 않음'}.")
    st.caption('반복 노출을 독립 표본으로 세지 않습니다. 양의 lift나 유의성은 보장되지 않으며 실제 서비스 효과로 해석할 수 없습니다.')
    with st.expander('근거'):
        st.json(display_value({key: ab.get(key) for key in ('run_id', 'source', 'denominators', 'limitations')}))
    section('A/B', 1)
    table(pd.DataFrame([{'군': name, '사용자': f"{row.get('users', 0):,}", '노출': f"{row.get('impressions', 0):,}",
                         '클릭': f"{row.get('clicks', 0):,}", '구매': f"{row.get('purchases', 0):,}",
                         '탐색 슬롯 노출': f"{row.get('explorations', 0):,}", '탐색 비율': f"{row.get('exploration_rate', 0):.1%}"}
                        for name, row in zip(arms, (control, treatment))]))
    risks = inference.get('independent_user_risks', {})
    if risks:
        st.markdown('**사용자 단위 위험** (한 사용자를 한 표본으로)')
        labels = dict(any_click='한 번 이상 클릭한 사용자', any_purchase='한 번 이상 구매한 사용자')
        table(pd.DataFrame([{'지표': labels.get(name, name), '인기순': f"{row['control']:.1%}", '전체 파이프라인': f"{row['treatment']:.1%}",
                             '양측 Z 검정 p': display_value(row['z_p_value']), '카이제곱 검정 p': display_value(row['chi_square_p_value']),
                             '기대 빈도 부족': '예' if row['low_expected_counts'] else '아니오'} for name, row in risks.items()]))
        if any(row['low_expected_counts'] for row in risks.values()):
            st.info('**주의** 기대 빈도가 부족한 항목이 있어 근사 검정이 불안정합니다. 그 행의 p는 참고만 하세요.')
    st.caption('통계 검산 통과는 계산 절차가 맞았다는 뜻이며 개선을 뜻하지 않습니다. 합성 실험이므로 실제 서비스 효과로 해석하지 않습니다.')
    offline = report.get('recommendation', {}).get('relative_lift', {}).get('train_popularity', {})
    online = [inference.get(key, {}).get('relative_lift') for key in ('ctr', 'cvr')]
    if offline and None not in online:
        section('A/B', 2)
        left, right = st.columns(2)
        with left.container(border=True):
            st.markdown('**오프라인 · 고정된 과거 노출 이후의 실제 구매를 맞혔는가**')
            a, b = st.columns(2)
            a.metric('HitRate@50 개선율', f"{offline['hit_rate_at_50']:+.1%}")
            b.metric('NDCG@50 개선율', f"{offline['ndcg_at_50']:+.1%}")
        with right.container(border=True):
            st.markdown('**온라인(합성) · 정책이 새로 만든 노출에 사용자가 반응했는가**')
            a, b = st.columns(2)
            a.metric('CTR 상대 변화', f'{online[0]:+.1%}')
            b.metric('CVR 상대 변화', f'{online[1]:+.1%}')
        st.markdown(f"- **측정 대상이 다릅니다.** 오프라인은 고정 시점 이후 실제로 일어난 장바구니 담기·구매를 추천 50개가 맞혔는지 봅니다. "
                    f"합성 A/B는 정책이 새로 만든 노출({ab['days']}일)에 시뮬레이터가 반응한 결과입니다.\n"
                    '- 같은 “전체 파이프라인 vs 인기순” 비교라도 두 숫자는 서로를 대신하지 못합니다. '
                    '이것이 과제 목표 6번(오프라인-온라인 지표 불일치)의 관측 사례입니다.\n'
                    '- 원인 분해(ablation)는 하지 않았습니다. 탐색 슬롯 비율, 시뮬레이터 반응 모델 등 후보 요인이 있지만 '
                    '이 화면은 원인을 단정하지 않습니다.')


# ── 시스템 ───────────────────────────────────────────────────────────────────
def system_tab(report: dict, bundle: dict | None, config: dict) -> None:
    health = api_call(config['api_url'], 'GET', '/health', timeout=min(config['api_timeout'], 2))
    ready = api_call(config['api_url'], 'GET', '/ready', timeout=min(config['api_timeout'], 2))
    live = health['data'].get('model_version') if health['ok'] else None
    st.caption(f"지금 API 상태 — 연결 {'정상' if health['ok'] else '연결 안 됨'} · 모델 {'준비됨' if ready['ok'] else '준비 안 됨'} · "
               f"현재 모델 버전 {live or '미측정'}. 아래는 저장된 측정이며 그때의 모델 버전은 {report.get('model_version', '미측정')}입니다."
               + (f" ({health['error']})" if not health['ok'] else ''))
    rows = [row for row in report.get('metrics', []) if row['name'].endswith('_ms')]
    if rows:
        inside = sum(row['status'] == 'PASS' for row in rows)
        section('시스템', 0, f"응답 시간 {len(rows)}개 {'모두 기준 안' if inside == len(rows) else f'중 {inside}개 기준 안'}")
        st.markdown(' / '.join(f"{LABELS[row['name']].replace(' p95', '')} {fmt(row['name'], row['value'])}(기준 {row['target']:g}ms)"
                               for row in rows) + ' · p95 기준')
        table(pd.DataFrame([{'지표': LABELS[row['name']], '측정값': fmt(row['name'], row['value']), '기준': f"{row['target']:g}",
                             '판정': STATUS.get(row['status'], row['status']), '평가 구간': row['split'], '출처 필드': row.get('source') or '—'}
                            for row in rows]))
    samples_section(report)
    conditions_section(report, bundle, config)
    ct_section(bundle, config)


def box(title: str, groups: list[tuple[str, list[float]]], p95: float | None, target: float | None) -> go.Figure:
    fig = go.Figure()
    for label, values in groups:
        fig.add_box(y=values, name=label, marker_color=INDIGO, fillcolor='rgba(97,85,245,.45)', line=dict(width=1.4),
                    boxpoints='outliers')
    # On a log axis Plotly reads annotation y in log10 units, so lines and labels are placed explicitly.
    for value, label, dash, color, side in ((target, f'기준 {target:g}ms' if target else '', 'dash', BASE, 'right'),
                                            (p95, f'p95 {p95:.1f}ms' if p95 else '', 'dot', INDIGO, 'left')):
        if value:
            fig.add_shape(type='line', xref='paper', x0=0, x1=1, y0=value, y1=value, line=dict(dash=dash, color=color, width=1.4))
            fig.add_annotation(xref='paper', x=1 if side == 'right' else 0, y=math.log10(value), text=label, showarrow=False,
                               xanchor='left' if side == 'right' else 'left', yanchor='bottom' if side == 'left' else 'middle',
                               font=dict(color=color if side == 'left' else None, size=11), xshift=4 if side == 'right' else 2)
    values = [v for _, group in groups for v in group] + [v for v in (target, p95) if v]
    low, high = min(values) * .8, max(values) * 1.4
    ticks = [m * 10 ** e for e in range(math.floor(math.log10(low)), math.ceil(math.log10(high)) + 1)
             for m in (1, 2, 5) if low <= m * 10 ** e <= high]
    chart(fig, title, 320).update_yaxes(type='log', range=[math.log10(low), math.log10(high)],
                                        tickvals=ticks, ticktext=[f'{t:g}' for t in ticks])
    return fig.update_layout(margin_r=72)


def samples_section(report: dict) -> None:
    modes = report.get('api', {}).get('modes', {})
    feature, candidate = report.get('feature_store', {}), report.get('candidate_latency', {})
    rows = {row['name']: row for row in report.get('metrics', [])}
    charts = []
    search = [(label, modes[mode]['http_samples_ms']) for mode, label in MODES if modes.get(mode, {}).get('http_samples_ms')]
    if search:
        charts.append(('search_p95_ms', search,
                       f'검색 HTTP p95 — 단건 요청 중 95번째로 느린 응답 시간(가장 느린 모드) · 표본 {sum(len(v) for _, v in search)}개'))
    if modes.get('recommendation', {}).get('http_samples_ms'):
        values = modes['recommendation']['http_samples_ms']
        charts.append(('recommend_p95_ms', [('추천 HTTP', values)], f'추천 HTTP p95 — 단건 요청 중 95번째로 느린 응답 시간 · 표본 {len(values)}개'))
    if isinstance(candidate.get('elapsed_ms'), list) and candidate['elapsed_ms']:
        charts.append(('candidate_p95_ms', [('후보 생성', candidate['elapsed_ms'])],
                       f"후보 생성 p95 — 사용자 벡터 계산과 FAISS 검색 300개 시간 · 표본 {len(candidate['elapsed_ms'])}개"))
    if feature.get('samples_ms'):
        charts.append(('feature_p95_ms', [('Redis 조회', feature['samples_ms'])],
                       f"Redis 조회 p95 — 최근 조회·프로필 조회 시간 · 표본 {len(feature['samples_ms'])}개"))
    if not charts:
        return
    section('시스템', 1)
    for start in range(0, len(charts), 2):
        for column, (name, groups, caption) in zip(st.columns(2), charts[start:start + 2]):
            row = rows.get(name, {})
            value, target = row.get('value'), row.get('target')
            title = f'{LABELS[name]} {fmt(name, value)}' + (f" · 기준 {target:g}ms · {STATUS.get(row.get('status'), '')}" if target else '')
            column.plotly_chart(box(title + ' (ms, 로그 눈금)', groups, value, target), use_container_width=True)
            with column.expander('표로 보기'):
                table(pd.DataFrame([dict(구분=label, 표본=len(values), p50ms=statistics.median(values), 최대ms=max(values))
                                    for label, values in groups]))
            column.caption(caption)
    stages = [row for row in modes.get('recommendation', {}).get('pipeline_samples') or [] if row]
    if stages:
        names = [(key, label) for key, label in (('candidate_ms', '후보 생성'), ('ranking_ms', '랭킹'), ('reranking_ms', '재정렬'),
                                                 ('total_ms', '전체')) if any(key in row for row in stages)]
        fig = go.Figure()
        for key, label in names:
            fig.add_box(x=[row[key] for row in stages if key in row], name=label, orientation='h', marker_color=INDIGO,
                        fillcolor='rgba(97,85,245,.45)', line=dict(width=1.4), boxpoints='outliers')
        chart(fig, f'추천 파이프라인 단계별 시간 (서비스 내부, 요청 {len(stages)}회)', 300).update_yaxes(autorange='reversed')
        fig.update_xaxes(title='ms')
        st.plotly_chart(fig, use_container_width=True)
        with st.expander('표로 보기'):
            table(pd.DataFrame([dict(단계=label, p50ms=statistics.median(row[key] for row in stages if key in row),
                                     최대ms=max(row[key] for row in stages if key in row)) for key, label in names]))


def conditions_section(report: dict, bundle: dict | None, config: dict) -> None:
    environment = report.get('environment', {})
    modes = report.get('api', {}).get('modes', {})
    conditions = (read_json(bundle['folder'] / 'latency_conditions.json', config['results_dir']) if bundle else None) or {}
    sample: dict = next(iter(modes.values()), {})
    if not (environment or sample or conditions):
        return
    section('시스템', 2)
    allocation = environment.get('docker_allocation', {})
    memory = str(allocation.get('memory.max', ''))
    cpu = str(allocation.get('cpu.max', '')).split()
    rows = [('예열 요청 수', conditions.get('warmup', sample.get('warmup'))), ('측정 요청 수', conditions.get('requests', sample.get('requests'))),
            ('동시성', conditions.get('concurrency', sample.get('concurrency'))),
            ('오류 수(모드 합)', sum(row.get('errors', 0) for row in modes.values()) if modes else None),
            ('플랫폼', environment.get('platform')),
            ('CPU', f"{environment['cpu']} · 논리 {environment['logical_cpus']}개" if 'cpu' in environment else None),
            ('RAM', f"{environment['ram_bytes'] / 2 ** 30:.1f} GiB" if 'ram_bytes' in environment else None),
            ('Docker 할당', f'메모리 {int(memory) / 2 ** 30:.0f} GiB · CPU {int(cpu[0]) / int(cpu[1]):.0f}개'
             if memory.isdigit() and len(cpu) == 2 and all(part.isdigit() for part in cpu) else None),
            ('torch / faiss 스레드', f"{environment['torch_threads']} / {environment['faiss_threads']}" if 'torch_threads' in environment else None),
            ('GPU 사용', ('예' if environment['gpu_used'] else '아니오') if 'gpu_used' in environment else None),
            ('후보 캐시', report.get('candidate_latency', {}).get('cache'))]
    table(pd.DataFrame([dict(항목=name, 값=str(value)) for name, value in rows if value is not None]))
    with st.expander('근거'):
        st.json(display_value(dict(environment=environment, latency_conditions=conditions, latency_source=report.get('latency_source'))))


def ct_section(bundle: dict | None, config: dict) -> None:
    section('시스템', 3)
    root = config['results_dir']
    folder = bundle['folder'] if bundle else root
    ct = read_json(folder / 'ct_full.json', root)
    if ct:
        monitor = ct.get('monitor', {})
        limits = {**config.get('ct', {}), **monitor.get('thresholds', {})}
        cards = [('재학습 트리거 (신규 로그)', f"{ct.get('threshold', limits.get('retrain_log_threshold', 0)):,}건",
                  f"관측 신규 이벤트 {ct.get('observed_new_events', 0):,}건")]
        if 'hitrate_threshold' in limits:
            cards.append(('HitRate@50 경보 임계', f"{limits['hitrate_threshold']:.3f}",
                          f"관측 {monitor.get('hit_rate_at_50', 0):.3f} · 성숙 요청 {monitor.get('mature_requests', 0):,}"))
        if 'ctr_threshold' in limits:
            cards.append(('CTR 경보 임계', f"{limits['ctr_threshold']:.3f}",
                          f"관측 {monitor.get('ctr', 0):.3f} · 노출 {monitor.get('exposures', 0):,}"))
        for column, (label, value, note) in zip(st.columns(3), cards):
            with column.container(border=True):
                st.metric(label, value)
                st.caption(note)
        retraining = ct.get('retraining', {})
        comparison = retraining.get('comparison', {})
        if retraining:
            decision = dict(RETAINED='유지', PROMOTED='승격').get(retraining.get('status'), retraining.get('status'))
            text = f"**실제 재학습 판정: {decision}** (후보 {retraining.get('version')}, 운영 {retraining.get('active')})"
            before, after = comparison.get('baseline', {}).get('ctr_auc'), comparison.get('candidate', {}).get('ctr_auc')
            if before is not None and after is not None:
                text += f" — {comparison.get('split')} CTR_AUC {before:.3f} → {after:.3f}, 개선폭 {after - before:+.4f}"
                if 'min_improvement' in limits:
                    text += f" vs 승격 기준 {limits['min_improvement']:g}"
            st.markdown(text)
            st.caption('개선폭이 기준 이하이면 운영 모델을 유지합니다. 승격·HTTP 교체·롤백은 별도 통제 실험'
                       '(integration.checks.ct_retrain_and_rollback)으로 확인했습니다.')
    name = 'ct_controlled_lifecycle_full.jsonl' if (folder / 'ct_controlled_lifecycle_full.jsonl').is_file() else 'ct_log.jsonl'
    logs = ct_log(folder, name=name)
    if logs['rows']:
        st.markdown(f'**버전 이력** ({name}, 최근 100줄)')
        if name != 'ct_log.jsonl':
            st.caption('제출 기준 묶음의 버전 이력은 통제 실험(승격 → 롤백) 기록입니다. 실제 운영 재학습 판정은 위 문장을 따릅니다.')
        if any(row.get('scope') == 'controlled_fixture' for row in logs['rows']):
            st.caption('controlled_fixture 기록은 소규모 기능 검증이며 실제 서비스 품질을 뜻하지 않습니다.')
        frame = pd.json_normalize(logs['rows'], sep='.')
        columns = {'at': '시각', 'event': '이벤트', 'version': '버전', 'parent': '이전 버전', 'active': '운영 버전',
                   'comparison.split': '비교 분할', 'reason': '사유'}
        shown = frame[[c for c in columns if c in frame]].rename(columns=columns)
        st.dataframe(display_frame(shown), hide_index=True, use_container_width=True)
        with st.expander('버전 이력 원본'):
            st.dataframe(display_frame(frame), hide_index=True, use_container_width=True)
        if logs['invalid_lines']:
            st.warning(f'읽을 수 없는 로그 {logs["invalid_lines"]}개를 제외했습니다.')
    elif not ct:
        st.info(logs.get('reason', 'CT 실행 기록이 없습니다. CT 모니터 실행과 결과 경로를 확인하세요.'))
    paired = read_json(folder / 'ct_controlled_paired_ctr_full.json', root)
    if paired and paired.get('comparison'):
        st.markdown('**승격 비교** (기존 모델과 후보 모델을 같은 검증 데이터로 평가)')
        comparison = paired['comparison']
        table(pd.DataFrame([{'모델': name, '비교 분할': comparison.get('split'), 'CTR AUC': f"{row['ctr_auc']:.3f}",
                             'CTR logloss': f"{row['ctr_logloss']:.3f}", 'CTR 표본': f"{row['ctr_samples']:,}",
                             'CTR 양성': f"{row.get('ctr_positives', 0):,}"}
                            for name, row in (('기존', comparison['baseline']), ('후보', comparison['candidate']))]))
    if ct:
        with st.expander('근거'):
            st.json(display_value({key: ct.get(key) for key in ('status', 'scope', 'checks', 'limitations')}))


# ── 화면 틀 ──────────────────────────────────────────────────────────────────
VIEWS = {'개요': overview_tab, '데이터': data_tab, '검색': search_tab, '추천': recommendation_tab, 'A/B': ab_tab, '시스템': system_tab}


def go_tab(name: str) -> None:
    st.session_state['tab'] = name


def navigation(tab: str, config: dict, report: dict) -> None:
    """Sidebar table of contents: the open tab lists its sections; other tabs switch the view."""
    with st.sidebar:
        for name in TABS:
            if name == tab:
                st.button(name, key=f'nav_{name}', type='tertiary', icon=':material/expand_more:')
                st.markdown(''.join(f'<a class="toc-item" href="#{anchor}" target="_self">{title}</a>'
                                    for title, anchor in SECTIONS[name]), unsafe_allow_html=True)
            else:
                st.button(name, key=f'nav_{name}', type='tertiary', icon=':material/chevron_right:', on_click=go_tab, args=(name,))
        st.markdown('<div class="toc-label">도구</div>', unsafe_allow_html=True)
        with st.container(key='tools'):
            st.button('결과 새로고침', type='tertiary', icon=':material/refresh:')
            st.link_button('API 문서 열기', f'{config["public_api_url"]}/docs', type='tertiary', icon=':material/open_in_new:')
        if report:
            with st.expander('근거'):
                st.json(display_value(dict(identity=report.get('identity', {}), limitations=report.get('limitations', []))))


def main() -> None:
    st.set_page_config(page_title='검색·추천 평가실', page_icon='◈', layout='wide')
    st.markdown(CSS, unsafe_allow_html=True)
    config = settings(ROOT)
    items, default = bundles(config['results_dir'], config['scale'])
    st.session_state.setdefault('tab', TABS[0])
    report: dict = {}
    bundle: dict | None = None
    error: Exception | None = None
    with st.sidebar:
        st.button('평가 결과', key='nav_results', type='tertiary', icon=':material/expand_more:')
        if items:
            choice = st.radio('평가 결과', range(len(items)), index=default, format_func=lambda i: items[i]['label'],
                              key='bundle', label_visibility='collapsed')
            bundle = items[choice]
            try:
                report = read_report(bundle['path'], config['results_dir'])
            except (OSError, ValueError, KeyError, TypeError) as exc:
                error = exc
        else:
            st.info('저장된 통합 평가 결과가 없습니다.')
    st.title('멀티모달 검색 및 Multi-Stage 추천 시스템')
    if report and bundle:
        counts = report['data_counts']
        st.caption(f"{bundle['label']} · 상품 {counts['products']:,} · 사용자 {counts['users']:,} · 이벤트 {counts['events']:,} · "
                   '저장된 측정값을 보여주며 새로 측정하지 않습니다 · 시간 KST')
    else:
        st.caption('저장된 측정값을 보여주며 새로 측정하지 않습니다 · 시간 KST')
    tab = st.radio('화면', TABS, key='tab', horizontal=True, label_visibility='collapsed')
    navigation(tab, config, report)
    if error:
        st.error(f'결과를 읽을 수 없습니다: {error}')
    if not report and tab in ('개요', 'A/B'):
        st.info('통합 평가를 실행하면 측정값이 표시됩니다. 데모는 실행 중인 API에 연결합니다.')
        return
    try:
        VIEWS[tab](report, bundle, config)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        st.error(f'{tab} 화면을 그릴 수 없습니다: {exc}')


if __name__ == '__main__':
    main()
