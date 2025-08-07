import os
import time
import threading
import logging
import re
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

from app.plugins import _PluginBase
from app.schemas.types import EventType, SystemConfigKey, NotificationType
from app.core.config import settings
from app.core.event import eventmanager, Event
from app.db.systemconfig_oper import SystemConfigOper
from app.log import logger

@dataclass
class PluginConfigModel:
    """插件配置模型"""
    enabled: bool = False
    notify: bool = False
    onlyonce: bool = False
    monitor_dirs: str = ""
    video_exts: str = "mp4,mkv,avi,ts"
    sub_exts: str = "ass,ssa,srt"
    recursive: bool = True  # 新增：是否递归监控子目录

class SubtitleRenamer:
    """字幕文件重命名工具（优化版）"""
    
    def rename_subtitle(self, sub_path: str, video_exts: List[str]) -> Tuple[bool, str]:
        """
        重命名字幕文件 - 只处理同一目录下的文件
        
        :param sub_path: 字幕文件路径
        :param video_exts: 视频文件扩展名列表
        :return: (是否成功, 消息)
        """
        # 获取字幕文件所在目录
        dir_path = os.path.dirname(sub_path)
        sub_name = os.path.basename(sub_path)
        sub_base, sub_ext = os.path.splitext(sub_name)
        
        # 提取字幕文件中的季集信息
        sub_episode = self.extract_episode_info(sub_base)
        if not sub_episode:
            msg = f"字幕文件 {sub_name} 中未找到季集信息"
            logger.info(msg)
            return False, msg
            
        # 在同一个目录中查找匹配的视频文件
        video_file = self.find_matching_video(dir_path, video_exts, sub_episode)
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
        new_sub_path = os.path.join(dir_path, new_sub_name)
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
        """提取季集信息（优化匹配模式）"""
        # 增强匹配模式：支持S01E01、S1E1、Season01Episode01等格式
        patterns = [
            r"[sS](?:eason)?\s*(\d{1,2})\s*[eE](?:pisode)?\s*(\d{1,2})",  # S01E01
            r"(\d{1,2})[xX](\d{1,2})",  # 01x01
            r"[sS](\d{1,2})[eE](\d{1,2})",  # S01E01（简写）
        ]
        
        for pattern in patterns:
            match = re.search(pattern, filename)
            if match:
                season = match.group(1).zfill(2)  # 补齐为两位数
                episode = match.group(2).zfill(2)
                return f"S{season}E{episode}"
        
        return None
    
    def find_matching_video(self, directory: str, video_exts: List[str], episode: str) -> Optional[str]:
        """
        在同一个目录中查找匹配的视频文件
        
        :param directory: 目录路径
        :param video_exts: 视频扩展名列表
        :param episode: 季集信息
        :return: 匹配的视频文件名
        """
        for filename in os.listdir(directory):
            file_path = os.path.join(directory, filename)
            
            # 跳过目录
            if os.path.isdir(file_path):
                continue
                
            # 检查文件扩展名
            _, file_ext = os.path.splitext(filename)
            ext = file_ext.lstrip(".").lower()
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
    
    def generate_new_sub_name(self, video_file: str, sub_ext: str) -> str:
        """生成新的字幕文件名（保持原视频文件名）"""
        # 获取视频文件的主文件名（不含扩展名）
        video_base = os.path.splitext(video_file)[0]
        
        # 生成新的字幕文件名（保留原语言标记如.chs等）
        if ".chs" in video_base or ".cht" in video_base or ".eng" in video_base:
            return f"{video_base}{sub_ext}"
        else:
            return f"{video_base}.chs{sub_ext}"  # 默认添加简体中文标记

