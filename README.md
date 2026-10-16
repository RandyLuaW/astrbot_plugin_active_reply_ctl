<div align="center">

# 不刷屏、不潜水，主动回复刚刚好

<img src="https://count.getloli.com/@astrbot_plugin_active_reply_ctl?name=astrbot_plugin_active_reply_ctl&theme=rule34&padding=6&offset=0&align=top&scale=1&pixelated=1&darkmode=auto" alt="count" />

**AstrBot 主动回复冷却限频插件：概率抽签 + 群级冷却 + 对话延续 + 关键词必回，让 Bot 像真人一样自然地混迹群聊。**

![AstrBot](https://img.shields.io/badge/AstrBot-%3E%3D4.17-5865f2?style=flat-square)
![Version](https://img.shields.io/badge/version-1.5.0-22c55e?style=flat-square)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776ab?style=flat-square)
![Platform](https://img.shields.io/badge/platform-aiocqhttp-f97316?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-3b82f6?style=flat-square)

简体中文 | [English](README_EN.md)

<img src="logo.png" alt="主动回复冷却限频 Logo" width="180">

</div>

> 📦 **规范性说明**：本仓库是一个 [AstrBot](https://github.com/AstrBotDevs/AstrBot) **插件组件仓库**，仅作为 AstrBot 的插件使用，不能独立运行。请将本插件安装至 AstrBot 的 `data/plugins/` 目录，由 AstrBot 框架加载并调度。

---

## 目录

- [它解决什么问题](#它解决什么问题)
- [功能一览](#功能一览)
- [安装](#安装)
- [配置项](#配置项)
- [工作机制](#工作机制)
- [调参建议](#调参建议)
- [注意事项](#注意事项)
- [版本历史](#版本历史)

---

## 它解决什么问题

AstrBot 原生的「群聊上下文感知 → 主动回复」只有一条**纯概率抽签**路径，存在两难：

- **概率调高** → 活跃群里疯狂插话，刷屏招人烦；
- **概率调低** → Bot 几乎永远潜水，等于没开。

本插件在概率抽签之上叠加**群级冷却**与**对话占用守卫**，并补上「对话延续」与「关键词必回」两条稳定触发路径；v1.5.0 起概率/延续路径还带有**指向性判定（SKIP）**——LLM 会结合近期群聊记录判断消息是否真的在跟你说话，无关话题自动静默跳过，不再乱接话。

---

## 功能一览

| 触发路径 | 触发方式 | 频率控制 | 适用场景 |
|----------|----------|----------|----------|
| 🎲 概率主动回复 | 概率抽签命中 | 群级冷却（默认 180s）+ 占用守卫 + SKIP 判定 | 偶尔自然接话，保持存在感 |
| 💬 对话延续 | 成员 @/引用/唤醒 Bot 后，窗口期内的后续消息 | 成员级冷却（默认 10s），窗口内默认必回 + SKIP 判定 | 追问不断片，聊得起来 |
| 🔑 关键词必回 | 消息包含配置的关键词 | 成员级冷却（默认 8s），默认必回（不做 SKIP 判定） | 被叫昵称必回应 |

### 其他内置守卫

| 守卫 | 效果 |
|------|------|
| SKIP 静默跳过 | LLM 结合近期群聊记录判断消息是否指向自己，无关消息输出 `[SKIP]` 后插件静默放弃发送（群里无感、不进对话历史） |
| 对话占用守卫 | 群内有人正与 Bot 对话时，概率路径静默，不插话无关内容 |
| 指向他人过滤 | 消息 @ 了他人或引用他人消息时不插话（延续路径同样踢出） |
| 防回环 | 忽略 Bot 自身消息，开启「上报自身消息」也不会自触发 |
| 白名单 | 可限定仅指定群生效 |
| 内容长度门槛 | 过短的纯文本不触发概率路径（含图片消息不受限） |
| 配置热重载 | WebUI 保存配置即生效，无需重启 AstrBot |

---

## 安装

### 方式一：插件市场（推荐）

AstrBot WebUI → 插件管理 → 从插件市场安装，搜索 `astrbot_plugin_active_reply_ctl` 或「主动回复冷却限频」。

### 方式二：Releases 下载

前往 [Releases](../../releases) 页下载最新版安装包（`astrbot_plugin_active_reply_ctl-vX.Y.Z.zip`），在 AstrBot WebUI「插件管理 → 上传安装」中导入。

### 方式三：手动克隆

```bash
cd AstrBot/data/plugins
git clone https://github.com/RandyLuaW/astrbot_plugin_active_reply_ctl.git
```

> [!TIP]
> 本插件无第三方依赖，无需额外安装 requirements。

### 启用前必须做的一件事

> [!WARNING]
> 在 AstrBot WebUI 中**关闭原生主动回复**，避免双重触发：
>
> 配置页 → 群聊上下文感知 → 主动回复开关 → **关闭**

---

## 配置项

### 基础

| 配置 | 说明 | 默认值 |
|------|------|--------|
| `enable` | 总开关 | `true` |
| `whitelist` | 群白名单（填群号字符串），留空 = 所有群生效 | `[]` |
| `min_message_len` | 概率路径最小文本长度，含图片的消息不受限 | `2` |

### 概率主动回复

| 配置 | 说明 | 默认值 |
|------|------|--------|
| `possibility` | 抽签命中率，有群级冷却兜底可适当调高 | `0.02` |
| `cooldown_seconds` | 同群两次概率回复的最小间隔（秒），`0` 为关闭 | `180` |
| `prompt_template` | 触发时发给 LLM 的提示词，支持 `{message}`、`{sender}` 占位符 | 见下方 |

### 对话延续

| 配置 | 说明 | 默认值 |
|------|------|--------|
| `continue_window_seconds` | 交互后延续窗口时长（秒），`0` = 关闭延续 | `120` |
| `continue_possibility` | 窗口内触发概率，`1.0` = 必回 | `1.0` |
| `continue_cooldown_seconds` | 同一成员两次延续回复的最小间隔（秒） | `10` |
| `continue_prompt_template` | 延续提示词，支持 `{message}`、`{member}`、`{sender}` 占位符 | 见下方 |

### 关键词必回

| 配置 | 说明 | 默认值 |
|------|------|--------|
| `keyword_list` | 命中即回复的关键词（如机器人昵称），留空 = 不启用 | `[]` |
| `keyword_possibility` | 命中后触发概率 | `1.0` |
| `keyword_cooldown_seconds` | 同一成员两次关键词回复的最小间隔（秒） | `8` |
| `keyword_prompt_template` | 关键词触发提示词，支持 `{message}`、`{sender}` 占位符（必回语义，无 SKIP 判定） | 见下方 |

### 其他

| 配置 | 说明 | 默认值 |
|------|------|--------|
| `ignore_when_chatting` | 对话占用守卫：有人处于延续窗口时概率路径静默 | `true` |
| `skip_marker` | 静默跳过标记，LLM 输出该标记表示判定消息不指向自己 | `[SKIP]` |

### 默认提示词

概率路径：告知 LLM「群成员【{sender}】发了一条没有 @ 你的消息」，要求**结合近期群聊记录判断指向性**——消息在跟别人聊、与你无关或群里刷屏/玩梗时只回复 `[SKIP]`（插件静默跳过，不发送）；确实适合搭话时再以当前人设自然接一句。

延续路径：告知 LLM「正在和成员【{member}】持续对话」，同样带指向性判定——这条后续消息其实是在跟群里其他人说话时只回复 `[SKIP]`；否则延续对话回应这个人。

关键词路径：告知 LLM「成员【{sender}】在消息里提到了你的名字」，直接以当前人设回应（必回，无 SKIP 判定，防止把真呼唤误判为无关）。

---

## 工作机制

```
群消息进入
   │
   ├─ @Bot / 唤醒 / 引用 Bot ──► 交回 AstrBot 主链路正常回复
   │                              （同时开启该成员的延续窗口）
   │
   ├─ 消息指向他人（@他人 / 引用他人）──► 忽略
   │
   ├─ 命中关键词 ──► 成员级冷却检查 ──► 概率抽签 ──► 回复（必回，无 SKIP 判定）
   │
   ├─ 处于延续窗口 ──► 成员级冷却检查 ──► 概率抽签 ──► LLM 指向性判定
   │                                                  ├─ 无关 ──► [SKIP] 静默放弃
   │                                                  └─ 相关 ──► 回复
   │
   └─ 走概率路径 ──► 对话占用守卫 ──► 群级冷却 ──► 概率抽签
                     ──► 内容长度/图片检查 ──► LLM 指向性判定
                                              ├─ 无关 ──► [SKIP] 静默放弃
                                              └─ 相关 ──► 回复
```

触发后，插件携带当前人格与上下文调用 `event.request_llm(...)`，回复走 AstrBot 标准 LLM 链路，并正常记入对话历史。SKIP 跳过的请求不会发送、也不会写入对话历史，群里完全无感。

### 频率控制细节

- **冷却只在真正触发时启动**：被拦截的消息不会延长冷却，不会越拦越哑
- **三层冷却互不干扰**：群级冷却只约束概率路径；延续与关键词仅受各自成员级冷却限制
- **内存自动清理**：每命中 100 次清理一次过期冷却记录，无内存泄漏风险
- **抽签在后，硬检查在前**：占用守卫、白名单、长度门槛先过滤，不浪费抽签机会

---

## 调参建议

| 目标 | 建议 |
|------|------|
| 大群保持克制 | `possibility` 保持 `0.02`，`cooldown_seconds` 保持 `180` |
| 小群更活跃 | `possibility` 调到 `0.05~0.1`，群冷却降到 `60~120` |
| 追问总是漏回 | 确认 `continue_possibility = 1.0`，窗口拉长到 `180` |
| 只想被叫名字时回 | 清空 `possibility` 路径（`0`），保留关键词必回 |
| 总在别人聊天时插话 | 确认 `ignore_when_chatting = true` |

---

## 注意事项

> [!IMPORTANT]
> 本仓库仅为 AstrBot 插件组件，需随 AstrBot 一起使用，无法独立运行。

- 必须关闭原生「群聊上下文感知 → 主动回复」，否则会双重触发
- @Bot / 唤醒前缀 / 引用 Bot 的消息由 AstrBot 主链路处理，本插件只负责「没有 @ Bot 的消息」的主动接话
- 支持 AstrBot WebUI 可视化配置（基于 `_conf_schema.json`），保存即热重载

---

## 版本历史

### v1.5.0
- 新增指向性判定（SKIP 静默跳过）：概率/延续路径触发时，LLM 结合近期群聊记录判断消息是否真的在跟你说话，无关消息自动静默跳过（不发送、不进历史），治「分不清群消息是否指向 Bot」的乱接话
- 新增关键词专用提示词模板 `keyword_prompt_template`，必回语义不变
- 新增 `skip_marker` 配置项与 `{sender}` 占位符支持

### v1.4.1
- 加个 logo：新增插件图标 `logo.png`，AstrBot WebUI 插件市场与插件列表显示自定义图标

### v1.4.0
- 修复延续漏回：延续触发概率 `0.5` → `1.0`（此前抽签会随机丢掉一半追问）
- 新增「指向他人过滤」：@ 他人 / 引用他人消息不再插话
- 新增「对话占用守卫」`ignore_when_chatting`：Bot 正在与人对话时概率路径静默

### v1.3.0
- 支持 WebUI 可视化配置与保存热重载（`_conf_schema.json`）
- 未注入配置时回退读取插件目录 `config.json`

### v1.2.1
- 延续防错乱：@ 他人或引用他人（非 Bot）的消息不再视为延续

### v1.2.0
- 新增关键词必回：命中关键词稳定触发，绕过群级冷却与概率抽签

### v1.1.0
- 新增对话延续窗口：交互后窗口期内后续消息稳定触发，追问不断片

### v1.0.0
- 首个正式版本：群级冷却、白名单、最小消息长度、防回环与提示词模板

完整变更记录见 [CHANGELOG.md](CHANGELOG.md)。

---

## 致谢

- 插件图标由 AI（Gemini）生成
- 主页排版参考 [astrbot_plugin_get_px](https://github.com/shitianyaa/astrbot_plugin_get_px) 的组织方式
- 访客计数由 [Moe Counter](https://github.com/journey-ad/Moe-Counter) 提供

---

**🌟 如果这个插件对你有帮助，请给个 Star 支持一下！**

## 许可证

[MIT](LICENSE) © Randy Lua
