"""query_weather — Amap weather API."""

from __future__ import annotations

import os
from typing import Optional

import requests


def query_weather(city: str, date: Optional[str] = None) -> str:
    """查询目的地天气。

    Args:
        city: 城市名称，如"北京"、"大理"。
        date: 日期描述，如"7月"、"2025-01-15"。

    Returns:
        天气信息文本。
    """
    api_key = os.environ.get("AMAP_KEY")
    if not api_key:
        return "天气查询不可用：未配置 AMAP_KEY"

    try:
        url = "https://restapi.amap.com/v3/weather/weatherInfo"
        resp = requests.get(url, params={
            "key": api_key,
            "city": city,
            "extensions": "all",  # 预报
            "output": "JSON",
        }, timeout=10)
        data = resp.json()

        if data.get("status") != "1":
            return f"天气查询失败：{data.get('info', '未知错误')}"

        forecasts = data.get("forecasts", [])
        if not forecasts:
            return f"该时段暂无天气预报数据，按历史气候参考推荐"

        casts = forecasts[0].get("casts", [])
        if not casts:
            return f"该时段暂无天气预报数据，按历史气候参考推荐"

        lines = [f"{city}天气预报："]
        for cast in casts[:5]:  # 最多5天
            lines.append(
                f"  {cast.get('date', '')}: 白天{cast.get('daytemp', '')}°C / "
                f"夜间{cast.get('nighttemp', '')}°C, "
                f"{cast.get('dayweather', '')}, "
                f"{cast.get('daywind', '')}风{cast.get('daypower', '')}级"
            )
        return "\n".join(lines)

    except requests.exceptions.Timeout:
        return "天气服务暂时不可用，推荐中不含天气信息"
    except requests.exceptions.RequestException as e:
        return f"天气查询失败（{e}），请按无天气数据推荐"
