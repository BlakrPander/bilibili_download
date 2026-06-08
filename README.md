# 🎬 Bilibili 视频/音频下载器

一个基于 Python 的 Bilibili 内容下载工具，支持视频/音频下载、批量下载、UP 主空间爬取。

## 功能概览

| 功能 | 说明 |
|------|------|
| 📺 单个视频下载 | 输入 URL/BV号，下载完整视频（最高 4K） |
| 🎵 仅下载音频 | 提取 DASH 音频流，保存为 `.m4a` |
| 📦 批量下载 | 从 `input.txt` 逐行读取链接，自动打包到时间戳目录 |
| 🔍 UP主空间爬取 | 模拟浏览器访问空间页，爬取指定数量的视频/音频 |

## 环境要求

| 依赖 | 用途 | 必需 |
|------|------|------|
| Python 3.9+ | 运行环境 | ✅ |
| `requests` | 视频下载 API 调用 | ✅ |
| `playwright` | UP 主空间页面渲染 | ✅（仅「UP主爬取」需要） |
| `ffmpeg` | 1080P+ 视频音视频合并 | ❌（无 ffmpeg 时使用低画质流） |

## 快速开始

```bash
# 1. 创建虚拟环境 & 安装依赖
python3 -m venv .venv
source .venv/bin/activate
pip install requests playwright

# 2. 安装 Chromium（仅一次，UP主爬取需要）
playwright install chromium

# 3. 运行
python main.py
```

### 可选：安装 ffmpeg（推荐）

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg

# Windows
# 下载: https://ffmpeg.org/download.html ，添加到 PATH
```

没有 ffmpeg 也能用，但 1080P+ 视频会回退到传统流（画质可能较低）。

---

## 使用方式

### 交互模式（推荐）

直接运行 `python main.py`，进入菜单：

```
=======================================================
  🎬 Bilibili 视频/音频下载器
=======================================================
  1. 下载单个视频
  2. 下载单个音频
  3. 批量下载（从 input.txt）
  4. UP主空间爬取
  0. 退出
```

#### 选项 1 & 2：单个下载

```
请选择: 1
视频URL或BV号: https://www.bilibili.com/video/BV1owEu6qEQg

可选清晰度:
  1. 360P
  2. 480P
  3. 720P
  4. 1080P
  5. 1080P+
  6. 4K
  7. 不选择（返回）
请选择 (1-6, 默认 4=1080P): 

保存目录 (默认 ./downloads/single): 
```

**支持的输入格式：**
- 完整 URL：`https://www.bilibili.com/video/BV1owEu6qEQg`
- 短链接：`https://b23.tv/xxxxx`
- 纯 BV 号：`BV1owEu6qEQg`

**输出：**
- 视频模式 → `downloads/single/{标题}.mp4`
- 音频模式 → `downloads/single/{标题}.m4a`

#### 选项 3：批量下载

准备 `input.txt`（每行一个链接，支持 `#` 注释）：

```text
# 这是注释行，会被忽略
https://www.bilibili.com/video/BV1owEu6qEQg
https://www.bilibili.com/video/BV1xx411c7mD
BV1jYVm6PEyS
```

运行后自动创建时间戳目录，所有文件收纳其中：

```
downloads/batch/
└── 2026-06-08_17-30-22/
    ├── 视频1.mp4
    └── 视频2.m4a
```

#### 选项 4：UP主空间爬取

**首次使用**需要登录——程序会自动弹出 Chrome 浏览器，登录后按 Enter，cookie 会保存到 `cookies.json`，之后无需重复登录。

```
请选择: 4

已收藏的 UP 主:
  1. 戒社  (mid=27492426)  [2026-06-08 17:30:22]
  n. 输入新的 UP 主链接
  0. 返回

请选择: 1
下载数量 (默认10): 5
下载模式 (1=视频, 2=仅音频, 默认1): 2
```

**支持的输入：**
- UP 主空间首页：`https://space.bilibili.com/27492426`
- 该 UP 主的任意视频链接（自动识别 mid）

**输出：**

```
downloads/uploader/
└── 戒社/                          ← 按 UP 主名分类
    ├── 2026-06-08_15-35-28/       ← 按下载时间分类
    │   ├── 视频1.m4a
    │   └── 视频2.m4a
    └── 2026-06-08_17-40-15/
        └── ...
```

每次下载后自动保存 UP 主到收藏，下次可直接选择。

### 命令行模式

适合脚本/定时任务：

```bash
# 单个视频
python main.py "https://www.bilibili.com/video/BV1owEu6qEQg"
python main.py BV1owEu6qEQg ./my_output          # 指定输出目录
python main.py BV1owEu6qEQg downloads audio      # 仅音频
python main.py BV1owEu6qEQg downloads video 120  # 4K 视频

# 批量下载
python main.py batch                    # 默认读 input.txt
python main.py batch my_list.txt        # 指定列表文件
python main.py batch input.txt audio    # 批量仅音频
python main.py batch input.txt video 64 # 批量 720P

# UP主爬取
python main.py uploader "https://space.bilibili.com/27492426"
python main.py uploader "https://space.bilibili.com/27492426" 20
python main.py uploader "https://space.bilibili.com/27492426" 10 audio
```

---

## 输出目录结构

```
downloads/
├── single/                          # 单个下载
│   └── {视频标题}.mp4
├── batch/                           # 批量下载
│   └── {YYYY-MM-DD_HH-MM-SS}/
│       └── {视频标题}.mp4
└── uploader/                        # UP主下载
    └── {UP主名}/
        └── {YYYY-MM-DD_HH-MM-SS}/
            └── {视频标题}.mp4
```

## 数据文件

| 文件 | 说明 |
|------|------|
| `cookies.json` | Bilibili 登录态（UP主爬取需要，首次自动生成） |
| `uploaders.json` | 已收藏的 UP 主列表（下载后自动保存） |
| `input.txt` | 批量下载的链接列表（一行一个） |

---

## 清晰度说明

| 选项 | qn 值 | 需要 ffmpeg | 需要登录 |
|------|-------|------------|----------|
| 360P | 16 | ❌ | ❌ |
| 480P | 32 | ❌ | ❌ |
| 720P | 64 | ❌ | ❌ |
| 1080P | 80 | ✅ | ❌ |
| 1080P+ | 112 | ✅ | ✅ |
| 4K | 120 | ✅ | ✅ |

> 无 ffmpeg 时，1080P+ 会自动回退到传统合并流（画质受限于 B 站转码策略）。

---

## 常见问题

**Q: UP主爬取时报「风控校验失败」？**
A: cookies 可能过期了，删除 `cookies.json` 重新登录即可。

**Q: 下载速度慢？**
A: B 站 CDN 对非大陆 IP 有限速，可尝试使用代理或切换网络环境。

**Q: 视频下载后无法播放？**
A: 检查是否安装了 ffmpeg。无 ffmpeg 时下载的传统流是 `.flv` 容器，部分播放器不兼容。安装 ffmpeg 后会自动下载 `.mp4` 格式。

**Q: 能下载付费/番剧内容吗？**
A: 不支持。本工具仅下载普通用户上传的公开视频。

**Q: 能下载弹幕/字幕吗？**
A: 目前不支持，仅下载视频/音频流。

---

## 技术架构

```
输入 (URL/BV号)
  │
  ├─ 单视频/批量: requests → Bilibili API → 获取下载地址 → 流式下载
  │
  └─ UP主爬取: Playwright → 渲染空间页面 → 提取 DOM 中的 BV 链接
                └─ 逐个调用 requests 下载（同上）
```
