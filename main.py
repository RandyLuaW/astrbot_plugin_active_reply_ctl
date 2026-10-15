# -*- coding: utf-8 -*-
"""主动回复冷却限频插件（astrbot_plugin_active_reply_ctl）

解决 AstrBot 原生主动回复「纯概率、无冷却」的两难：
- 概率高 → 活跃群刷屏；概率低 → 几乎不主动
- 本插件在原概率抽签之上增加「群级冷却」：抽中且距上次主动回复超过冷却时间才真正触发

需配合关闭原生「群聊上下文感知 → 主动回复」（active_reply.enable=false），避免双重触发。
"""

from __future__ import annotations

import json
import math
import random
import time
from pathlib import Path

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import At, Image, Reply
from astrbot.api.star import Context, Star

VERSION = "1.4.1"
LEGACY_CONFIG_NAME = "config.json"  # 旧版独立配置文件，仅在 AstrBot 未注入配置时兜底

DEFAULT_CONFIG: dict = {
    "enable": True,
    "possibility": 0.02,  # 概率抽签命中率（有冷却兜底，可适当调高）
    "cooldown_seconds": 180,  # 群级冷却：距上次主动回复 ≥ 该秒数才再触发
    "whitelist": [],  # 限定群号（空 = 不限制）
    "min_message_len": 2,  # 纯文本消息的最小长度（含图片的消息不受此限制）
    "continue_window_seconds": 120,  # 对话延续窗口：@/引用 bot 后 N 秒内，该成员后续消息稳定触发
    "continue_possibility": 1.0,  # 延续窗口内触发概率（1.0 = 必回）
    "continue_cooldown_seconds": 10,  # 延续模式成员级冷却（防个人刷屏，不影响他人、不受群级冷却限制）
    "ignore_when_chatting": True,  # 对话占用守卫：群内有人处于延续窗口内时，概率路径静默
    "keyword_list": [],  # 关键词命中即主动回复（空 = 不启用）
    "keyword_possibility": 1.0,  # 关键词命中触发概率（1.0 = 必回）
    "keyword_cooldown_seconds": 8,  # 关键词触发成员级冷却（防刷屏，不受群级冷却限制）
    "prompt_template": (
        "群聊里有一条消息（没有@你）：\n{message}\n\n"
        "请保持当前人设，自然、简短地接一句。不要客服腔、不要长篇大论。"
    ),
    "continue_prompt_template": (
        "你正在和群成员【{member}】持续对话中，这是他/她刚发来的后续消息（没有@你）：\n{message}\n\n"
        "请延续你们正在进行的对话、回应这个人。保持当前人设，简短自然。不要客服腔。"
    ),
}

CLEANUP_INTERVAL = 100  # 每命中 N 次清理一次过期冷却记录


