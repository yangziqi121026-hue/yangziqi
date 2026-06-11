"""A股盘前自动报告生成器（供每日定时任务调用）。

汇总：① 隔夜美股三大指数 ② 东财财经快讯(外围/科技/政策/减持过滤)
③ A股分层观察池技术清单(daily_watch) → 生成 Markdown 报告存到 reports/。

所有网络调用异常兜底；个股主力/北向资金本环境取不到 → 资金面降权。
不构成投资建议；所有买点配破 MA5 硬止损。
"""

import os
from datetime import datetime
from typing import List

import pandas as pd

from . import daily_watch

try:
    pd.set_option("future.infer_string", False)
except Exception:  # noqa: BLE001
    pass

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPORTS = os.path.join(_BASE, "reports")

_NEWS_KW = ["CPI", "通胀", "美股", "纳指", "道指", "标普", "降息", "加息", "美联储",
            "芯片", "光刻", "算力", "光模块", "硅光", "稀土", "减持", "解禁", "业绩",
            "工信部", "英伟达", "出口管制", "6G", "光伏", "AI"]

# 外国/海外/地缘 专栏关键词
_FOREIGN_KW = ["美国", "美股", "纳指", "道指", "标普", "美联储", "降息", "加息", "CPI",
               "PCE", "非农", "美债", "美元", "鲍威尔", "特朗普", "英伟达", "甲骨文",
               "台积电", "AMD", "博通", "苹果", "微软", "谷歌", "特斯拉", "OpenAI",
               "出口管制", "关税", "欧洲", "欧央行", "日本", "日银", "韩国", "俄", "乌",
               "伊朗", "中东", "OPEC", "原油", "黄金", "地缘", "以色列", "比特币"]


def _us_indices() -> List[str]:
    out = []
    try:
        import akshare as ak

        for nm, s in [("纳指", ".IXIC"), ("标普", ".INX"), ("道指", ".DJI"),
                      ("费城半导体SOX", ".SOX")]:
            try:
                d = ak.index_us_stock_sina(symbol=s)
                r = d.iloc[-1]; p = d.iloc[-2]
                chg = (float(r["close"]) / float(p["close"]) - 1) * 100
                out.append(f"- {nm}：{float(r['close']):.2f}（{chg:+.2f}%）｜日期 {r.get('date','')}")
            except Exception:  # noqa: BLE001
                out.append(f"- {nm}：取数失败，需核验")
    except Exception:  # noqa: BLE001
        out.append("- 美股指数接口不可用，需核验")
    return out


def _us_leaders() -> List[str]:
    """美股科技龙头（隔夜表现，直接映射A股算力/半导体情绪）。"""
    out = []
    try:
        import akshare as ak

        for nm, s in [("英伟达", "NVDA"), ("台积电", "TSM"), ("AMD", "AMD"),
                      ("博通", "AVGO")]:
            try:
                d = ak.stock_us_daily(symbol=s)
                r = d.iloc[-1]; p = d.iloc[-2]
                chg = (float(r["close"]) / float(p["close"]) - 1) * 100
                out.append(f"- {nm} {s}：{float(r['close']):.2f}（{chg:+.2f}%）")
            except Exception:  # noqa: BLE001
                out.append(f"- {nm} {s}：取数失败，需核验")
    except Exception:  # noqa: BLE001
        out.append("- 美股龙头接口不可用，需核验")
    return out


def _foreign_news(limit: int = 8) -> List[str]:
    """海外/外围/地缘 新闻专栏（从东财快讯按外国关键词过滤）。"""
    try:
        import akshare as ak

        df = ak.stock_info_global_em().rename(columns={"标题": "t", "发布时间": "tm"})
        hits = []
        for _, x in df.iterrows():
            if any(k in str(x["t"]) for k in _FOREIGN_KW):
                hits.append(f"- [{str(x['tm'])[:16]}] {str(x['t'])[:60]}")
            if len(hits) >= limit:
                break
        return hits or ["- 暂无命中海外关键词的快讯，需核验"]
    except Exception as exc:  # noqa: BLE001
        return [f"- 海外快讯获取失败：{exc}"]


