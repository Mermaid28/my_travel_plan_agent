"""CLI entry point — REPL loop for the travel recommendation agent."""

from __future__ import annotations

import argparse
import os
import signal
import sys

from dotenv import load_dotenv

from travel_agent.agent import TravelAgent
from travel_agent.session import Session

# Load .env file at startup
load_dotenv()

BANNER = """
╔══════════════════════════════════════╗
║     旅行推荐助手                      ║
║  告诉我你想去哪里，我来帮你规划行程     ║
║  输入 exit 退出                       ║
╚══════════════════════════════════════╝
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="旅行推荐助手")
    parser.add_argument(
        "--writable",
        action="store_true",
        help="启用可写模式，允许保存行程到本地文件",
    )
    return parser.parse_args()


def check_env() -> list[str]:
    """Check required environment variables, return list of missing ones."""
    required = ["LLM_API_KEY", "AMAP_KEY"]
    missing = [v for v in required if not os.environ.get(v)]
    return missing


def main() -> None:
    args = parse_args()

    # Check environment
    missing = check_env()
    if missing:
        print(f"错误：缺少必要的环境变量：{', '.join(missing)}")
        print("请创建 .env 文件或在环境中设置这些变量。")
        sys.exit(1)

    # Create session and agent
    session = Session(writable=args.writable)
    agent = TravelAgent(session)

    print(BANNER)

    if args.writable:
        print("  [可写模式已启用]")
    else:
        print("  [只读模式 — 保存功能不可用]")
    print()

    # REPL loop
    while True:
        try:
            user_input = input("请输入旅行需求 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！祝您旅途愉快！")
            break

        if not user_input:
            continue

        if user_input.lower() in ("exit", "quit"):
            print("再见！祝您旅途愉快！")
            break

        try:
            result = agent.process(user_input)
            # Sanitize output for terminal display
            result = result.encode("utf-8", errors="replace").decode("utf-8")
            print()
            print(result)
            print()
        except Exception as e:
            print(f"\n处理请求时出错：{e}")
            print("请重试或输入 exit 退出。\n")


def handle_sigint(signum, frame):
    """Handle Ctrl+C gracefully."""
    print("\n再见！祝您旅途愉快！")
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, handle_sigint)
    main()