class AutoSubRename(_PluginBase):
    plugin_name = "字幕自动重命名"
    plugin_desc = "自动重命名匹配的剧集字幕文件"
    plugin_icon = "rename.png"
    plugin_version = "1.0.0"
    plugin_author = "xdormaelx"
    plugin_author_url = ""
    plugin_order = 1
    reusable = True
    
    def __init__(self):
        self._config_model = PluginConfigModel
        self._config_key = f"{self.plugin_name}:config"
        self._current_config = self._get_config()
        self._monitor_dirs = []
        self._thread = None
        self._running = False
        self._renamer = SubtitleRenamer()
        self._processed_files = set()
    
    def _get_config(self) -> PluginConfigModel:
        config_data = SystemConfigOper().get(self._config_key)
        if not config_data:
            return self._config_model()
        
        return PluginConfigModel(
            enabled=config_data.get("enabled", False),
            notify=config_data.get("notify", False),
            onlyonce=config_data.get("onlyonce", False),
            monitor_dirs=config_data.get("monitor_dirs", ""),
            video_exts=config_data.get("video_exts", "mp4,mkv,avi,ts"),
            sub_exts=config_data.get("sub_exts", "ass,ssa,srt"),
            recursive=config_data.get("recursive", True)  # 默认递归监控
        )
    
    def init_plugin(self, config: Dict = None):
        if config:
            self._current_config = PluginConfigModel(
                enabled=config.get("enabled", False),
                notify=config.get("notify", False),
                onlyonce=config.get("onlyonce", False),
                monitor_dirs=config.get("monitor_dirs", ""),
                video_exts=config.get("video_exts", "mp4,mkv,avi,ts"),
                sub_exts=config.get("sub_exts", "ass,ssa,srt"),
                recursive=config.get("recursive", True)
            )
            self.__update_config()
        
        self._monitor_dirs = [d.strip() for d in self._current_config.monitor_dirs.split("\n") if d.strip()]
        self.stop_service()
        
        if self._current_config.onlyonce:
            logger.info("执行立即运行一次")
            self.batch_rename()
            self._current_config.onlyonce = False
            self.__update_config()
        
        if self._current_config.enabled and self._monitor_dirs:
            self.start_service()
    
    def __update_config(self):
        config_data = {
            "enabled": self._current_config.enabled,
            "notify": self._current_config.notify,
            "onlyonce": self._current_config.onlyonce,
            "monitor_dirs": self._current_config.monitor_dirs,
            "video_exts": self._current_config.video_exts,
            "sub_exts": self._current_config.sub_exts,
            "recursive": self._current_config.recursive
        }
        SystemConfigOper().set(self._config_key, config_data)
    
    def start_service(self):
        if self._running:
            return
            
        logger.info(f"{self.plugin_name} 启动监控服务...")
        self._running = True
        self._thread = threading.Thread(target=self.__monitor_files)
        self._thread.daemon = True
        self._thread.start()
        logger.info(f"监控模式: {'递归所有子目录' if self._current_config.recursive else '仅监控根目录'}")
    
    def batch_rename(self):
        if not self._monitor_dirs:
            logger.warning("未配置监控目录，无法执行批量重命名")
            return
            
        logger.info("开始批量重命名字幕文件...")
        video_extensions = [ext.strip().lower() for ext in self._current_config.video_exts.split(",")]
        sub_extensions = [ext.strip().lower() for ext in self._current_config.sub_exts.split(",")]
        
        results = []
        processed_count = 0
        
        for monitor_dir in self._monitor_dirs:
            if not os.path.exists(monitor_dir):
                logger.warning(f"监控目录不存在: {monitor_dir}")
                continue
                
            # 根据递归设置选择遍历方式
            if self._current_config.recursive:
                file_generator = self.__recursive_file_generator(monitor_dir)
            else:
                file_generator = [(monitor_dir, filename) for filename in os.listdir(monitor_dir)]
            
            for dir_path, filename in file_generator:
                file_path = os.path.join(dir_path, filename)
                
                if os.path.isdir(file_path):
                    continue
                
                _, file_ext = os.path.splitext(filename)
                ext = file_ext.lstrip(".").lower()
                
                if ext in sub_extensions:
                    # 只处理同一目录下的文件
                    success, msg = self._renamer.rename_subtitle(
                        sub_path=file_path,
                        video_exts=video_extensions
                    )
                    results.append(msg)
                    if success:
                        processed_count += 1
        
        # 发送通知
        if self._current_config.notify:
            summary = f"批量重命名完成: 处理了 {processed_count} 个字幕文件"
            self.post_message(
                mtype=NotificationType.Plugin,
                title=f"【{self.plugin_name}】批量重命名结果",
                text=f"{summary}\n\n详细结果:\n" + "\n".join(results[:10]) + ("\n..." if len(results) > 10 else "")
            )
        
        logger.info(f"批量重命名完成，处理了 {processed_count} 个字幕文件")
    
    def __recursive_file_generator(self, base_dir: str):
        """递归生成器：遍历所有子目录中的文件"""
        for root, _, files in os.walk(base_dir):
            for filename in files:
                yield root, filename
    
    def __monitor_files(self):
        """文件监控线程（支持递归）"""
        video_extensions = [ext.strip().lower() for ext in self._current_config.video_exts.split(",")]
        sub_extensions = [ext.strip().lower() for ext in self._current_config.sub_exts.split(",")]
        
        logger.info(f"开始监控目录: {self._monitor_dirs}")
        
        while self._running:
            try:
                # 遍历所有监控目录
                for monitor_dir in self._monitor_dirs:
                    if not os.path.exists(monitor_dir):
                        continue
                        
                    # 根据递归设置选择遍历方式
                    if self._current_config.recursive:
                        file_generator = self.__recursive_file_generator(monitor_dir)
                    else:
                        file_generator = [(monitor_dir, filename) for filename in os.listdir(monitor_dir)]
                    
                    for dir_path, filename in file_generator:
                        if not self._running:
                            return
                            
                        file_path = os.path.join(dir_path, filename)
                        
                        # 跳过目录
                        if os.path.isdir(file_path):
                            continue
                        
                        # 跳过已处理文件
                        if file_path in self._processed_files:
                            continue
                        
                        # 检查文件扩展名
                        _, file_ext = os.path.splitext(filename)
                        ext = file_ext.lstrip(".").lower()
                        
                        # 处理字幕文件
                        if ext in sub_extensions:
                            logger.info(f"发现新的字幕文件: {file_path}")
                            success, msg = self._renamer.rename_subtitle(
                                sub_path=file_path,
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
                for _ in range(30):
                    if not self._running:
                        return
                    time.sleep(1)
                
            except Exception as e:
                logger.error(f"监控线程发生错误: {str(e)}")
                time.sleep(60)
    
    # 其余方法保持不变（get_form, stop_service等）...
    
    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        return [
            {
                "component": "VForm",
                "content": [
                    # ... 其他配置项 ...
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "recursive",
                                            "label": "递归监控子目录",
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
            "sub_exts": self._current_config.sub_exts,
            "recursive": self._current_config.recursive  # 新增递归选项
        }
