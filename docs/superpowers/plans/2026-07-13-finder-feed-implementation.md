# 微信视频号分享消息兼容 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 ComWeChat 的 `type=51` 视频号分享转换为可在 Telegram 播放的视频，并提供可靠的文字/封面降级。

**Architecture:** 新增无 EFB 依赖的 `finder_feed.py` 负责 XML 字段提取，现有 `MsgDeco.py` 负责下载临时媒体并构造 EFB 消息。普通分享消息继续走原有分支，部署仅替换 EFB 镜像。

**Tech Stack:** Python 3.11、lxml、EH Forwarder Bot、pytest、Docker/GHCR

## Global Constraints

- 仅修改 `efb_wechat_comwechat_slave` 的分享解析及对应测试。
- 不修改 ComWeChat、Telegram Master、Bot API、watchdog、登录逻辑和文件大小配置。
- 修改 NAS 前备份；只重建 `efb2026-efb-1`。
- Git 提交使用中文说明。

---

### Task 1: 视频号 XML 解析器

**Files:**
- Create: `efb_wechat_comwechat_slave/finder_feed.py`
- Create: `tests/test_finder_feed.py`

**Interfaces:**
- Produces: `FinderFeed(author, description, video_url, cover_url, duration_seconds)`
- Produces: `parse_finder_feed(xml_text: str) -> Optional[FinderFeed]`

- [ ] **Step 1: 写入失败测试**

测试真实结构的 `type=51` XML，断言作者、文案、视频 URL、封面和时长；同时断言普通 `type=5` 返回 `None`。

- [ ] **Step 2: 验证 RED**

Run: `pytest -q tests/test_finder_feed.py`
Expected: FAIL，原因是 `finder_feed.py` 或接口尚不存在。

- [ ] **Step 3: 最小实现**

使用 `lxml.etree.fromstring` 和兼容大小写的 XPath 候选路径提取字段；仅当 `appmsg/type=51` 且存在 `finderFeed` 时返回数据类。

- [ ] **Step 4: 验证 GREEN**

Run: `pytest -q tests/test_finder_feed.py`
Expected: 全部 PASS。

### Task 2: EFB 视频及降级消息包装

**Files:**
- Modify: `efb_wechat_comwechat_slave/MsgDeco.py`
- Modify: `tests/test_finder_feed.py`

**Interfaces:**
- Consumes: `parse_finder_feed(xml_text)`
- Produces: `efb_finder_feed_wrapper(xml_text, downloader=download_file)`

- [ ] **Step 1: 写入失败测试**

通过最小 EFB stub 加载 `MsgDeco.py`，验证视频下载成功返回 `MsgType.Video` 且正文包含作者、文案和时长；视频下载失败时再次下载封面并返回 `MsgType.Image`；两次均失败时返回文字。

- [ ] **Step 2: 验证 RED**

Run: `pytest -q tests/test_finder_feed.py`
Expected: FAIL，原因是 `efb_finder_feed_wrapper` 尚不存在或 `type=51` 未调用它。

- [ ] **Step 3: 最小实现**

在 `MsgDeco.py` 中新增包装函数；视频文件名固定为 `wechat-channel.mp4`，正文格式为“微信视频号分享 + 作者 + 文案 + 时长”。失败时按封面图片、纯文字顺序降级，并在 `type=51` 分支调用该函数。

- [ ] **Step 4: 验证 GREEN 与回归**

Run: `pytest -q`
Expected: 全部 PASS。

- [ ] **Step 5: 编译检查并提交**

Run: `python3 -m compileall -q efb_wechat_comwechat_slave tests`
Expected: exit 0。

Commit message: `功能：兼容微信视频号分享消息`

### Task 3: 镜像构建与 NAS 部署

**Files:**
- Read: NAS `/vol4/1000/docker/efb/docker-compose.yaml`
- Backup: NAS `/vol4/1000/docker/efb/backups/finder-feed-20260713/`

- [ ] **Step 1: 推送源码并触发/执行现有镜像构建流程**

确认 GHCR 镜像仍基于现有自定义 EFB 镜像链，不替换 Telegram Master、中间件或大文件配置。

- [ ] **Step 2: 备份 NAS 配置和当前镜像标识**

逐个创建备份文件，不删除任何目录；记录当前镜像 digest 作为回退依据。

- [ ] **Step 3: 拉取镜像并仅重建 EFB**

Run on NAS: `docker compose pull efb && docker compose up -d --no-deps efb`
Expected: `efb2026-efb-1` running，其余容器启动时间不变。

- [ ] **Step 4: 部署验证**

检查容器内源码包含 `parse_finder_feed`，运行脱敏 XML 解析，并核对 EFB 启动日志无异常。

### Task 4: 实发验证

- [ ] **Step 1: 用户再次向自己发送视频号分享**

- [ ] **Step 2: 核对日志与 Telegram**

Expected: EFB 日志收到 `type=51`，Telegram 收到可播放视频；若 CDN 下载失败，则收到封面和文案，不出现“微信版本过低”卡片。
