from typing import Any, List, Dict, Tuple
from app.core.event import eventmanager, Event
from app.schemas.types import EventType
from app.plugins import _PluginBase
from app.log import logger
from pathlib import Path
import subprocess
import re
import os


class TrailerDownloader(_PluginBase):
    # 插件名称
    plugin_name = "预告片自动下载"
    # 插件描述
    plugin_desc = "电影入库后自动从 YouTube 下载预告片"
    # 插件版本
    plugin_version = "1.0"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/jxxghp/MoviePilot-Plugins/main/icons/movie.png"
    # 插件作者
    plugin_author = "User"
    # 作者主页
    author_url = ""
    # 插件配置项ID前缀
    plugin_config_prefix = "trailerdownloader_"
    # 加载顺序
    plugin_order = 1
    # 可使用的用户级别
    auth_level = 1

    # 私有属性
    _enabled = False
    _max_size_mb = 100
    _video_quality = "best[height<=1080]"
    _skip_existing = True
    _trailer_language = "zh"  # 预告片语言: zh/en/any
    _source = "youtube"  # 来源: youtube/tmdb
    _proxy = ""  # 代理地址，空则使用系统代理
    _monitor_paths = ""  # 监控路径，多个用逗号分隔，空则监控所有
    _enable_schedule = False  # 启用定时扫描
    _schedule_time = "03:00"  # 定时扫描时间

    def init_plugin(self, config: dict = None):
        """初始化插件"""
        if config:
            self._enabled = config.get("enabled", False)
            self._max_size_mb = config.get("max_size_mb", 100)
            self._video_quality = config.get("video_quality", "best[height<=1080]")
            self._skip_existing = config.get("skip_existing", True)
            self._trailer_language = config.get("trailer_language", "zh")
            self._source = config.get("source", "youtube")
            self._proxy = config.get("proxy", "")
            self._monitor_paths = config.get("monitor_paths", "")
            self._enable_schedule = config.get("enable_schedule", False)
            self._schedule_time = config.get("schedule_time", "03:00")

        if self._enabled:
            logger.info(f"预告片自动下载插件已启用，语言: {self._trailer_language}, 来源: {self._source}")
            if self._enable_schedule:
                logger.info(f"定时扫描已启用，时间: {self._schedule_time}")

    def get_state(self) -> bool:
        """获取插件状态"""
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """注册插件命令"""
        pass

    def get_api(self) -> List[Dict[str, Any]]:
        """注册插件API"""
        pass

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """获取插件配置表单"""
        return [
            {
                'component': 'VForm',
                'content': [
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
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
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'skip_existing',
                                            'label': '跳过已存在的预告片',
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VSelect',
                                        'props': {
                                            'model': 'trailer_language',
                                            'label': '预告片语言',
                                            'items': [
                                                {'title': '中文优先', 'value': 'zh'},
                                                {'title': '英文优先', 'value': 'en'},
                                                {'title': '不限制', 'value': 'any'}
                                            ]
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VSelect',
                                        'props': {
                                            'model': 'source',
                                            'label': '下载来源',
                                            'items': [
                                                {'title': 'YouTube', 'value': 'youtube'},
                                                {'title': 'TMDb (实验性)', 'value': 'tmdb'}
                                            ]
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VSelect',
                                        'props': {
                                            'model': 'video_quality',
                                            'label': '视频质量',
                                            'items': [
                                                {'title': '最佳质量', 'value': 'best'},
                                                {'title': '1080p', 'value': 'best[height<=1080]'},
                                                {'title': '720p', 'value': 'best[height<=720]'}
                                            ]
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'max_size_mb',
                                            'label': '最大文件大小 (MB)',
                                            'placeholder': '100',
                                            'type': 'number'
                                        }
                                    }
                                ]
                            }
                        ]
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
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'proxy',
                                            'label': '代理地址 (可选)',
                                            'placeholder': 'http://192.168.1.1:7890，留空使用系统代理'
                                        }
                                    }
                                ]
                            }
                        ]
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
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'monitor_paths',
                                            'label': '监控路径 (可选)',
                                            'placeholder': '/nas/电影,/nas/Movies，留空监控所有电影'
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'enable_schedule',
                                            'label': '启用定时全库扫描',
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'schedule_time',
                                            'label': '扫描时间',
                                            'placeholder': '03:00'
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ], {
            "enabled": self._enabled,
            "max_size_mb": self._max_size_mb,
            "video_quality": self._video_quality,
            "skip_existing": self._skip_existing,
            "trailer_language": self._trailer_language,
            "source": self._source,
            "proxy": self._proxy,
            "monitor_paths": self._monitor_paths,
            "enable_schedule": self._enable_schedule,
            "schedule_time": self._schedule_time
        }

    def get_page(self) -> List[dict]:
        """获取插件页面"""
        pass

    def stop_service(self):
        """停止插件"""
        self._enabled = False

    @eventmanager.register(EventType.TransferComplete)
    def download_trailer(self, event: Event):
        """
        监听转移完成事件，自动下载预告片
        """
        if not self._enabled:
            return

        event_data = event.event_data
        if not event_data:
            return

        # 获取转移后的文件路径
        file_path = event_data.get("file_path")
        file_name = event_data.get("file_name")
        media_type = event_data.get("media_type")

        # 只处理电影
        if media_type != "电影":
            logger.info(f"跳过非电影类型: {media_type}")
            return

        if not file_path:
            logger.warning("未获取到文件路径")
            return

        # 获取电影文件夹路径
        movie_folder = Path(file_path).parent
        
        # 检查是否在监控路径内
        if not self._is_path_monitored(movie_folder):
            logger.info(f"路径不在监控范围内，跳过: {movie_folder}")
            return
        
        # 检查是否已存在预告片
        if self._skip_existing and self._check_existing_trailer(movie_folder):
            logger.info(f"预告片已存在，跳过: {movie_folder.name}")
            return

        # 获取电影名称
        movie_name = self._get_movie_name(movie_folder, file_name)
        
        logger.info(f"开始下载预告片: {movie_name}")
        
        # 下载预告片
        success = self._download_trailer(movie_folder, movie_name)
        
        if success:
            logger.info(f"预告片下载成功: {movie_name}")
        else:
            logger.warning(f"预告片下载失败: {movie_name}")

    def _is_path_monitored(self, path: Path) -> bool:
        """检查路径是否在监控范围内"""
        if not self._monitor_paths:
            return True  # 未设置则监控所有
        
        monitored_paths = [p.strip() for p in self._monitor_paths.split(",")]
        path_str = str(path)
        
        for monitored in monitored_paths:
            if monitored in path_str:
                return True
        return False

    def _check_existing_trailer(self, folder: Path) -> bool:
        """检查是否已存在预告片"""
        trailer_patterns = ['-trailer', '_trailer', ' trailer', '预告片', '预告']
        video_extensions = {'.mp4', '.mkv', '.avi', '.mov'}
        
        for file in folder.iterdir():
            if file.is_file():
                file_lower = file.name.lower()
                if any(pattern in file_lower for pattern in trailer_patterns):
                    if file.suffix.lower() in video_extensions:
                        return True
        return False

    def _get_movie_name(self, folder: Path, file_name: str = None) -> str:
        """从文件夹名或文件名提取电影名称"""
        # 优先使用文件夹名
        folder_name = folder.name
        
        # 清理名称（移除年份、分辨率等）
        clean_name = re.sub(r'[\(\[\.\s]\d{4}[\)\]\.\s].*$', '', folder_name)
        clean_name = re.sub(r'[\(\[\s]\d{3,4}[pP][\)\]\s].*$', '', clean_name)
        clean_name = re.sub(r'[\.\-_]', ' ', clean_name)
        clean_name = clean_name.strip()
        
        return clean_name or folder_name

    def _download_trailer(self, movie_folder: Path, movie_name: str) -> bool:
        """使用 yt-dlp 下载预告片"""
        # 预告片文件名
        trailer_file = movie_folder / f"{movie_folder.name}-trailer.mp4"
        
        # 根据语言设置搜索词
        lang_suffix = ""
        if self._trailer_language == "zh":
            lang_suffix = " 中文预告片"
        elif self._trailer_language == "en":
            lang_suffix = " official trailer"
        else:
            lang_suffix = " trailer"
        
        search_query = f"{movie_name}{lang_suffix}"
        
        # yt-dlp 命令
        cmd = [
            "yt-dlp",
            "--search-terms", search_query,
            "--format", self._video_quality,
            "--max-filesize", f"{self._max_size_mb}M",
            "--output", str(trailer_file),
            "--merge-output-format", "mp4",
            "--no-playlist",
            "--no-warnings",
            "--quiet",
            "--match-filter", "duration < 300",  # 小于5分钟
        ]
        
        # 添加代理
        if self._proxy:
            cmd.extend(["--proxy", self._proxy])
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode == 0 and trailer_file.exists():
                size_mb = trailer_file.stat().st_size / (1024 * 1024)
                logger.info(f"预告片下载成功: {movie_name} ({size_mb:.1f}MB)")
                return True
            else:
                error_msg = result.stderr[:200] if result.stderr else "未知错误"
                logger.error(f"下载失败: {movie_name} - {error_msg}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error(f"下载超时: {movie_name}")
            return False
        except Exception as e:
            logger.error(f"下载异常: {movie_name} - {str(e)}")
            return False
