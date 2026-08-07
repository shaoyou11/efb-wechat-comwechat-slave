import logging, tempfile
import time
import threading
from lxml import etree
from traceback import print_exc
from pydub import AudioSegment
import os
import base64
from pathlib import Path
from xml.sax.saxutils import escape

import re
import json
from ehforwarderbot.chat import (
    SystemChat,
    PrivateChat,
    GroupChat,
    SystemChatMember,
    ChatMember,
    SelfChatMember,
)
import hashlib
from typing import Tuple, Optional, Collection, BinaryIO, Dict, Any , Union , List
from datetime import datetime
from cachetools import TTLCache

from ehforwarderbot import MsgType, Chat, Message, Status, coordinator
from wechatrobot import WeChatRobot

from . import __version__ as version

from ehforwarderbot.channel import SlaveChannel
from ehforwarderbot.types import MessageID, ChatID, InstanceID
from ehforwarderbot import utils as efb_utils
from ehforwarderbot.exceptions import EFBException, EFBChatNotFound, EFBMessageError
from ehforwarderbot.message import MessageCommand, MessageCommands
from ehforwarderbot.status import MessageRemoval, ChatUpdates

from .ChatMgr import ChatMgr
from .CustomTypes import EFBGroupChat, EFBPrivateChat, EFBGroupMember, EFBSystemUser
from .MsgDeco import qutoed_text
from .MsgProcess import MsgProcess, MsgWrapper
from .Utils import download_file , load_config , load_temp_file_to_local , WC_EMOTICON_CONVERSION
from .db import DatabaseManager
from .Constant import QUOTE_MESSAGE
from .offline_notification import OfflineNotificationPolicy
from .offline_trigger import notify_watchdog
from .login_confirmation import LoginConfirmation, login_confirmation_message
from .contact_display import (
    extract_mentioned_alias,
    resolve_contact_name,
    update_existing_chat_name,
)
from .command_validation import chatroom_member_ids, group_command_error
from .media_recovery import (
    cdn_media_path,
    is_historical_media,
    media_wait_timeout,
    observe_media_file_size,
    should_request_original_media,
    should_use_historical_fallback,
    should_use_thumbnail,
)
from .sent_message import should_ignore_sent_msg
from .pending_files import (
    PendingFileStore,
    build_pending_file_record,
    delivery_confirmed,
)
from .login_qr import LoginQrStore, select_revoke_uids
from .member_avatar_marker import MemberAvatarMarkerStore

from rich.console import Console
from rich import print as rprint
from io import BytesIO
from PIL import Image


OFFLINE_LOGIN_NOTICE = (
    "检测到微信未登录，请发送 /login 获取登录二维码，或发送 /wechat "
    "打开微信管理"
)


