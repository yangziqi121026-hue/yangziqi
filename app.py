"""TradingAgents 多市场智能体金融分析系统 - Streamlit 主页面。

只负责界面与交互，业务逻辑全部放在 src 目录：
- 数据获取 / 指标 / 智能体 / 报告生成 都在 src 中实现。
- app.py 不直接做数据处理与报告拼装。
"""

import datetime as dt

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src import database
from src.config import config
from src.data_providers import get_provider
from src.indicators import compute_all
from src.workflow import stream_analysis

# ----------------------------------------------------------------------------
# 页面基础配置
# ----------------------------------------------------------------------------
st.set_page_config(
    page_title="TradingAgents 多市场智能体金融分析框架",
    page_icon="📈",
    layout="wide",
)

database.init_db()

st.title("TradingAgents：多市场智能体 LLM 金融分析框架")
st.caption("A股优先｜预留美股与港股扩展")

# ----------------------------------------------------------------------------
# 侧边栏：配置项
# ----------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ 分析配置")

    market = st.selectbox("市场选择", ["A股", "美股", "港股"], index=0)
    symbol = st.text_input("股票代码", value="600519", help="A 股请输入 6 位数字代码")
    depth = st.selectbox("分析深度", ["快速", "标准", "深度"], index=1)
    adjust_label = st.selectbox("复权方式", ["前复权 (qfq)", "后复权 (hfq)", "不复权 (none)"], index=0)
    period_label = st.selectbox("数据周期", ["日线 (daily)", "周线 (weekly)", "月线 (monthly)"], index=0)

    today = dt.date.today()
    default_start = today - dt.timedelta(days=365)
    start_date = st.date_input("开始日期", value=default_start)
    end_date = st.date_input("结束日期", value=today)

    st.markdown("---")
    st.subheader("🤖 模型信息")
    for k, v in config.summary().items():
        st.write(f"- {k}：{v}")
    if config.is_mock_mode():
        st.info("当前为 Mock 模式：无需 API Key 也可跑通完整流程，结果为占位输出。")

    st.markdown("---")
    start_btn = st.button("🚀 开始分析", type="primary", use_container_width=True)

# 复权 / 周期映射
_adjust_map = {"前复权 (qfq)": "qfq", "后复权 (hfq)": "hfq", "不复权 (none)": ""}
_period_map = {"日线 (daily)": "daily", "周线 (weekly)": "weekly", "月线 (monthly)": "monthly"}
adjust = _adjust_map[adjust_label]
period = _period_map[period_label]


# ----------------------------------------------------------------------------
# 校验输入
# ----------------------------------------------------------------------------
def _validate_inputs() -> bool:
    provider = get_provider(market)
    if market == "A股" and not provider.validate_symbol(symbol):
        st.error("请输入正确的 A 股 6 位股票代码")
        return False
    if not str(symbol).strip():
        st.error("请输入股票代码")
        return False
    if start_date > end_date:
        st.error("开始日期不能晚于结束日期")
        return False
    return True


