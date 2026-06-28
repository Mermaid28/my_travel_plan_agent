"""save_itinerary — Save itinerary to local file system."""

from __future__ import annotations

import os
from pathlib import Path

SAVED_DIR = Path(__file__).resolve().parent.parent.parent / "saved"


def save_itinerary(
    content: str,
    filename: str = "",
    writable: bool = False,
    destination: str = "",
    travel_dates: str = "",
) -> str:
    """保存行程到本地文件。

    Args:
        content: 行程内容（Markdown 格式）。
        filename: 文件名（可选，不指定则自动生成）。
        writable: 是否允许写入（由 session 控制）。
        destination: 目的地，用于自动生成文件名。
        travel_dates: 旅行时间，用于自动生成文件名。

    Returns:
        保存结果消息。
    """
    if not writable:
        return "当前为只读模式，请用 --writable 重新启动"

    # Auto-generate filename if not provided
    if not filename:
        parts = [destination or "旅行", travel_dates or ""]
        filename = "".join(parts).strip() + "行程.md"
        if not filename.endswith(".md"):
            filename += ".md"

    try:
        os.makedirs(SAVED_DIR, exist_ok=True)
        filepath = SAVED_DIR / filename
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return f"已保存到 saved/{filename}\n你可随时用 cat saved/{filename} 查看"
    except Exception as e:
        return f"保存失败：{e}"
