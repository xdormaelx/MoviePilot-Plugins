import os
import threading
import logging
import re
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from app.plugins import _PluginBase
from app.schemas.types import EventType, NotificationType
from app.core.event import eventmanager, Event
from app.log import logger


@dataclass
class PluginConfigModel:
    """插件配置模型"""
    enabled: bool = False  # 启用插件开关
    notify: bool = False   # 发送通知开关
    onlyonce: bool = False # 立即运行一次开关
    monitor_dirs: str = ""  # 监控目录路径（多行）
    video_exts: str = "mp4,mkv,avi,ts"  # 视频文件扩展名
    sub_exts: str = "ass,ssa,srt"  # 字幕文件扩展名


class SubtitleRenamer:
    """字幕文件重命名工具"""

    def rename_subtitle(self, sub_path: str, video_dir: str, video_exts: List[str]) -> Tuple[bool, str]:
        sub_name = os.path.basename(sub_path)
        sub_base, sub_ext = os.path.splitext(sub_name)
        sub_episode = self.extract_episode_info(sub_base)
        if not sub_episode:
            return False, f"字幕文件 {sub_name} 中未找到季集信息"

        video_file = self.find_matching_video(video_dir, video_exts, sub_episode)
        if not video_file:
            return False, f"未找到匹配的视频文件，字幕: {sub_episode}"

        new_sub_name = self.generate_new_sub_name(video_file, sub_ext)
        if not new_sub_name:
            return False, "无法生成新的字幕文件名"

        new_sub_path = os.path.join(video_dir, new_sub_name)
        if os.path.exists(new_sub_path):
            return False, f"目标字幕文件已存在: {new_sub_name}"

        try:
            os.rename(sub_path, new_sub_path)
            return True, f"字幕文件重命名成功: {sub_name} -> {new_sub_name}"
        except Exception as e:
            return False, f"重命名失败: {str(e)}"

    def extract_episode_info(self, filename: str) -> Optional[str]:
        pattern = r"[sS]\d{1,2}[eE]\d{1,2}"
        match = re.search(pattern, filename)
        return match.group().upper() if match else None

    def find_matching_video(self, directory: str, video_exts: List[str], episode: str) -> Optional[str]:
        for filename in os.listdir(directory):
            ext = os.path.splitext(filename)[-1].lstrip(".").lower()
            if ext not in video_exts:
                continue
            file_base = os.path.splitext(filename)[0]
            video_episode = self.extract_episode_info(file_base)
            if video_episode == episode:
                return filename
        return None

    def generate_new_sub_name(self, video_file: str, sub_ext: str) -> Optional[str]:
        video_base = os.path.splitext(video_file)[0]
        return f"{video_base}{sub_ext}"


