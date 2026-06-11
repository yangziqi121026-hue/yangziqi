"""个股深度分析 Dashboard：输入代码 → 隔夜美股+美国新闻外围层 + 六模块技术研判。

逻辑在 src/stock_deepdive.py。隔夜美股(指数+龙头+SOX)与美国/地缘新闻自动带入，
并据纳指/SOX 给出 risk-on/off 定调注入 DeepSeek。资金面(主力/北向)取不到、降权。
不构成投资建议；所有买点配破 MA5 硬止损。
"""

import os
import sys

import streamlit as st

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src import stock_deepdive as sd  # noqa: E402

st.set_page_config(page_title="个股深度分析", page_icon="🔬", layout="wide")
st.title("🔬 个股深度分析 · 含隔夜美股+美国新闻外围层")
st.caption("输入A股代码 → 外围(隔夜美股/SOX/龙头+美国新闻) + 六模块技术研判 + DeepSeek ｜ 不构成投资建议")

with st.sidebar:
    st.header("⚙️ 深度分析")
    code = st.text_input("股票代码（6位）", value="603516", max_chars=6)
    name = st.text_input("名称（可选，留空自动取/回退代码）", value="")
    theme = st.text_input("题材标签（可选）", value="")
    fund = st.text_input("基本面备注（可选）", value="")
    run = st.button("🔬 生成深度报告", type="primary", use_container_width=True)
    st.caption("拉个股日线+隔夜美股+美国新闻+DeepSeek，约 20-40 秒。")

st.warning("⚠️ 数据来自 AKShare 实时接口；**个股主力/北向资金取不到，资金面已降权**（用量比/换手代理）。"
           "隔夜美股据纳指/SOX 自动给 risk-on/off 定调。本工具仅供研究，不构成投资建议。所有买点配破 MA5 硬止损。")

if run and code.strip():
    with st.spinner("生成中：隔夜美股 → 美国新闻 → 个股技术 → DeepSeek …"):
        try:
            md = sd.analyze(code.strip(), name=name.strip() or None,
                            theme=theme.strip() or "—", fund=fund.strip() or "—", save=True)
            st.session_state["deepdive_md"] = md
            st.session_state["deepdive_code"] = code.strip()
        except Exception as exc:  # noqa: BLE001
            st.error(f"生成出错：{exc}")

md = st.session_state.get("deepdive_md")
if not md:
    st.info("左侧输入代码，点「生成深度报告」。")
    st.stop()

st.markdown(md)
st.download_button("⬇️ 导出报告(Markdown)", data=md,
                   file_name=f"深度_{st.session_state.get('deepdive_code','stock')}.md",
                   mime="text/markdown")
