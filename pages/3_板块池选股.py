"""板块池选股 Dashboard。

下拉选板块 → 一键真跑筛选（新浪K线，套超卖短线标准）→ DeepSeek 精析。
逻辑在 src/sector_screener.py，本页只负责交互与展示。
"""

import os
import sys

import pandas as pd
import streamlit as st

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src import sector_screener as ss  # noqa: E402
from src import deepseek_analyst  # noqa: E402
from src.screener import ScreenConfig  # noqa: E402
from src.config import config  # noqa: E402

st.set_page_config(page_title="板块池选股", page_icon="🧺", layout="wide")

st.title("🧺 板块池选股（超卖短线 + DeepSeek）")
st.caption("下拉选板块 ｜ 真实K线逐只筛 ｜ 明确入场·止损·目标·盈亏比 ｜ 不构成投资建议")

with st.sidebar:
    st.header("⚙️ 选股参数")
    sector = st.selectbox("板块池", ss.list_sectors(), index=0)
    top_n = st.slider("最多输出候选", 1, 8, 5)

    with st.expander("🎚️ 筛选阈值（默认=超卖短线标准）", expanded=False):
        dft = ScreenConfig()
        rsi_band = st.slider("RSI14 区间", 0, 100, (int(dft.rsi_min), int(dft.rsi_max)))
        chg20_band = st.slider("近20日涨幅区间(%)", -30, 30, (int(dft.chg20_min_pct), int(dft.chg20_max_pct)))
        dist52_band = st.slider("距52周低区间(%)", 0, 600, (int(dft.dist52_low_min_pct), int(dft.dist52_low_max_pct)),
                                help="上限剔除高位远离低点的暴涨股（无安全垫）")
        turn_band = st.slider("换手率区间(%)", 0, 30, (int(dft.turnover_min), int(dft.turnover_max)))
        volr = st.slider("最小量比", 0.5, 5.0, float(dft.vol_ratio_min), step=0.1)
        rr_min = st.slider("最小盈亏比", 1.0, 4.0, float(dft.min_rr), step=0.1)
        c1, c2 = st.columns(2)
        macd_rev = c1.checkbox("MACD反转", value=dft.require_macd_reversal)
        above_ma20 = c2.checkbox("站上MA20", value=dft.require_above_ma20, help="规避空头排列")

    run_btn = st.button("🚀 开始筛选", type="primary", use_container_width=True)
    st.caption("逐只拉真实日线，约 30–60 秒。")

    st.markdown("---")
    st.subheader("🧠 LLM 精析")
    _c = config.summary()
    st.write(f"- 服务商：{_c['服务商']}　模型：{_c['模型名称']}")
    st.write(f"- 模式：{_c['运行模式']}")
    if st.button("🔌 测试 DeepSeek 连接", use_container_width=True):
        with st.spinner("正在 ping…"):
            res = deepseek_analyst.test_connection()
        (st.success if res["ok"] else st.warning)(f"[{res['provider']}] {res['message']}")


def _build_cfg():
    return ScreenConfig(
        rsi_min=rsi_band[0], rsi_max=rsi_band[1],
        chg20_min_pct=chg20_band[0], chg20_max_pct=chg20_band[1],
        dist52_low_min_pct=dist52_band[0], dist52_low_max_pct=dist52_band[1],
        turnover_min=turn_band[0], turnover_max=turn_band[1],
        vol_ratio_min=volr, min_rr=rr_min,
        require_macd_reversal=macd_rev, require_above_ma20=above_ma20,
    )


st.warning("⚠️ 数据来自 AKShare 实时接口；本工具仅供研究，不构成投资建议。短线风险高，务必小仓、严格止损。")

if run_btn:
    prog = st.progress(0.0, text="准备开始…")

    def cb(msg, frac):
        prog.progress(min(max(frac, 0.0), 1.0), text=msg)

    try:
        st.session_state["pool_result"] = ss.screen_pool(sector, cfg=_build_cfg(), progress_callback=cb)
        st.session_state["pool_top_n"] = top_n
    except Exception as exc:  # noqa: BLE001
        st.error(f"筛选出错：{exc}")
    prog.empty()

result = st.session_state.get("pool_result")
if not result:
    st.info("左侧选板块 → 点「开始筛选」。")
    st.stop()

meta = result["meta"]
rows = result["rows"]
cands = result["candidates"][: st.session_state.get("pool_top_n", 5)]

st.header(f"一、{meta['sector']} 板块池筛选结果")
st.caption(f"数据时间：{meta['data_time']}｜池内 {meta['count']} 只 → 成功拉取 {meta['fetched']} → "
           f"通过硬性条件 {len(result['candidates'])} 只")
if meta.get("errors"):
    with st.expander(f"⚠️ 拉取/计算告警 {len(meta['errors'])} 条"):
        for e in meta["errors"]:
            st.text(e)

# 全池总览表
if rows:
    overview = pd.DataFrame([{
        "代码": r["code"], "名称": r["name"], "现价": r["price"], "RSI": r["rsi"],
        "MACD": r["macd_state"], "近20日%": r["chg20"], "距52低%": r["dist_52w_low_pct"],
        "换手%": r["turnover"], "量比": r["vol_ratio"], "市值(亿)": r["float_cap_yi"],
        "结果": "✅通过" if r["pass"] else "✗ " + "/".join(r["fails"][:3]),
    } for r in rows])
    st.dataframe(overview, use_container_width=True, hide_index=True)

st.header("二、候选股票")
if not cands:
    st.warning("本板块本次**无一通过**全部硬性条件（含盈亏比）。这是正常结果——"
               "说明该板块当前要么超买涨多、要么超卖未企稳，不符合超卖低吸标准。宁缺毋滥。")
else:
    if st.button("🧠 DeepSeek 精析（对候选逐只研判）"):
        env = {"trend": f"{meta['sector']}板块", "volume": "—", "sentiment": "—", "suggested_position": "3-5成"}
        with st.spinner("DeepSeek 精析中…"):
            st.session_state["pool_ds"] = deepseek_analyst.analyze_candidates(cands, env)
    ds = st.session_state.get("pool_ds", {})
    for i, c in enumerate(cands, 1):
        with st.container(border=True):
            st.subheader(f"{i}）{c['code']} {c['name']}　现价 {c['price']}")
            st.markdown(f"**核心逻辑：** {c['logic']}")
            cc = st.columns(4)
            cc[0].metric("入场区间", f"{c['entry_low']}~{c['entry_high']}")
            cc[1].metric("止损位", c["stop"])
            cc[2].metric("第一目标", c["target"])
            cc[3].metric("盈亏比", c["rr"])
            st.markdown(f"- 首仓 {c['first_position']}｜加仓：{c['add_condition']}｜市值 {c['float_cap_yi']} 亿")
            if ds.get(c["code"]):
                st.markdown("**🧠 DeepSeek 精析：**")
                st.markdown(ds[c["code"]])

st.markdown("---")
st.caption("本结果由板块池引擎基于 AKShare 真实日线生成，DeepSeek 交叉验证；仅供研究，不构成投资建议。")
