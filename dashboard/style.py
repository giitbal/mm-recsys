"""Look of the evaluation room (Figma design 2026-11-19): purple navigation, HIG system colors for data.

Light theme follows the design; light-dark() keeps the same layout readable when Streamlit runs dark.
"""
from __future__ import annotations

import plotly.graph_objects as go

# Data colors follow Apple HIG system colors: our system = indigo, comparison = gray, modes = indigo/mint/orange.
INDIGO, GRAY, TEAL, ORANGE = '#6155f5', '#6c6c70', '#008575', '#c55300'
GRID, BASE = 'rgba(128,128,128,.28)', '#97979d'

CSS = """<style>
[data-testid="stDecoration"]{background:#7a4fe0;background-image:none;height:2px}
[data-testid="stSidebar"]{background:light-dark(#f0f0f0, #1c1c1e);min-width:336px;max-width:336px}
[data-testid="stSidebarUserContent"]{padding-top:3.5rem}
.block-container{padding:4rem 5rem 4rem;max-width:1440px}
[data-testid="stAppViewContainer"] :is(p, li, span, summary, h1, h2, h3){word-break:keep-all;overflow-wrap:break-word}
[data-testid="stAppViewContainer"] h1{font-size:2.05rem;letter-spacing:-.025em;padding-bottom:0}
[data-testid="stMain"] h2{font-size:1.5rem}
[data-testid="stMain"] h3{font-size:1.375rem}
/* tab bar: horizontal radio drawn as underline tabs */
.st-key-tab [role="radiogroup"]{gap:1rem;border-bottom:2px solid light-dark(#e8e2f6, #3a3450);flex-wrap:wrap}
.st-key-tab label[data-baseweb="radio"]{margin:0 0 -2px;padding:0 0 .5rem;border-bottom:2px solid transparent}
.st-key-tab label[data-baseweb="radio"] > div:first-child{display:none}
.st-key-tab label[data-baseweb="radio"] p{font-size:15px}
.st-key-tab label[data-baseweb="radio"]:has(input:checked){border-color:#7a4fe0}
.st-key-tab label[data-baseweb="radio"]:has(input:checked) p{color:light-dark(#6a3fd4, #b9a4ff)}
/* sidebar table of contents */
.toc-label{font-size:13px;font-weight:500;margin:.4rem 0 .1rem}
.st-key-bundle label[data-baseweb="radio"]{width:calc(100% - 22px);margin:0 0 2px 22px;padding:5px 8px;border-radius:6px}
.st-key-bundle label[data-baseweb="radio"] > div:first-child{display:none}
.st-key-bundle label[data-baseweb="radio"] p{font-size:14.5px;opacity:.85}
.st-key-bundle label[data-baseweb="radio"]:has(input:checked){background:light-dark(#e3dafa, rgba(122,79,224,.35))}
.st-key-bundle label[data-baseweb="radio"]:has(input:checked) p{font-weight:700;opacity:1;color:light-dark(#4b2c9f, #e4dbff)}
[data-testid="stSidebar"] [data-testid="stBaseButton-tertiary"] p{font-size:17px;font-weight:700}
.st-key-tools [data-testid="stBaseButton-tertiary"] p, .st-key-tools a p{font-size:16px;font-weight:400}
.toc-item{display:block;margin-left:22px;padding:5px 8px;border-radius:6px;font-size:14.5px;color:inherit !important;
  opacity:.85;text-decoration:none !important;line-height:1.38}
.toc-item:hover{background:light-dark(#e3dafa, rgba(122,79,224,.35));opacity:1}
/* "측정 결과 / 직접 해보기": radio drawn as a segmented control, HIG blue accent */
:is(.st-key-search_view, .st-key-recommend_view) [role="radiogroup"]{gap:0}
:is(.st-key-search_view, .st-key-recommend_view) label[data-baseweb="radio"]{margin:0;padding:4px 16px;border:1px solid light-dark(#d5d6d8, #4a4a4f)}
:is(.st-key-search_view, .st-key-recommend_view) label[data-baseweb="radio"]:first-child{border-radius:8px 0 0 8px}
:is(.st-key-search_view, .st-key-recommend_view) label[data-baseweb="radio"]:last-child{border-radius:0 8px 8px 0;border-left:none}
:is(.st-key-search_view, .st-key-recommend_view) label[data-baseweb="radio"] > div:first-child{display:none}
:is(.st-key-search_view, .st-key-recommend_view) label[data-baseweb="radio"]:has(input:checked){border-color:#1e6ef4;background:light-dark(#e0f1ff, rgba(30,110,244,.25))}
:is(.st-key-search_view, .st-key-recommend_view) label[data-baseweb="radio"]:has(input:checked) p{color:light-dark(#1e6ef4, #8ab8ff)}
/* chart cards */
[data-testid="stPlotlyChart"]{background:light-dark(#f2f2f7, #1c1c1e);border-radius:14px;overflow:hidden}
.st-key-verdict [data-testid="stMetricValue"]{font-size:20px;font-weight:700}
.st-key-verdict [data-testid="stMetricLabel"] p{font-size:14px}
.stage-note{font-size:14px;opacity:.75}
</style>"""


def chart(fig: go.Figure, title: str, height: int = 320, legend: bool = False) -> go.Figure:
    """Chart card: bold title on the card background (CSS), gridlines only where values are read."""
    fig.update_layout(
        title=dict(text=f'<b>{title}</b>', x=0.02, xanchor='left', y=0.97, yanchor='top', font=dict(size=15)),
        height=height, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(size=12),
        margin=dict(l=16, r=24, t=64 + 22 * title.count('<br>'), b=16 if not legend else 40), showlegend=legend, bargap=0.35,
        legend=dict(orientation='h', x=0.5, xanchor='center', y=-0.18, bgcolor='rgba(0,0,0,0)'))
    fig.update_xaxes(gridcolor=GRID, zeroline=False, linecolor=GRID)
    fig.update_yaxes(gridcolor=GRID, zeroline=False)
    return fig


def baseline(fig: go.Figure, value: float, label: str, horizontal: bool = True) -> go.Figure:
    """Dashed target line with its label beside the plot so it never covers the bars."""
    if horizontal:
        fig.add_hline(y=value, line_dash='dash', line_color=BASE, annotation_text=label, annotation_position='right')
        fig.update_layout(margin_r=80)
    else:
        fig.add_vline(x=value, line_dash='dash', line_color=BASE, annotation_text=label, annotation_position='top')
    return fig
