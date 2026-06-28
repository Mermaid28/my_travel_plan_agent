"""query_hotels — Amap POI API for hotel search."""

from __future__ import annotations

import os

import requests


def query_hotels(city: str, check_in: str = "", check_out: str = "") -> str:
    """查询目的地酒店。

    Args:
        city: 城市名称，如"北京"、"大理"。
        check_in: 入住日期，如"2025-07-01"。
        check_out: 离店日期，如"2025-07-03"。

    Returns:
        酒店列表文本。
    """
    api_key = os.environ.get("AMAP_KEY")
    if not api_key:
        return "酒店查询不可用：未配置 AMAP_KEY"

    try:
        url = "https://restapi.amap.com/v3/place/text"
        resp = requests.get(url, params={
            "key": api_key,
            "keywords": "酒店",
            "city": city,
            "offset": 10,
            "page": 1,
            "output": "JSON",
        }, timeout=10)
        data = resp.json()

        if data.get("status") != "1":
            return f"酒店查询失败：{data.get('info', '未知错误')}"

        pois = data.get("pois", [])
        if not pois:
            return f"未找到 {city} 的酒店信息"

        lines = [f"{city}酒店推荐："]
        for poi in pois[:8]:
            name = poi.get("name", "")
            address = poi.get("address", "")
            price = poi.get("biz_ext", {}).get("rating", "")
            if price:
                price_str = f"参考价约{price}元"
            else:
                price_str = "价格待询"
            lines.append(f"  - {name}，{address}，{price_str}")

        if check_in or check_out:
            lines.append(f"\n入住：{check_in or '未指定'}，离店：{check_out or '未指定'}")
            lines.append("注：以上价格为参考，请以实际预订为准。")

        return "\n".join(lines)

    except requests.exceptions.Timeout:
        return "酒店查询超时"
    except requests.exceptions.RequestException as e:
        return f"酒店查询失败（{e}）"
