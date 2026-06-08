# 🎬 Bilibili 视频/音频下载器

一个基于 Python 的 Bilibili 内容下载工具，支持视频/音频下载、批量下载、UP 主空间爬取。

## 功能概览

| 功能 | 说明 |
|------|------|
| 🔐 全局登录 | 启动时自动检测/引导登录，所有模式共享登录态，解锁 1080P+ 高清画质 |
| 📺 单个视频下载 | 输入 URL/BV号，动态查询可用画质，智能选择最优流 |
| 🎵 仅下载音频 | 提取 DASH 音频流，保存为 `.m4a` |
| 📦 批量下载 | 从 `input.txt` 逐行读取链接，自动打包到时间戳目录 |
| 🔍 UP主空间爬取 | Playwright 渲染页面，爬取指定数量视频/音频，支持 UP 主收藏 |
| 🎯 智能画质 | 实际查询视频可用画质后再展示菜单，DASH/durl 自动择优，画质不足时降级提示 |

## 环境要求

| 依赖 | 用途 | 必需 |
|------|------|------|
| Python 3.9+ | 运行环境 | ✅ |
| `requests` | 视频下载 API 调用 | ✅ |
| `playwright` | UP 主空间页面渲染 + 首次登录 | ✅（仅「UP主爬取」+「首次登录」需要） |
| `ffmpeg` | 1080P+ 视频音视频合并 | ❌（无 ffmpeg 时自动走传统流） |

## 快速开始

```bash
# 1. 创建虚拟环境 & 安装依赖
python3 -m venv .venv
source .venv/bin/activate
pip install requests playwright

# 2. 安装 Chromium（仅一次，UP主爬取 + 首次登录需要）
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

没有 ffmpeg 也能用 —— 1080P+ 视频会自动走传统合并流（durl），画质不损失。

---

## 使用方式

### 启动流程

首次运行时，程序会自动检测登录状态：

```
$ python main.py

  未检测到登录信息（登录后可解锁 1080P+ 高清画质）
  是否现在登录？[Y/n]:

→ 选 Y → 弹出 Chrome 浏览器 → 手动登录 B站 → 按 Enter → cookie 保存 → 进菜单
→ 选 n → 游客模式（画质受限，最高约 720P）→ 进菜单
```

之后每次启动自动验证 cookie 有效性，过期才重新提示登录。**登录态全局共享**，单视频、批量、UP主爬取全部受益。

### 交互模式（推荐）

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

#### 选项 1：单个视频下载

输入 URL 后，**程序会先查询该视频实际可下载的画质**，再展示菜单：

```
请选择: 1
视频URL或BV号: https://www.bilibili.com/video/BV1owEu6qEQg
  正在查询可用画质…

该视频可用清晰度 (3 种):          ← 动态查询，只显示真实可下的
  1. 720P
  2. 480P
  3. 360P
  4. 不选择（返回）
请选择 (1-3, 默认 1=720P):
保存目录 (默认 ./downloads/single):
```

**支持的输入格式：**
- 完整 URL：`https://www.bilibili.com/video/BV1owEu6qEQg`
- 短链接：`https://b23.tv/xxxxx`
- 纯 BV 号：`BV1owEu6qEQg`

**画质选择逻辑：**
- 已登录 → 展示实际可下载的最高画质（通常 1080P+）
- 游客模式 → 最高约 720P
- 若所选画质不可用 → 自动降级并提示 `⚠ 1080P 不可用，实际画质: 720P`
- DASH 分离流 vs 传统合并流 → 自动比较两边的实际画质，选更优的

**输出：**
- 视频模式 → `downloads/single/video/{标题}.mp4`
- 音频模式 → `downloads/single/audio/{标题}.m4a`

#### 选项 2：仅下载音频

提取视频的 DASH 音频流，自动选择最高码率。无需选择画质。

#### 选项 3：批量下载

准备 `input.txt`（每行一个链接，支持 `#` 注释）：

```text
# 这是注释行，会被忽略
https://www.bilibili.com/video/BV1owEu6qEQg
https://www.bilibili.com/video/BV1xx411c7mD
BV1jYVm6PEyS
```

运行后自动创建时间戳目录：

```
downloads/batch/
└── 2026-06-08_17-30-22/
    ├── 视频1.mp4
    └── 视频2.m4a
```

#### 选项 4：UP主空间爬取

输入 UP 主链接后**先验证有效性**，通过后才询问下载数量：

```
请选择: 4

已收藏的 UP 主:
  1. 戒社  (mid=27492426)  [2026-06-08 17:30:22]
  n. 输入新的 UP 主链接
  0. 返回

请选择: n
UP主空间URL: https://space.bilibili.com/27492426
  ✓ UP主 mid=27492426
下载数量 (默认10):
```

**支持的输入：**
- UP 主空间首页：`https://space.bilibili.com/27492426`
- 该 UP 主的任意视频链接（自动识别 mid）

**输出：**

```
downloads/uploader/
└── 戒社/                    ← 按 UP 主名
    ├── video/               ← 视频
    └── audio/               ← 音频
```

下载前自动查重：同类型且已有画质 ≥ 当前 → 跳过；已有画质较低 → 覆盖升级。记录保存在 `_downloaded.json`。

