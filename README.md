# EFB ComWechat 微信从端

这是 `shaoyou11` 维护的 ComWechat 从端，用于连接 Windows 微信并将微信消息交给 EH Forwarder Bot。
当前版本配合自有 EFB Telegram 主端、ComWechat 容器和微信会话 Watchdog 使用。

## 功能范围

- 收发微信文字、图片、文件、语音、视频、链接和引用消息。
- 读取联系人、群聊、群成员和系统账号。
- 检测微信登录状态，获取二维码并执行强制退出。
- 在登录成功、确认失败或二维码过期后，收回 Telegram 中的登录二维码。
- 通过容器内部接口发送微信离线事件，触发 Watchdog。
- 解析微信视频号分享，提供作者、标题、时长、封面和页面链接。
- 按消息 ID 主动请求普通图片原文件；原文件不可用时再尝试缩略图。
- Bridge 队列中的历史图片也会主动重新请求原文件。
- 合并历史失效媒体提醒，避免超时通知刷屏。
- 将微信技术标识转换为联系人、群聊或系统账号中文名称。

## Telegram 登录入口

日常使用主端提供的固定命令：

| 命令 | 作用 |
| --- | --- |
| `/login` | 获取微信登录二维码。 |
| `/wechat` | 打开微信管理面板。 |
| `/watchdog` | 管理自动恢复开关。 |

兼容命令：

- `/extra`：旧附加功能入口，由主端转入微信管理面板。
- `/0_reauth`：旧的重新扫码命令。
- `/h_0_reauth`：旧的重新扫码用法说明。

从端实际提供的附加功能只有“重新扫码登录”和“强制退出微信”。日常使用无需记忆 EFB 动态组件序号。

## 微信会话内指令

这些命令只在对应微信会话中使用。自定义 Telegram 主端会按绑定类型生成斜杠菜单：普通联系人绑定群只显示通用命令，
微信群绑定群会增加群管理命令；机器人主会话和未绑定群组不会显示这些命令。

| 命令 | 参数与作用 |
| --- | --- |
| `/helpcomwechat` | 显示 ComWechat 会话内指令。 |
| `/search 关键字` | 按联系人昵称搜索并返回 wxid。 |
| `/addtogroup wxid` | 将指定微信用户加入当前群聊；仅限微信群。 |
| `/getmemberlist` | 列出当前群聊成员 wxid 与昵称；仅限微信群。 |
| `/at wxid 消息` | 在群聊中提醒指定成员；仅限微信群，多个 wxid 使用英文逗号分隔。 |
| `/sendcard wxid 昵称` | 向当前会话发送联系人名片。 |
| `/changename 新群名` | 修改当前微信群名称；仅限微信群。 |
| `/addfriend wxid 验证消息` | 发送好友申请。 |
| `/getstaticinfo friends` | 查看好友缓存。 |
| `/getstaticinfo groups` | 查看群聊缓存。 |
| `/getstaticinfo group_members` | 查看群成员缓存。 |
| `/getstaticinfo contacts` | 查看联系人缓存。 |
| `/membercolor` | 查看群成员头像配色状态，并提供开关。 |
| `/membercolor on` / `/membercolor off` | 开启或关闭 Telegram 群成员姓名前的头像主色标记。 |
| `/forward` | 回复目标微信消息后生成跨会话转发信息。 |

群管理指令在联系人私聊中会提示“该命令只能在微信群会话中使用”。是否执行成功仍取决于微信账号权限、群聊状态和
ComWechat 接口返回结果。

## 登录与自动恢复

从端约每 10 秒检查一次微信登录状态。首次检测到离线时：

1. 向 Telegram 发送中文离线提醒。
2. 通过容器内部接口通知 Watchdog。
3. Watchdog 再次复核登录状态。
4. 仅在本机会话仍有效时尝试“确定”和“进入微信”。

如果 Windows 微信提示自动登录失效或要求重新扫码，只能使用 `/login` 获取二维码；Watchdog 不会绕过微信服务端验证。