def _news(limit: int = 12) -> List[str]:
    try:
        import akshare as ak

        df = ak.stock_info_global_em().rename(columns={"标题": "t", "发布时间": "tm"})
        hits = []
        for _, x in df.iterrows():
            if any(k in str(x["t"]) for k in _NEWS_KW):
                hits.append(f"- [{str(x['tm'])[:16]}] {str(x['t'])[:60]}")
            if len(hits) >= limit:
                break
        return hits or ["- 无命中关键词的快讯，需核验"]
    except Exception as exc:  # noqa: BLE001
        return [f"- 快讯获取失败：{exc}"]


def generate(save: bool = True) -> str:
    """生成盘前报告 Markdown，返回内容（并默认存盘）。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [f"# A股盘前报告 {now}", ""]

    lines.append("## 一、隔夜美股（指数 + 科技龙头 + 费城半导体）")
    lines += _us_indices()
    lines.append("")
    lines.append("**美股科技龙头（直接映射A股算力/半导体情绪）：**")
    lines += _us_leaders()
    lines.append("")

    lines.append("## 二、外国/海外·地缘新闻雷达")
    lines += _foreign_news()
    lines.append("")

    lines.append("## 三、隔夜/盘前财经快讯（外围/科技/政策/减持）")
    lines += _news()
    lines.append("")

    lines.append("## 四、A股分层观察池（技术清单 + 信号）")
    try:
        res = daily_watch.scan_watchlist()
        m = res["meta"]
        lines.append(f"扫描 {m['scanned']}/{m['total']}"
                     + (f"｜失败 {len(m['fails'])}：{', '.join(m['fails'])}" if m["fails"] else ""))
        if res["alerts"]:
            lines.append("\n**🚨 信号提醒：**")
            for r in res["alerts"]:
                lines.append(f"- {r['signal']} {r['code']} {r['name']}｜现价{r['close']}"
                             f"｜量比{r['volr']}｜入场{r['entry']} 止损{r['stop']} 目标{r['target']} RR{r['rr']}")
        lines.append("")
        for cat in daily_watch.CATEGORY_ORDER:
            items = res["by_category"].get(cat, [])
            if not items:
                continue
            lines.append(f"### {cat}（{len(items)}）")
            for r in items:
                cap = (f"{r['cap']}亿" + ("⚠超规" if not r["cap_ok"] else "")) if r["cap"] else "—"
                lines.append(f"- {r['code']} {r['name']}｜收{r['close']}｜RSI{r['rsi']}｜{r['macd']}｜"
                             f"MA5 {r['ma5']}/MA10 {r['ma10']}｜量比{r['volr']}｜近20 {r['chg20']}%｜"
                             f"距52低{r['dist52']}%｜市值{cap}｜{r['signal']}｜入场{r['entry']} 止损{r['stop']} 目标{r['target']} RR{r['rr']}")
            lines.append("")
    except Exception as exc:  # noqa: BLE001
        lines.append(f"A股扫描失败：{exc}")

    lines.append("> 规则：量比>1.3才算放量、站MA5/MA10、破MA5止损、市值20-500亿（超出降级）。")
    lines.append("> 资金面（主力/北向）未取到、降权；美债/美元未取到处需核验（标注「需核验」处同理）。")
    lines.append("> 本报告由自动任务生成，仅供研究，不构成投资建议；所有买点配破 MA5 硬止损。")

    report = "\n".join(lines)
    if save:
        os.makedirs(_REPORTS, exist_ok=True)
        path = os.path.join(_REPORTS, f"盘前报告_{datetime.now().strftime('%Y%m%d')}.md")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(report)
            print(f"[morning_report] 已保存：{path}")
        except Exception as exc:  # noqa: BLE001
            print(f"[morning_report] 保存失败：{exc}")
    return report


if __name__ == "__main__":
    print(generate())
