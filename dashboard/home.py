"""Home tab: only the background needed before the measurement tabs — what was built, how search and recommendation
work, and how they were scored. Text and HTML figures only, so it reads even when no result is saved.

Layout follows Apple HIG charting guidance: a few values are shown as text instead of an invented chart shape, each
figure has a one-line summary above it, and every figure sits in the same gray card as the dashboard's chart cards."""
from __future__ import annotations

import streamlit as st

from dashboard.style import BASE, GRAY, INDIGO, ORANGE, TEAL

HOME_SECTIONS = [('전체 구조', 'structure'), ('검색: 뜻이 가까운 상품 찾기', 'how-search'), ('추천: 세 단계로 좁히기', 'how-recommend'),
                 ('평가: 데이터 분할과 지표', 'how-evaluate'), ('화면 보는 법', 'how-to-read')]
# PDF full scale; the selected result's own data_counts replace it.
SPEC = dict(products=50_000, users=10_000)
# Metric glossary grouped by area: (group, [(metric, meaning, how to read)]).
TERMS = [('검색', [('MRR · NDCG@10', '정답 상품이 위쪽에 나올수록 커지는 점수', '높을수록 좋음 · 최대 1')]),
         ('추천', [('Recall@300', '실제로 담거나 산 상품이 후보 300개 안에 든 비율', '높을수록 좋음'),
                   ('CTR AUC', '클릭한 상품을 안 한 상품보다 높게 매긴 비율', '높을수록 좋음 · 0.5는 무작위'),
                   ('HitRate@50 · NDCG@50', '추천 50개에 실제로 담거나 산 상품이 들어 있는 정도', '높을수록 좋음'),
                   ('Coverage', '전체 상품 중 한 번이라도 추천된 비율', '높을수록 고르게 추천')]),
         ('속도', [('p95', '요청 100번 중 95번째로 느린 응답 시간', '낮을수록 좋음')]),
         ('A/B', [('CTR · CVR', '보여 준 상품 중 클릭 · 구매로 이어진 비율', '두 그룹을 비교'),
                  ('p값 · 95% 신뢰구간', '두 그룹의 차이가 우연인지 판단하는 값', 'p값이 0.05 미만이거나 구간이 0을 벗어나면 의미 있는 차이')])]


def heading(index: int) -> None:
    title, anchor = HOME_SECTIONS[index]
    st.subheader(title, anchor=anchor)


def html(body: str) -> None:
    # One line starting with <div: markdown would turn indented or blank-line-split HTML into code blocks.
    st.markdown(body, unsafe_allow_html=True)


def steps(items: list[tuple[str, str, str, str, str]]) -> str:
    """Steps in one gray card joined by chevrons, footers lined up at the bottom. The system structure and the
    recommendation stages share it so both sequences look alike. Each item: (count, count note, title, body, footer)."""
    cells = []
    for count, note, title, body, foot in items:
        unit = '<small>개</small>' if count[:1].isdigit() else ''  # a missing value shows as — without a unit
        head = f'<div class="step-num">{count}{unit}</div><div class="step-sub">{note}</div>' if count else ''
        cells.append(f'<div class="step">{head}<b>{title}</b><span>{body}</span>' + (f'<em>{foot}</em>' if foot else '') + '</div>')
    kind = ' numbers' if any(item[0] for item in items) else ''
    # The wrapper is a CSS container so the steps stack by their own width, not the window's (the sidebar eats ~340px).
    return (f'<div class="steps-box"><div class="steps{kind}">' + '<div class="step-arrow" aria-hidden="true">›</div>'.join(cells)
            + '</div></div>')


def stages(products: int) -> str:
    """Recommendation stages as plain numbers. HIG (Charting data): a few values read better as text than as a chart, and
    50,000 vs 50 spans three orders of magnitude that no honest bar or funnel width can show together."""
    share = lambda n: f'전체의 {n / products:.1%}'
    return steps([(f'{products:,}', '전체', '전체 상품', '쇼핑몰의 모든 상품', ''),
                  ('300', share(300), '① 후보 생성 · Two-Tower', '사용자 취향과 가까운 상품 고르기', '지표 Recall@300'),
                  ('300', '개수 그대로', '② 랭킹 · DeepFM', '클릭·구매 확률을 예측해 순서 매기기', '지표 AUC'),
                  ('50', share(50), '③ 재정렬', '같은 종류 연속 방지, 신상품·탐색 자리 추가', '지표 HitRate@50 · NDCG@50 · Coverage')])


