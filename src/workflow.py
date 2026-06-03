"""分析流程编排。

职责：
- 根据 market 选择 provider。
- 拉取数据（行情、基本信息、财务、新闻），任何失败都不中断。
- 计算技术指标。
- 按顺序调用所有智能体。
- 生成最终报告并保存历史。

提供 run_analysis() 一次性执行，和 stream_analysis() 生成器版本（用于
界面实时展示进度）。智能体不直接取数，只消费 context。
"""

from datetime import datetime
from typing import Callable, Dict, Iterator, Optional, Tuple

from . import indicators
from .agents import (
    BearResearcher,
    BullResearcher,
    FundamentalAnalyst,
    NewsAnalyst,
    ResearchManager,
    RiskManager,
    SentimentAnalyst,
    TechnicalAnalyst,
    Trader,
)
from .data_providers import get_provider
from .report_generator import generate_report, save_report
from . import database

# 智能体执行顺序：(context key, 显示名, Agent 类)
_AGENT_PIPELINE: Tuple[Tuple[str, str, type], ...] = (
    ("fundamental", "基本面分析师", FundamentalAnalyst),
    ("news", "新闻分析师", NewsAnalyst),
    ("sentiment", "情绪分析师", SentimentAnalyst),
    ("technical", "技术分析师", TechnicalAnalyst),
    ("bull", "看涨研究员", BullResearcher),
    ("bear", "看跌研究员", BearResearcher),
    ("research_manager", "研究经理", ResearchManager),
    ("trader", "交易员", Trader),
    ("risk_manager", "风控员", RiskManager),
)


def _build_data_context(
    market: str,
    symbol: str,
    start_date: str,
    end_date: str,
    period: str,
    adjust: str,
) -> Dict:
    """拉取数据并构建初始 context（含 price_df 与指标）。"""
    provider = get_provider(market)

    # 名称 + 历史行情
    stock_name = provider.get_stock_name(symbol)
    price_df = provider.get_history(symbol, start_date, end_date, period, adjust)

    # 基本信息 / 财务 / 新闻（失败都不中断）
    basic_info = provider.get_basic_info(symbol)
    financial = provider.get_financial(symbol)
    news = provider.get_news(symbol, stock_name)

    # 名称兜底
    if basic_info.get("name"):
        stock_name = basic_info["name"]

    # 当前价格：优先历史最后收盘，A股可补实时
    current_price = None
    if price_df is not None and not price_df.empty:
        current_price = round(float(price_df["close"].iloc[-1]), 3)
    if current_price is None and hasattr(provider, "get_realtime_price"):
        try:
            rt = provider.get_realtime_price(symbol)
            current_price = rt.get("current_price")
        except Exception:  # noqa: BLE001
            current_price = None

    # 技术指标
    ind_summary = indicators.summarize(price_df)

    # 数据质量说明
    price_ok = price_df is not None and not price_df.empty
    data_quality = {
        "price": (
            f"已获取 {ind_summary.get('data_points')} 条 K 线数据。"
            if price_ok
            else "行情数据获取失败或为空，请检查代码/日期/网络。"
        ),
        "financial": financial.get("summary", "暂未获取到完整财务数据"),
        "news": (
            "新闻数据为模拟/占位，需接入真实新闻源后提高可信度。"
            if news.get("is_mock")
            else "新闻数据来自真实接口。"
        ),
        "anomaly": "无" if price_ok else "行情数据缺失",
        "reliability": (
            "本报告含 mock/占位数据，结论可信度有限，仅供研究与学习。"
            if (news.get("is_mock") or not financial.get("available") or not price_ok)
            else "数据相对完整，但仍需谨慎参考。"
        ),
    }

    context: Dict = {
        "stock_info": {
            "market": market,
            "symbol": symbol,
            "name": stock_name,
            "current_price": current_price,
            "currency": provider.currency,
            "analysis_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "period": period,
            "adjust": adjust,
        },
        "basic_info": basic_info,
        "financial": financial,
        "news": news,
        "indicators": ind_summary,
        "price_df": price_df,
        "data_quality": data_quality,
        "agents": {},
    }
    return context


