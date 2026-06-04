"""全球新闻 → A股事件雷达 Dashboard（支持自动刷新）。

实时拉全球财经快讯 → DeepSeek 研判影响/动向/触发/传导/受益板块 → 映射板块池真实标的。
自动刷新用原生 st.fragment(run_every=...)：默认只滚动快讯流(免费)，
勾选"自动研判"才在每次刷新重跑 DeepSeek(消耗 API)。逻辑在 src/news_radar.py。
"""

import os
import sys
from datetime import datetime

import streamlit as st

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src import news_radar as nr  # noqa: E402
from src import deepseek_analyst  # noqa: E402
from src.config import config  # noqa: E402

st.set_page_config(page_title="全球新闻雷达", page_icon="📡", layout="wide")

st.title("📡 全球新闻 → A股事件雷达")
st.caption("实时全球财经快讯 ｜ DeepSeek 研判：动向·触发·传导·受益板块·标的 ｜ 不构成投资建议")

with st.sidebar:
    st.header("⚙️ 雷达参数")
    limit = st.slider("拉取快讯条数", 20, 200, 60, step=20)
    analyze_top = st.slider("AI 研判前 N 条", 1, 12, 6,
                            help="每条调用一次 DeepSeek，越多越慢/越贵")
    keyword = st.text_input("关键词过滤（可选）", value="", placeholder="如 芯片 / 美联储 / 锂")

    st.markdown("---")
    auto = st.toggle("🔄 自动刷新", value=False)
    interval_min = st.selectbox("刷新间隔（分钟）", [1, 2, 3, 5, 10], index=3, disabled=not auto)
    auto_analyze = st.checkbox("自动刷新时重新 AI 研判（消耗 DeepSeek）",
                               value=False, disabled=not auto)
    scan_btn = st.button("📡 扫描并研判", type="primary", use_container_width=True)

    st.markdown("---")
    _c = config.summary()
    st.write(f"服务商：{_c['服务商']}｜模式：{_c['运行模式']}")
    if st.button("🔌 测试 DeepSeek 连接", use_container_width=True):
        with st.spinner("ping…"):
            res = deepseek_analyst.test_connection()
        (st.success if res["ok"] else st.warning)(f"[{res['provider']}] {res['message']}")

st.warning("⚠️ 快讯来自东财实时接口；事件研判由 DeepSeek 生成，标的为板块池映射的研究候选，需核验。"
           "本工具仅用于研究，不构成投资建议。")

# 触发：首次扫描
if scan_btn:
    st.session_state["radar_on"] = True
    st.session_state["force_scan"] = True

if not st.session_state.get("radar_on"):
    st.info("左侧点「📡 扫描并研判」启动雷达；可开启「自动刷新」持续滚动。")
    st.stop()

# 参数存入 session 供 fragment 读取
st.session_state["radar_params"] = {"limit": limit, "analyze_top": analyze_top,
                                    "keyword": keyword.strip() or None}

run_every = (interval_min * 60) if auto else None


def _render(radar):
    meta = radar["meta"]
    st.caption(f"⏱ 更新于 {datetime.now().strftime('%H:%M:%S')} ｜ 快讯 {meta['count']} 条 ｜ "
               f"已研判 {meta['analyzed']} 条 ｜ {'真实 DeepSeek' if meta['real_llm'] else 'Mock 占位'}"
               f"{' ｜ 自动刷新中' if auto else ''}")
    st.header("🚨 事件研判（DeepSeek + 板块池映射）")
    if not radar["events"]:
        st.info("暂无已研判事件。点「扫描并研判」或勾选「自动研判」。")
    for ev in radar["events"]:
        it = ev["item"]
        with st.container(border=True):
            st.markdown(f"**📰 {it.get('title')}**　<span style='color:gray'>{it.get('time','')}</span>",
                        unsafe_allow_html=True)
            if it.get("summary"):
                st.caption(it["summary"][:200])
            st.markdown(ev["analysis"])
            if ev["targets"]:
                st.markdown("**🎯 板块池映射的研究候选标的（需核验，非推荐）：**")
                for sector, names in ev["targets"].items():
                    st.markdown(f"- **{sector}**：{'、'.join(names)}")
            if it.get("url"):
                st.markdown(f"[查看原文]({it['url']})")
    st.markdown("---")
    st.subheader("📋 全部快讯流")
    df = radar["news"].rename(columns={"time": "时间", "title": "标题", "summary": "摘要"})
    show = [c for c in ["时间", "标题", "摘要"] if c in df.columns]
    st.dataframe(df[show], use_container_width=True, hide_index=True, height=340)


@st.fragment(run_every=run_every)
def radar_block():
    p = st.session_state["radar_params"]
    force = st.session_state.pop("force_scan", False)
    need_analyze = force or (auto and auto_analyze) or ("radar_data" not in st.session_state)
    if need_analyze:
        st.session_state["radar_data"] = nr.scan(p["limit"], p["analyze_top"], p["keyword"])
    else:
        # 仅刷新快讯流（免费），沿用上次研判结果
        news = nr.fetch_global_news(p["limit"])
        if "radar_data" in st.session_state and not news.empty:
            st.session_state["radar_data"]["news"] = news
            st.session_state["radar_data"]["meta"]["count"] = len(news)
    _render(st.session_state["radar_data"])


radar_block()
st.caption("数据：东财全球财经快讯实时接口；研判：DeepSeek。仅供研究，不构成投资建议。")
