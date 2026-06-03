"""最终报告生成器。

按照固定格式生成 Markdown 报告，并支持保存到 reports/ 目录。
报告格式严格固定，不允许随意更改。
"""

import os
import re
from datetime import datetime
from typing import Dict

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPORTS_DIR = os.path.join(_BASE_DIR, "reports")


def _v(value, default: str = "暂无数据") -> str:
    """把可能为 None 的值转换为展示字符串。"""
    if value is None or value == "":
        return default
    return str(value)


def generate_report(context: Dict) -> str:
    """根据 workflow 产出的 context 生成固定格式报告。"""
    info = context.get("stock_info", {})
    ind = context.get("indicators", {})
    agents = context.get("agents", {})
    dq = context.get("data_quality", {})
    final = context.get("final", {})

    report = f"""# TradingAgents 多市场智能体金融分析报告

## 一、股票基本信息
- 市场：{_v(info.get('market'))}
- 股票代码：{_v(info.get('symbol'))}
- 股票名称：{_v(info.get('name'))}
- 当前价格：{_v(info.get('current_price'))}
- 交易货币：{_v(info.get('currency'))}
- 分析时间：{_v(info.get('analysis_time'))}
- 数据周期：{_v(info.get('period'))}
- 复权方式：{_v(info.get('adjust'))}

## 二、市场概况
- 当前趋势：{_v(ind.get('trend'))}
- 近 20 日涨跌幅：{_v(ind.get('change_20d_pct'))}%
- 近 52 周高点：{_v(ind.get('high_52w'))}
- 近 52 周低点：{_v(ind.get('low_52w'))}
- 成交量变化：{_v(ind.get('volume_change_pct'))}%
- 初步市场判断：{_v(ind.get('trend'))}

## 三、基本面分析
{_v(agents.get('fundamental'), '暂无基本面分析。')}

## 四、新闻与政策分析
{_v(agents.get('news'), '暂无新闻分析。')}

## 五、市场情绪分析
{_v(agents.get('sentiment'), '暂无情绪分析。')}

## 六、技术面分析
- MA5：{_v(ind.get('MA5'))}
- MA10：{_v(ind.get('MA10'))}
- MA20：{_v(ind.get('MA20'))}
- MA60：{_v(ind.get('MA60'))}
- RSI14：{_v(ind.get('RSI14'))}
- MACD：{_v(ind.get('MACD'))}（Signal：{_v(ind.get('MACD_Signal'))} / Hist：{_v(ind.get('MACD_Hist'))}）
- 支撑位：{_v(ind.get('support'))}
- 压力位：{_v(ind.get('resistance'))}
- 技术面结论：
{_v(agents.get('technical'), '暂无技术面分析。')}

## 七、多空辩论
### 看涨观点
{_v(agents.get('bull'), '暂无看涨观点。')}

### 看跌观点
{_v(agents.get('bear'), '暂无看跌观点。')}

## 八、研究经理总结
{_v(agents.get('research_manager'), '暂无研究经理总结。')}

## 九、交易员建议
{_v(agents.get('trader'), '暂无交易员建议。')}

## 十、风控结论
{_v(agents.get('risk_manager'), '暂无风控结论。')}

## 十一、数据质量说明
- 行情数据：{_v(dq.get('price'))}
- 财务数据：{_v(dq.get('financial'))}
- 新闻数据：{_v(dq.get('news'))}
- 数据异常：{_v(dq.get('anomaly'), '无')}
- 可信度提醒：{_v(dq.get('reliability'))}

## 十二、最终结论
- 综合评级：{_v(final.get('rating'))}
- 核心理由：{_v(final.get('reason'))}
- 注意事项：{_v(final.get('caution'))}
- 免责声明：本报告由 AI 多智能体系统生成，仅用于研究和学习，不构成任何投资建议。
"""
    return report


def save_report(report_markdown: str, symbol: str, market: str = "") -> str:
    """保存报告到 reports/ 目录，返回文件路径。"""
    os.makedirs(_REPORTS_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_symbol = re.sub(r"[^0-9A-Za-z_]", "", str(symbol)) or "stock"
    filename = f"report_{safe_symbol}_{timestamp}.md"
    path = os.path.join(_REPORTS_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(report_markdown)
    return path