class Main(Star):
    def __init__(self, context: Context, config: AstrBotConfig = None) -> None:
        super().__init__(context)
        self.plugin_dir = Path(__file__).parent

        # AstrBot 依据 _conf_schema.json 注入配置（WebUI 可视化编辑，保存后自动热重载本插件）
        if isinstance(config, dict) and len(config) > 0:
            cfg = config
        else:
            cfg = self._load_legacy_config()
            logger.warning(
                "[active_reply_ctl] 未收到 AstrBot 注入配置，已回退读取插件目录 config.json"
            )
        # 运行时状态（与配置无关，重载插件时随实例重建）
        self._last_reply_ts: dict[str, float] = {}
        self._last_interaction: dict[tuple[str, str], float] = {}  # (group_id, sender_id) -> ts
        self._hit_count = 0

        self._apply_config(cfg)

    def _apply_config(self, cfg: dict) -> None:
        self._enabled = bool(cfg.get("enable", True))

        try:
            p = float(cfg.get("possibility", 0.12))
            self._possibility = p if math.isfinite(p) and 0 <= p <= 1 else 0.12
        except (TypeError, ValueError):
            self._possibility = 0.12

        try:
            c = float(cfg.get("cooldown_seconds", 60))
            self._cooldown = c if math.isfinite(c) and c >= 0 else 60.0
        except (TypeError, ValueError):
            self._cooldown = 60.0

        self._whitelist = {str(x) for x in (cfg.get("whitelist") or [])}

        try:
            self._min_len = int(cfg.get("min_message_len", 2))
        except (TypeError, ValueError):
            self._min_len = 2

        self._prompt_template = str(
            cfg.get("prompt_template", DEFAULT_CONFIG["prompt_template"])
        )
        self._continue_prompt_template = str(
            cfg.get(
                "continue_prompt_template",
                DEFAULT_CONFIG["continue_prompt_template"],
            )
        )

        # 对话延续窗口
        try:
            w = float(cfg.get("continue_window_seconds", 120))
            self._continue_window = w if math.isfinite(w) and w >= 0 else 120.0
        except (TypeError, ValueError):
            self._continue_window = 120.0

        try:
            p = float(cfg.get("continue_possibility", 1.0))
            self._continue_possibility = p if math.isfinite(p) and 0 <= p <= 1 else 1.0
        except (TypeError, ValueError):
            self._continue_possibility = 1.0

        try:
            c = float(cfg.get("continue_cooldown_seconds", 10))
            self._continue_cooldown = c if math.isfinite(c) and c >= 0 else 10.0
        except (TypeError, ValueError):
            self._continue_cooldown = 10.0

        # 对话占用守卫：bot 正在群内与人对话（延续窗口激活）时，概率路径静默
        self._ignore_when_chatting = bool(cfg.get("ignore_when_chatting", True))

        # 关键词触发
        self._keywords = [
            str(k).strip() for k in (cfg.get("keyword_list") or []) if str(k).strip()
        ]
        try:
            p = float(cfg.get("keyword_possibility", 1.0))
            self._keyword_possibility = p if math.isfinite(p) and 0 <= p <= 1 else 1.0
        except (TypeError, ValueError):
            self._keyword_possibility = 1.0
        try:
            c = float(cfg.get("keyword_cooldown_seconds", 8))
            self._keyword_cooldown = c if math.isfinite(c) and c >= 0 else 8.0
        except (TypeError, ValueError):
            self._keyword_cooldown = 8.0

        logger.info(
            f"[active_reply_ctl] 插件 v{VERSION} 配置已应用｜概率={self._possibility}｜"
            f"冷却={self._cooldown}s｜延续窗口={self._continue_window}s@{self._continue_possibility}｜"
            f"延续冷却={self._continue_cooldown}s｜对话占用守卫="
            f"{'开' if self._ignore_when_chatting else '关'}｜"
            f"关键词={self._keywords or '无'}｜"
            f"{'启用' if self._enabled else '停用'}"
        )

    # ---------------- 配置 ----------------

    def _load_legacy_config(self) -> dict:
        path = self.plugin_dir / LEGACY_CONFIG_NAME
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except Exception as e:
                logger.error(f"[active_reply_ctl] config.json 解析失败: {e}")
        return dict(DEFAULT_CONFIG)

    # ---------------- 工具 ----------------

    async def _get_conversation(self, event: AstrMessageEvent):
        """获取（或新建）当前会话的 conversation，用于保持人格与历史连续性。"""
        umo = event.unified_msg_origin
        conv_mgr = self.context.conversation_manager
        try:
            cid = await conv_mgr.get_curr_conversation_id(umo)
            if not cid:
                cid = await conv_mgr.new_conversation(umo, event.get_platform_id())
            return await conv_mgr.get_conversation(umo, cid)
        except Exception:
            logger.exception("[active_reply_ctl] 获取 conversation 失败")
            return None

    @staticmethod
    def _collect_images(event: AstrMessageEvent) -> list[Image]:
        return [c for c in event.get_messages() if isinstance(c, Image)]

    @staticmethod
    def _talking_to_others(event: AstrMessageEvent, self_id: str) -> bool:
        """消息明确指向他人：@ 了他人，或引用了他人（非 bot）的消息。

        引用 bot 的消息由主链路唤醒处理（WakingCheckStage），不会进入本插件；
        sender_id 缺失时保守视为引用他人。
        """
        for c in event.get_messages():
            if isinstance(c, At):
                qq = str(getattr(c, "qq", "") or "")
                if qq not in ("", self_id):
                    return True
            elif isinstance(c, Reply):
                sender = str(getattr(c, "sender_id", "") or "")
                if sender != self_id:
                    return True
        return False

    def _group_chatting(self, gid: str, now: float) -> bool:
        """该群是否有成员处于延续窗口内（= bot 正在与人对话）。"""
        if not gid:
            return False
        return any(
            g == gid and now - ts < self._continue_window
            for (g, _), ts in self._last_interaction.items()
        )

    def _cleanup(self) -> None:
        now = time.monotonic()
        expire_after = max(600, self._cooldown * 4, self._continue_window * 2)
        expired = [
            k for k, ts in self._last_reply_ts.items() if now - ts > expire_after
        ]
        for k in expired:
            del self._last_reply_ts[k]
        expired_inter = [
            k for k, ts in self._last_interaction.items() if now - ts > expire_after
        ]
        for k in expired_inter:
            del self._last_interaction[k]

    # ---------------- 主逻辑 ----------------

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def on_group_message(self, event: AstrMessageEvent):
        """监听群消息，按「概率 + 冷却 + 对话延续窗口」决定是否主动接话。"""
        if not self._enabled:
            return

        gid = str(event.get_group_id() or "")
        sender_id = str(event.get_sender_id() or "")
        inter_key = (gid, sender_id)
        now = time.monotonic()

        # 防回环：忽略 bot 自己发出的群消息（开了"上报自身消息"也不会自触发）
        self_id = str(event.get_self_id() or "")
        if self_id and sender_id and sender_id == self_id:
            return

        # @bot / 唤醒前缀 / 引用 bot → 走正常回复链路；同时记录交互时间（开启延续窗口）
        if event.is_at_or_wake_command:
            if self._continue_window > 0 and gid:
                self._last_interaction[inter_key] = now
            return

        # 白名单过滤
        if self._whitelist:
            if gid not in self._whitelist and event.unified_msg_origin not in self._whitelist:
                return

        text = (event.message_str or "").strip()

        # 关键词判定：消息命中关键词 → 稳定触发（成员级冷却，绕过群级冷却与概率抽签）
        keyword_hit = bool(self._keywords) and any(k in text for k in self._keywords)

        # 对话延续判定：该成员刚与 bot 交互过 → 稳定触发（成员级冷却，绕过群级冷却与概率抽签）
        # 但消息明确"在跟别人说话"（@ 了他人 / 引用他人消息）时不视为延续，落回概率路径
        in_continue = False
        if self._continue_window > 0:
            last_inter = self._last_interaction.get(inter_key)
            in_continue = (
                last_inter is not None
                and now - last_inter < self._continue_window
            )
            if in_continue and self._talking_to_others(event, self_id):
                in_continue = False

        if keyword_hit:
            last_self = self._last_reply_ts.get(f"keyword:{inter_key}")
            if last_self is not None and now - last_self < self._keyword_cooldown:
                return
            possibility = self._keyword_possibility
            min_len = 1  # 关键词命中即视为有效内容
        elif in_continue:
            last_self = self._last_reply_ts.get(f"continue:{inter_key}")
            if last_self is not None and now - last_self < self._continue_cooldown:
                return
            possibility = self._continue_possibility
            min_len = 1  # 延续对话放宽：短句追问也能接上
        else:
            # 对话占用守卫：bot 正在群内与人对话时，概率路径静默（不插话无关内容）
            if self._ignore_when_chatting and self._group_chatting(gid, now):
                return
            # 明确在跟别人说话的消息不随机插话
            if self._talking_to_others(event, self_id):
                return
            possibility = self._possibility
            min_len = self._min_len

        # 概率抽签
        if random.random() >= possibility:
            return

        # 内容判断：纯文本过短且无图片 → 不触发
        images = self._collect_images(event)
        if not images and len(text) < min_len:
            return

        if keyword_hit:
            # 关键词触发：只受成员级冷却限制
            self._last_reply_ts[f"keyword:{inter_key}"] = now
        elif in_continue:
            # 延续触发：只受成员级冷却限制
            self._last_reply_ts[f"continue:{inter_key}"] = now
        else:
            # 概率触发：记录群级冷却
            umo = event.unified_msg_origin
            last = self._last_reply_ts.get(umo)
            if last is not None and now - last < self._cooldown:
                return
            self._last_reply_ts[umo] = now

        # bot 参与对话也算交互：延续用户的后续追问
        if self._continue_window > 0 and gid:
            self._last_interaction[inter_key] = now

        self._hit_count += 1
        if self._hit_count % CLEANUP_INTERVAL == 0:
            self._cleanup()

        conversation = await self._get_conversation(event)

        if in_continue:
            template = self._continue_prompt_template
        else:
            template = self._prompt_template

        if "{message}" in template:
            prompt = template.replace("{message}", text)
        else:
            prompt = text
        if in_continue and "{member}" in prompt:
            member_name = str(event.get_sender_name() or sender_id or "群成员")
            prompt = prompt.replace("{member}", member_name)

        image_urls: list[str] = []
        for img in images:
            try:
                image_urls.append(await img.convert_to_file_path())
            except Exception:
                logger.exception("[active_reply_ctl] 处理图片失败")

        mode = "关键词" if keyword_hit else ("延续对话" if in_continue else "主动回复")
        logger.info(
            f"[active_reply_ctl] #{self._hit_count} {mode}触发｜群={gid}｜成员={sender_id}"
        )
        yield event.request_llm(
            prompt=prompt,
            image_urls=image_urls,
            conversation=conversation,
        )