离线提醒首次立即发送，持续离线时每 8 小时提醒一次，避免每半小时重复推送。

## 媒体处理

- 普通图片会调用 ComWechat CDN 接口主动请求原图，并作为 Telegram 文件发送，避免二次压缩。
- Bridge 队列中的历史图片会重新请求原图；原图接口不可用时最多等待 120 秒后才回退。
- 普通视频沿用微信电脑端自动下载流程；ComWechat CDN 与自动下载取得的是同一份微信转码视频。
- CDN 文件大小连续 3 秒不变后才发送，避免提前发送下载中的半成品。
- 主动请求失败时继续使用原来的本地文件等待流程。
- 原图明确不存在时才尝试缩略图。
- 正常新消息最长等待 120 秒，不会因上限设置延迟已经下载完成的消息。
- 图片、视频、语音和普通文件都会先写入持久待发清单；EFB 重启后可继续投递，确认 Telegram 已接收后才移除记录。
- EFB 重启后恢复出的历史图片会逐条触发 CDN 下载，避免直接把队列中的缩略图当作原图发送。
- 视频号无法取得原视频时发送封面和可点击页面链接。
- 语音发送到微信前会转换为微信端可接受的格式。
- 文件和媒体临时数据写入配置的 `dir`，应通过 Docker 挂载持久化。

## 配置

最小配置：

```yaml
dir: "/comwechat/Files/"
qrcode_timeout: 10
login_qrcode_ttl_seconds: 180
login_qrcode_login_grace_seconds: 30
bridge_health_url: "http://127.0.0.1:19088/healthz"
bridge_health_timeout_seconds: 2
force_original_media_download: true
force_original_historical_media_download: true
member_avatar_markers: true
```

| 配置项 | 说明 |
| --- | --- |
| `dir` | EFB 容器内可访问的微信文件目录。 |
| `qrcode_timeout` | 获取二维码接口的等待时间。 |
| `login_qrcode_ttl_seconds` | 登录二维码在 Telegram 中的最长保留秒数，默认 180 秒。 |
| `login_qrcode_login_grace_seconds` | 获取二维码后忽略微信接口瞬时“已登录”状态的秒数，默认 30 秒，避免二维码被提前收回。 |
| `bridge_health_url` | ComWechat Bridge 健康接口，用于识别微信栈是否重启，默认 `http://127.0.0.1:19088/healthz`。 |
| `bridge_health_timeout_seconds` | 读取微信栈代次的超时时间，默认 2 秒。 |
| `force_original_media_download` | 是否主动请求图片原文件，默认开启。 |
| `force_original_historical_media_download` | 是否对 Bridge 队列中的历史图片重新请求原文件，默认开启。 |
| `member_avatar_markers` | 是否显示群成员头像主色标记，默认开启；状态持久保存在 `member-avatar-markers.json`。 |

实际微信文件目录必须同时挂载到 ComWechat 容器和 EFB 容器。账号、密码、Token 和真实部署路径不得提交到公开仓库。

同一微信栈中生成的登录二维码仍在有效期内时，重复执行 `/login` 不会重新请求微信接口。若扫码失败后微信主进程和 Bridge 已恢复重建，旧二维码会按微信栈代次判定为失效；系统在新 Bridge 就绪后生成新二维码，发送成功后再收回旧消息。二维码生成期间若恰好发生恢复，本次结果不会发送到 Telegram。

## 数据边界

- 删除微信文件目录会丢失本地媒体缓存，但不会删除 Telegram 云端聊天记录。
- 删除 EFB 数据库可能导致 Telegram 群组绑定、回复、引用和撤回映射失效。
- 微信登录会话属于 Windows 微信数据，不等同于 EFB 配置或 Telegram 云端记录。

## 维护说明

本分支与 `shaoyou11` 的 EFB 镜像固定提交配套构建。升级前应备份配置、微信文件目录映射和旧镜像标识，
再进行有序重启。升级后应验证二维码收回、登录提示、普通图片、视频号分享和持久待发清单。
