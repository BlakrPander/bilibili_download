# -*- coding: utf-8 -*-
"""
工具函数：文件名清理、ffmpeg 检测、下载进度条
"""

import re
import shutil
import time
from typing import Optional


def sanitize_filename(name: str) -> str:
    """清理文件名中的非法字符"""
    return re.sub(r'[<>:"/\\|?*]', "_", name).strip()


# ============================================================================
# ffmpeg 检测（带缓存）
# ============================================================================

_has_ffmpeg: Optional[bool] = None


def check_ffmpeg() -> bool:
    """检查 ffmpeg 是否可用（带缓存）"""
    global _has_ffmpeg
    if _has_ffmpeg is None:
        _has_ffmpeg = shutil.which("ffmpeg") is not None
    return _has_ffmpeg


# ============================================================================
# 下载进度条
# ============================================================================

def progress_bar(
    downloaded: int, total: int, start_time: float
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
