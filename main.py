#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bilibili 视频/音频下载器
支持：单个下载 | 仅下载音频 | 批量下载 | UP主空间爬取（Playwright）
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any

import requests


# ============================================================================
# 常量
# ============================================================================

QUALITY_MAP: Dict[str, int] = {
    "360P": 16,
    "480P": 32,
    "720P": 64,
    "1080P": 80,
    "1080P+": 112,
    "4K": 120,
}
# 反向映射：qn 值 → 名称
QN_NAMES: Dict[int, str] = {v: k for k, v in QUALITY_MAP.items()}

DEFAULT_OUTPUT_DIR = "downloads"
COOKIE_FILE = Path(__file__).parent / "cookies.json"
UPLOADERS_FILE = Path(__file__).parent / "uploaders.json"

# 下载子目录
DIR_SINGLE = "downloads/single"
DIR_BATCH = "downloads/batch"
DIR_UPLOADER = "downloads/uploader"


# ============================================================================
# 下载器类
# ============================================================================

class BilibiliDownloader:
    """Bilibili 视频/音频下载器"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.bilibili.com",
        })
        self._has_ffmpeg: Optional[bool] = None
        self._playwright = None

        # 启动时尝试加载 cookie，有则直接用于所有下载请求
        self._apply_saved_cookies()

    def _apply_saved_cookies(self) -> None:
        """将 cookies.json 中的 cookie 同步到 requests session"""
        saved = self._load_cookies()
        if saved:
            cookie_str = "; ".join(
                f"{c['name']}={c['value']}"
                for c in saved
                if c.get("name") and c.get("value")
            )
            if cookie_str:
                self.session.headers["Cookie"] = cookie_str

    def _check_cookies_valid(self) -> bool:
        """用 nav API 快速验证 cookie 是否有效（不依赖 Playwright）"""
        data = self._request("GET", "https://api.bilibili.com/x/web-interface/nav")
        if data and data.get("data", {}).get("isLogin"):
            print(f"  ✓ 已登录: {data['data']['uname']}")
            return True
        return False

    # ========================================================================
    # 内部工具
    # ========================================================================

    def _request(
        self, method: str, url: str, retries: int = 3, **kwargs
    ) -> Optional[Dict[str, Any]]:
        """带重试的 HTTP 请求"""
        kwargs.setdefault("timeout", 30)
        last_error: Optional[Exception] = None

        for attempt in range(retries):
            try:
                resp = self.session.request(method, url, **kwargs)
                resp.raise_for_status()
                data = resp.json()
                code = data.get("code", -1)
                if code != 0:
                    print(f"  ⚠ API 错误: {data.get('message', '未知')} (code={code})")
                    return None
                return data
            except requests.exceptions.RequestException as e:
                last_error = e
                if attempt < retries - 1:
                    wait = (attempt + 1) * 2
                    print(f"  ⚠ 请求失败 ({e})，{wait}秒后重试…")
                    time.sleep(wait)

        print(f"  ✗ 请求失败（已重试 {retries} 次）: {last_error}")
        return None

    def _check_ffmpeg(self) -> bool:
        """检查 ffmpeg 是否可用（带缓存）"""
        if self._has_ffmpeg is None:
            self._has_ffmpeg = shutil.which("ffmpeg") is not None
        return self._has_ffmpeg

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        """清理文件名中的非法字符"""
        return re.sub(r'[<>:"/\\|?*]', "_", name).strip()

    def _progress_bar(
        self, downloaded: int, total: int, start_time: float
    ) -> None:
        """绘制进度条"""
        percent = int((downloaded / total) * 100) if total > 0 else 0
        elapsed = time.time() - start_time
        speed = (downloaded / elapsed / 1024 / 1024) if elapsed > 0 else 0
        downloaded_mb = downloaded / 1024 / 1024
        total_mb = total / 1024 / 1024
        bar_filled = percent // 5
        bar = "█" * bar_filled + "░" * (20 - bar_filled)
        print(
            f"\r  [{bar}] {percent:3d}%  "
            f"{downloaded_mb:.1f}/{total_mb:.1f}MB  "
            f"{speed:.1f}MB/s",
            end="",
        )

    # ========================================================================
    # 信息提取（requests 部分 —— 单视频/批量下载用）
    # ========================================================================

    def extract_bv(self, input_str: str) -> Optional[str]:
        """从输入中提取 BV 号（支持 BV号 / 完整URL / 短链接）"""
        input_str = input_str.strip()

        if re.match(r"^BV[a-zA-Z0-9]+$", input_str):
            return input_str

        bv_match = re.search(r"BV[a-zA-Z0-9]+", input_str)
        if bv_match:
            return bv_match.group(0)

        if "b23.tv" in input_str:
            try:
                resp = self.session.head(input_str, allow_redirects=True, timeout=15)
                bv_match = re.search(r"BV[a-zA-Z0-9]+", resp.url)
                if bv_match:
                    return bv_match.group(0)
            except Exception as e:
                print(f"  ✗ 展开短链接失败: {e}")

        return None

    def get_video_info(self, bvid: str) -> Optional[Dict[str, Any]]:
        """获取视频基本信息"""
        data = self._request(
            "GET", f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
        )
        if not data:
            return None

        vd = data["data"]
        return {
            "title": vd["title"],
            "bvid": vd["bvid"],
            "cid": vd["cid"],
            "mid": vd["owner"]["mid"],
            "owner": vd["owner"]["name"],
            "pic": vd["pic"],
            "desc": vd["desc"],
            "duration": vd["duration"],
        }

    def get_play_url_data(self, bvid: str, cid: int, quality: int = 80,
                          fnval: int = 4048) -> Optional[Dict[str, Any]]:
        """获取播放地址。fnval=4048=DASH+durl，fnval=1=仅传统流"""
        from urllib.parse import urlencode
        params = urlencode({
            "bvid": bvid,
            "cid": cid,
            "qn": quality,
            "fnval": fnval,
            "fourk": 1,
        })
        data = self._request(
            "GET", f"https://api.bilibili.com/x/player/playurl?{params}"
        )
        return data.get("data") if data else None

    def get_available_qualities(self, bvid: str, cid: int) -> List[Tuple[str, int]]:
        """
        获取视频实际可用的清晰度列表。
        先请求最高画质，从响应的 accept_quality 中提取。
        """
        play_data = self.get_play_url_data(bvid, cid, quality=120)
        if not play_data:
            return []
        accept = play_data.get("accept_quality", [])
        if not accept:
            accept = [play_data.get("quality", 0)]
        result = []
        for qn in sorted(accept, reverse=True):
            name = QN_NAMES.get(qn)
            if name:
                result.append((name, qn))
        return result

    # ========================================================================
    # 下载核心
    # ========================================================================

    def _download_file(self, url: str, filepath: Path) -> bool:
        """下载单个文件，带进度条"""
        filepath.parent.mkdir(parents=True, exist_ok=True)

        try:
            resp = self.session.get(
                url,
                stream=True,
                timeout=120,
                headers={"Referer": "https://www.bilibili.com"},
            )
            resp.raise_for_status()

            total_size = int(resp.headers.get("content-length", 0))

            with open(filepath, "wb") as f:
                downloaded = 0
                last_percent = -1
                start_time = time.time()

                for chunk in resp.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

                        if total_size > 0:
                            percent = int((downloaded / total_size) * 100)
                            if percent > last_percent:
                                last_percent = percent
                                self._progress_bar(downloaded, total_size, start_time)

                if total_size > 0:
                    print()

            return True
        except Exception as e:
            print(f"\n  ✗ 下载失败: {e}")
            if filepath.exists():
                filepath.unlink()
            return False

    def _merge_video_audio(
        self, video_path: Path, audio_path: Path, output_path: Path
    ) -> bool:
        """使用 ffmpeg 合并视频和音频流"""
        if not self._check_ffmpeg():
            print("  ✗ 需要 ffmpeg 来合并音视频，请安装 ffmpeg 后重试")
            return False

        try:
            subprocess.run(
                ["ffmpeg", "-y",
                 "-i", str(video_path),
                 "-i", str(audio_path),
                 "-c", "copy",
                 str(output_path)],
                check=True,
                capture_output=True,
            )
            video_path.unlink(missing_ok=True)
            audio_path.unlink(missing_ok=True)
            return True
        except subprocess.CalledProcessError as e:
            print(f"  ✗ ffmpeg 合并失败: {e}")
            return False

    # ========================================================================
    # 单视频 / 批量下载
    # ========================================================================

    def download(
        self,
        input_str: str,
        output_dir: str = DIR_SINGLE,
        audio_only: bool = False,
        quality: int = 80,
        show_detail: bool = True,
    ) -> bool:
        """下载单个视频或音频"""
        bvid = self.extract_bv(input_str)
        if not bvid:
            print(f"  ✗ 无法识别 BV 号: {input_str}")
            return False

        if show_detail:
            print(f"  📺 BV号: {bvid}")

        video_info = self.get_video_info(bvid)
        if not video_info:
            return False

        if show_detail:
            print(f"  标题: {video_info['title']}")
            print(f"  上传者: {video_info['owner']}")

        play_data = self.get_play_url_data(bvid, video_info["cid"], quality)
        if not play_data:
            return False

        safe_title = self._sanitize_filename(video_info["title"])
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # --- 仅音频 ---
        if audio_only:
            dash = play_data.get("dash")
            if dash and dash.get("audio"):
                audios = sorted(dash["audio"], key=lambda x: x["bandwidth"], reverse=True)
                if show_detail:
                    print(f"  音频编码: {audios[0].get('codecs', 'unknown')}")
                audio_file = output_path / f"{safe_title}.m4a"
                print(f"  下载音频: {safe_title}.m4a")
                return self._download_file(audios[0]["base_url"], audio_file)
            else:
                print("  ✗ 该视频无可用的独立音频流")
                return False

        # --- 完整视频 ---
        dash = play_data.get("dash")
        durl = play_data.get("durl")
        actual_quality = play_data.get("quality", 0)

        # 质量降级提示
        if actual_quality < quality and show_detail:
            req_name = QN_NAMES.get(quality, str(quality))
            got_name = QN_NAMES.get(actual_quality, str(actual_quality))
            print(f"  ⚠ {req_name} 不可用，实际画质: {got_name}")

        # 比较 DASH 和 durl 各自的最佳质量，选更优的
        dash_best_q = max((v["id"] for v in dash["video"]), default=0) if dash and dash.get("video") else 0
        durl_q = actual_quality

        # fnval=4048 有时不返回 durl，但传统流画质可能更好 → 补一次 fnval=1 请求
        if durl_q > dash_best_q and not durl:
            if show_detail:
                print("  正在查询传统流…")
            durl_data = self.get_play_url_data(bvid, video_info["cid"],
                                               quality, fnval=1)
            if durl_data:
                durl = durl_data.get("durl")

        prefer_dash = (
            dash and dash.get("video") and dash.get("audio")
            and self._check_ffmpeg()
            and dash_best_q >= durl_q
        )

        if prefer_dash:
            videos = sorted(dash["video"], key=lambda x: (x["id"], x["bandwidth"]), reverse=True)
            audios = sorted(dash["audio"], key=lambda x: x["bandwidth"], reverse=True)

            if show_detail:
                dash_name = QN_NAMES.get(videos[0]["id"], str(videos[0]["id"]))
                print(f"  画质: {dash_name}  |  编码: {videos[0].get('codecs', 'unknown')}")

            tmp_video = output_path / f".tmp_{safe_title}_video.m4s"
            tmp_audio = output_path / f".tmp_{safe_title}_audio.m4s"

            print("  下载视频流…")
            if not self._download_file(videos[0]["base_url"], tmp_video):
                tmp_audio.unlink(missing_ok=True)
                return False

            print("  下载音频流…")
            if not self._download_file(audios[0]["base_url"], tmp_audio):
                tmp_video.unlink(missing_ok=True)
                return False

            print("  合并音视频…")
            return self._merge_video_audio(tmp_video, tmp_audio, output_path / f"{safe_title}.mp4")

        elif durl:
            if len(durl) > 1:
                print(f"  ⚠ 该视频有 {len(durl)} 个分段，将只下载第一段")
            durl_name = QN_NAMES.get(durl_q, str(durl_q))
            print(f"  画质: {durl_name}  |  下载: {safe_title}.mp4")
            return self._download_file(durl[0]["url"], output_path / f"{safe_title}.mp4")

        elif dash and dash.get("video") and dash.get("audio") and self._check_ffmpeg():
            # durl 不可用，兜底走 DASH
            if show_detail:
                print("  ⚠ 传统流不可用，使用 DASH 流")
            videos = sorted(dash["video"], key=lambda x: (x["id"], x["bandwidth"]), reverse=True)
            audios = sorted(dash["audio"], key=lambda x: x["bandwidth"], reverse=True)

            if show_detail:
                dash_name = QN_NAMES.get(videos[0]["id"], str(videos[0]["id"]))
                print(f"  画质: {dash_name}  |  编码: {videos[0].get('codecs', 'unknown')}")

            tmp_video = output_path / f".tmp_{safe_title}_video.m4s"
            tmp_audio = output_path / f".tmp_{safe_title}_audio.m4s"

            print("  下载视频流…")
            if not self._download_file(videos[0]["base_url"], tmp_video):
                tmp_audio.unlink(missing_ok=True)
                return False

            print("  下载音频流…")
            if not self._download_file(audios[0]["base_url"], tmp_audio):
                tmp_video.unlink(missing_ok=True)
                return False

            print("  合并音视频…")
            return self._merge_video_audio(tmp_video, tmp_audio, output_path / f"{safe_title}.mp4")

        else:
            print("  ✗ 无法获取视频下载地址")
            return False

    def download_batch(
        self,
        input_file: str = "input.txt",
        output_base: str = DIR_BATCH,
        audio_only: bool = False,
        quality: int = 80,
    ) -> Tuple[int, int, str]:
        """批量下载（从文件逐行读取 URL/BV号）"""
        input_path = Path(input_file)
        if not input_path.exists():
            print(f"✗ 输入文件不存在: {input_file}")
            return 0, 1, ""

        urls: List[str] = []
        with open(input_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    urls.append(line)

        if not urls:
            print("输入文件中没有找到有效的 URL")
            return 0, 0, ""

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        output_dir = Path(output_base) / timestamp
        output_dir.mkdir(parents=True, exist_ok=True)

        mode_label = "音频" if audio_only else "视频"
        print(f"\n{'=' * 55}")
        print(f"  📦 批量下载模式")
        print(f"  任务数: {len(urls)}  |  模式: {mode_label}  |  保存到: {output_dir}")
        print(f"{'=' * 55}\n")

        success = 0
        fail = 0
        for i, url in enumerate(urls, 1):
            print(f"[{i}/{len(urls)}]", end="")
            if self.download(url, str(output_dir), audio_only, quality, show_detail=True):
                success += 1
            else:
                fail += 1
            print()

        print(f"{'=' * 55}")
        print(f"  📊 批量下载完成: 成功 {success} / 失败 {fail}")
        print(f"{'=' * 55}")
        return success, fail, str(output_dir)

    # ========================================================================
    # Cookie 管理（Playwright 登录用）
    # ========================================================================

    def _load_cookies(self) -> Optional[List[Dict[str, Any]]]:
        """从文件加载 cookie"""
        if COOKIE_FILE.exists():
            try:
                with open(COOKIE_FILE, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return None

    def _save_cookies(self, cookies: List[Dict[str, Any]]) -> None:
        """保存 cookie 到文件"""
        with open(COOKIE_FILE, "w") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)

    def _ensure_cookies(self) -> List[Dict[str, Any]]:
        """
        确保有可用的 cookie：
        - 有文件且有效 → 直接返回
        - 无效/不存在 → 打开有头浏览器让用户登录 → 保存并返回
        """
        from playwright.sync_api import sync_playwright

        # 先尝试用已有 cookie（headless 验证）
        saved = self._load_cookies()
        if saved:
            print("  验证已保存的 cookie…")
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context()
                context.add_cookies(saved)
                page = context.new_page()
                try:
                    page.goto("https://space.bilibili.com/27492426/upload/video",
                              timeout=30000, wait_until="networkidle")
                    page.wait_for_selector("a[href*='BV']", timeout=10000)
                    # 能拿到 BV 链接说明 cookie 有效
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
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            page = context.new_page()
            page.goto("https://www.bilibili.com", timeout=30000)

            input("  登录完成后按 Enter 继续…")

            cookies = context.cookies()
            self._save_cookies(cookies)
            self._apply_saved_cookies()
            print(f"  ✓ 已保存 {len(cookies)} 条 cookie 到 {COOKIE_FILE}")
            browser.close()
            return cookies

    @staticmethod
    def _get_mid_from_url(url: str) -> Optional[int]:
        """从 UP 主空间 URL 提取 mid"""
        match = re.search(r"space\.bilibili\.com/(\d+)", url)
        return int(match.group(1)) if match else None

    def _get_mid_from_video(self, bvid: str) -> Optional[int]:
        """通过视频 BV 号获取 UP 主 mid"""
        info = self.get_video_info(bvid)
        return info["mid"] if info else None

    # ========================================================================
    # UP 主收藏管理
    # ========================================================================

    def _load_uploaders(self) -> List[Dict[str, Any]]:
        """加载已收藏的 UP 主列表"""
        if UPLOADERS_FILE.exists():
            try:
                with open(UPLOADERS_FILE, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def _save_uploaders(self, uploaders: List[Dict[str, Any]]) -> None:
        """保存 UP 主列表"""
        with open(UPLOADERS_FILE, "w") as f:
            json.dump(uploaders, f, ensure_ascii=False, indent=2)

    def _save_uploader(self, mid: int, name: str, url: str) -> None:
        """添加/更新一个 UP 主记录"""
        uploaders = self._load_uploaders()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 查找是否已存在
        for u in uploaders:
            if u["mid"] == mid:
                u["name"] = name
                u["last_access"] = now
                self._save_uploaders(uploaders)
                return

        # 新增
        uploaders.append({
            "mid": mid,
            "name": name,
            "url": url,
            "last_access": now,
        })
        self._save_uploaders(uploaders)

    def _pick_uploader(self) -> Optional[str]:
        """
        展示已收藏的 UP 主，让用户选择或输入新的。
        返回 UP 主空间 URL。
        """
        uploaders = self._load_uploaders()
        if uploaders:
            print("\n已收藏的 UP 主:")
            for i, u in enumerate(uploaders, 1):
                print(f"  {i}. {u['name']}  (mid={u['mid']})  [{u['last_access']}]")
            print(f"  n. 输入新的 UP 主链接")
            print(f"  0. 返回")

            while True:
                choice = input("\n请选择: ").strip().lower()
                if choice == "0":
                    return None
                if choice == "n":
                    return input("UP主空间URL 或 该UP主的任意视频URL: ").strip()
                try:
                    idx = int(choice) - 1
                    if 0 <= idx < len(uploaders):
                        return uploaders[idx]["url"]
                except ValueError:
                    pass
                print("输入无效，请重新选择")
        else:
            return input("UP主空间URL 或 该UP主的任意视频URL: ").strip()

    # ========================================================================
    # UP 主空间爬取（Playwright 网页解析）
    # ========================================================================

    def _scrape_uploader_videos(
        self, mid: int, count: int
    ) -> List[Dict[str, str]]:
        """
        用 Playwright 渲染空间页面，从 DOM 中提取视频 BV 号和标题。
        通过滚动页面加载更多视频。
        """
        from playwright.sync_api import sync_playwright

        print(f"  正在从网页抓取 UP 主 (mid={mid}) 的视频列表…")

        cookies = self._ensure_cookies()

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
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
            seen_bvs: set = set()
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
                        # 可能是缩略图链接，尝试获取真正的标题
                        # 取同 BV 下文字最长的那个
                        for other in links:
                            other_href = other.get_attribute("href") or ""
                            if bv in other_href:
                                other_title = other.inner_text().strip()
                                if len(other_title) > len(title):
                                    title = other_title

                    if len(title) < 3:
                        title = bv  # fallback

                    videos.append({"bvid": bv, "title": title, "author": ""})
                    new_found += 1

                    if len(videos) >= count:
                        break

                if new_found == 0:
                    no_new_count += 1
                else:
                    no_new_count = 0

                # 还没够 → 滚动加载更多
                if len(videos) < count:
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    page.wait_for_timeout(2000)

            browser.close()

        print(f"  获取到 {len(videos)} 个视频")
        return videos[:count]

    def download_uploader(
        self,
        uploader_input: str,
        count: int = 10,
        output_base: str = DIR_UPLOADER,
        audio_only: bool = False,
        quality: int = 80,
    ) -> Tuple[int, int, str]:
        """爬取并下载 UP 主空间中的视频/音频"""
        # ---- 获取 mid ----
        mid = self._get_mid_from_url(uploader_input)
        if not mid:
            bvid = self.extract_bv(uploader_input)
            if bvid:
                mid = self._get_mid_from_video(bvid)

        if not mid:
            print(f"  ✗ 无法获取 UP 主信息: {uploader_input}")
            return 0, 1, ""

        # ---- 网页抓取视频列表 ----
        videos = self._scrape_uploader_videos(mid, count)
        if not videos:
            print("  ✗ 未找到任何视频")
            return 0, 0, ""

        # ---- 保存 UP 主记录 ----
        # 用第一个视频的 API 信息获取 UP 主名字（失败则用 mid）
        author_name = f"uid_{mid}"
        first_info = self.get_video_info(videos[0]["bvid"])
        if first_info:
            author_name = self._sanitize_filename(first_info["owner"])

        space_url = f"https://space.bilibili.com/{mid}"
        self._save_uploader(mid, author_name, space_url)

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        output_dir = Path(output_base) / author_name / timestamp
        output_dir.mkdir(parents=True, exist_ok=True)

        mode_label = "音频" if audio_only else "视频"
        print(f"\n{'=' * 55}")
        print(f"  📦 UP主: {author_name}")
        print(f"  任务数: {len(videos)}  |  模式: {mode_label}  |  保存到: {output_dir}")
        print(f"{'=' * 55}\n")

        success = 0
        fail = 0
        for i, v in enumerate(videos, 1):
            print(f"[{i}/{len(videos)}]", end="")
            if self.download(v["bvid"], str(output_dir), audio_only, quality, show_detail=True):
                success += 1
            else:
                fail += 1
            print()

        print(f"{'=' * 55}")
        print(f"  📊 UP主下载完成: 成功 {success} / 失败 {fail}")
        print(f"{'=' * 55}")
        return success, fail, str(output_dir)


# ============================================================================
# 交互界面
# ============================================================================

def _select_quality(available: Optional[List[Tuple[str, int]]] = None) -> int:
    """交互式选择清晰度。传入 available 则只显示可用画质。"""
    if available:
        items = available
        print(f"\n该视频可用清晰度 ({len(items)} 种):")
    else:
        items = list(QUALITY_MAP.items())
        print("\n可选清晰度:")

    for i, (label, _) in enumerate(items, 1):
        print(f"  {i}. {label}")
    print(f"  {len(items) + 1}. 不选择（返回）")

    default_idx = min(3, len(items) - 1)  # 默认选靠高画质
    default_label = items[default_idx][0] if len(items) > default_idx else items[-1][0]
    default_qn = items[default_idx][1] if len(items) > default_idx else items[-1][1]

    while True:
        choice = input(f"请选择 (1-{len(items)}, 默认 {default_idx + 1}={default_label}): ").strip()
        if not choice:
            return default_qn
        if choice == str(len(items) + 1):
            return -1
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(items):
                return items[idx][1]
        except ValueError:
            pass
        print("输入无效，请重新选择")


def _interactive(downloader: BilibiliDownloader) -> None:
    """交互模式主菜单"""
    while True:
        print(f"\n{'=' * 55}")
        print("  🎬 Bilibili 视频/音频下载器")
        print(f"{'=' * 55}")
        print("  1. 下载单个视频")
        print("  2. 下载单个音频")
        print("  3. 批量下载（从 input.txt）")
        print("  4. UP主空间爬取")
        print("  0. 退出")

        choice = input("\n请选择: ").strip()

        if choice == "0":
            print("再见！")
            break

        elif choice == "1":
            url = input("视频URL或BV号: ").strip()
            if not url:
                continue
            # 预查可用画质
            available = None
            bvid = downloader.extract_bv(url)
            if bvid:
                info = downloader.get_video_info(bvid)
                if info:
                    print("  正在查询可用画质…")
                    available = downloader.get_available_qualities(bvid, info["cid"])
            quality = _select_quality(available if available else None)
            if quality < 0:
                continue
            output = input(f"保存目录 (默认 ./{DIR_SINGLE}): ").strip()
            downloader.download(url, output or DIR_SINGLE, audio_only=False, quality=quality)

        elif choice == "2":
            url = input("视频URL或BV号: ").strip()
            if not url:
                continue
            output = input(f"保存目录 (默认 ./{DIR_SINGLE}): ").strip()
            downloader.download(url, output or DIR_SINGLE, audio_only=True)

        elif choice == "3":
            input_file = input(f"URL列表文件 (默认 ./input.txt): ").strip() or "input.txt"
            mode = input("下载模式 (1=视频, 2=仅音频, 默认1): ").strip()
            audio_only = mode == "2"
            quality = 80
            if not audio_only:
                quality = _select_quality()
                if quality < 0:
                    continue
            downloader.download_batch(input_file, audio_only=audio_only, quality=quality)

        elif choice == "4":
            url = downloader._pick_uploader()
            if not url:
                continue

            # 验证链接有效性
            mid = downloader._get_mid_from_url(url)
            if not mid:
                bvid = downloader.extract_bv(url)
                if bvid:
                    print("  正在通过视频链接获取 UP 主信息…")
                    mid = downloader._get_mid_from_video(bvid)
            if not mid:
                print("  ✗ 无法识别该链接，请确认是 UP 主空间链接或视频链接后重试")
                continue
            print(f"  ✓ UP主 mid={mid}")

            try:
                n = input("下载数量 (默认10): ").strip()
                count = int(n) if n else 10
            except ValueError:
                count = 10
            mode = input("下载模式 (1=视频, 2=仅音频, 默认1): ").strip()
            audio_only = mode == "2"
            quality = 80
            if not audio_only:
                quality = _select_quality()
                if quality < 0:
                    continue
            downloader.download_uploader(url, count, audio_only=audio_only, quality=quality)

        else:
            print("无效选项，请重新选择")


# ============================================================================
# 程序入口
# ============================================================================

def main() -> None:
    """主入口"""
    downloader = BilibiliDownloader()

    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()

        if cmd == "batch":
            input_file = sys.argv[2] if len(sys.argv) > 2 else "input.txt"
            audio_only = len(sys.argv) > 3 and sys.argv[3] == "audio"
            quality = int(sys.argv[4]) if len(sys.argv) > 4 else 80
            downloader.download_batch(input_file, audio_only=audio_only, quality=quality)

        elif cmd == "uploader":
            if len(sys.argv) < 3:
                print("用法: python main.py uploader <UP主空间URL/视频URL> [数量] [video|audio] [清晰度qn]")
                sys.exit(1)
            url = sys.argv[2]
            count = int(sys.argv[3]) if len(sys.argv) > 3 else 10
            audio_only = len(sys.argv) > 4 and sys.argv[4] == "audio"
            quality = int(sys.argv[5]) if len(sys.argv) > 5 else 80
            downloader.download_uploader(url, count, audio_only=audio_only, quality=quality)

        else:
            url = sys.argv[1]
            output = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_OUTPUT_DIR
            audio_only = len(sys.argv) > 3 and sys.argv[3] == "audio"
            quality = int(sys.argv[4]) if len(sys.argv) > 4 else 80
            downloader.download(url, output, audio_only=audio_only, quality=quality)

    else:
        # 启动时检测登录状态
        if COOKIE_FILE.exists():
            print("  检测到登录信息，验证中…")
            if not downloader._check_cookies_valid():
                print("  ⚠ Cookie 已过期，需要重新登录")
                downloader._ensure_cookies()
        else:
            print("  未检测到登录信息（登录后可解锁 1080P+ 高清画质）")
            choice = input("  是否现在登录？[Y/n]: ").strip().lower()
            if choice in ("", "y", "yes"):
                downloader._ensure_cookies()
            else:
                print("  已跳过，将以游客模式运行（画质受限）\n")

        _interactive(downloader)


if __name__ == "__main__":
    main()