def embedding_map() -> str:
    """Three same-shaped groups mirrored around the middle one (x=360); the dashed circle is what 「검정 후드티」 returns."""
    groups = [(130, '「청바지」', '데님 팬츠', '일자 청바지'), (360, '「검정 후드티」', '블랙 후디', '오버핏 후드'),
              (590, '「흰 운동화」', '흰 스니커즈', '캔버스화')]

    def label(x: int, y: int, text: str, size: float = 13) -> str:
        return f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="middle" fill="currentColor">{text}</text>'

    marks = ''.join(f'<circle cx="{cx}" cy="60" r="7" fill="{INDIGO}"/>' + label(cx, 86, query) +
                    ''.join(f'<rect x="{x - 6}" y="108" width="12" height="12" rx="2" fill="{TEAL}"/>' + label(x, 138, name)
                            for x, name in ((cx - 45, left), (cx + 45, right)))
                    for cx, query, left, right in groups)
    return ('<div class="figure"><svg viewBox="0 30 720 190" role="img" aria-label="검색어와 상품 사진이 같은 좌표 공간에서 뜻이 비슷할수록 '
            '가깝게 놓인 그림"><ellipse cx="360" cy="97" rx="128" ry="60" fill="none" stroke="currentColor" stroke-opacity=".45" '
            'stroke-dasharray="5 4"/><text x="360" y="178" font-size="12.5" text-anchor="middle" fill="currentColor" opacity=".75">'
            '검색어와 가장 가까운 상품 = 검색 결과</text>' + marks +
            f'<circle cx="278" cy="202" r="6" fill="{INDIGO}"/><text x="290" y="206" font-size="12.5" fill="currentColor">글(검색어)</text>'
            f'<rect x="370" y="196" width="12" height="12" rx="2" fill="{TEAL}"/>'
            '<text x="388" y="206" font-size="12.5" fill="currentColor">상품 사진</text></svg></div>')


def split_bar() -> str:
    """Time split as a thin proportional strip; the labels go in a legend because a 10% slice is too narrow for text."""
    parts = [(8, INDIGO, '학습 train 80%', '모델이 배우는 과거 기록'), (1, TEAL, '검증 valid 10%', '설정 고르기'),
             (1, ORANGE, '시험 test 10%', '최종 채점')]
    bar = ''.join(f'<i style="flex:{flex};background:{color}"></i>' for flex, color, *_ in parts)
    legend = ''.join(f'<span><i class="sw" style="background:{color}"></i><b>{name}</b>{note}</span>' for _, color, name, note in parts)
    return (f'<div class="figure"><div class="split-bar" role="img" aria-label="시간순으로 학습 80%, 검증 10%, 시험 10%">{bar}</div>'
            f'<div class="split-axis"><span>과거</span><span>시간 →</span><span>최근</span></div><div class="legend">{legend}</div></div>')


def terms_table() -> str:
    """Metric glossary with each area named once (rowspan) and a column saying which direction is good."""
    rows = ''.join('<tr>' + (f'<td class="cat" rowspan="{len(items)}">{group}</td>' if i == 0 else '') +
                   f'<td>{name}</td><td>{meaning}</td><td class="read">{read}</td></tr>'
                   for group, items in TERMS for i, (name, meaning, read) in enumerate(items))
    return ('<div><table class="terms"><colgroup><col style="width:9%"><col style="width:21%"><col style="width:40%">'
            '<col style="width:30%"></colgroup><thead><tr><th>구분</th><th>지표</th><th>뜻</th><th>읽는 법</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div>')


