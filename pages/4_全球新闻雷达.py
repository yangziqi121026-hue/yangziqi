"""全球新闻 → A股事件雷达 Dashboard。

实时拉全球财经快讯 → DeepSeek 研判影响/动向/触发/传导/受益板块 → 映射板块池真实标的。
逻辑在 src/news_radar.py，本页只负责交互与展示。
"""

import os
import sys

import pandas as pd
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

if scan_btn:
    with st.spinner("拉取全球快讯 + DeepSeek 研判中…"):
        try:
            st.session_state["radar"] = nr.scan(limit=limit, analyze_top=analyze_top,
                                                keyword=keyword.strip() or None)
        except Exception as exc:  # noqa: BLE001
            st.error(f"扫描出错：{exc}")

radar = st.session_state.get("radar")
if not radar:
    st.info("左侧点「📡 扫描并研判」拉取全球快讯并研判。")
    st.stop()

meta = radar["meta"]
st.caption(f"快讯 {meta['count']} 条 ｜ 已研判 {meta['analyzed']} 条 ｜ "
           f"{'真实 DeepSeek' if meta['real_llm'] else 'Mock 占位'}")

st.header("🚨 事件研判（DeepSeek + 板块池映射）")
if not radar["events"]:
    st.info("无匹配快讯。换关键词或增大研判条数。")
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
        else:
            st.caption("（未命中本系统板块池——该板块标的待补充）")
        if it.get("url"):
            st.markdown(f"[查看原文]({it['url']})")

st.markdown("---")
st.subheader("📋 全部快讯流")
df = radar["news"].rename(columns={"time": "时间", "title": "标题", "summary": "摘要"})
st.dataframe(df[["时间", "标题", "摘要"]] if "摘要" in df.columns else df,
             use_container_width=True, hide_index=True, height=360)

st.caption("数据：东财全球财经快讯实时接口；研判：DeepSeek。仅供研究，不构成投资建议。")
