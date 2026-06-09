# -*- coding: utf-8 -*-
"""
命令行界面：交互式菜单、清晰度选择、参数解析
"""

import sys
from typing import List, Optional, Tuple

from src.api import BiliAPI
from src.config import (
    DEFAULT_OUTPUT_DIR, DIR_BATCH, DIR_SINGLE,
    QUALITY_MAP,
)
from src.downloader import Downloader


# ============================================================================
# 清晰度选择
# ============================================================================

def select_quality(
    available: Optional[List[Tuple[str, int]]] = None,
) -> int:
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

    default_idx = min(3, len(items) - 1)
    default_label = (
        items[default_idx][0]
        if len(items) > default_idx
        else items[-1][0]
    )
    default_qn = (
        items[default_idx][1]
        if len(items) > default_idx
        else items[-1][1]
    )

    while True:
        choice = input(
            f"请选择 (1-{len(items)}, "
            f"默认 {default_idx + 1}={default_label}): "
        ).strip()
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


# ============================================================================
# 交互式菜单
# ============================================================================

def interactive_menu(
    downloader: Downloader, api: BiliAPI,
) -> None:
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
            bvid = api.extract_bv(url)
            if bvid:
                info = api.get_video_info(bvid)
                if info:
                    print("  正在查询可用画质…")
                    available = api.get_available_qualities(
                        bvid, info["cid"]
                    )
            quality = select_quality(available if available else None)
            if quality < 0:
                continue
            output = input(
                f"保存目录 (默认 ./{DIR_SINGLE}): "
            ).strip()
            downloader.download(
                url, output or DIR_SINGLE, audio_only=False,
                quality=quality,
            )

        elif choice == "2":
            url = input("视频URL或BV号: ").strip()
            if not url:
                continue
            output = input(
                f"保存目录 (默认 ./{DIR_SINGLE}): "
            ).strip()
            downloader.download(
                url, output or DIR_SINGLE, audio_only=True,
            )

        elif choice == "3":
            input_file = (
                input("URL列表文件 (默认 ./input.txt): ").strip()
                or "input.txt"
            )
            mode = input(
                "下载模式 (1=视频, 2=仅音频, 默认1): "
            ).strip()
            audio_only = mode == "2"
            quality = 80
            if not audio_only:
                quality = select_quality()
                if quality < 0:
                    continue
            downloader.download_batch(
                input_file, audio_only=audio_only, quality=quality,
            )

        elif choice == "4":
            url = downloader.pick_uploader()
            if not url:
                continue

            # 验证链接有效性
            mid = api.resolve_mid(url)
            if not mid:
                print(
                    "  ✗ 无法识别该链接，请确认是 UP 主空间链接"
                    "或视频链接后重试"
                )
                continue
            print(f"  ✓ UP主 mid={mid}")

            try:
                n = input("下载数量 (默认10): ").strip()
                count = int(n) if n else 10
            except ValueError:
                count = 10
            mode = input(
                "下载模式 (1=视频, 2=仅音频, 默认1): "
            ).strip()
            audio_only = mode == "2"
            quality = 80
            if not audio_only:
                quality = select_quality()
                if quality < 0:
                    continue
            downloader.download_uploader(
                url, count, audio_only=audio_only, quality=quality,
            )

        else:
            print("无效选项，请重新选择")


# ============================================================================
# 命令行参数模式
# ============================================================================

def parse_and_run(downloader: Downloader, args: List[str]) -> None:
    """解析命令行参数并执行对应操作"""
    if len(args) < 2:
        return

    cmd = args[1].lower()

    if cmd == "batch":
        input_file = args[2] if len(args) > 2 else "input.txt"
        audio_only = len(args) > 3 and args[3] == "audio"
        quality = int(args[4]) if len(args) > 4 else 80
        downloader.download_batch(
            input_file, audio_only=audio_only, quality=quality,
        )

    elif cmd == "uploader":
        if len(args) < 3:
            print(
                "用法: python main.py uploader "
                "<UP主空间URL/视频URL> [数量] [video|audio] [清晰度qn]"
            )
            sys.exit(1)
        url = args[2]
        count = int(args[3]) if len(args) > 3 else 10
        audio_only = len(args) > 4 and args[4] == "audio"
        quality = int(args[5]) if len(args) > 5 else 80
        downloader.download_uploader(
            url, count, audio_only=audio_only, quality=quality,
        )

    else:
        url = args[1]
        output = args[2] if len(args) > 2 else DEFAULT_OUTPUT_DIR
        audio_only = len(args) > 3 and args[3] == "audio"
        quality = int(args[4]) if len(args) > 4 else 80
        downloader.download(
            url, output, audio_only=audio_only, quality=quality,
        )