def home_tab(report: dict, bundle: dict | None, config: dict) -> None:
    counts = {**SPEC, **report.get('data_counts', {})}
    criteria = len(report.get('metrics', []))
    retrain = config.get('ct', {}).get('retrain_log_threshold')

    st.markdown(f"상품 {counts['products']:,}개 · 사용자 {counts['users']:,}명 규모의 가상 쇼핑몰에서 **검색**(글·사진으로 상품 찾기)과 "
                f"**추천**(살 만한 상품 먼저 보여 주기)을 만들고, 과제가 정한 품질·속도 기준{f' {criteria}개를' if criteria else '을'} "
                '넘는지 측정했습니다. 실제 고객 기록 대신 고객 행동을 흉내 내는 시뮬레이터로 데이터를 만들었습니다.')

    heading(0)
    st.markdown('데이터를 만들고, 그 데이터로 모델을 학습해 서비스한 뒤, 결과를 채점하고 필요하면 다시 학습합니다.')
    html(steps([('', '', '① 데이터', '시뮬레이터가 상품·사용자·행동 기록을 만듭니다', '데이터 탭에서 확인'),
                ('', '', '② 검색·추천 모델', '이 기록으로 검색과 추천 모델을 학습합니다', '검색 · 추천 탭에서 확인'),
                ('', '', '③ API 서비스', '쇼핑몰의 검색·추천 요청에 응답합니다', '시스템 탭에서 확인'),
                ('', '', '④ 평가·재학습', '기준으로 채점하고 A/B 실험을 하며, 성능이 떨어지면 다시 학습합니다',
                 '개요 · A/B · 시스템 탭에서 확인')]))

    heading(1)
    st.markdown('CLIP 모델이 검색어와 상품 사진을 같은 공간의 좌표(벡터)로 바꿉니다. 뜻이 비슷할수록 가까이 놓이므로, 검색어와 가장 가까운 상품이 '
                '검색 결과가 됩니다.')
    html(embedding_map())
    st.markdown('- **검색 방식** 텍스트 · 이미지 · 하이브리드(글과 사진을 함께)\n'
                '- **빠르게 찾기** 모든 상품과 일일이 비교하지 않고, FAISS 색인으로 가까운 상품을 근사 검색(ANN)합니다\n'
                '- **비교 기준** 검색어와 단어가 겹치는 정도로 찾는 키워드 검색 BM25')

    heading(2)
    st.markdown('상품 전부를 정밀한 모델로 계산하면 느리기 때문에, 빠른 단계에서 300개로 줄인 뒤 정밀한 단계에서 순서를 다듬어 '
                '최종 50개를 추천합니다.')
    html(stages(counts['products']))
    st.caption('기록이 거의 없는 신규 사용자에게는 인기 상품을 보여 주고, 방금 본 상품의 흐름은 GRU 세션 모델로 반영합니다.')

    heading(3)
    st.markdown('기록을 시간순으로 나눠, 과거로 학습하고 그 뒤에 실제로 일어난 행동을 맞히는지로 채점합니다.')
    html(split_bar())
    st.markdown('채점에 쓰는 지표는 아래와 같습니다. 추천은 이와 별도로 가상 사용자를 두 그룹으로 나눠 인기순과 비교하는 **A/B 실험**도 했습니다.')
    html(terms_table())
    st.caption('자동 재학습(CT): 추천 성과가 기준 아래로 떨어지거나 새 행동 기록이 '
               f"{f'{retrain:,}건' if retrain else '일정량'} 쌓이면 다시 학습하고, 기존 모델보다 나을 때만 교체합니다.")

    heading(4)
    html('<div class="legend"><b>그래프 색</b>'
         f'<span><i class="sw" style="background:{INDIGO}"></i>이 프로젝트의 방식</span>'
         f'<span><i class="sw" style="background:{GRAY}"></i>비교 대상(인기순 · BM25 등)</span>'
         f'<span><i class="sw-line" style="border-color:{BASE}"></i>과제 기준선</span></div>')
    st.markdown('- **미측정**은 측정하지 않았다는 뜻이며 0이 아닙니다.\n'
                '- 왼쪽 목차 아래의 「**평가 결과**」에서 볼 결과를 고릅니다. 기본 선택이 최종 제출 결과이고, 「이전 도안」·「교정 실험」은 상품 그림이나 '
                '데이터를 바꿔 측정한 비교용 결과입니다.\n'
                '- 「**직접 해보기**」는 API 서버를 실행한 로컬 환경에서만 동작합니다.')
