"""数据库模块：使用 SQLite 保存与查询分析历史。"""

import json
import os
import sqlite3
from datetime import datetime
from typing import List, Optional

# 数据库文件路径：项目根目录下 data/tradingagents.db
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_DIR = os.path.join(_BASE_DIR, "data")
DB_PATH = os.path.join(_DATA_DIR, "tradingagents.db")


def _get_connection() -> sqlite3.Connection:
    """获取数据库连接，确保目录存在。"""
    os.makedirs(_DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """初始化数据库，建表（如不存在）。"""
    conn = _get_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                market TEXT,
                symbol TEXT,
                stock_name TEXT,
                current_price TEXT,
                final_rating TEXT,
                trade_suggestion TEXT,
                report_markdown TEXT,
                result_json TEXT
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def save_analysis(
    market: str,
    symbol: str,
    stock_name: str,
    current_price: str,
    final_rating: str,
    trade_suggestion: str,
    report_markdown: str,
    result: dict,
) -> int:
    """保存一次分析记录，返回记录 id。"""
    init_db()
    conn = _get_connection()
    try:
        cursor = conn.execute(
            """
            INSERT INTO analysis_history
            (created_at, market, symbol, stock_name, current_price,
             final_rating, trade_suggestion, report_markdown, result_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                market,
                symbol,
                stock_name,
                current_price,
                final_rating,
                trade_suggestion,
                report_markdown,
                json.dumps(result, ensure_ascii=False, default=str),
            ),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def list_history(limit: int = 50) -> List[dict]:
    """查询历史记录列表（不含完整报告正文，提升性能）。"""
    init_db()
    conn = _get_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, created_at, market, symbol, stock_name,
                   current_price, final_rating, trade_suggestion
            FROM analysis_history
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_report(record_id: int) -> Optional[dict]:
    """根据 id 查询完整记录（含报告正文）。"""
    init_db()
    conn = _get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM analysis_history WHERE id = ?",
            (record_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()
