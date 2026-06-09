# -*- coding: utf-8 -*-
"""
认证模块：Cookie 加载/保存/验证，Playwright 登录
"""

import json
from typing import Any, Dict, List, Optional

import requests

from src.config import COOKIE_FILE, USER_AGENT


class AuthManager:
    """管理 Bilibili 登录态（Cookie 持久化 + Playwright 登录）"""

    def __init__(self) -> None:
        self._cookies: Optional[List[Dict[str, Any]]] = None

    # ========================================================================
    # Cookie 文件读写
    # ========================================================================

    def load_cookies(self) -> Optional[List[Dict[str, Any]]]:
        """从文件加载 cookie"""
        if self._cookies is not None:
            return self._cookies
        if COOKIE_FILE.exists():
            try:
                with open(COOKIE_FILE, "r") as f:
                    self._cookies = json.load(f)
                    return self._cookies
            except Exception:
                pass
        return None

    def save_cookies(self, cookies: List[Dict[str, Any]]) -> None:
        """保存 cookie 到文件并更新内存缓存"""
        self._cookies = cookies
        with open(COOKIE_FILE, "w") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)

    # ========================================================================
    # Cookie 注入 & 验证
    # ========================================================================

    def apply_to_session(self, session: requests.Session) -> None:
        """将已保存的 cookie 逐条注入 requests session 的 cookie jar"""
        saved = self.load_cookies()
        if saved:
            for c in saved:
                if c.get("name") and c.get("value"):
                    session.cookies.set(
                        name=c["name"],
                        value=c["value"],
                        domain=c.get("domain", ""),
                        path=c.get("path", "/"),
                    )

    def validate(self, session: requests.Session) -> bool:
        """用 nav API 快速验证 cookie 是否有效（不依赖 Playwright）"""
        try:
            resp = session.get(
                "https://api.bilibili.com/x/web-interface/nav",
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("data", {}).get("isLogin"):
                print(f"  ✓ 已登录: {data['data']['uname']}")
                return True
        except Exception:
            pass
        return False

    # ========================================================================
    # Playwright 登录流程
    # ========================================================================

    def ensure_cookies(
        self, session: Optional[requests.Session] = None,
    ) -> List[Dict[str, Any]]:
        """
        确保有可用的 cookie：
        - 有文件且有效 → 直接返回
        - 无效/不存在 → 打开有头浏览器让用户登录 → 保存并返回

        session 不为 None 时，登录后自动将新 cookie 注入 session。
        """
        from playwright.sync_api import sync_playwright

        # 先尝试用已有 cookie（headless 验证）
        saved = self.load_cookies()
        if saved:
            print("  验证已保存的 cookie…")
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context()
                context.add_cookies(saved)
                page = context.new_page()
                try:
                    page.goto(
                        "https://space.bilibili.com/27492426/upload/video",
                        timeout=30000,
                        wait_until="networkidle",
                    )
                    page.wait_for_selector("a[href*='BV']", timeout=10000)
                    links = page.query_selector_all("a[href*='BV']")
                    if len(links) > 0:
                        print(f"  ✓ Cookie 有效（检测到 {len(links)} 个视频链接）")
                        browser.close()
                        return saved
                except Exception:
                    pass
                browser.close()

        # Cookie 无效或不存在 → 打开有头浏览器让用户登录
        print("\n  🔐 需要登录 Bilibili")
        print("  即将打开浏览器，请在浏览器中完成登录…")
        print("  登录成功后回到这里按 Enter 继续\n")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent=USER_AGENT,
            )
            page = context.new_page()
            page.goto("https://www.bilibili.com", timeout=30000)

            input("  登录完成后按 Enter 继续…")

            cookies = context.cookies()
            self.save_cookies(cookies)
            if session is not None:
                self.apply_to_session(session)
            print(f"  ✓ 已保存 {len(cookies)} 条 cookie 到 {COOKIE_FILE}")
            browser.close()
            return cookies
