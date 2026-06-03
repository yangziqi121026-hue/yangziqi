"""基本面分析师。"""

from typing import Dict

from .base_agent import BaseAgent


class FundamentalAnalyst(BaseAgent):
    name = "Fundamental Analyst"
    role = "基本面分析师"
    mock_role = "fundamental"
    system_prompt = (
        "你是 Fundamental Analyst 基本面分析师。"
        "你只负责分析股票基本面，包括营收、利润、估值、成长性、财务健康度。"
        "如果数据不足，必须明确说明数据不足，并指出结论可信度下降。"
        "不要给出最终交易建议，只输出基本面判断。"
        "输出使用简洁的中文 Markdown。"
    )

    def build_user_prompt(self, context: Dict) -> str:
        info = context.get("stock_info", {})
        basic = context.get("basic_info", {})
        fin = context.get("financial", {})

        fin_status = fin.get("summary", "暂未获取到完整财务数据")
        fin_indicators = fin.get("indicators", {})
        indicators_text = "\n".join(
            f"- {k}: {v}" for k, v in list(fin_indicators.items())[:20]
        ) or "（无财务指标明细）"

        data_sufficient = "充足" if fin.get("available") else "不足"

        return (
            f"请基于以下信息进行基本面分析：\n\n"
            f"{self.format_stock_info(context)}\n"
            f"行业：{basic.get('industry')}\n"
            f"总市值：{basic.get('total_market_cap')}\n"
            f"市盈率：{basic.get('pe')} 市净率：{basic.get('pb')}\n\n"
            f"财务数据状态：{fin_status}（数据完整度：{data_sufficient}）\n"
            f"财务指标明细：\n{indicators_text}\n\n"
            f"请输出：营收与利润情况、估值水平、成长性、财务风险、基本面结论、"
            f"以及数据完整性说明。若财务数据不足，请明确指出结论可信度下降。"
        )
