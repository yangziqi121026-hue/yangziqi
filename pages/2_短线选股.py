"""短线选股 Dashboard（1–5 天超短线）。

点「开始选股」实时跑全A筛选，按严格规则输出候选 + 入场/加仓/止损/目标/盈亏比。
逻辑全在 src/screener.py，本页只负责交互与展示。
"""

import os
import sys

import pandas as pd
import streamlit as st

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src import screener  # noqa: E402

st.set_page_config(page_title="短线选股", page_icon="⚡", layout="wide")

st.title("⚡ 短线选股引擎（1–5 天超短线）")
st.caption("全A实时筛选 ｜ 左侧低吸/放量突破 ｜ 明确入场·加仓·止损·盈亏比 ｜ 不构成投资建议")

with st.sidebar:
    st.header("⚙️ 选股参数")
    deep_limit = st.slider("深筛数量上限", 10, 80, 40, step=5,
                           help="粗筛后进入深度技术筛选的股票数，越大越慢")
    top_n = st.slider("最多输出候选", 1, 8, 5)
    st.markdown("---")
    run_btn = st.button("🚀 开始选股", type="primary", use_container_width=True)
    st.caption("数据来自 AKShare 实时接口；全市场扫描较慢请耐心等待。")

st.warning(
    "⚠️ 数据来自 AKShare 实时接口，受网络与接口稳定性影响可能不完整；"
    "本工具仅供研究，不构成投资建议。短线风险高，务必小仓、严格止损。"
)

# 触发选股
if run_btn:
    prog = st.progress(0.0, text="准备开始…")

    def cb(msg, frac):
        prog.progress(min(max(frac, 0.0), 1.0), text=msg)

    try:
        result = screener.run_screen(deep_limit=deep_limit, top_n=top_n, progress_callback=cb)
        st.session_state["screen_result"] = result
    except Exception as exc:  # noqa: BLE001
        st.error(f"选股过程出错：{exc}")
    prog.empty()

result = st.session_state.get("screen_result")

if not result:
    st.info("点击左侧「开始选股」运行实时筛选。")
    st.stop()

env = result["market_env"]
meta = result["meta"]
cands = result["candidates"]

# ---------------------------------------------------------------------------
# 一、大盘与环境
# ---------------------------------------------------------------------------
st.header("一、大盘与环境")
e1, e2, e3, e4 = st.columns(4)
e1.metric("大盘趋势", env.get("trend", "未知"),
          help=f"上证收盘 {env.get('index_close')} / MA20 {env.get('index_ma20')}")
e2.metric("量能", env.get("volume", "未知"))
e3.metric("情绪/宽度", env.get("sentiment", "未知"), help=env.get("breadth", ""))
e4.metric("建议总仓位", env.get("suggested_position", "—"))
st.caption(
    f"数据时间：{meta['data_time']}　｜　全市场 {meta['universe']} 只 → 粗筛 {meta['coarse']} 只 "
    f"→ 深筛 {meta['deep_checked']} 只 → 入选 {len(cands)} 只"
)
if meta.get("errors"):
    with st.expander(f"⚠️ 过程告警 {len(meta['errors'])} 条", expanded=False):
        for e in meta["errors"][:30]:
            st.text(e)

# ---------------------------------------------------------------------------
# 二、候选股票
# ---------------------------------------------------------------------------
st.header("二、下周一候选股票")
if not cands:
    st.warning(
        "本次未筛出满足全部硬性条件（含盈亏比≥1.5）的标的。"
        "这是正常结果——宁缺毋滥。可放宽深筛数量或换交易日重试。"
    )
else:
    # 概览表
    overview = pd.DataFrame([{
        "代码": c["code"], "名称": c["name"], "现价": c["price"],
        "RSI": c["rsi"], "MACD": c["macd_state"], "近20日%": c["chg20"],
        "量比": c["vol_ratio"], "换手%": c["turnover"], "流通市值(亿)": c["float_cap_yi"],
        "题材": c["theme"], "入场区间": f"{c['entry_low']}~{c['entry_high']}",
        "止损": c["stop"], "目标": c["target"], "盈亏比": c["rr"], "首仓": c["first_position"],
    } for c in cands])
    st.dataframe(overview, use_container_width=True, hide_index=True)

    for i, c in enumerate(cands, 1):
        with st.container(border=True):
            st.subheader(f"{i}）{c['code']} {c['name']}　现价 {c['price']}")
            st.markdown(f"**核心逻辑：** {c['logic']}")
            cc = st.columns(4)
            cc[0].metric("入场区间", f"{c['entry_low']}~{c['entry_high']}")
            cc[1].metric("止损位", c["stop"])
            cc[2].metric("第一目标", c["target"])
            cc[3].metric("盈亏比", c["rr"])
            st.markdown(
                f"- **首仓仓位**：{c['first_position']}（占总仓位）\n"
                f"- **加仓条件**：{c['add_condition']}\n"
                f"- **基本面**：{c['fund_status']}　｜　流通市值 {c['float_cap_yi']} 亿"
            )

# ---------------------------------------------------------------------------
# 三、最终结论
# ---------------------------------------------------------------------------
st.header("三、最终结论")
if cands:
    top = cands[0]
    st.success(
        f"**首选（最值得小仓试错）：{top['code']} {top['name']}** —— "
        f"盈亏比 {top['rr']}、{top['macd_state']}、题材 {top['theme']}；"
        f"入场 {top['entry_low']}~{top['entry_high']}，止损 {top['stop']}，目标 {top['target']}，"
        f"首仓 {top['first_position']}。"
    )
    if len(cands) > 1:
        sub = "；".join(f"{c['code']} {c['name']}(RR {c['rr']})" for c in cands[1:3])
        st.info(f"**次选（观察，等放量站稳信号再介入）：** {sub}")
    st.error(
        "**需规避：** ST/退市风险股、高位连板接力、量比异常放大已涨停的票、"
        "近1月解禁股（解禁数据若缺失请自行核验）、无 Q1 业绩确认的标的。"
    )
else:
    st.info("无候选则**首选空仓**，等下一个符合条件的交易日。短线最大的纪律是「没有就不做」。")

st.markdown("---")
st.caption("本结果由选股引擎基于 AKShare 实时数据生成，仅供研究学习，不构成投资建议；请以实时行情核验为准。")