每次下载后自动保存 UP 主到收藏（`uploaders.json`），下次可直接选择。

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
├── single/                    # 单个下载
│   ├── video/                 # 视频 (.mp4)
│   └── audio/                 # 音频 (.m4a)
├── batch/                     # 批量下载
│   └── {YYYY-MM-DD_HH-MM-SS}/
│       ├── video/
│       └── audio/
└── uploader/                  # UP主下载（无时间戳）
    └── {UP主名}/
        ├── video/
        └── audio/
```

## 数据文件

| 文件 | 说明 |
|------|------|
| `cookies.json` | Bilibili 登录态（启动时自动检测/生成，全局共享） |
| `uploaders.json` | 已收藏的 UP 主列表（下载后自动保存） |
| `input.txt` | 批量下载的链接列表（一行一个，支持 `#` 注释） |

---

## 清晰度说明

### 画质选择机制

1. **动态查询** — 选视频后先请求最高画质，从 API 响应中提取实际可下载的清晰度列表
2. **登录影响** — 游客模式通常最高 720P；登录后可达 1080P+/4K
3. **自动降级** — 选 4K 但视频只有 720P 时，自动降级并提示
4. **流择优** — DASH 分离流（需 ffmpeg）和传统合并流（durl）之间自动比较实际画质，选更优的

### 画质对照

| 选项 | qn 值 | 登录后 | 游客 |
|------|-------|--------|------|
| 360P | 16 | ✅ | ✅ |
| 480P | 32 | ✅ | ✅ |
| 720P | 64 | ✅ | ✅ |
| 1080P | 80 | ✅ | ❌ |
| 1080P+ | 112 | ✅ | ❌ |
| 4K | 120 | ✅ | ❌ |

---

## 常见问题

**Q: 为什么选 1080P 却下到 720P？**
A: 两种情况 — ① 未登录，游客画质上限约 720P，启动时登录即可；② 视频本身最高只有 720P，程序会显示 `⚠ 1080P 不可用，实际画质: 720P`。

**Q: Cookie 过期了怎么办？**
A: 启动时自动检测，过期会提示重新登录。也可手动删除 `cookies.json` 后重新运行。

**Q: 下载速度慢？**
A: B 站 CDN 对非大陆 IP 有限速，可尝试使用代理或切换网络环境。

**Q: 视频下载后无法播放？**
A: 检查是否安装了 ffmpeg。无 ffmpeg 时自动走传统流（`.mp4`），通常都能播放。

**Q: 能下载付费/番剧内容吗？**
A: 不支持。本工具仅下载普通用户上传的公开视频。

**Q: 能下载弹幕/字幕吗？**
A: 目前不支持，仅下载视频/音频流。

---

## 技术架构

```
启动 → cookie 检测 → 有效? → 进菜单
                    → 无效 → 浏览器登录 → 保存 cookie → 进菜单

单视频/批量下载:
  requests (带 cookie) → Bilibili API → 动态画质查询 → DASH/durl 择优 → 流式下载

UP主爬取:
  Playwright (带 cookie) → 渲染空间页面 → 提取 DOM 中的 BV 链接
    └─ 逐个 requests 下载（同上）
```

---

## 更新日志

### v1.1.1 (2026-06-08)
- 🔧 **修复 Windows 无 ffmpeg 无法下载** — durl 为空时无条件补拉传统流
- 🔧 **Cookie 请求修复** — 改用 requests cookie jar，解决登录后仍无法获取高清画质
- 🎬 **setup.bat 新增 ffmpeg 自动安装** — `winget install Gyan.FFmpeg` 一键装好 1080P+ 所需

### v1.1 (2026-06-08)
- 🔐 **全局登录** — 启动时自动检测/引导登录，所有下载模式共享登录态，解锁 1080P+ 高清画质
- 🎯 **智能画质** — 动态查询视频实际可用清晰度后再展示菜单，过滤虚假画质选项
- 🔀 **DASH/durl 择优** — 自动比较两种流的实际画质，选更优的下载；durl 为空时补请求兜底
- 📂 **video/audio 分离** — single、batch、uploader 下均自动归类到 video/ 或 audio/ 子目录
- 🗂 **UP主目录扁平化** — 去掉时间戳层级，直接 `{UP主名}/video/` 和 `audio/`
- ✅ **下载去重** — UP主模式自动检查 `_downloaded.json`，同画质跳过、低画质覆盖升级
- 🔗 **UP主链接预验证** — 输入链接后先验证有效性，通过后才询问下载数量

### v1.0 (2026-06-08)
- 📺 单个视频/音频下载，支持 360P ~ 4K 清晰度
- 📦 批量下载（input.txt）
- 🔍 UP主空间爬取（Playwright + Cookie 管理）
- ⭐ UP主收藏（uploaders.json）
- 📊 实时下载进度条

---

## 开源协议

本软件采用 **Creative Commons Attribution-NonCommercial 4.0 (CC BY-NC 4.0)** 协议。

您可以自由地：
- **共享** — 复制、分发本软件
- **修改** — 创作衍生作品

但需遵守以下条件：
- **署名** — 必须标注原作者（BlakrPander）及原始项目链接
- **非商业性使用** — 不得将本软件用于商业目的

完整协议文本：https://creativecommons.org/licenses/by-nc/4.0/legalcode.zh-hans

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND.