class ComWeChatChannel(SlaveChannel):
    channel_name : str = "ComWechatChannel"
    channel_emoji : str = "💻"
    channel_id : str = "honus.comwechat"

    bot : WeChatRobot = None
    config : Dict = {}

    friends : EFBPrivateChat = []
    groups : EFBGroupChat    = []

    contacts : Dict = {}            # {wxid : {alias : str , remark : str, nickname : str , type : int}} -> {wxid : name(after handle)}
    nicknames : Dict = {}
    group_members : Dict = {}       # {"group_id" : { "wxID" : "displayName"}}

    time_out : int = 120
    cache =  TTLCache(maxsize=200, ttl= time_out)  # 缓存发送过的消息ID
    file_msg : Dict = {}                           # 存储待修改的文件类消息 {path : msg}
    delete_file : Dict = {}                        # 存储待删除的消息 {path : time}
    forward_pattern = r"ehforwarderbot:\/\/([^/]+)\/forward\/(\d+)"

    __version__ = version.__version__
    logger: logging.Logger = logging.getLogger("comwechat")
    logger.setLevel(logging.DEBUG)

    #MsgType.Voice
    supported_message_types = {MsgType.Text, MsgType.Sticker, MsgType.Image , MsgType.Link , MsgType.File , MsgType.Video , MsgType.Animation, MsgType.Voice}
    self_update_lock = threading.Lock()
    contact_update_lock = threading.Lock()
    group_update_lock = threading.Lock()

    def __init__(self, instance_id: InstanceID = None):
        super().__init__(instance_id=instance_id)
        self.logger.info("ComWeChat Slave Channel initialized.")
        self.logger.info("Version: %s" % self.__version__)
        config_path = efb_utils.get_config_path(self.channel_id)
        self.config = load_config(config_path)
        self.db: DatabaseManager = DatabaseManager(self)
        self.bot = WeChatRobot()
        self.login_confirmation = LoginConfirmation()
        self.started_at = int(time.time())
        self.historical_media_notice_sent = False
        self.cache = TTLCache(maxsize=200, ttl=self.time_out)
        self.file_msg = {}
        self.file_retry_at = {}
        self.pending_file_store = PendingFileStore(
            Path(config_path).parent / "pending-files.json"
        )
        self.login_qr_store = LoginQrStore(
            Path(config_path).parent / "login-qrcodes.json"
        )
        self.member_avatar_markers = MemberAvatarMarkerStore(
            Path(config_path).parent / "member-avatar-markers.json",
            enabled=self.config.get("member_avatar_markers", True),
        )
        self.login_qr_ttl_seconds = max(
            30, int(self.config.get("login_qrcode_ttl_seconds", 180))
        )
        self.login_qr_lock = threading.RLock()
        self.watchdog_recovery_success_path = Path(
            os.getenv(
                "WATCHDOG_RECOVERY_SUCCESS_PATH",
                "/data/watchdog/state/auto-recovery-success.json",
            )
        )
        self.watchdog_recovery_lock = threading.RLock()
        self.delete_file = {}

        self.wxid = None
        self.base_path = self.config["base_path"] if "base_path" in self.config else self.bot.get_base_path()
        self.load()
        self.dir = self.config["dir"]
        if not self.dir.endswith(os.path.sep):
            self.dir += os.path.sep
        ChatMgr.slave_channel = self
        self.user_auth_chat = ChatMgr.build_efb_chat_as_system_user(EFBSystemUser(
            uid = self.channel_name,
            name = self.channel_name,
        ))
        self.restore_pending_file_messages()

        def update_contacts_wrapper(func):
            def wrapper(msg):
                if self.wxid is None:
                    if self.confirm_login():
                        return func(msg)
                else:
                    return func(msg)
            return wrapper

        @self.bot.on("self_msg")
        @update_contacts_wrapper
        def on_self_msg(msg : Dict):
            self.logger.debug(f"self_msg:{msg}")
            sender = msg["sender"]

            name = self.get_name_by_wxid(sender)

            if "@chatroom" in sender:
                chat = ChatMgr.build_efb_chat_as_group(EFBGroupChat(
                    uid = sender,
                    name = name,
                ))
                author = chat.self
                self.extract_alias(msg)
            else:
                chat = ChatMgr.build_efb_chat_as_private(EFBPrivateChat(
                    uid = sender,
                    name = name,
                ))
                if sender.startswith('gh_'):
                    chat.vendor_specific = {'is_mp' : True}
                author = chat.self

            self.handle_msg(msg , author , chat)

        @self.bot.on("sent_msg")
        def on_sent_msg(msg: Dict):
            if should_ignore_sent_msg(msg):
                self.logger.debug(
                    "忽略微信电脑端发送回环消息: msgid=%s",
                    msg.get("msgid"),
                )

        @self.bot.on("friend_msg")
        @update_contacts_wrapper
        def on_friend_msg(msg : Dict):
            self.logger.debug(f"friend_msg:{msg}")

            sender = msg['sender']

            if msg["type"] == "eventnotify":
                return

            name = self.get_name_by_wxid(sender)

            chat = ChatMgr.build_efb_chat_as_private(EFBPrivateChat(
                    uid= sender,
                    name= name,
            ))
            if sender.startswith('gh_'):
                chat.vendor_specific = {'is_mp' : True}
                self.logger.debug(f'modified_chat:{chat}')
            author = chat.other
            self.handle_msg(msg, author, chat)

        @self.bot.on("group_msg")
        @update_contacts_wrapper
        def on_group_msg(msg : Dict):
            self.logger.debug(f"group_msg:{msg}")
            sender = msg["sender"]
            wxid  =  msg["wxid"]

            chatname = self.get_name_by_wxid(sender)

            chat = ChatMgr.build_efb_chat_as_group(EFBGroupChat(
                uid = sender,
                name = chatname,
            ))

            try:
                name = self.contacts[wxid]
            except:
                name = wxid
            self.extract_alias(msg)
            alias = self.group_members.get(sender,{}).get(wxid , None)
            if alias == self.nicknames.get(wxid, None):
                alias = None

            author = ChatMgr.build_efb_chat_as_member(chat, EFBGroupMember(
                uid = wxid,
                name = name,
                alias = alias
            ))
            self.handle_msg(msg, author, chat)

        @self.bot.on("revoke_msg")
        @update_contacts_wrapper
        def on_revoked_msg(msg : Dict):
            self.logger.debug(f"revoke_msg:{msg}")
            sender = msg["sender"]
            if "@chatroom" in sender:
                wxid  =  msg["wxid"]

            name = self.get_name_by_wxid(sender)

            if "@chatroom" in sender:
                chat = ChatMgr.build_efb_chat_as_group(EFBGroupChat(
                    uid = sender,
                    name = name,
                ))
                xml = etree.fromstring(msg["message"])
                text = xml.xpath('string(/sysmsg/revokemsg/replacemsg)')
                alias = re.search(r'^"(.*?)" (撤回了一条消息|recalled a message)$', text)
                if alias and alias.group(1) != self.get_nickname_by_wxid(wxid):
                    self.merge_group_members(sender, {
                        wxid: alias.group(1)
                    })
            else:
                chat = ChatMgr.build_efb_chat_as_private(EFBPrivateChat(
                    uid = sender,
                    name = name,
                ))

            newmsgid = re.search("<newmsgid>(.*?)<\/newmsgid>", msg["message"]).group(1)

            efb_msg = Message(chat = chat , uid = newmsgid)
            coordinator.send_status(
                MessageRemoval(source_channel=self, destination_channel=coordinator.master, message=efb_msg)
            )

        @self.bot.on("transfer_msg")
        @update_contacts_wrapper
        def on_transfer_msg(msg : Dict):
            self.logger.debug(f"transfer_msg:{msg}")
            sender = msg["sender"]
            name = self.get_name_by_wxid(sender)

            if msg["isSendMsg"]:
                if msg["isSendByPhone"]:
                    chat = ChatMgr.build_efb_chat_as_private(EFBPrivateChat(
                            uid= sender,
                            name= name,
                    ))
                    author = chat.other
                    self.handle_msg(msg, author, chat)
                    return

            content = {}

            money = re.search("收到转账(.*)元", msg["message"]).group(1)
            transcationid = re.search("<transcationid><!\[CDATA\[(.*)\]\]><\/transcationid>", msg["message"]).group(1)
            transferid = re.search("<transferid><!\[CDATA\[(.*)\]\]><\/transferid>", msg["message"]).group(1)
            text = (
                f"收到 {name} 转账:\n"
                f"金额为 {money} 元\n"
            )

            commands = [
                MessageCommand(
                    name=("Accept"),
                    callable_name="process_transfer",
                    kwargs={"transcationid" : transcationid , "transferid" : transferid , "wxid" : sender},
                )
            ]

            content["sender"] = sender
            content["message"] = text
            content["commands"] = commands
            content["name"] = name
            self.system_msg(content)

        @self.bot.on("frdver_msg")
        @update_contacts_wrapper
        def on_frdver_msg(msg : Dict):
            self.logger.debug(f"frdver_msg:{msg}")
            content = {}
            sender = msg["sender"]
            fromnickname = re.search('fromnickname="(.*?)"', msg["message"]).group(1)
            apply_content = re.search('content="(.*?)"', msg["message"]).group(1)
            url = re.search('bigheadimgurl="(.*?)"', msg["message"]).group(1)
            v3 = re.search('encryptusername="(v3.*?)"', msg["message"]).group(1)
            v4 = re.search('ticket="(v4.*?)"', msg["message"]).group(1)
            text = (
                "好友申请:\n"
                f"名字: {fromnickname}\n"
                f"验证内容: {apply_content}\n"
                f"头像: {url}"
            )

            commands = [
                MessageCommand(
                    name=("Accept"),
                    callable_name="process_friend_request",
                    kwargs={"v3" : v3 , "v4" : v4},
                )
            ]

            content["sender"] = sender
            content["message"] = text
            content["commands"] = commands
            self.system_msg(content)

        @self.bot.on("card_msg")
        @update_contacts_wrapper
        def on_card_msg(msg : Dict):
            self.logger.debug(f"card_msg:{msg}")
            sender = msg["sender"]
            wxid = msg["wxid"]
            content = {}
            name = self.get_name_by_wxid(sender)

            bigheadimgurl = re.search('bigheadimgurl="(.*?)"', msg["message"]).group(1)
            nickname = re.search('nickname="(.*?)"', msg["message"]).group(1)
            province = re.search('province="(.*?)"', msg["message"]).group(1)
            city = re.search('city="(.*?)"', msg["message"]).group(1)
            sex = re.search('sex="(.*?)"', msg["message"]).group(1)
            username = re.search('username="(.*?)"', msg["message"]).group(1)

            text = "名片信息:\n"
            if nickname:
                text += f"昵称: {nickname}\n"
            if city:
                text += f"城市: {city}\n"
            if province:
                text += f"省份: {province}\n"
            if sex:
                if sex == "0":
                    text += "性别: 未知\n"
                elif sex == "1":
                    text += "性别: 男\n"
                elif sex == "2":
                    text += "性别: 女\n"
            if bigheadimgurl:
                text += f"头像: {bigheadimgurl}\n"

            commands = [
                MessageCommand(
                    name=("Add To Friend"),
                    callable_name="add_friend",
                    kwargs={"v3" : username},
                )
            ]

            if "@chatroom" in sender:
                chat = ChatMgr.build_efb_chat_as_group(EFBGroupChat(
                    uid = sender,
                    name = self.get_name_by_wxid(sender)
                ))
                if sender == wxid:
                    author = chat.self
                else:
                    alias = self.group_members.get(sender,{}).get(wxid , None),
                    alias = None if alias == name else alias
                    author = ChatMgr.build_efb_chat_as_member(chat, EFBGroupMember(
                        uid = wxid,
                        name = name,
                        alias = alias
                    ))
            else:
                chat = ChatMgr.build_efb_chat_as_private(EFBPrivateChat(
                    uid = sender,
                    name = name,
                ))
                author = chat.self if sender == self.wxid else chat.other
                if sender.startswith('gh_'):
                    chat.vendor_specific = {'is_mp' : True}

            # if "v3" in username:
            #     content["commands"] = commands
            # 暂时屏蔽
            m = Message(
                type=MsgType.Text,
                text=text
            )
            self.send_efb_msgs(MsgWrapper(msg, m), author=author, chat=chat, uid=MessageID(str(msg['msgid'])))

    def is_login(self) -> bool:
        try:
            response = self.bot.IsLoginIn()
            return response.get("is_login", 0) == 1
        except:
            return False

    def get_qrcode(self):
        result = self.bot.GetQrcodeImage()
        
        # 检查是否返回了 JSON 数据（已登录）
        try:
            json_result = json.loads(result)
            return None
        except Exception:
            return self.save_qr_code(result)

    @staticmethod
    def save_qr_code(qr_code):
        # 创建临时文件保存二维码图片
        tmp_file = tempfile.NamedTemporaryFile(suffix='.png')
        try:
            tmp_file.write(qr_code)
            tmp_file.flush()
        except:
            print("[red]获取二维码失败[/red]")
            tmp_file.close()
            return None
        return tmp_file

    def confirm_login(self):
        return self.login_confirmation.run(
            is_confirmed=lambda: self.wxid is not None,
            confirm=self._confirm_login,
        )

    def _confirm_login(self):
        chat = self.user_auth_chat
        author = self.user_auth_chat.other
        msg = Message(
            type=MsgType.Text,
            uid=MessageID(str(int(time.time()))),
        )
        has_pending_qr = bool(self.login_qr_store.records())
        if self.is_login():
            self.after_login()
            auto_recovery = self.announce_watchdog_recovery_success()
            if auto_recovery:
                msg.text = None
            else:
                msg.text = login_confirmation_message(
                    logged_in=True,
                    has_pending_qr=has_pending_qr,
                )
            if msg.text:
                self.send_efb_msgs(msg, chat=chat, author=author)
            result = True
        else:
            if not has_pending_qr:
                return False
            self.revoke_login_qrcodes(completed=True)
            msg.text = login_confirmation_message(
                logged_in=False,
                has_pending_qr=True,
            )
            self.send_efb_msgs(msg, chat=chat, author=author)
            result = False
        return result

    def _send_login_confirmation(self, text: str):
        msg = Message(
            type=MsgType.Text,
            uid=MessageID(f"login-{time.time_ns()}"),
        )
        msg.text = text
        self.send_efb_msgs(
            msg,
            chat=self.user_auth_chat,
            author=self.user_auth_chat.other,
        )

    def _remove_watchdog_recovery_success(self):
        try:
            self.watchdog_recovery_success_path.unlink(missing_ok=True)
        except OSError as error:
            self.logger.warning("删除 watchdog 恢复标记失败: %s", error)

    def announce_watchdog_recovery_success(self) -> bool:
        with self.watchdog_recovery_lock:
            try:
                payload = json.loads(
                    self.watchdog_recovery_success_path.read_text(
                        encoding="utf-8"
                    )
                )
            except FileNotFoundError:
                return False
            except (OSError, ValueError, TypeError) as error:
                self.logger.warning("读取 watchdog 恢复标记失败: %s", error)
                return False

            if not isinstance(payload, dict):
                self._remove_watchdog_recovery_success()
                return False
            if payload.get("version") != 1:
                self._remove_watchdog_recovery_success()
                return False
            if payload.get("source") not in {"event", "night"}:
                self._remove_watchdog_recovery_success()
                return False
            try:
                age = time.time() - float(payload["created_at"])
            except (KeyError, TypeError, ValueError):
                self._remove_watchdog_recovery_success()
                return False
            if not 0 <= age <= 15 * 60:
                self.logger.info("忽略过期的 watchdog 恢复标记")
                self._remove_watchdog_recovery_success()
                return False

            text = login_confirmation_message(
                logged_in=True,
                has_pending_qr=False,
                auto_recovery=True,
            )
            if text:
                try:
                    self._send_login_confirmation(text)
                except Exception as error:
                    self.logger.warning(
                        "发送 watchdog 登录成功通知失败，保留恢复标记: %s",
                        error,
                    )
                    return False
            self._remove_watchdog_recovery_success()
            return bool(text)

    def after_login(self):
        self.revoke_login_qrcodes(completed=True)
        self.get_me()
        self.GetContactListBySql()
        self.GetGroupListBySql()
        master = getattr(coordinator, "master", None)
        cleanup = getattr(master, "cleanup_same_day_offline_notices", None)
        if callable(cleanup):
            try:
                removed = cleanup()
                if removed:
                    self.logger.info("登录成功后清理当天微信未登录提醒: %s 条", removed)
            except Exception as error:
                self.logger.warning("清理当天微信未登录提醒失败: %s", error)

    def revoke_login_qrcodes(self, completed=False):
        if getattr(coordinator, "master", None) is None:
            return 0
        with self.login_qr_lock:
            uids = select_revoke_uids(
                self.login_qr_store.records(),
                now=int(time.time()),
                ttl_seconds=self.login_qr_ttl_seconds,
                completed=completed,
            )
            removed = 0
            for uid in uids:
                message = Message(
                    type=MsgType.Image,
                    uid=MessageID(uid),
                    chat=self.user_auth_chat,
                    author=self.user_auth_chat.other,
                )
                try:
                    coordinator.send_status(
                        MessageRemoval(
                            source_channel=self,
                            destination_channel=coordinator.master,
                            message=message,
                        )
                    )
                except Exception as error:
                    self.logger.warning("登录二维码收回失败，稍后重试: %s", error)
                    continue
                self.login_qr_store.remove(uid)
                removed += 1
            return removed

    @efb_utils.extra(name="重新扫码登录",
           desc="重新扫码登录")
    def reauth(self, _: str = "") -> str:
        self.revoke_login_qrcodes(completed=True)
        file = self.get_qrcode()
        chat = self.user_auth_chat
        author = self.user_auth_chat.other
        msg = Message(
            type=MsgType.Text,
            uid=MessageID(f"login-qr-{time.time_ns()}"),
        )

        if not file:
            if self.is_login():
                self.after_login()
                return "登录成功"
            else:
                return "获取二维码失败，请稍后再试"
        else:
            msg.type = MsgType.Image
            msg.path = Path(file.name)
            msg.file = file
            msg.mime = 'image/png'
            self.send_efb_msgs(msg, chat=chat, author=author)
            self.login_qr_store.add(msg.uid, created_at=int(time.time()))
        return "请扫描二维码登录"

    @efb_utils.extra(name="强制退出微信",
           desc="强制退出")
    def force_logout(self, _: str = "") -> str:
        res = self.bot.post(44, params=EmptyJsonResponse())
        if self.is_login():
            return "退出失败，原因: %s" % res
        else:
            self.wxid = None
            return "退出成功"

    @staticmethod
    def send_efb_msgs(efb_msgs: Union[Message, List[Message]], **kwargs):
        if not efb_msgs:
            return []
        efb_msgs = [efb_msgs] if isinstance(efb_msgs, Message) else efb_msgs
        if 'deliver_to' not in kwargs:
            kwargs['deliver_to'] = coordinator.master
        results = []
        for efb_msg in efb_msgs:
            for k, v in kwargs.items():
                setattr(efb_msg, k, v)
            try:
                results.append(coordinator.send_message(efb_msg))
            finally:
                if efb_msg.file:
                    efb_msg.file.close()
        return results

    def queue_file_message(self, path, msg, author, chat):
        record = build_pending_file_record(
            msg=msg,
            author=author,
            chat=chat,
            chat_kind="group" if isinstance(chat, GroupChat) else "private",
        )
        self.pending_file_store.put(path, record)
        self.file_msg[path] = (msg, author, chat)
        self.logger.info(
            "文件已进入持久待发队列: msgid=%s path=%s",
            msg.get("msgid"),
            path,
        )

    def request_pending_file_delivery(self, path):
        """Allow the EFB operations panel to release one pending attachment."""
        path = str(path)
        pending = self.file_msg.get(path)
        if pending is None:
            return "not_found"
        try:
            if not os.path.isfile(path) or os.path.getsize(path) <= 0:
                return "not_ready"
        except OSError:
            return "not_ready"
        msg = pending[0]
        msg["wait_for_stable_media"] = False
        msg.pop("_media_observed_size", None)
        msg.pop("_media_stable_since", None)
        self.file_retry_at[path] = 0
        self.logger.info("手动释放待发文件: path=%s", path)
        return "queued"

    def remove_pending_file(self, path):
        """Remove one pending attachment from memory and its durable index."""
        path = str(path)
        if self.file_msg.pop(path, None) is None:
            return "not_found"
        self.file_retry_at.pop(path, None)
        self.pending_file_store.remove(path)
        self.logger.info("手动删除待发文件记录: path=%s", path)
        return "removed"

    def restore_pending_file_messages(self):
        restored = 0
        for path, record in self.pending_file_store.items():
            try:
                msg = record["msg"]
                msg["timestamp"] = int(time.time())
                if record.get("chat_kind") == "group":
                    chat = ChatMgr.build_efb_chat_as_group(EFBGroupChat(
                        uid=record["chat_uid"],
                        name=record["chat_name"],
                    ))
                    author = ChatMgr.build_efb_chat_as_member(chat, EFBGroupMember(
                        uid=record["author_uid"],
                        name=record.get("author_name") or record["author_uid"],
                        alias=record.get("author_alias"),
                    ))
                else:
                    chat = ChatMgr.build_efb_chat_as_private(EFBPrivateChat(
                        uid=record["chat_uid"],
                        name=record["chat_name"],
                    ))
                    author = chat.other
                self.file_msg[path] = (msg, author, chat)
                restored += 1
            except Exception:
                self.logger.exception("恢复待发文件失败: path=%s", path)
        if restored:
            self.logger.warning("已恢复 %s 个持久待发文件。", restored)

    def system_msg(self, content : Dict):
        self.logger.debug(f"system_msg:{content}")
        msg = Message()
        sender = content["sender"]
        if "name" in content:
            name = content["name"]
        else:
            name  = '\u2139 System'

        chat = ChatMgr.build_efb_chat_as_system_user(EFBSystemUser(
            uid = sender,
            name = name
        ))

        try:
            author = chat.get_member(SystemChatMember.SYSTEM_ID)
        except KeyError:
            author = chat.add_system_member()

        if content.get("message") == OFFLINE_LOGIN_NOTICE:
            msg.commands = MessageCommands([
                MessageCommand("关闭提醒", "__delete_message__"),
            ])
        elif "commands" in content:
            msg.commands = MessageCommands(content["commands"])
        if "message" in content:
            msg.text = content['message']
        if "target" in content:
            msg.target = content['target']

        self.send_efb_msgs(msg, uid=int(time.time()), chat=chat, author=author, type=MsgType.Text)

    def handle_msg(self , msg : Dict[str, Any] , author : 'ChatMember' , chat : 'Chat'):
        if chat.uid.endswith("@chatroom") and author.uid != self.wxid:
            marker = self.member_avatar_markers.marker_for(
                author.uid,
                self._load_member_avatar,
            )
            if marker:
                vendor_specific = dict(getattr(author, "vendor_specific", {}) or {})
                vendor_specific["avatar_color_marker"] = marker
                author.vendor_specific = vendor_specific
        emojiList = re.findall('\[[\w|！|!| ]+\]' , msg["message"])
        for emoji in emojiList:
            try:
                msg["message"] = msg["message"].replace(emoji, WC_EMOTICON_CONVERSION[emoji])
            except:
                pass

        if self.cache.get(msg["msgid"]) == msg["type"]:
            return

        try:
            original_timestamp = msg.get("timestamp")
            force_original_historical = (
                self.config.get("force_original_media_download", True)
                and self.config.get(
                    "force_original_historical_media_download",
                    True,
                )
            )
            if (
                self.config.get("force_original_media_download", True)
                and should_request_original_media(
                    msg["type"],
                    original_timestamp,
                    self.started_at,
                    allow_historical=force_original_historical,
                )
            ):
                try:
                    result = self.bot.GetCdn(msgid=int(msg["msgid"]))
                    original_path = cdn_media_path(result, self.dir)
                    if original_path:
                        msg["timestamp"] = int(time.time())
                        msg["historical_media"] = False
                        msg["wait_for_stable_media"] = True
                        msg["force_send_as_file"] = msg["type"] == "image"
                        msg["filepath"] = original_path
                        self.queue_file_message(original_path, msg, author, chat)
                        self.cache[msg["msgid"]] = msg["type"]
                        self.logger.info(
                            "已触发原始媒体下载: type=%s msgid=%s",
                            msg["type"],
                            msg["msgid"],
                        )
                        return
                except Exception as e:
                    self.logger.warning(
                        "触发原始媒体下载失败，将使用现有附件流程: "
                        "type=%s msgid=%s reason=%s",
                        msg["type"],
                        msg["msgid"],
                        e,
                    )

            if ("FileStorage" in msg["filepath"]) and ("Cache" not in msg["filepath"]):
                msg["timestamp"] = int(time.time())
                msg["historical_media"] = (
                    should_use_historical_fallback(
                        msg["type"],
                        original_timestamp,
                        self.started_at,
                        force_original_retry=force_original_historical,
                    )
                )
                msg["filepath"] = msg["filepath"].replace("\\","/")
                msg["filepath"] = f'''{self.dir}{msg["filepath"]}'''
                self.queue_file_message(msg["filepath"], msg, author, chat)
                self.cache[msg["msgid"]] = msg["type"]
                return
            if msg["type"] == "video":
                msg["timestamp"] = int(time.time())
                msg["filepath"] = msg["thumb_path"].replace("\\","/").replace(".jpg", ".mp4")
                msg["filepath"] = f'''{self.dir}{msg["filepath"]}'''
                self.queue_file_message(msg["filepath"], msg, author, chat)
                self.cache[msg["msgid"]] = msg["type"]
                return
        except Exception:
            if msg.get("type") in ("image", "video", "voice", "share"):
                self.logger.exception(
                    "附件进入持久队列失败，交由 Bridge 延迟重试: "
                    "type=%s msgid=%s",
                    msg.get("type"),
                    msg.get("msgid"),
                )
                raise

        if msg["type"] == "voice":
            file_path = re.search("clientmsgid=\"(.*?)\"", msg["message"]).group(1) + ".amr"
            original_timestamp = msg.get("timestamp")
            msg["timestamp"] = int(time.time())
            msg["historical_media"] = is_historical_media(
                original_timestamp,
                self.started_at,
            )
            msg["filepath"] = f'''{self.dir}{msg["self"]}/{file_path}'''
            self.queue_file_message(msg["filepath"], msg, author, chat)
            self.cache[msg["msgid"]] = msg["type"]
            return

        self.send_efb_msgs(MsgWrapper(msg, MsgProcess(msg, chat)), author=author, chat=chat, uid=MessageID(str(msg['msgid'])))
        self.cache[msg["msgid"]] = msg["type"]

    def handle_file_msg(self):
        while True:
            if len(self.file_msg) == 0:
                time.sleep(1)
            else:
                for path in list(self.file_msg.keys()):
                    if time.time() < self.file_retry_at.get(path, 0):
                        continue
                    flag = False
                    should_send = True
                    pending = self.file_msg.get(path)
                    if pending is None:
                        continue
                    msg = pending[0]
                    author = pending[1]
                    chat = pending[2]
                    thumb_path = ""
                    if msg["type"] == "image" and msg.get("thumb_path"):
                        thumb_path = msg["thumb_path"].replace("\\", "/")
                        thumb_path = f"{self.dir}{thumb_path}"
                    full_image_exists = os.path.exists(path)
                    full_media_ready = full_image_exists
                    if full_image_exists and msg.get("wait_for_stable_media"):
                        try:
                            (
                                full_media_ready,
                                observed_size,
                                stable_since,
                            ) = observe_media_file_size(
                                current_size=os.path.getsize(path),
                                previous_size=msg.get("_media_observed_size"),
                                stable_since=msg.get("_media_stable_since"),
                                now=time.monotonic(),
                            )
                            msg["_media_observed_size"] = observed_size
                            msg["_media_stable_since"] = stable_since
                        except OSError:
                            full_media_ready = False
                    thumbnail_exists = bool(
                        thumb_path and os.path.exists(thumb_path)
                    )
                    elapsed_seconds = int(time.time()) - msg["timestamp"]
                    timeout_seconds = media_wait_timeout(
                        msg.get("historical_media", False)
                    )
                    if full_media_ready:
                        flag = True
                    elif should_use_thumbnail(
                        full_image_exists,
                        thumbnail_exists,
                        elapsed_seconds,
                        timeout_seconds,
                    ):
                        msg["filepath"] = thumb_path
                        flag = True
                    elif elapsed_seconds >= timeout_seconds:
                        msg_type = msg["type"]
                        if msg.get("historical_media", False):
                            if self.historical_media_notice_sent:
                                should_send = False
                            else:
                                msg["message"] = (
                                    "[EFB 重启后检测到历史图片或语音附件已失效，"
                                    "后续重复提示已自动省略，请在手机端查看]"
                                )
                                msg["type"] = "text"
                                self.historical_media_notice_sent = True
                        else:
                            msg['message'] = f"[{msg_type} 下载超时,请在手机端查看]"
                            msg["type"] = "text"
                        flag = True
                    elif msg["type"] == "voice":
                        sql = f'SELECT Buf FROM Media WHERE Reserved0 = {msg["msgid"]}'
                        dbresult = self.bot.QueryDatabase(db_handle=self.bot.GetDBHandle("MediaMSG0.db"), sql=sql)["data"]
                        if len(dbresult) == 2:
                            filebuffer = dbresult[1][0]
                            decoded = bytes(base64.b64decode(filebuffer))
                            with open(msg["filepath"], 'wb') as f:
                                f.write(decoded)
                            f.close()
                            flag = True

                    if flag:
                        if not should_send:
                            self.file_msg.pop(path, None)
                            self.file_retry_at.pop(path, None)
                            self.pending_file_store.remove(path)
                            continue
                        try:
                            msg.pop("_media_observed_size", None)
                            msg.pop("_media_stable_since", None)
                            msg.pop("wait_for_stable_media", None)
                            results = self.send_efb_msgs(
                                MsgWrapper(msg, MsgProcess(msg, chat)),
                                author=author,
                                chat=chat,
                                uid=MessageID(str(msg["msgid"])),
                            )
                            if not delivery_confirmed(results):
                                raise EFBMessageError("Telegram 未返回投递确认")
                        except Exception:
                            self.file_retry_at[path] = time.time() + 30
                            self.logger.exception(
                                "文件投递未确认，30 秒后重试: msgid=%s path=%s",
                                msg.get("msgid"),
                                path,
                            )
                        else:
                            self.file_msg.pop(path, None)
                            self.file_retry_at.pop(path, None)
                            self.pending_file_store.remove(path)
                            status = (
                                getattr(results[0], "vendor_specific", {})
                                .get("telegram_delivery_status")
                            )
                            self.logger.info(
                                "文件投递已确认: msgid=%s status=%s",
                                msg.get("msgid"),
                                status,
                            )

                time.sleep(0.1)

            if len(self.delete_file):
                for k in list(self.delete_file.keys()):
                    file_path = k
                    begin_time = self.delete_file[k]
                    if  (int(time.time()) - begin_time) > self.time_out:
                        try:
                            os.remove(file_path)
                        except:
                            pass
                        del self.delete_file[file_path]

    def process_friend_request(self , v3 , v4):
        self.logger.debug(f"process_friend_request:{v3} {v4}")
        res = self.bot.VerifyApply(v3 = v3 , v4 = v4)
        if str(res['msg']) != "0":
            return "Success"
        else:
            return "Failed"

    def process_transfer(self, transcationid , transferid , wxid):
        res = self.bot.GetTransfer(transcationid = transcationid , transferid = transferid , wxid = wxid)
        if str(res["msg"]) != "0":
            return "Success"
        else:
            return "Failed"

    def add_friend(self , v3):
        res = self.bot.AddContactByV3(v3 = v3 , msg = "")
        if str(res['msg']) != "0":
            return "Success"
        else:
            return "Failed"

    # 定时任务
    def scheduled_job(self):
        count = 0
        offline_notification = OfflineNotificationPolicy(interval_seconds=8 * 60 * 60)
        content = {
            "name": self.channel_name,
            "sender": self.channel_name,
            "message": "检测到微信未登录，请发送 /login 获取登录二维码，或发送 /wechat 打开微信管理",
        }
        while True:
            time.sleep(1)
            count += 1
            if count % 1800 == 0:
                if self.wxid is not None:
                    self.GetGroupListBySql()
                    self.GetContactListBySql()
            if count % 10 == 3 and getattr(coordinator, 'master', None) is not None:
                logged_in = self.is_login()
                login_transition = offline_notification.observe_login_transition(
                    logged_in
                )
                self.revoke_login_qrcodes(completed=logged_in)
                auto_recovery_announced = False
                if logged_in and self.watchdog_recovery_success_path.exists():
                    self.after_login()
                    auto_recovery_announced = self.announce_watchdog_recovery_success()
                if (
                    login_transition
                    and self.wxid is None
                    and not auto_recovery_announced
                    and not self.watchdog_recovery_success_path.exists()
                ):
                    self.after_login()
                    self._send_login_confirmation("登录成功")
                if offline_notification.observe(logged_in, time.monotonic()):
                    self.wxid = None
                    try:
                        notify_watchdog()
                    except Exception as error:
                        self.logger.warning("Unable to trigger login watchdog: %s", error)
                    self.system_msg(content)

    #获取全部联系人
    def get_chats(self) -> Collection['Chat']:
        return list(self.friends) + list(self.groups)

    #获取联系人
    def get_chat(self, chat_uid: ChatID) -> 'Chat':
        if "@chatroom" in chat_uid:
            for group in self.groups:
                if group.uid == chat_uid:
                    return group
        else:
            for friend in self.friends:
                if friend.uid == chat_uid:
                    return friend
        raise EFBChatNotFound

    #发送消息
    def send_message(self, msg : Message) -> Message:
        chat_uid = msg.chat.uid

        if msg.edit:
            pass     # todo

        if self.wxid is None:
            if self.is_login():
                self.after_login()
            else:
                content = {
                    "name": self.user_auth_chat.name,
                    "sender": self.user_auth_chat.uid,
                    "message": "检测到微信未登录，请发送 /login 获取登录二维码，或发送 /wechat 打开微信管理"
                }
                self.system_msg(content)
                return msg

        if msg.text:
            match = re.search(self.forward_pattern, msg.text)
            if match:
                if match.group(1) == hashlib.md5(self.channel_id.encode('utf-8')).hexdigest():
                    msgid = match.group(2)
                    self.logger.debug(f"提取到的消息 ID: {msgid}")
                    self.bot.ForwardMessage(wxid = chat_uid, msgid = msgid)
                else:
                    self.logger.debug(f"非本 slave 消息: {match.group(1)}/{match.group(2)}")
                return msg

        if msg.type == MsgType.Voice:
            f = tempfile.NamedTemporaryFile(prefix='voice_message_', suffix=".mp3")
            AudioSegment.from_ogg(msg.file.name).export(f, format="mp3")
            msg.file = f
            msg.file.name = "语音留言.mp3"
            msg.type = MsgType.Video
            msg.filename = os.path.basename(f.name)

        if msg.type in [MsgType.Text]:
            command_error = group_command_error(msg.text, chat_uid)
            if command_error:
                self.system_msg({
                    "sender": chat_uid,
                    "message": command_error,
                })
                return msg

            if msg.text.startswith('/changename'):
                newname = msg.text.strip('/changename ')
                res = self.bot.SetChatroomName(chatroom_id = chat_uid , chatroom_name = newname)
            elif msg.text.startswith('/getmemberlist'):
                memberlist = self.bot.GetChatroomMemberList(chatroom_id = chat_uid)
                members = chatroom_member_ids(memberlist)
                if not members:
                    self.system_msg({
                        "sender": chat_uid,
                        "message": "未获取到群成员，请稍后重试。",
                    })
                    return msg
                message = '群组成员包括：'
                for wxid in members:
                    try:
                        name = self.contacts[wxid]
                    except:
                        try:
                            name = self.bot.GetChatroomMemberNickname(chatroom_id = chat_uid, wxid = wxid)['nickname'] or wxid
                        except:
                            name = wxid
                    message += '\n' + wxid + ' : ' + name
                self.system_msg({'sender':chat_uid, 'message':message})
            elif msg.text.startswith('/getstaticinfo'):
                info = msg.text[15::]
                if info == 'friends':
                    message = str(self.friends)
                elif info == 'groups':
                    message = str(self.groups)
                elif info == 'group_members':
                    message = json.dumps(self.group_members)
                elif info == 'contacts':
                    message = json.dumps(self.contacts)
                else:
                    message = '当前仅支持查询friends, groups, group_members, contacts'
                self.system_msg({'sender':chat_uid, 'message':message})
            elif msg.text.startswith('/membercolor'):
                argument = msg.text[len('/membercolor'):].strip().lower()
                if argument in {"on", "enable", "1", "开启"}:
                    self.member_avatar_markers.set_enabled(True)
                elif argument in {"off", "disable", "0", "关闭"}:
                    self.member_avatar_markers.set_enabled(False)
                avatar_count, total_count = self.member_avatar_markers.counts()
                enabled = self.member_avatar_markers.enabled
                commands = [MessageCommand(
                    name="关闭头像配色" if enabled else "开启头像配色",
                    callable_name="set_member_avatar_markers",
                    kwargs={"enabled": not enabled},
                )]
                self.system_msg({
                    'sender': chat_uid,
                    'message': (
                        f"群成员头像配色：{'已开启' if enabled else '已关闭'}\n"
                        f"已缓存：{total_count} 人（头像取色 {avatar_count} 人）\n"
                        "仅影响 Telegram 群聊成员名称前的标记。"
                    ),
                    'commands': commands,
                })
                return msg
            elif msg.text.startswith('/helpcomwechat'):
                message = '''ComWechat 会话内命令（需在具体微信会话中手动输入）：

/search - 按关键字匹配好友昵称搜索联系人

/addtogroup - 按 wxid 添加好友到当前群聊（仅群聊）

/getmemberlist - 查看当前群聊成员 wxid（仅群聊）

/at - 提醒群成员（仅群聊）

/sendcard - 后面格式'wxid nickname'

/changename - 修改当前群聊名称（仅群聊）

/addfriend - 后面格式'wxid message'

/membercolor - 查看、开启或关闭群成员头像配色

/getstaticinfo - 可获取 friends、groups、group_members、contacts 信息'''
                self.system_msg({'sender':chat_uid, 'message':message})
            elif msg.text.startswith('/search'):
                keyword = msg.text[8::]
                message = 'result:'
                for key, value in self.contacts.items():
                    if keyword in value:
                        message += '\n' + str(key) + " : " + str(value)
                self.system_msg({'sender':chat_uid, 'message':message})
            elif msg.text.startswith('/addtogroup'):
                users = msg.text[12::]
                res = self.bot.AddChatroomMember(chatroom_id = chat_uid, wxids = users)
            elif msg.text.startswith('/forward'):
                if isinstance(msg.target, Message):
                    msgid = msg.target.uid
                    if msgid.isdecimal():
                        url = f"ehforwarderbot://{hashlib.md5(self.channel_id.encode('utf-8')).hexdigest()}/forward/{msgid}"
                        prompt = "请将这条信息转发到目标聊天中"
                        text = f"{url}\n{prompt}"
                        if msg.target.text:
                            match = re.search(self.forward_pattern, msg.target.text)
                            if match:
                                msg.target.text = f"{msg.target.text[0:match.start()]}{text}"
                            else:
                                msg.target.text = f"{msg.target.text}\n\n---\n{text}"
                        else:
                            msg.target.text = text
                        self.send_efb_msgs(msg.target, edit=True)
                    else:
                        text = f"无法转发{msgid},不是有效的微信消息"
                        self.system_msg({'sender': chat_uid, 'message': text, 'target': msg.target})
                    return msg
            elif msg.text.startswith('/at'):
                users_message = msg.text[4::].split(' ', 1)
                if isinstance(msg.target, Message):
                    users = msg.target.author.uid
                    message = msg.text[4::]
                elif len(users_message) == 2:
                    users, message = users_message
                else:
                    users, message = users_message[0], ''
                if users != '':
                    res = self.bot.SendAt(chatroom_id = chat_uid, wxids = users, msg = message)
                else:
                    self.bot.SendText(wxid = chat_uid , msg = msg.text)
            elif msg.text.startswith('/sendcard'):
                user_nickname = msg.text[10::].split(' ', 1)
                if len(user_nickname) == 2:
                    user, nickname = user_nickname
                else:
                    user, nickname = user_nickname[0], ''
                if user != '':
                    res = self.bot.SendCard(receiver = chat_uid, share_wxid = user, nickname = nickname)
                else:
                    self.bot.SendText(wxid = chat_uid , msg = msg.text)
            elif msg.text.startswith('/addfriend'):
                user_invite = msg.text[11::].split(' ', 1)
                if len(user_invite) == 2:
                    user, invite = user_invite
                else:
                    user, invite = user_invite[0], ''
                if user != '':
                    res = self.bot.AddContactByWxid(wxid = user, msg = invite)
                else:
                    self.bot.SendText(wxid = chat_uid , msg = msg.text)
            else:
                res = self.send_text(wxid = chat_uid , msg = msg)
        elif msg.type in [MsgType.Link]:
            self.send_text(wxid = chat_uid , msg = msg)
        elif msg.type in [MsgType.Image , MsgType.Sticker]:
            name = os.path.basename(msg.file.name)
            local_path =f"{self.dir}{self.wxid}/{name}"
            load_temp_file_to_local(msg.file, local_path)
            img_path = self.base_path + "\\" + self.wxid + "\\" + name
            res = self.bot.SendImage(receiver = chat_uid , img_path = img_path)
            self.delete_file[local_path] = int(time.time())
            if msg.text:
                self.send_text(wxid = chat_uid , msg = msg)
        elif msg.type in [MsgType.File , MsgType.Video]:
            name = os.path.basename(msg.file.name)
            local_path = f"{self.dir}{self.wxid}/{name}"
            load_temp_file_to_local(msg.file, local_path)
            file_path = self.base_path + "\\" + self.wxid + "\\" + name
            if msg.filename:
                try:
                    os.rename(local_path , f"{self.dir}{self.wxid}/{msg.filename}")
                except:
                    os.replace(local_path , f"{self.dir}{self.wxid}/{msg.filename}")
                local_path = f"{self.dir}{self.wxid}/{msg.filename}"
                file_path = self.base_path + "\\" + self.wxid + "\\" + msg.filename
            res = self.bot.SendFile(receiver = chat_uid , file_path = file_path)
            self.delete_file[local_path] = int(time.time())
            if msg.text:
                self.send_text(wxid = chat_uid , msg = msg)
            if msg.type == MsgType.Video:
                res["msg"] = 1
        elif msg.type in [MsgType.Animation]:
            name = os.path.basename(msg.file.name)
            local_path = f"{self.dir}{self.wxid}/{name}"
            load_temp_file_to_local(msg.file, local_path)
            file_path = self.base_path + "\\" + self.wxid + "\\" + local_path.split("/")[-1]
            res = self.bot.SendEmotion(wxid = chat_uid , img_path = file_path)
            self.delete_file[local_path] = int(time.time())
            if msg.text:
                self.send_text(wxid = chat_uid , msg = msg)

        try:
            if str(res["msg"]) == "0":
                raise EFBMessageError("发送失败，请在手机端确认")
        except:
            ...
        return msg

    def _load_member_avatar(self, wxid: str) -> Optional[BinaryIO]:
        url = self.bot.GetPictureBySql(wxid=wxid)
        if not url:
            return None
        return download_file(url, retry=1)

    def set_member_avatar_markers(self, enabled: bool):
        self.member_avatar_markers.set_enabled(bool(enabled))
        return "群成员头像配色已开启" if enabled else "群成员头像配色已关闭"

    def send_text(self, wxid: ChatID, msg: Message) -> 'Message':
        text = msg.text
        if isinstance(msg.target, Message):
                if isinstance(msg.target.author, SelfChatMember) and isinstance(msg.target.deliver_to, SlaveChannel):
                    qt_txt = msg.target.text or msg.target.type.name
                    text = qutoed_text(qt_txt, msg.text)
                else:
                    msgid = msg.target.uid
                    sender = msg.target.author.uid
                    displayname = self.group_members.get(wxid,{}).get(sender, self.get_nickname_by_wxid(sender))
                    content = escape(msg.target.vendor_specific.get("wx_xml", ""), {
                        "\n": "&#x0A;",
                        "\t": "&#x09;",
                        '"': "&quot;",
                    }) or msg.target.text
                    comwechat_info = msg.target.vendor_specific.get("comwechat_info", {})
                    if comwechat_info.get("type", None) == "animatedsticker":
                        refer_type = 47
                    elif msg.target.type == MsgType.Image:
                        refer_type = 3
                    elif msg.target.type == MsgType.Voice:
                        refer_type = 34
                    elif msg.target.type == MsgType.Video:
                        refer_type = 43
                    elif msg.target.type == MsgType.Sticker:
                        refer_type = 47
                    elif msg.target.type == MsgType.Location:
                        refer_type = 48
                    elif msg.target.type == MsgType.File:
                        refer_type = 49
                    elif comwechat_info.get("type", None) == "share":
                        refer_type = 49
                    else:
                        refer_type = 1
                    if content:
                        content = "<content>%s</content>" % content
                    else:
                        content = "<content />"
                    xml = QUOTE_MESSAGE % (self.wxid, text, refer_type, msgid, sender, sender, displayname, content)
                    return self.bot.SendXml(wxid = wxid , xml = xml, img_path = "")
        return self.bot.SendText(wxid = wxid , msg = text)

    def get_chat_picture(self, chat: 'Chat') -> BinaryIO:
        wxid = chat.uid
        result = self.bot.GetPictureBySql(wxid = wxid)
        if result:
            return download_file(result)
        else:
            return None

    def get_chat_member_picture(self, chat_member: 'ChatMember') -> BinaryIO:
        wxid = chat_member.uid
        result = self.bot.GetPictureBySql(wxid = wxid)
        if result:
            return download_file(result)
        else:
            return None

    def poll(self):
        timer = threading.Thread(target = self.scheduled_job)
        timer.daemon = True
        timer.start()

        while True:
            time.sleep(1)
            try:
                #防止偶尔 comwechat 启动落后
                if self.bot.run(main_thread = False) is not None:
                    break
            except Exception as e:
                self.logger.error("Start failed. Reason: %s" % e)

        t = threading.Thread(target = self.handle_file_msg)
        t.daemon = True
        t.start()

    def send_status(self, status: 'Status'):
        ...

    def stop_polling(self):
        self.db.stop_worker()

    def get_message_by_id(self, chat: 'Chat', msg_id: MessageID) -> Optional['Message']:
        ...

    def get_name_by_wxid(self, wxid):
        cached_name = self.contacts.get(wxid, wxid)
        name = resolve_contact_name(wxid, cached_name, lambda contact: self.bot.GetContactBySql(wxid=contact))
        self.contacts[wxid] = name
        return name

    @staticmethod
    def non_blocking_lock_wrapper(lock: threading.Lock) :
        def wrapper(func):
            def inner(*args, **kwargs):
                if not lock.acquire(False):
                    return
                try:
                    return func(*args, **kwargs)
                finally:
                    lock.release()
            return inner
        return wrapper

    @non_blocking_lock_wrapper(contact_update_lock)
    def get_me(self):
        self.me = self.bot.GetSelfInfo()["data"]
        self.wxid = self.me["wxId"]

    def get_nickname_by_wxid(self, wxid):
        try:
            nickname = self.nicknames[wxid]
            if nickname == "":
                nickname = wxid
        except:
            data = self.bot.GetContactBySql(wxid = wxid)
            if data:
                nickname = data[3]
                if nickname == "":
                    nickname = wxid
                else:
                    self.nicknames[wxid] = nickname
            else:
                nickname = wxid
        return nickname

    #定时更新 Start
    @non_blocking_lock_wrapper(contact_update_lock)
    def GetContactListBySql(self, notify: bool = True):
        new_chats = []
        modified_chats = []
        contacts = self.bot.GetContactListBySql()
        for contact in contacts:
            data = contacts[contact]
            name = (f"{data['remark']}({data['nickname']})") if data["remark"] else data["nickname"]
            name = resolve_contact_name(contact, name, lambda wxid: self.bot.GetContactBySql(wxid=wxid))

            self.contacts[contact] = name
            self.nicknames[contact] = data["nickname"]
            if data["type"] == 0 or data["type"] == 4:
                continue

            if "@chatroom" in contact:
                update_existing_chat_name(self.groups, contact, name)
                new_entity = EFBGroupChat(
                    uid=contact,
                    name=name
                )
                try:
                    self.get_chat(contact)
                    modified_chats.append(contact)
                except EFBChatNotFound:
                    self.groups.append(ChatMgr.build_efb_chat_as_group(new_entity))
                    new_chats.append(contact)
            else:
                update_existing_chat_name(self.friends, contact, name)
                new_entity = EFBPrivateChat(
                    uid=contact,
                    name=name
                )
                try:
                    self.get_chat(contact)
                    modified_chats.append(contact)
                except EFBChatNotFound:
                    self.friends.append(ChatMgr.build_efb_chat_as_private(new_entity))
                    new_chats.append(contact)

        if notify and (new_chats or modified_chats):
            coordinator.send_status(ChatUpdates(channel=self, new_chats=new_chats, modified_chats=modified_chats))

    def load(self):
        rows = self.db.get_all_group_aliases()
        for r in rows:
            self.group_members[r.group_uid] = self.group_members.get(r.group_uid, {})
            self.group_members[r.group_uid][r.wxid] = r.group_alias

    def merge_group_members(self, group, new_members):
        self.group_members[group] = self.group_members.get(group, {})
        for wxid, alias in new_members.items():
            if self.group_members[group].get(wxid, None) != alias:
                self.group_members[group][wxid] = alias
                self.db.update_group_alias(group, wxid, alias)

    @non_blocking_lock_wrapper(group_update_lock)
    def GetGroupListBySql(self):
        groups = self.bot.GetAllGroupMembersBySql()
        for group, members in groups.items():
            self.merge_group_members(group, members)

    def extract_alias(self, msg):
        sender = msg["sender"]
        extracted = False
        message = msg.get("message", "")
        if "<refermsg>" in message:
            xml = etree.fromstring(message)
            id = xml.xpath('string(/msg/appmsg/refermsg/chatusr)')
            alias = xml.xpath('string(/msg/appmsg/refermsg/displayname)')
            name = self.get_nickname_by_wxid(id)
            if alias and alias != name:
                extracted = True
                self.merge_group_members(sender, {
                    id: alias
                })

        if not extracted and "<atuserlist>" in msg.get("extrainfo", ""):
            xml = etree.fromstring(msg["extrainfo"])
            at_user = xml.xpath('string(/msgsource/atuserlist)')
            user_list = [user for user in at_user.split(",") if user]
            if len(user_list) == 1:
                try:
                    name = self.get_nickname_by_wxid(user_list[0])
                    alias = extract_mentioned_alias(message)
                    if not alias:
                        return
                    if alias != name:
                        self.merge_group_members(sender, {
                            user_list[0]: alias
                        })
                except:
                    print_exc()
    #定时更新 End

class EmptyJsonResponse:
    def json(self):
        return {}
