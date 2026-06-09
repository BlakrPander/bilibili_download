# -*- coding: utf-8 -*-
"""
UP 主空间爬取：通过 Playwright 渲染空间页面，提取视频 BV 号和标题
"""

import re
from typing import Dict, List, Set

from src.auth import AuthManager
from src.config import USER_AGENT


class SpaceScraper:
    """使用 Playwright 爬取 UP 主空间中的视频列表"""

    def __init__(self, auth: AuthManager) -> None:
        self.auth = auth

    def scrape_videos(self, mid: int, count: int) -> List[Dict[str, str]]:
        """
        用 Playwright 渲染空间页面，从 DOM 中提取视频 BV 号和标题。
        通过滚动页面加载更多视频。
        """
        from playwright.sync_api import sync_playwright

        print(f"  正在从网页抓取 UP 主 (mid={mid}) 的视频列表…")

        cookies = self.auth.ensure_cookies()

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent=USER_AGENT,
            )
            context.add_cookies(cookies)
            page = context.new_page()

            # 访问空间上传页面
            space_url = f"https://space.bilibili.com/{mid}/upload/video"
            page.goto(space_url, timeout=30000, wait_until="networkidle")

            # 等视频卡片出现
            try:
                page.wait_for_selector("a[href*='BV']", timeout=15000)
            except Exception:
                print("  ✗ 页面加载超时，未找到视频链接")
                browser.close()
                return []

            # 滚动加载 + 提取
            seen_bvs: Set[str] = set()
            videos: List[Dict[str, str]] = []
            no_new_count = 0

            while len(videos) < count and no_new_count < 5:
                links = page.query_selector_all("a[href*='BV']")
                new_found = 0

                for link in links:
                    href = link.get_attribute("href") or ""
                    bv_match = re.search(r"BV[a-zA-Z0-9]+", href)
                    if not bv_match:
                        continue
                    bv = bv_match.group(0)
                    if bv in seen_bvs:
                        continue
                    seen_bvs.add(bv)

                    title = link.inner_text().strip()
                    # 标题链接通常文字较长；缩略图链接是短的统计数字
                    if len(title) < 5:
                        for other in links:
                            other_href = other.get_attribute("href") or ""
                            if bv in other_href:
                                other_title = other.inner_text().strip()
                                if len(other_title) > len(title):
                                    title = other_title

                    if len(title) < 3:
                        title = bv  # fallback

                    videos.append({
                        "bvid": bv,
                        "title": title,
                        "author": "",
                    })
                    new_found += 1

                    if len(videos) >= count:
                        break

                if new_found == 0:
                    no_new_count += 1
                else:
                    no_new_count = 0

                # 还没够 → 滚动加载更多
                if len(videos) < count:
                    page.evaluate(
                        "window.scrollTo(0, document.body.scrollHeight)"
                    )
                    page.wait_for_timeout(2000)

            browser.close()

        print(f"  获取到 {len(videos)} 个视频")
        return videos[:count]
