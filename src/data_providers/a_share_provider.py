"""A 股数据 provider，基于 AKShare。

设计原则：
- 任何 AKShare 接口失败都不能中断整个流程。
- 个股基本信息失败 -> 返回 mock/空值结构。
- 财务接口失败 -> 返回 "暂未获取到完整财务数据"。
- 新闻第一版使用 mock，并明确标注。
"""

import re
import time
from typing import Dict

import pandas as pd

from .base_provider import BaseDataProvider

# pandas 3.x 默认 future.infer_string=True，会把字符串列改为 pyarrow 后端。
# 而 AKShare 多个接口（stock_news_em / stock_zh_a_spot_em 等）内部使用
# str.replace(r"　", ...) 这类正则清洗，pyarrow 的 RE2 引擎不支持 \u 转义，
# 会抛 ArrowInvalid。关闭该推断即可让正则回退到 Python re 引擎，恢复正常。
try:
    pd.set_option("future.infer_string", False)
except Exception:  # noqa: BLE001
    pass


class AShareProvider(BaseDataProvider):
    """A 股数据源（AKShare）。"""

    market_name = "A股"
    currency = "人民币 CNY"

    # ------------------------------------------------------------------
    # 代码校验
    # ------------------------------------------------------------------
    def validate_symbol(self, symbol: str) -> bool:
        """A 股代码只需 6 位数字。"""
        return bool(re.fullmatch(r"\d{6}", str(symbol).strip()))

    # ------------------------------------------------------------------
    # 股票名称 + 实时行情
    # ------------------------------------------------------------------
    def get_stock_name(self, symbol: str) -> str:
        """通过 ak.stock_zh_a_spot_em 获取股票名称。"""
        symbol = str(symbol).strip()
        try:
            import akshare as ak

            spot = ak.stock_zh_a_spot_em()
            row = spot[spot["代码"] == symbol]
            if not row.empty:
                return str(row.iloc[0]["名称"])
        except Exception as exc:  # noqa: BLE001
            print(f"[AShareProvider] 获取股票名称失败: {exc}")
        return f"股票{symbol}"

    def get_realtime_price(self, symbol: str) -> Dict[str, object]:
        """获取实时行情（当前价等）。失败返回空值结构。"""
        symbol = str(symbol).strip()
        result = {"current_price": None, "change_pct": None, "volume": None}
        try:
            import akshare as ak

            spot = ak.stock_zh_a_spot_em()
            row = spot[spot["代码"] == symbol]
            if not row.empty:
                r = row.iloc[0]
                result["current_price"] = _to_float(r.get("最新价"))
                result["change_pct"] = _to_float(r.get("涨跌幅"))
                result["volume"] = _to_float(r.get("成交量"))
        except Exception as exc:  # noqa: BLE001
            print(f"[AShareProvider] 获取实时行情失败: {exc}")
        return result

    # ------------------------------------------------------------------
    # 历史 K 线
    # ------------------------------------------------------------------
    def get_history(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        period: str = "daily",
        adjust: str = "qfq",
    ) -> pd.DataFrame:
        """使用 ak.stock_zh_a_hist 获取历史行情并标准化列名。"""
        symbol = str(symbol).strip()
        # AKShare 需要 YYYYMMDD 格式
        start = _normalize_date(start_date)
        end = _normalize_date(end_date)

        # 公开数据接口偶发抖动，做有限次重试，提升弱网下的成功率
        last_exc = None
        for attempt in range(3):
            try:
                import akshare as ak

                df = ak.stock_zh_a_hist(
                    symbol=symbol,
                    period=period,
                    start_date=start,
                    end_date=end,
                    adjust=adjust,
                )
                if df is None or df.empty:
                    return self.empty_history()

                rename_map = {
                    "日期": "date",
                    "开盘": "open",
                    "最高": "high",
                    "最低": "low",
                    "收盘": "close",
                    "成交量": "volume",
                    "成交额": "amount",
                    "涨跌幅": "change_pct",
                }
                df = df.rename(columns=rename_map)
                keep_cols = [c for c in ["date", "open", "high", "low", "close", "volume"] if c in df.columns]
                df = df[keep_cols].copy()
                df["date"] = pd.to_datetime(df["date"], errors="coerce")
                for col in ["open", "high", "low", "close", "volume"]:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors="coerce")
                df = df.dropna(subset=["close"]).reset_index(drop=True)
                return df
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                print(f"[AShareProvider] 获取历史行情失败(第{attempt + 1}次): {exc}")
                time.sleep(1.0)

        print(f"[AShareProvider] 历史行情重试均失败: {last_exc}")
        return self.empty_history()

    # ------------------------------------------------------------------
    # 个股基本信息
    # ------------------------------------------------------------------
    def get_basic_info(self, symbol: str) -> Dict[str, object]:
        """获取个股基本信息，失败返回 mock/空值结构。"""
        symbol = str(symbol).strip()
        info: Dict[str, object] = {
            "symbol": symbol,
            "name": None,
            "industry": None,
            "total_market_cap": None,
            "pe": None,
            "pb": None,
            "is_mock": False,
        }
        try:
            import akshare as ak

            raw = ak.stock_individual_info_em(symbol=symbol)
            # raw 是两列 DataFrame: item / value
            kv = dict(zip(raw["item"], raw["value"]))
            info["name"] = kv.get("股票简称") or info["name"]
            info["industry"] = kv.get("行业")
            info["total_market_cap"] = kv.get("总市值")
            info["pe"] = kv.get("市盈率") or kv.get("市盈率-动态")
            info["pb"] = kv.get("市净率")
            return info
        except Exception as exc:  # noqa: BLE001
            print(f"[AShareProvider] 获取个股基本信息失败: {exc}")
            info["is_mock"] = True
            info["note"] = "个股基本信息获取失败，返回占位结构。"
            return info

    # ------------------------------------------------------------------
    # 财务指标
    # ------------------------------------------------------------------
    def get_financial(self, symbol: str) -> Dict[str, object]:
        """获取财务指标，失败返回提示文本。"""
        symbol = str(symbol).strip()
        result: Dict[str, object] = {
            "available": False,
            "summary": "暂未获取到完整财务数据",
            "indicators": {},
        }
        try:
            import akshare as ak

            # 同花顺财务摘要（按报告期）
            df = ak.stock_financial_abstract_ths(symbol=symbol, indicator="按报告期")
            if df is not None and not df.empty:
                latest = df.iloc[0].to_dict()
                # 只保留可序列化的标量
                indicators = {str(k): _stringify(v) for k, v in latest.items()}
                result["available"] = True
                result["summary"] = "已获取财务摘要（最新报告期）。"
                result["indicators"] = indicators
                return result
        except Exception as exc:  # noqa: BLE001
            print(f"[AShareProvider] 获取财务摘要(ths)失败: {exc}")

        # 退一步：尝试关键财务指标接口
        try:
            import akshare as ak

            df2 = ak.stock_financial_analysis_indicator(symbol=symbol)
            if df2 is not None and not df2.empty:
                latest = df2.iloc[-1].to_dict()
                indicators = {str(k): _stringify(v) for k, v in latest.items()}
                result["available"] = True
                result["summary"] = "已获取财务分析指标（最新一期）。"
                result["indicators"] = indicators
                return result
        except Exception as exc:  # noqa: BLE001
            print(f"[AShareProvider] 获取财务分析指标失败: {exc}")

        return result

    # ------------------------------------------------------------------
    # 新闻（第一版 mock）
    # ------------------------------------------------------------------
    def get_news(self, symbol: str, stock_name: str = "", limit: int = 8) -> Dict[str, object]:
        """获取真实新闻（东方财富 ak.stock_news_em）。

        - 解析标题、发布时间、来源、正文摘要等真实字段。
        - 接口偶发抖动，做有限次重试。
        - 全部失败或为空时才退回 mock，并标注 is_mock=True。
        """
        symbol = str(symbol).strip()
        name = stock_name or f"股票{symbol}"

        # 尝试真实新闻接口（带重试）
        last_exc = None
        for attempt in range(3):
            try:
                import akshare as ak

                df = ak.stock_news_em(symbol=symbol)
                if df is None or df.empty:
                    # 接口正常但当前无新闻，直接退回 mock 分支
                    break

                items = []       # 给界面/报告展示的精简条目
                details = []      # 给新闻分析师推理的含正文摘要条目
                for _, row in df.head(limit).iterrows():
                    title = _stringify(row.get("新闻标题") or row.get("标题")).strip()
                    if not title:
                        continue
                    publish_time = _stringify(row.get("发布时间")).strip()
                    source = _stringify(row.get("文章来源") or row.get("来源")).strip()
                    content = _stringify(row.get("新闻内容") or row.get("内容")).strip()
                    link = _stringify(row.get("新闻链接") or row.get("链接")).strip()

                    meta = " ｜ ".join([x for x in (source, publish_time) if x])
                    items.append(f"{title}（{meta}）" if meta else title)

                    snippet = content[:120] + ("…" if len(content) > 120 else "")
                    detail = f"- 标题：{title}"
                    if meta:
                        detail += f"\n  来源/时间：{meta}"
                    if snippet:
                        detail += f"\n  摘要：{snippet}"
                    details.append({
                        "title": title,
                        "time": publish_time,
                        "source": source,
                        "snippet": snippet,
                        "link": link,
                        "text": detail,
                    })

                if items:
                    return {
                        "is_mock": False,
                        "items": items,
                        "details": details,
                        "summary": "；".join(items),
                        "note": (
                            f"新闻来自 AKShare 东方财富 stock_news_em 接口，"
                            f"共 {len(items)} 条最新个股相关新闻。"
                        ),
                    }
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                print(f"[AShareProvider] 获取真实新闻失败(第{attempt + 1}次): {exc}")
                time.sleep(1.0)

        if last_exc is not None:
            print(f"[AShareProvider] 真实新闻重试均失败，使用 mock: {last_exc}")

        # Mock 新闻（仅在真实接口失败/为空时使用）
        mock_items = [
            f"{name}近期经营保持稳定，暂无重大异常公告（占位）。",
            f"{name}所处行业整体政策环境中性偏暖（占位）。",
            f"市场对{name}关注度一般，无明显资金异动（占位）。",
        ]
        return {
            "is_mock": True,
            "items": mock_items,
            "details": [],
            "summary": "；".join(mock_items),
            "note": "新闻数据为模拟/占位，需接入真实新闻源后提高可信度。",
        }


# ----------------------------------------------------------------------------
# 辅助函数
# ----------------------------------------------------------------------------

def _normalize_date(date_str: str) -> str:
    """把各种日期格式标准化为 AKShare 需要的 YYYYMMDD。"""
    s = str(date_str).strip().replace("-", "").replace("/", "")
    return s


def _to_float(value):
    try:
        if value is None or value == "" or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _stringify(value) -> str:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return ""
        return str(value)
    except Exception:  # noqa: BLE001
        return ""
