import threading
from queue import Queue
from time import time, sleep
from typing import Any, List, Dict, Tuple


from app.log import logger
from app.plugins import _PluginBase
from app.utils.http import RequestUtils
from app.schemas import WebhookEventInfo
from app.core.event import eventmanager, Event
from app.schemas.types import EventType, MediaType, MediaImageType, NotificationType

class HA(_PluginBase):
    # 插件名称
    plugin_name = "HA助手"
    # 插件描述
    plugin_desc = "与HA联动"
    # 插件图标
    plugin_icon = "https://github.com/aClarkChen/MoviePilot-Plugins/blob/main/icons/ha.png?raw=true"
    # 插件版本
    plugin_version = "1.0.3"
    # 插件作者
    plugin_author = "ClarkChen"
    # 作者主页
    author_url = "https://github.com/aClarkChen"
    # 插件配置项ID前缀
    plugin_config_prefix = "HA_"
    # 加载顺序
    plugin_order = 23
    # 可使用的用户级别
    auth_level = 2
    # 日志前缀
    LOG_TAG = "[HA]"

    _enabled = False
    _notify = False
    _get_dir = ""
    _msg_type = []

    # 消息处理线程
    processing_thread = None
    # 上次发送时间
    last_send_time = 0
    # 消息队列
    message_queue = Queue()
    # 消息发送间隔（秒）
    send_interval = 5
    # 退出事件
    __event = threading.Event()

    def init_plugin(self, config: dict = None):
        if config:
            self._enabled = config.get("enabled")
            self._notify = config.get("notify")
            self._get_dir = config.get("get_dir")
            self._msg_type = config.get("msg_type") or []

            if self._enabled and self._get_dir:
                # 启动处理队列的后台线程
                self.processing_thread = threading.Thread(target=self.process_queue)
                self.processing_thread.daemon = True
                self.processing_thread.start()

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        pass

    def get_api(self) -> List[Dict[str, Any]]:
        pass

    @eventmanager.register(EventType.UserMessage)
    def get_user_msg(self, event: Event):
        logger.warn(f"收到UserMessage消息")
        if not self._enabled or not event.event_data:
            return
        msg_body = event.event_data
        logger.warn(f"消息为:{msg_body}")

    @eventmanager.register(EventType.WebhookMessage)
    def get_webhook_msg(self, event: Event):
        logger.warn(f"收到WebhookMessage消息")
        if not self._enabled or not event.event_data:
            return
        msg_body = event.event_data
        logger.warn(f"消息为:{msg_body}")
        return

        event_info = event.event_data
        expiring_key = f"{event_info.item_id}-{event_info.client}-{event_info.user_name}"

        # 消息标题
        if event_info.item_type in ["TV", "SHOW"]:
            message_title = f"剧集 {event_info.item_name}"
        elif event_info.item_type == "MOV":
            message_title = f"电影 {event_info.item_name}"
        elif event_info.item_type == "AUD":
            message_title = f"有声书 {event_info.item_name}"
        else:
            message_title = event_info.item_name

        # 消息内容
        message_texts = []
        if event_info.user_name:
            message_texts.append(f"用户：{event_info.user_name}")

        # 消息内容
        message_content = "\n".join(message_texts)

        # 消息图片
        image_url = event_info.image_url
        # 查询剧集图片
        if (event_info.tmdb_id
                and event_info.season_id
                and event_info.episode_id):
            specific_image = self.chain.obtain_specific_image(
                mediaid=event_info.tmdb_id,
                mtype=MediaType.TV,
                image_type=MediaImageType.Backdrop,
                season=event_info.season_id,
                episode=event_info.episode_id
            )
            if specific_image:
                image_url = specific_image
        # 不使用图片
        if not image_url:
            image_url = None

        # 发送消息
        self.post_message(title=message_title, text=message_content, image=image_url)

    @eventmanager.register(EventType.NoticeMessage)
    def send(self, event: Event):
        if not self.get_state() or not event.event_data or not self._notify:
            return
        msg_body = event.event_data
        if not msg_body.get("title") and not msg_body.get("text"):
            logger.warn("标题和内容不能同时为空")
            return
        self.message_queue.put(msg_body)
        logger.info("消息已加入队列等待发送")

    def process_queue(self):
        while True:
            if self.__event.is_set():
                logger.info("消息发送线程正在退出...")
                break
            # 获取队列中的下一条消息
            msg_body = self.message_queue.get()
            # 检查是否满足发送间隔时间
            current_time = time()
            time_since_last_send = current_time - self.last_send_time
            if time_since_last_send < self.send_interval:
                sleep(self.send_interval - time_since_last_send)

            # 处理消息内容
            channel = msg_body.get("channel")
            if channel:
                continue
            msg_type: NotificationType = msg_body.get("type")
            # 检查消息类型是否已启用
            if msg_type and self._msg_type and msg_type.name not in self._msg_type:
                logger.info(f"消息类型 {msg_type.value} 未开启消息发送")
                continue
            data = {"title": msg_body.get("title"), "text": msg_body.get("text")}
            # 尝试发送消息
            try:
                res = RequestUtils().post_res(url=self._get_dir, data=data)
                if res and res.status_code == 200:
                    ret_json = res.json()
                    errno = ret_json.get('errcode')
                    error = ret_json.get('errmsg')
                    if errno == 0:
                        logger.info("HA消息发送成功")
                        # 更新上次发送时间
                        self.last_send_time = time()
                    else:
                        logger.warn(f"HA消息发送失败，错误码：{errno}，错误原因：{error}")
                elif res is not None:
                    logger.warn(f"HA消息发送失败，错误码：{res.status_code}，错误原因：{res.reason}")
                else:
                    logger.warn("HA消息发送失败，未获取到返回信息")
            except Exception as msg_e:
                logger.error(f"HA消息发送失败，{str(msg_e)}")
            # 标记任务完成
            self.message_queue.task_done()

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        MsgTypeOptions = []
        for item in NotificationType:
            MsgTypeOptions.append({
                "title": item.value,
                "value": item.name
            })
        return (
            [{
                'component': 'VForm',
                'content': [
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 6
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'enabled',
                                            'label': '启用插件',
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 6
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'notify',
                                            'label': '消息通知',
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {
                                    "cols": 12
                                },
                                "content": [
                                    {
                                        "component": "VTextarea",
                                        "props": {
                                            "model": "get_dir",
                                            "label": "接受消息的网址",
                                            "rows": 1,
                                            "placeholder": "如:https://XXXX:8123",
                                        },
                                    }
                                ],
                            }
                        ],
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12
                                },
                                'content': [
                                    {
                                        'component': 'VSelect',
                                        'props': {
                                            'multiple': True,
                                            'chips': True,
                                            'model': 'msg_type',
                                            'label': '消息类型',
                                            'items': MsgTypeOptions
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }],
            {
                "enabled": False,
                "notify": False,
                "get_dir": "",
                "msg_type": []
            }
        )

    def get_page(self) -> List[dict]:
        pass

    def stop_service(self):
        pass
