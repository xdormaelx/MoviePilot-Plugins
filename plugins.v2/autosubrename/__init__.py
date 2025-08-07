import os
import time
import threading
import logging
import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from app.plugins import _PluginBase
from app.schemas.types import EventType, SystemConfigKey, NotificationType
from app.core.config import settings
from app.core.event import eventmanager, Event
from app.db.systemconfig_oper import SystemConfigOper
from app.utils.string import StringUtils
from app.log import logger

@dataclass
class PluginConfigModel:
    """插件配置模型"""
    enabled: bool = False  # 启用插件开关
    notify: bool = False   # 发送通知开关
    onlyonce: bool = False # 立即运行开关
    monitor_dirs: str = ""  # 监控目录路径（多行）
    video_exts: str = "mp4,mkv,avi,ts"  # 视频文件扩展名
    sub_exts: str = "ass,ssa,srt"  # 字幕文件扩展名

class SubtitleRenamer:
    """字幕文件重命名工具"""
    
    def rename_subtitle(self, sub_path: str, monitor_dir: str, video_exts: List[str]) -> Tuple[bool, str]:
        """
        重命名字幕文件
        
        :param sub_path: 字幕文件路径
        :param monitor_dir: 监控目录
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
            
        # 查找匹配的视频文件
        video_file = self.find_matching_video(monitor_dir, video_exts, sub_episode)
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
        
        # 重命名字幕文件
        new_sub_path = os.path.join(monitor_dir, new_sub_name)
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

class AutoSubRename(_PluginBase):
    # 插件名称
    plugin_name = "字幕自动重命名"
    # 插件描述
    plugin_desc = "自动重命名匹配的字幕文件"
    # 插件图标
    plugin_icon = "rename.png"
    # 插件版本
    plugin_version = "1.1.0"
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
        # 文件监控线程
        self._thread = None
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
        # 初始化配置
        self._current_config = self._get_config()
        
        # 解析监控目录
        self._monitor_dirs = [d.strip() for d in self._current_config.monitor_dirs.split("\n") if d.strip()]
        
        # 处理立即运行
        if self._current_config.onlyonce:
            logger.info("执行立即运行一次")
            self.batch_rename()
            # 重置立即运行标志
            self._current_config.onlyonce = False
            self.__update_config()
        
        # 启动文件监控
        if self._current_config.enabled and self._monitor_dirs:
            self._running = True
            self._thread = threading.Thread(target=self.__monitor_files)
            self._thread.daemon = True
            self._thread.start()
            logger.info(f"{self.plugin_name} 插件已启动，监控目录: {self._monitor_dirs}")
        elif self._current_config.enabled and not self._monitor_dirs:
            logger.warning(f"{self.plugin_name} 已启用但未配置监控目录")
        else:
            logger.info(f"{self.plugin_name} 插件未启用")
    
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
    
    def batch_rename(self):
        """批量重命名所有监控目录中的字幕文件"""
        if not self._monitor_dirs:
            logger.warning("未配置监控目录，无法执行批量重命名")
            return
            
        logger.info("开始批量重命名字幕文件...")
        video_extensions = [ext.strip().lower() for ext in self._current_config.video_exts.split(",")]
        sub_extensions = [ext.strip().lower() for ext in self._current_config.sub_exts.split(",")]
        
        results = []
        for monitor_dir in self._monitor_dirs:
            if not os.path.exists(monitor_dir):
                logger.warning(f"监控目录不存在: {monitor_dir}")
                continue
                
            for filename in os.listdir(monitor_dir):
                file_path = os.path.join(monitor_dir, filename)
                
                # 跳过目录
                if os.path.isdir(file_path):
                    continue
                
                # 获取文件扩展名
                _, file_ext = os.path.splitext(filename)
                ext = file_ext.lstrip(".").lower()
                
                # 处理字幕文件
                if ext in sub_extensions:
                    success, msg = self._renamer.rename_subtitle(
                        sub_path=file_path,
                        monitor_dir=monitor_dir,
                        video_exts=video_extensions
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
                                            "placeholder": "每行一个目录路径"
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
                    }
                ]
            }
        ], {
            "enabled": False,
            "notify": False,
            "onlyonce": False,
            "monitor_dirs": "",
            "video_exts": "mp4,mkv,avi,ts",
            "sub_exts": "ass,ssa,srt"
        }

    def get_page(self) -> List[Dict]:
        return []

    def get_state(self) -> bool:
        return self._current_config.enabled

    def stop_service(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
            logger.info(f"{self.plugin_name} 插件服务已停止")
    
    def __monitor_files(self):
        """
        文件监控线程函数
        """
        video_extensions = [ext.strip().lower() for ext in self._current_config.video_exts.split(",")]
        sub_extensions = [ext.strip().lower() for ext in self._current_config.sub_exts.split(",")]
        
        logger.info(f"{self.plugin_name} 开始监控目录: {self._monitor_dirs}")
        
        while self._running:
            try:
                # 遍历所有监控目录
                for monitor_dir in self._monitor_dirs:
                    if not os.path.exists(monitor_dir):
                        continue
                        
                    # 扫描目录中的所有文件
                    for filename in os.listdir(monitor_dir):
                        file_path = os.path.join(monitor_dir, filename)
                        
                        # 跳过目录
                        if os.path.isdir(file_path):
                            continue
                        
                        # 检查文件是否已处理过
                        if file_path in self._processed_files:
                            continue
                        
                        # 获取文件扩展名
                        _, file_ext = os.path.splitext(filename)
                        ext = file_ext.lstrip(".").lower()
                        
                        # 处理字幕文件
                        if ext in sub_extensions:
                            logger.info(f"发现新的字幕文件: {filename}")
                            success, msg = self._renamer.rename_subtitle(
                                sub_path=file_path,
                                monitor_dir=monitor_dir,
                                video_exts=video_extensions
                            )
                            
                            # 发送通知
                            if success and self._current_config.notify:
                                self.post_message(
                                    mtype=NotificationType.Plugin,
                                    title=f"【{self.plugin_name}】字幕重命名",
                                    text=msg
                                )
                            
                            self._processed_files.add(file_path)
                
                # 每30秒扫描一次
                time.sleep(30)
                
            except Exception as e:
                logger.error(f"{self.plugin_name} 监控线程发生错误: {str(e)}")
                time.sleep(60)