def _derive_final(context: Dict) -> Dict:
    """从风控/交易结论中粗略提炼最终结论（不依赖 LLM，保证稳定）。"""
    trader_text = context.get("agents", {}).get("trader", "") or ""
    risk_text = context.get("agents", {}).get("risk_manager", "") or ""

    # 操作建议
    suggestion = "观望"
    if "买入" in trader_text:
        suggestion = "买入"
    elif "卖出" in trader_text:
        suggestion = "卖出"

    # 风险等级（按显式标注优先匹配）
    if "风险等级：高" in risk_text:
        risk_level = "高"
    elif "风险等级：低" in risk_text:
        risk_level = "低"
    else:
        risk_level = "中"

    rating_map = {"买入": "偏多", "卖出": "偏空", "观望": "中性"}
    return {
        "rating": rating_map.get(suggestion, "中性"),
        "reason": f"交易员建议为「{suggestion}」，风控判断风险等级约为「{risk_level}」，综合多空分析得出。",
        "caution": "请结合数据质量说明审慎参考；mock/占位数据会显著降低结论可信度。",
        "suggestion": suggestion,
        "risk_level": risk_level,
    }


def stream_analysis(
    market: str,
    symbol: str,
    start_date: str,
    end_date: str,
    period: str = "daily",
    adjust: str = "qfq",
) -> Iterator[Dict]:
    """生成器版本：逐步产出进度，便于界面实时展示。

    每次 yield 一个事件 dict：
    - {"stage": "data", "message": ..., "context": context}
    - {"stage": "agent", "key": ..., "name": ..., "output": ..., "context": context}
    - {"stage": "done", "report": markdown, "context": context, "record_id": id}
    """
    # 1. 数据
    context = _build_data_context(market, symbol, start_date, end_date, period, adjust)
    yield {"stage": "data", "message": "数据准备完成", "context": context}

    # 2. 依次执行智能体
    for key, display_name, agent_cls in _AGENT_PIPELINE:
        agent = agent_cls()
        output = agent.run(context)
        context["agents"][key] = output
        yield {
            "stage": "agent",
            "key": key,
            "name": display_name,
            "output": output,
            "context": context,
        }

    # 3. 最终结论 + 报告
    context["final"] = _derive_final(context)
    report = generate_report(context)
    context["report"] = report

    # 4. 保存报告文件 + 历史
    record_id = None
    try:
        save_report(report, symbol, market)
    except Exception as exc:  # noqa: BLE001
        print(f"[workflow] 保存报告文件失败: {exc}")
    try:
        info = context["stock_info"]
        # 历史记录里不保存 DataFrame
        serializable = {k: v for k, v in context.items() if k != "price_df"}
        record_id = database.save_analysis(
            market=market,
            symbol=symbol,
            stock_name=str(info.get("name")),
            current_price=str(info.get("current_price")),
            final_rating=str(context["final"].get("rating")),
            trade_suggestion=str(context["final"].get("suggestion")),
            report_markdown=report,
            result=serializable,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[workflow] 保存历史记录失败: {exc}")

    yield {"stage": "done", "report": report, "context": context, "record_id": record_id}


def run_analysis(
    market: str,
    symbol: str,
    start_date: str,
    end_date: str,
    period: str = "daily",
    adjust: str = "qfq",
    progress_callback: Optional[Callable[[str, str], None]] = None,
) -> Dict:
    """一次性执行完整分析，返回包含 report 与 context 的结果 dict。

    progress_callback(stage, message) 可选，用于非流式场景下报告进度。
    """
    result: Dict = {}
    for event in stream_analysis(market, symbol, start_date, end_date, period, adjust):
        if progress_callback:
            if event["stage"] == "agent":
                progress_callback("agent", event["name"])
            elif event["stage"] == "data":
                progress_callback("data", event["message"])
        if event["stage"] == "done":
            result = {
                "report": event["report"],
                "context": event["context"],
                "record_id": event.get("record_id"),
            }
    return result
