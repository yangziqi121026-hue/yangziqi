"""东财 F10 / 数据中心通用取数层（P0 地基）。

所有专业版基本面模块的统一底座：直连 datacenter.eastmoney.com 的 reportName 接口
（带浏览器 UA，实测可连；akshare 的同源接口在本环境被远端断开）。

用法：
    rows = report("RPT_F10_FINANCE_MAINFINADATA", "002929", page_size=8)
    # rows 是 list[dict]，按报告期倒序（最新在前）

字段映射（财务相关）见 FIELD_CN。其余模块按需扩充各自的 reportName。
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional

import requests

_H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
_URL = "https://datacenter.eastmoney.com/securities/api/data/v1/get"


def secucode(code: str) -> str:
    """600089 -> 600089.SH；000938/300474 -> .SZ；688/605/60 -> .SH；83/87/43/8/4 -> .BJ。"""
    c = code.strip().upper()
    if c.endswith((".SH", ".SZ", ".BJ")):
        return c
    if c[0] == "6":
        return c + ".SH"
    if c[0] in "03":
        return c + ".SZ"
    return c + ".BJ"  # 北交所 8/4/9 开头


def report(
    report_name: str,
    code: str,
    page_size: int = 8,
    page: int = 1,
    sort_col: str = "REPORT_DATE",
    desc: bool = True,
    extra_filter: str = "",
    columns: str = "ALL",
    retries: int = 3,
) -> List[Dict]:
    """通用 reportName 取数。返回 list[dict]，失败返回 []。

    extra_filter: 追加过滤，如 '(REPORT_TYPE="年报")'，会与 SECUCODE 过滤用 AND 拼接。
    """
    sec = secucode(code)
    flt = f'(SECUCODE="{sec}")'
    if extra_filter:
        flt += extra_filter if extra_filter.startswith("(") else f"({extra_filter})"
    params = {
        "reportName": report_name, "columns": columns, "filter": flt,
        "pageNumber": str(page), "pageSize": str(page_size),
        "sortColumns": sort_col, "sortTypes": "-1" if desc else "1",
        "source": "HSF10", "client": "PC",
    }
    for _ in range(retries):
        try:
            r = requests.get(_URL, params=params, headers=_H, timeout=20)
            j = r.json()
            data = (j.get("result") or {}).get("data")
            if data:
                return data
            # 有些 reportName 无 SECUCODE 列或无数据，返回空但 200
            if j.get("success") and data is not None:
                return data
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.6)
    return []


def first(rows: List[Dict]) -> Optional[Dict]:
    return rows[0] if rows else None


# ---- 财务字段中文映射（供 financial_quarter_tracker 等使用）----
FIELD_CN = {
    "REPORT_DATE_NAME": "报告期",
    "REPORT_DATE": "报告日",
    # 主要指标 (RPT_F10_FINANCE_MAINFINADATA) — 累计值
    "TOTALOPERATEREVE": "营收",
    "TOTALOPERATEREVETZ": "营收同比",
    "PARENTNETPROFIT": "归母净利",
    "PARENTNETPROFITTZ": "归母同比",
    "KCFJCXSYJLR": "扣非净利",
    "KCFJCXSYJLRTZ": "扣非同比",
    "XSMLL": "毛利率",
    "XSMLL_TB": "毛利率同比变动",
    "XSJLL": "净利率",
    "NETCASH_OPERATE_PK": "经营现金流",
    "ROEJQ": "ROE加权",
    "ROEJQTZ": "ROE同比",
    "ZCFZL": "资产负债率",
    "EPSJB": "每股收益",
    # 单季度同比/环比
    "DJD_TOI_YOY": "单季营收同比",
    "DJD_TOI_QOQ": "单季营收环比",
    "DJD_DPNP_YOY": "单季净利同比",
    "DJD_DPNP_QOQ": "单季净利环比",
    "DJD_DEDUCTDPNP_YOY": "单季扣非同比",
    "DJD_DEDUCTDPNP_QOQ": "单季扣非环比",
    # 资产负债表 (RPT_F10_FINANCE_GBALANCE)
    "INVENTORY": "存货",
    "INVENTORY_YOY": "存货同比",
    "ACCOUNTS_RECE": "应收账款",
    "ACCOUNTS_RECE_YOY": "应收同比",
    "CONTRACT_LIAB": "合同负债",
    "CONTRACT_LIAB_YOY": "合同负债同比",
}

# 常用 reportName 常量
RPT_MAIN = "RPT_F10_FINANCE_MAINFINADATA"   # 主要财务指标(季度)
RPT_BALANCE = "RPT_F10_FINANCE_GBALANCE"    # 资产负债表
