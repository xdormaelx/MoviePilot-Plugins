import os
import time
import threading
import logging
import re
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from app.plugins import _PluginBase
from app.schemas.types import EventType, SystemConfigKey, NotificationType
from app.core.config import settings
from app.core.event import eventmanager, Event
from app.db.systemconfig_oper import SystemConfigOper
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
        """
        重命名字幕文件
        
        :param sub_path: 字幕文件路径
        :param video_dir: 视频文件所在目录
        :param video_exts: 视频文件扩展名列表
        :return: (是否成功, 消息)
        """
        # 获取字幕文件名和扩展名
        sub_name = os.path.basename(sub_path)
        sub_base, sub_ext = os.path.splitext(sub_name)
        
        # 提取字幕文件中的季集信息
        sub_episode = self.extract_episode_info(sub_base)
        if not sub_episode:
            msg = f"字幕文件 {sub_name} 中未找到季集信息"
            logger.info(msg)
            return False, msg
            
        # 在当前目录查找匹配的视频文件
        video_file = self.find_matching_video(video_dir, video_exts, sub_episode)
        if not video_file:
            msg = f"未找到匹配的视频文件，字幕: {sub_episode}"
            logger.info(msg)
            return False, msg
            
        # 生成新的字幕文件名
        new_sub_name = self.generate_new_sub_name(video_file, sub_ext)
        if not new_sub_name:
            msg = f"无法生成新的字幕文件名"
            logger.warning(msg)
            return False, msg
        
        # 重命名字幕文件（保持在同一目录）
        new_sub_path = os.path.join(video_dir, new_sub_name)
        if os.path.exists(new_sub_path):
            msg = f"目标字幕文件已存在: {new_sub_name}"
            logger.warning(msg)
            return False, msg
        
        try:
            os.rename(sub_path, new_sub_path)
            msg = f"字幕文件重命名成功: {sub_name} -> {new_sub_name}"
            logger.info(msg)
            return True, msg
        except Exception as e:
            msg = f"重命名失败: {str(e)}"
            logger.error(msg)
            return False, msg
    
    def extract_episode_info(self, filename: str) -> Optional[str]:
        """
        从文件名中提取季集信息
        
        :param filename: 文件名（不含扩展名）
        :return: 季集信息（如 S01E01），不区分大小写
        """
        # 匹配季集格式：SxxExx 或 sxxexx
        pattern = r"[sS]\d{1,2}[eE]\d{1,2}"
        match = re.search(pattern, filename)
        if match:
            return match.group().upper()  # 统一转为大写
        return None
    
    def find_matching_video(self, directory: str, video_exts: List[str], episode: str) -> Optional[str]:
        """
        查找匹配的视频文件
        
        :param directory: 目录路径
        :param video_exts: 视频扩展名列表
        :param episode: 季集信息
        :return: 匹配的视频文件名
        """
        for filename in os.listdir(directory):
            # 检查文件扩展名
            ext = os.path.splitext(filename)[-1].lstrip(".").lower()
            if ext not in video_exts:
                continue
            
            # 提取视频文件中的季集信息
            file_base = os.path.splitext(filename)[0]
            video_episode = self.extract_episode_info(file_base)
            if not video_episode:
                continue
            
            # 比较季集信息是否匹配
            if video_episode == episode:
                return filename
        return None
    
    def generate_new_sub_name(self, video_file: str, sub_ext: str) -> Optional[str]:
        """
        生成新的字幕文件名
        
        :param video_file: 视频文件名
        :param sub_ext: 字幕文件扩展名
        :return: 新的字幕文件名
        """
        # 获取视频文件的主文件名（不含扩展名）
        video_base = os.path.splitext(video_file)[0]
        
        # 生成新的字幕文件名
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
    # 插件名称
    plugin_name = "字幕自动重命名"
    # 插件描述
    plugin_desc = "自动重命名匹配的字幕文件"
    # 插件图标
    plugin_icon = "rename.png"
    # 插件版本
    plugin_version = "1.0.0"
    # 插件作者
    plugin_author = "xdormaelx"
    # 作者主页
    plugin_author_url = ""
    # 插件顺序
    plugin_order = 1
    # 可重用
    reusable = True
    
    def __init__(self):
        # 配置模型
        self._config_model = PluginConfigModel
        # 配置键
        self._config_key = f"{self.plugin_name}:config"
        # 当前配置
        self._current_config = self._get_config()
        # 监控目录列表
        self._monitor_dirs = []
        # 文件监控观察者列表
        self._observer = []
        # 运行标志
        self._running = False
        # 重命名器实例
        self._renamer = SubtitleRenamer()
        # 已处理文件缓存
        self._processed_files = set()
    
    def _get_config(self) -> PluginConfigModel:
        """获取插件配置"""
        # 从系统配置中获取插件配置
        config_data = SystemConfigOper().get(self._config_key)
        
        if not config_data:
            return self._config_model()
        
        # 将配置数据转换为配置模型
        return PluginConfigModel(
            enabled=config_data.get("enabled", False),
            notify=config_data.get("notify", False),
            onlyonce=config_data.get("onlyonce", False),
            monitor_dirs=config_data.get("monitor_dirs", ""),
            video_exts=config_data.get("video_exts", "mp4,mkv,avi,ts"),
            sub_exts=config_data.get("sub_exts", "ass,ssa,srt")
        )
    
    def init_plugin(self, config: Dict = None):
        # 如果有新的配置传入，更新当前配置
        if config:
            self._current_config = PluginConfigModel(
                enabled=config.get("enabled", False),
                notify=config.get("notify", False),
                onlyonce=config.get("onlyonce", False),
                monitor_dirs=config.get("monitor_dirs", ""),
                video_exts=config.get("video_exts", "mp4,mkv,avi,ts"),
                sub_exts=config.get("sub_exts", "ass,ssa,srt")
            )
            # 保存新配置
            self.__update_config()
        
        # 解析监控目录
        self._monitor_dirs = [d.strip() for d in self._current_config.monitor_dirs.split("\n") if d.strip()]
        
        # 停止任何正在运行的服务
        self.stop_service()
        
        # 处理立即运行
        if self._current_config.onlyonce:
            logger.info("执行立即运行一次")
            self.batch_rename()
            # 重置立即运行标志
            self._current_config.onlyonce = False
            self.__update_config()
        
        # 如果插件已启用且有监控目录，启动服务
        if self._current_config.enabled and self._monitor_dirs:
            self.start_service()
    
    def __update_config(self):
        """更新配置到数据库"""
        config_data = {
            "enabled": self._current_config.enabled,
            "notify": self._current_config.notify,
            "onlyonce": self._current_config.onlyonce,
            "monitor_dirs": self._current_config.monitor_dirs,
            "video_exts": self._current_config.video_exts,
            "sub_exts": self._current_config.sub_exts
        }
        SystemConfigOper().set(self._config_key, config_data)
    
    def start_service(self):
        """启动监控服务"""
        if self._running:
            return
            
        logger.info(f"{self.plugin_name} 启动监控服务...")
        self._running = True
        
        # 添加监控目录（包括所有子目录）
        for monitor_dir in self._monitor_dirs:
            if not os.path.exists(monitor_dir):
                logger.warning(f"监控目录不存在: {monitor_dir}")
                continue
                
            observer = Observer()
            handler = SubtitleMonitorHandler(self)
            observer.schedule(handler, path=monitor_dir, recursive=True)  # 递归监控子目录
            observer.start()
            self._observer.append(observer)
            logger.info(f"开始监控目录: {monitor_dir}")
    
    def process_subtitle(self, sub_path: str):
        """处理字幕文件"""
        # 检查是否已处理过
        if sub_path in self._processed_files:
            return
            
        # 获取字幕文件所在目录
        sub_dir = os.path.dirname(sub_path)
        
        # 检查是否在监控目录下
        if not any(sub_dir.startswith(mon_dir) for mon_dir in self._monitor_dirs):
            return
            
        # 获取文件扩展名
        ext = os.path.splitext(sub_path)[-1].lstrip(".").lower()
        sub_exts = [e.strip().lower() for e in self._current_config.sub_exts.split(",")]
        
        # 检查是否是字幕文件
        if ext not in sub_exts:
            return
            
        # 重命名字幕文件
        video_exts = [e.strip().lower() for e in self._current_config.video_exts.split(",")]
        success, msg = self._renamer.rename_subtitle(
            sub_path=sub_path,
            video_dir=sub_dir,  # 在字幕文件所在目录查找视频
            video_exts=video_exts
        )
        
        # 处理结果
        if success:
            self._processed_files.add(sub_path)
            if self._current_config.notify:
                self.post_message(
                    mtype=NotificationType.Plugin,
                    title=f"【{self.plugin_name}】字幕重命名",
                    text=msg
                )
    
    def batch_rename(self):
        """批量重命名所有监控目录中的字幕文件"""
        if not self._monitor_dirs:
            logger.warning("未配置监控目录，无法执行批量重命名")
            return
            
        logger.info("开始批量重命名字幕文件...")
        video_exts = [ext.strip().lower() for ext in self._current_config.video_exts.split(",")]
        sub_exts = [ext.strip().lower() for ext in self._current_config.sub_exts.split(",")]
        
        results = []
        for monitor_dir in self._monitor_dirs:
            if not os.path.exists(monitor_dir):
                logger.warning(f"监控目录不存在: {monitor_dir}")
                continue
                
            # 递归遍历所有子目录
            for root, _, files in os.walk(monitor_dir):
                for filename in files:
                    file_path = os.path.join(root, filename)
                    
                    # 获取文件扩展名
                    ext = os.path.splitext(filename)[-1].lstrip(".").lower()
                    
                    # 处理字幕文件
                    if ext in sub_exts:
                        success, msg = self._renamer.rename_subtitle(
                            sub_path=file_path,
                            video_dir=root,  # 在当前目录查找视频
                            video_exts=video_exts
                        )
                        results.append(msg)
                        if success:
                            self._processed_files.add(file_path)
        
        # 发送通知
        if self._current_config.notify and results:
            success_count = sum("成功" in r for r in results)
            fail_count = len(results) - success_count
            summary = f"批量重命名完成: 成功 {success_count} 个, 失败 {fail_count} 个"
            self.post_message(
                mtype=NotificationType.Plugin,
                title=f"【{self.plugin_name}】批量重命名结果",
                text=f"{summary}\n\n详细结果:\n" + "\n".join(results)
            )
        
        logger.info("批量重命名完成")
    
    @eventmanager.register(EventType.PluginReload)
    def reload(self, event: Event):
        """
        插件重载事件
        """
        # 检查事件是否针对本插件
        if event.event_data and event.event_data.get("plugin_id") == self.plugin_name:
            logger.info(f"{self.plugin_name} 插件配置已重载")
            self.stop_service()
            self.init_plugin()

    def get_command(self) -> List[Dict[str, Any]]:
        return [{
            "cmd": "/subrename",
            "event": EventType.PluginAction,
            "desc": "字幕重命名",
            "data": {"action": "batch_rename"}
        }]

    def get_api(self) -> List[Dict[str, Any]]:
        return [{
            "path": "/batch_rename",
            "endpoint": self.batch_rename_api,
            "methods": ["GET"],
            "summary": "批量重命名字幕",
            "description": "立即执行一次批量重命名操作",
        }]
    
    def batch_rename_api(self) -> dict:
        """API批量重命名"""
        self.batch_rename()
        return {"code": 0, "msg": "批量重命名操作已启动"}

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """
        插件配置页面
        """
        return [
            {
                "component": "VForm",
                "content": [
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "enabled",
                                            "label": "启用插件",
                                        }
                                    }
                                ]
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "notify",
                                            "label": "发送通知",
                                        }
                                    }
                                ]
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "onlyonce",
                                            "label": "立即运行一次",
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
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VTextarea",
                                        "props": {
                                            "model": "monitor_dirs",
                                            "label": "监控目录",
                                            "rows": 3,
                                            "placeholder": "每行一个目录路径（支持子目录监控）"
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
                                "props": {"cols": 6},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "video_exts",
                                            "label": "视频扩展名",
                                            "placeholder": "多个用逗号分隔"
                                        }
                                    }
                                ]
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 6},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "sub_exts",
                                            "label": "字幕扩展名",
                                            "placeholder": "多个用逗号分隔"
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
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VAlert",
                                        "props": {
                                            "type": "info",
                                            "variant": "tonal",
                                            "text": "启用插件后，会自动监控目录及其所有子目录中的字幕文件，并与同目录下的视频文件进行匹配重命名。"
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
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VAlert",
                                        "props": {
                                            "type": "info",
                                            "variant": "tonal",
                                            "text": "点击'立即运行一次'会对所有监控目录及其子目录执行一次批量重命名操作，完成后自动关闭该选项。"
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ], {
            "enabled": self._current_config.enabled,
            "notify": self._current_config.notify,
            "onlyonce": self._current_config.onlyonce,
            "monitor_dirs": self._current_config.monitor_dirs,
            "video_exts": self._current_config.video_exts,
            "sub_exts": self._current_config.sub_exts
        }

    def get_page(self) -> List[Dict]:
        """主页面（已移除）"""
        pass

    def get_state(self) -> bool:
        return self._current_config.enabled

    def stop_service(self):
        """停止监控服务"""
        if not self._running:
            return
            
        logger.info(f"{self.plugin_name} 停止监控服务...")
        self._running = False
        
        # 停止所有观察者
        for observer in self._observer:
            try:
                observer.stop()
                observer.join(timeout=5)
            except Exception as e:
                logger.error(f"停止监控服务时出错: {str(e)}")
        
        self._observer = []
        logger.info(f"{self.plugin_name} 插件服务已停止")
