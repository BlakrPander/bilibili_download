# -*- coding: utf-8 -*-
"""
常量定义：画质映射、目录路径、文件路径
"""

from pathlib import Path
from typing import Dict


# ============================================================================
# 通用常量
# ============================================================================

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# ============================================================================
# 画质映射
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

# ============================================================================
# 目录 & 文件路径
# ============================================================================

DEFAULT_OUTPUT_DIR = "downloads"
COOKIE_FILE = Path(__file__).parent.parent / "cookies.json"
UPLOADERS_FILE = Path(__file__).parent.parent / "uploaders.json"

DIR_SINGLE = "downloads/single"
DIR_BATCH = "downloads/batch"
DIR_UPLOADER = "downloads/uploader"
