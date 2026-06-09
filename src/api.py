# -*- coding: utf-8 -*-
"""
Bilibili API 封装：视频信息、播放地址、画质查询、BV 提取
"""

import re
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

import requests

from src.config import QN_NAMES


class BiliAPI:
    """封装 Bilibili API 调用，使用已注入 cookie 的 requests.Session"""

    def __init__(self, session: requests.Session) -> None:
        self.session = session

    # ========================================================================
    # HTTP 请求基础
    # ========================================================================

    def request(
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

    # ========================================================================
    # BV 号提取
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
                resp = self.session.head(
                    input_str, allow_redirects=True, timeout=15
                )
                bv_match = re.search(r"BV[a-zA-Z0-9]+", resp.url)
                if bv_match:
                    return bv_match.group(0)
            except Exception as e:
                print(f"  ✗ 展开短链接失败: {e}")

        return None

    # ========================================================================
    # 视频信息 & 播放地址
    # ========================================================================

    def get_video_info(self, bvid: str) -> Optional[Dict[str, Any]]:
        """获取视频基本信息"""
        data = self.request(
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

    def get_play_url_data(
        self,
        bvid: str,
        cid: int,
        quality: int = 80,
        fnval: int = 4048,
    ) -> Optional[Dict[str, Any]]:
        """获取播放地址。fnval=4048=DASH+durl，fnval=1=仅传统流"""
        params = urlencode({
            "bvid": bvid,
            "cid": cid,
            "qn": quality,
            "fnval": fnval,
            "fourk": 1,
        })
        data = self.request(
            "GET", f"https://api.bilibili.com/x/player/playurl?{params}"
        )
        if not data:
            return None
        result = data.get("data")
        if not result:
            print(
                f"  ⚠ 播放地址为空 (code={data.get('code')})，"
                "可能需要登录或视频受限"
            )
        return result

    def get_available_qualities(
        self, bvid: str, cid: int
    ) -> List[Tuple[str, int]]:
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
    # UP 主信息提取
    # ========================================================================

    @staticmethod
    def get_mid_from_url(url: str) -> Optional[int]:
        """从 UP 主空间 URL 提取 mid"""
        match = re.search(r"space\.bilibili\.com/(\d+)", url)
        return int(match.group(1)) if match else None

    def get_mid_from_video(self, bvid: str) -> Optional[int]:
        """通过视频 BV 号获取 UP 主 mid"""
        info = self.get_video_info(bvid)
        return info["mid"] if info else None

    def resolve_mid(self, input_str: str) -> Optional[int]:
        """
        从任意输入（空间 URL / 视频 URL / BV 号）解析 UP 主 mid。
        先尝试空间 URL，再尝试视频链接兜底。
        """
        mid = self.get_mid_from_url(input_str)
        if mid:
            return mid
        bvid = self.extract_bv(input_str)
        if bvid:
            return self.get_mid_from_video(bvid)
        return None