# ----------------------------------------------------------------------------
# 技术图表
# ----------------------------------------------------------------------------
def _render_chart(price_df: pd.DataFrame, title: str = "") -> None:
    if price_df is None or price_df.empty:
        st.warning("暂无行情数据，无法绘制技术图表。")
        return

    df = compute_all(price_df.copy())
    x = df["date"] if "date" in df.columns else df.index

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=df["close"], mode="lines", name="收盘价",
                             line=dict(color="#1f77b4", width=2)))
    for ma, color in [("MA5", "#ff7f0e"), ("MA10", "#2ca02c"),
                      ("MA20", "#d62728"), ("MA60", "#9467bd")]:
        if ma in df.columns:
            fig.add_trace(go.Scatter(x=x, y=df[ma], mode="lines", name=ma,
                                     line=dict(color=color, width=1)))
    fig.update_layout(
        title=title or "收盘价与均线",
        xaxis_title="日期",
        yaxis_title="价格",
        hovermode="x unified",
        height=520,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    st.plotly_chart(fig, use_container_width=True)


# ----------------------------------------------------------------------------
# 主区域：tabs
# ----------------------------------------------------------------------------
tab_report, tab_process, tab_chart, tab_history = st.tabs(
    ["📑 最终报告", "🤝 智能体过程", "📊 技术图表", "🕘 历史记录"]
)

# 触发分析
if start_btn and _validate_inputs():
    start_str = start_date.strftime("%Y%m%d")
    end_str = end_date.strftime("%Y%m%d")

    process_area = tab_process.container()
    progress_bar = process_area.progress(0, text="准备开始...")
    agent_outputs = {}
    final_context = None
    final_report = None

    total_steps = 10  # 1 数据 + 9 智能体
    step = 0

    try:
        for event in stream_analysis(market, symbol.strip(), start_str, end_str, period, adjust):
            if event["stage"] == "data":
                step += 1
                progress_bar.progress(step / total_steps, text="✅ 数据准备完成")
                final_context = event["context"]
                info = final_context["stock_info"]
                process_area.success(
                    f"已加载：{info['name']}（{info['symbol']}）当前价 {info['current_price']} "
                    f"{info['currency']}"
                )
            elif event["stage"] == "agent":
                step += 1
                progress_bar.progress(step / total_steps, text=f"🤖 {event['name']} 分析中...")
                agent_outputs[event["key"]] = (event["name"], event["output"])
                final_context = event["context"]
                with process_area.expander(f"🤖 {event['name']}", expanded=False):
                    st.markdown(event["output"])
            elif event["stage"] == "done":
                progress_bar.progress(1.0, text="✅ 分析完成")
                final_report = event["report"]
                final_context = event["context"]

        # 缓存到 session_state 供各 tab 使用
        st.session_state["last_report"] = final_report
        st.session_state["last_context"] = final_context
    except Exception as exc:  # noqa: BLE001
        process_area.error(f"分析过程出错：{exc}")


# 最终报告 tab
with tab_report:
    if st.session_state.get("last_report"):
        report_md = st.session_state["last_report"]
        ctx = st.session_state.get("last_context", {})
        info = ctx.get("stock_info", {})
        st.download_button(
            "⬇️ 导出 Markdown 报告",
            data=report_md,
            file_name=f"report_{info.get('symbol', 'stock')}.md",
            mime="text/markdown",
        )
        st.markdown(report_md)
    else:
        st.info("请在左侧配置参数并点击「开始分析」生成报告。")


# 智能体过程 tab（若没有刚跑过，展示提示）
with tab_process:
    if not start_btn:
        ctx = st.session_state.get("last_context")
        if ctx and ctx.get("agents"):
            st.subheader("上次分析的智能体过程")
            labels = {
                "fundamental": "基本面分析师", "news": "新闻分析师",
                "sentiment": "情绪分析师", "technical": "技术分析师",
                "bull": "看涨研究员", "bear": "看跌研究员",
                "research_manager": "研究经理", "trader": "交易员",
                "risk_manager": "风控员",
            }
            for key, label in labels.items():
                if key in ctx["agents"]:
                    with st.expander(f"🤖 {label}", expanded=False):
                        st.markdown(ctx["agents"][key])
        else:
            st.info("智能体执行过程会在分析时实时展示在这里。")


# 技术图表 tab
with tab_chart:
    ctx = st.session_state.get("last_context")
    if ctx and ctx.get("price_df") is not None and not ctx["price_df"].empty:
        info = ctx.get("stock_info", {})
        _render_chart(ctx["price_df"], title=f"{info.get('name')}（{info.get('symbol')}）收盘价与均线")
    else:
        st.info("完成一次分析后，这里会展示收盘价与 MA5/MA10/MA20/MA60。")


# 历史记录 tab
with tab_history:
    st.subheader("历史分析记录")
    if st.button("🔄 刷新历史记录"):
        st.rerun()
    history = database.list_history(limit=50)
    if not history:
        st.info("暂无历史记录。")
    else:
        df_hist = pd.DataFrame(history)
        df_hist = df_hist.rename(columns={
            "id": "ID", "created_at": "时间", "market": "市场",
            "symbol": "代码", "stock_name": "名称", "current_price": "价格",
            "final_rating": "评级", "trade_suggestion": "建议",
        })
        st.dataframe(df_hist, use_container_width=True, hide_index=True)

        ids = [h["id"] for h in history]
        selected_id = st.selectbox("查看历史报告（选择 ID）", ids)
        if selected_id:
            record = database.get_report(selected_id)
            if record:
                st.download_button(
                    "⬇️ 导出该历史报告",
                    data=record["report_markdown"] or "",
                    file_name=f"history_{record['symbol']}_{selected_id}.md",
                    mime="text/markdown",
                )
                with st.expander("查看报告正文", expanded=True):
                    st.markdown(record["report_markdown"] or "（无正文）")