class SubtitleMonitorHandler(FileSystemEventHandler):
    """字幕文件监控处理器"""

    def __init__(self, plugin: Any):
        super().__init__()
        self.plugin = plugin

    def on_created(self, event):
        if not event.is_directory:
            self.plugin.process_subtitle(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self.plugin.process_subtitle(event.dest_path)


class AutoSubRename(_PluginBase):
    plugin_name = "剧集字幕重命名"
    plugin_desc = "自动重命名匹配的字幕文件"
    plugin_icon = "rename.png"
    plugin_version = "1.2.2"
    plugin_author = "xdormaelx"
    plugin_order = 1
    reusable = True

    def __init__(self):
        self._config_model = PluginConfigModel
        self._config_key = f"{self.plugin_name}:config"
        self._current_config = self.get_config() or self._config_model()
        self._monitor_dirs: List[str] = []
        self._observer: List[Observer] = []
        self._running = False
        self._renamer = SubtitleRenamer()
        self._processed_files = set()
        self._batch_thread = None
        self.chain = None  # 兼容V2，防止缺少chain属性报错

    def init_plugin(self, config: Dict = None):
        if config:
            self._current_config = PluginConfigModel(**config)
            self.update_config(config)

        self._monitor_dirs = [d.strip() for d in self._current_config.monitor_dirs.split("\n") if d.strip()]
        self.stop_service()

        if self._current_config.onlyonce:
            logger.info("执行立即运行一次")
            self._batch_thread = threading.Thread(target=self._batch_rename_thread, daemon=True)
            self._batch_thread.start()

        if self._current_config.enabled and self._monitor_dirs:
            self.start_service()

    def _batch_rename_thread(self):
        try:
            self.batch_rename()
        finally:
            self._current_config.onlyonce = False
            self.update_config(self._current_config.__dict__)

    def start_service(self):
        if self._running:
            return
        self._running = True
        for monitor_dir in self._monitor_dirs:
            if not os.path.exists(monitor_dir):
                logger.warning(f"监控目录不存在: {monitor_dir}")
                continue
            observer = Observer()
            handler = SubtitleMonitorHandler(self)
            observer.schedule(handler, path=monitor_dir, recursive=True)
            observer.start()
            self._observer.append(observer)
            logger.info(f"开始监控目录: {monitor_dir}")

    def process_subtitle(self, sub_path: str):
        if sub_path in self._processed_files:
            return
        sub_dir = os.path.dirname(sub_path)
        if not any(sub_dir.startswith(mon_dir) for mon_dir in self._monitor_dirs):
            return
        ext = os.path.splitext(sub_path)[-1].lstrip(".").lower()
        sub_exts = [e.strip().lower() for e in self._current_config.sub_exts.split(",")]
        if ext not in sub_exts:
            return
        try:
            video_exts = [e.strip().lower() for e in self._current_config.video_exts.split(",")]
            success, msg = self._renamer.rename_subtitle(sub_path, sub_dir, video_exts)
            if success:
                self._processed_files.add(sub_path)
                if self._current_config.notify:
                    self.post_message(mtype=NotificationType.Plugin, title=f"【{self.plugin_name}】字幕重命名", text=msg)
        except Exception as e:
            logger.error(f"处理字幕文件时出错: {str(e)}")

    def batch_rename(self):
        if not self._monitor_dirs:
            logger.warning("未配置监控目录，无法执行批量重命名")
            return
        video_exts = [ext.strip().lower() for ext in self._current_config.video_exts.split(",")]
        sub_exts = [ext.strip().lower() for ext in self._current_config.sub_exts.split(",")]
        results = []
        for monitor_dir in self._monitor_dirs:
            if not os.path.exists(monitor_dir):
                logger.warning(f"监控目录不存在: {monitor_dir}")
                continue
            for root, _, files in os.walk(monitor_dir):
                for filename in files:
                    ext = os.path.splitext(filename)[-1].lstrip(".").lower()
                    if ext in sub_exts:
                        try:
                            success, msg = self._renamer.rename_subtitle(os.path.join(root, filename), root, video_exts)
                            results.append(msg)
                            if success:
                                self._processed_files.add(os.path.join(root, filename))
                        except Exception as e:
                            results.append(f"处理字幕文件 {filename} 时出错: {str(e)}")
        if self._current_config.notify and results:
            success_count = sum("成功" in r for r in results)
            fail_count = len(results) - success_count
            self.post_message(
                mtype=NotificationType.Plugin,
                title=f"【{self.plugin_name}】批量重命名结果",
                text=f"批量重命名完成: 成功 {success_count} 个, 失败 {fail_count} 个\n" + "\n".join(results)
            )

    @eventmanager.register(EventType.PluginReload)
    def reload(self, event: Event):
        if event.event_data and event.event_data.get("plugin_id") == self.plugin_name:
            logger.info(f"{self.plugin_name} 插件配置已重载")
            self.stop_service()
            self.init_plugin()

    def get_command(self) -> List[Dict[str, Any]]:
        return [{"cmd": "/subrename", "event": EventType.PluginAction, "desc": "字幕重命名", "data": {"action": "batch_rename"}}]

    def get_api(self) -> List[Dict[str, Any]]:
        return [{"path": "/batch_rename", "endpoint": self.batch_rename_api, "methods": ["GET"], "summary": "批量重命名字幕"}]

    def batch_rename_api(self) -> dict:
        self._batch_thread = threading.Thread(target=self.batch_rename, daemon=True)
        self._batch_thread.start()
        return {"code": 0, "msg": "批量重命名操作已启动"}

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        return [
            {
                "component": "VForm",
                "content": [
                    {"component": "VRow", "content": [
                        {"component": "VCol", "props": {"cols": 12, "md": 4}, "content": [
                            {"component": "VSwitch", "props": {"model": "enabled", "label": "启用插件"}}]},
                        {"component": "VCol", "props": {"cols": 12, "md": 4}, "content": [
                            {"component": "VSwitch", "props": {"model": "notify", "label": "发送通知"}}]},
                        {"component": "VCol", "props": {"cols": 12, "md": 4}, "content": [
                            {"component": "VSwitch", "props": {"model": "onlyonce", "label": "立即运行一次"}}]}
                    ]},
                    {"component": "VRow", "content": [
                        {"component": "VCol", "props": {"cols": 12}, "content": [
                            {"component": "VTextarea", "props": {"model": "monitor_dirs", "label": "监控目录", "rows": 3,
                                                                  "placeholder": "每行一个目录路径"}}]}]},
                    {"component": "VRow", "content": [
                        {"component": "VCol", "props": {"cols": 6}, "content": [
                            {"component": "VTextField", "props": {"model": "video_exts", "label": "视频扩展名"}}]},
                        {"component": "VCol", "props": {"cols": 6}, "content": [
                            {"component": "VTextField", "props": {"model": "sub_exts", "label": "字幕扩展名"}}]}
                    ]}
                ]
            }
        ], self._current_config.__dict__

    def get_state(self) -> bool:
        return self._current_config.enabled

    def stop_service(self):
        if not self._running:
            return
        self._running = False
        for observer in self._observer:
            observer.stop()
            observer.join()
        self._observer.clear()
