# -*- coding: utf-8 -*-
"""
下载核心：文件下载、音视频合并、单视频/批量/UP主下载
"""

import json
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.api import BiliAPI
from src.auth import AuthManager
from src.config import (
    DIR_BATCH, DIR_SINGLE, DIR_UPLOADER,
    QN_NAMES, UPLOADERS_FILE,
)
from src.scraper import SpaceScraper
from src.utils import check_ffmpeg, progress_bar, sanitize_filename


class Downloader:
    """视频/音频下载器，编排 API 调用、文件下载、混流"""

    def __init__(
        self,
        api: BiliAPI,
        auth: AuthManager,
        scraper: Optional[SpaceScraper] = None,
    ) -> None:
        self.api = api
        self.auth = auth
        self.scraper = scraper or SpaceScraper(auth)

    # ========================================================================
    # 文件下载 & 合并
    # ========================================================================

    def download_file(self, url: str, filepath: Path) -> bool:
        """下载单个文件，带进度条"""
        filepath.parent.mkdir(parents=True, exist_ok=True)

        try:
            resp = self.api.session.get(
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
                                progress_bar(downloaded, total_size, start_time)

                if total_size > 0:
                    print()

            return True
        except Exception as e:
            print(f"\n  ✗ 下载失败: {e}")
            if filepath.exists():
                filepath.unlink()
            return False

    def merge_video_audio(
        self, video_path: Path, audio_path: Path, output_path: Path
    ) -> bool:
        """使用 ffmpeg 合并视频和音频流"""
        if not check_ffmpeg():
            print("  ✗ 需要 ffmpeg 来合并音视频，请安装 ffmpeg 后重试")
            return False

        try:
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-i", str(video_path),
                    "-i", str(audio_path),
                    "-c", "copy",
                    str(output_path),
                ],
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
    # 单视频下载
    # ========================================================================

    def _download_dash(
        self,
        dash: Dict[str, Any],
        output_path: Path,
        safe_title: str,
        show_detail: bool = True,
    ) -> bool:
        """下载 DASH 分离流（视频 + 音频）并合并"""
        videos = sorted(
            dash["video"],
            key=lambda x: (x["id"], x["bandwidth"]),
            reverse=True,
        )
        audios = sorted(
            dash["audio"],
            key=lambda x: x["bandwidth"],
            reverse=True,
        )

        if show_detail:
            dash_name = QN_NAMES.get(
                videos[0]["id"], str(videos[0]["id"])
            )
            print(
                f"  画质: {dash_name}  |  "
                f"编码: {videos[0].get('codecs', 'unknown')}"
            )

        tmp_video = output_path / f".tmp_{safe_title}_video.m4s"
        tmp_audio = output_path / f".tmp_{safe_title}_audio.m4s"

        print("  下载视频流…")
        if not self.download_file(videos[0]["base_url"], tmp_video):
            return False

        print("  下载音频流…")
        if not self.download_file(audios[0]["base_url"], tmp_audio):
            tmp_video.unlink(missing_ok=True)
            return False

        print("  合并音视频…")
        return self.merge_video_audio(
            tmp_video, tmp_audio, output_path / f"{safe_title}.mp4"
        )

    def download(
        self,
        input_str: str,
        output_dir: str = DIR_SINGLE,
        audio_only: bool = False,
        quality: int = 80,
        show_detail: bool = True,
    ) -> bool:
        """下载单个视频或音频"""
        bvid = self.api.extract_bv(input_str)
        if not bvid:
            print(f"  ✗ 无法识别 BV 号: {input_str}")
            return False

        if show_detail:
            print(f"  📺 BV号: {bvid}")

        video_info = self.api.get_video_info(bvid)
        if not video_info:
            return False

        if show_detail:
            print(f"  标题: {video_info['title']}")
            print(f"  上传者: {video_info['owner']}")

        play_data = self.api.get_play_url_data(bvid, video_info["cid"], quality)
        if not play_data:
            return False

        safe_title = sanitize_filename(video_info["title"])
        output_path = Path(output_dir) / ("audio" if audio_only else "video")
        output_path.mkdir(parents=True, exist_ok=True)

        # --- 仅音频 ---
        if audio_only:
            dash = play_data.get("dash")
            if dash and dash.get("audio"):
                audios = sorted(
                    dash["audio"],
                    key=lambda x: x["bandwidth"],
                    reverse=True,
                )
                if show_detail:
                    print(f"  音频编码: {audios[0].get('codecs', 'unknown')}")
                audio_file = output_path / f"{safe_title}.m4a"
                print(f"  下载音频: {safe_title}.m4a")
                return self.download_file(audios[0]["base_url"], audio_file)
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
        dash_best_q = (
            max((v["id"] for v in dash["video"]), default=0)
            if dash and dash.get("video")
            else 0
        )
        durl_q = actual_quality

        # fnval=4048 经常不返回 durl；没 ffmpeg 时只能靠 durl → 无条件补拉
        if not durl:
            if show_detail:
                print("  正在查询传统流…")
            durl_data = self.api.get_play_url_data(
                bvid, video_info["cid"], quality, fnval=1
            )
            if durl_data:
                durl = durl_data.get("durl")
                if durl:
                    durl_q = durl_data.get("quality", durl_q)

        prefer_dash = (
            dash
            and dash.get("video")
            and dash.get("audio")
            and check_ffmpeg()
            and dash_best_q >= durl_q
        )

        if prefer_dash:
            return self._download_dash(dash, output_path, safe_title, show_detail)

        elif durl:
            if len(durl) > 1:
                print(f"  ⚠ 该视频有 {len(durl)} 个分段，将只下载第一段")
            durl_name = QN_NAMES.get(durl_q, str(durl_q))
            print(f"  画质: {durl_name}  |  下载: {safe_title}.mp4")
            return self.download_file(
                durl[0]["url"], output_path / f"{safe_title}.mp4"
            )

        elif (
            dash
            and dash.get("video")
            and dash.get("audio")
            and check_ffmpeg()
        ):
            # durl 不可用，兜底走 DASH
            if show_detail:
                print("  ⚠ 传统流不可用，使用 DASH 流")
            return self._download_dash(dash, output_path, safe_title, show_detail)

        else:
            print("  ✗ 无法获取视频下载地址")
            return False

    # ========================================================================
    # 批量下载
    # ========================================================================

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
        print(
            f"  📦 批量下载模式\n"
            f"  任务数: {len(urls)}  |  模式: {mode_label}  "
            f"|  保存到: {output_dir}"
        )
        print(f"{'=' * 55}\n")

        success = 0
        fail = 0
        for i, url in enumerate(urls, 1):
            print(f"[{i}/{len(urls)}]", end="")
            if self.download(
                url, str(output_dir), audio_only, quality, show_detail=True
            ):
                success += 1
            else:
                fail += 1
            print()

        print(f"{'=' * 55}")
        print(f"  📊 批量下载完成: 成功 {success} / 失败 {fail}")
        print(f"{'=' * 55}")
        return success, fail, str(output_dir)

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

    def _save_uploader_record(
        self, mid: int, name: str, url: str
    ) -> None:
        """添加/更新一个 UP 主记录"""
        uploaders = self._load_uploaders()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for u in uploaders:
            if u["mid"] == mid:
                u["name"] = name
                u["last_access"] = now
                self._save_uploaders(uploaders)
                return

        uploaders.append({
            "mid": mid,
            "name": name,
            "url": url,
            "last_access": now,
        })
        self._save_uploaders(uploaders)

    def pick_uploader(self) -> Optional[str]:
        """
        展示已收藏的 UP 主，让用户选择或输入新的。
        返回 UP 主空间 URL。
        """
        uploaders = self._load_uploaders()
        if uploaders:
            print("\n已收藏的 UP 主:")
            for i, u in enumerate(uploaders, 1):
                print(
                    f"  {i}. {u['name']}  (mid={u['mid']})  "
                    f"[{u['last_access']}]"
                )
            print("  n. 输入新的 UP 主链接")
            print("  0. 返回")

            while True:
                choice = input("\n请选择: ").strip().lower()
                if choice == "0":
                    return None
                if choice == "n":
                    return input(
                        "UP主空间URL 或 该UP主的任意视频URL: "
                    ).strip()
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
    # UP 主空间下载
    # ========================================================================

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
        mid = self.api.resolve_mid(uploader_input)
        if not mid:
            print(f"  ✗ 无法获取 UP 主信息: {uploader_input}")
            return 0, 1, ""

        # ---- 网页抓取视频列表 ----
        # 爬取后同步 cookie 回 API session（爬取中若触发重新登录，cookie 已更新）
        videos = self.scraper.scrape_videos(mid, count)
        self.auth.apply_to_session(self.api.session)
        if not videos:
            print("  ✗ 未找到任何视频")
            return 0, 0, ""

        # ---- 保存 UP 主记录 ----
        author_name = f"uid_{mid}"
        first_info = self.api.get_video_info(videos[0]["bvid"])
        if first_info:
            author_name = sanitize_filename(first_info["owner"])

        space_url = f"https://space.bilibili.com/{mid}"
        self._save_uploader_record(mid, author_name, space_url)

        # 去掉时间戳，直接存到 UP 主名/ 下
        output_dir = Path(output_base) / author_name

        # 加载下载记录用于去重
        manifest_path = output_dir / "_downloaded.json"
        manifest: Dict[str, Any] = {}
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text("utf-8"))
            except Exception:
                pass

        mode_label = "音频" if audio_only else "视频"
        print(f"\n{'=' * 55}")
        print(
            f"  📦 UP主: {author_name}\n"
            f"  任务数: {len(videos)}  |  模式: {mode_label}  "
            f"|  保存到: {output_dir}"
        )
        print(f"{'=' * 55}\n")

        success = 0
        fail = 0
        skip = 0
        dl_type = "audio" if audio_only else "video"
        for i, v in enumerate(videos, 1):
            # 去重：同类型且画质 >= 当前 → 跳过；不同类型照下
            info = self.api.get_video_info(v["bvid"])
            safe_title = (
                sanitize_filename(info["title"])
                if info
                else v["bvid"]
            )
            prev = manifest.get(safe_title)
            if (
                prev
                and prev.get("type") == dl_type
                and prev.get("qn", 0) >= quality
            ):
                exist_name = QN_NAMES.get(prev["qn"], str(prev["qn"]))
                req_name = QN_NAMES.get(quality, str(quality))
                print(
                    f"[{i}/{len(videos)}] ⏭ 跳过: "
                    f"{safe_title[:40]}… "
                    f"(已有 {exist_name} ≥ {req_name})"
                )
                skip += 1
                continue

            print(f"[{i}/{len(videos)}]", end="")
            if self.download(
                v["bvid"], str(output_dir), audio_only, quality,
                show_detail=True,
            ):
                success += 1
                manifest[safe_title] = {"qn": quality, "type": dl_type}
            else:
                fail += 1
            print()

        # 保存下载记录
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8"
        )

        if skip > 0:
            print(f"  ⏭ 跳过 {skip} 个（已下载过同等或更高画质）")
        print(f"{'=' * 55}")
        print(
            f"  📊 UP主下载完成: "
            f"成功 {success} / 失败 {fail} / 跳过 {skip}"
        )
        print(f"{'=' * 55}")
        return success, fail, str(output_dir)
