#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bilibili 视频/音频下载器 —— 入口
支持：单个下载 | 仅下载音频 | 批量下载 | UP主空间爬取（Playwright）
"""

import sys

import requests

from src.auth import AuthManager
from src.api import BiliAPI
from src.downloader import Downloader
from src.cli import interactive_menu, parse_and_run
from src.config import COOKIE_FILE, USER_AGENT


def main() -> None:
    """主入口：初始化组件 → 检测登录 → 进入交互或命令行模式"""
    # ---- 初始化 ----
    auth = AuthManager()

    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Referer": "https://www.bilibili.com",
    })
    auth.apply_to_session(session)

    api = BiliAPI(session)
    downloader = Downloader(api, auth)

    # ---- 登录检测（仅交互模式） ----
    if len(sys.argv) == 1:
        if COOKIE_FILE.exists():
            print("  检测到登录信息，验证中…")
            if not auth.validate(session):
                print("  ⚠ Cookie 已过期，需要重新登录")
                auth.ensure_cookies(session)
        else:
            print("  未检测到登录信息（登录后可解锁 1080P+ 高清画质）")
            choice = input("  是否现在登录？[Y/n]: ").strip().lower()
            if choice in ("", "y", "yes"):
                auth.ensure_cookies(session)
            else:
                print("  已跳过，将以游客模式运行（画质受限）\n")

    # ---- 路由 ----
    if len(sys.argv) > 1:
        parse_and_run(downloader, sys.argv)
    else:
        interactive_menu(downloader, api)


if __name__ == "__main__":
    main()
