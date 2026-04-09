from typing import Any, List, Dict, Tuple
from app.core.event import eventmanager, Event
from app.schemas.types import EventType
from app.plugins import _PluginBase
from app.log import logger
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
import re


class TrailerDownloader(_PluginBase):
    # 插件名称
    plugin_name = "预告片自动下载"
    # 插件描述
    plugin_desc = "电影入库后自动从 YouTube 下载预告片，支持定时全库扫描"
    # 插件版本
    plugin_version = "2.1"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/jxxghp/MoviePilot-Plugins/main/icons/movie.png"
    # 插件作者
    plugin_author = "zacklee"
    # 作者主页
    author_url = "https://github.com/zacklee111/moviepilot-trailer-plugin"
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
    _trailer_language = "zh"
    _source = "youtube"
    _proxy = ""
    _monitor_paths = ""
    _enable_schedule = False
    _schedule_time = "03:00"
    _scheduler = None
    _scanning = False  # 防止重复扫描

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
        
        # 调试日志
        logger.info(f"代理配置: {self._proxy or '未设置'}")

        # 取消之前的定时任务
        self._cancel_schedule()
        
        if self._enabled:
            logger.info(f"预告片自动下载插件已启用，语言: {self._trailer_language}, 来源: {self._source}")

    def get_state(self) -> bool:
        """获取插件状态"""
        return self._enabled

    @eventmanager.register(EventType.PluginAction)
    def handle_action(self, event: Event):
        """处理插件命令"""
        if not event or not event.event_data:
            return
        action = event.event_data.get("action")
        if action == "trailer_scan":
            self._trigger_scan()

    def _trigger_scan(self):
        """触发扫描"""
        if not self._enabled:
            logger.warning("插件未启用，无法扫描")
            return
        if self._scanning:
            logger.info("正在扫描中，跳过本次请求")
            return
        logger.info("收到手动扫描指令，开始扫描...")
        ThreadPoolExecutor(max_workers=1).submit(self._scan_all_movies)

    def get_api(self) -> List[Dict[str, Any]]:
        """
        注册 API 路由（本插件不使用）
        """
        return []

    def get_service(self) -> List[Dict[str, Any]]:
        """
        注册定时服务
        """
        if not self._enabled or not self._enable_schedule or not self._schedule_time:
            return []

        try:
            parts = self._schedule_time.strip().split(":")
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
            cron_expr = f"{minute} {hour} * * *"
            return [{
                "id": "TrailerDownloaderScan",
                "name": "预告片全库扫描",
                "trigger": CronTrigger.from_crontab(cron_expr),
                "func": self._scan_all_movies,
                "kwargs": {}
            }]
        except Exception as e:
            logger.error(f"定时任务配置解析失败: {self._schedule_time} - {e}")
            return []

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """获取插件配置表单"""
        return [
            {
                'component': 'VForm',
                'content': [
                    # 第一行：启用开关和语言选择
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 4},
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {'model': 'enabled', 'label': '启用插件'}
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 4},
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {'model': 'skip_existing', 'label': '跳过已存在的预告片'}
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 4},
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
                    # 第二行：来源、质量、大小
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 4},
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
                                'props': {'cols': 12, 'md': 4},
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
                                'props': {'cols': 12, 'md': 4},
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
                    # 第三行：代理设置
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12},
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
                    # 第四行：监控路径
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12},
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
                    # 第五行：定时设置
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 6},
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {'model': 'enable_schedule', 'label': '启用定时全库扫描'}
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {'cols': 12, 'md': 6},
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
                    },
                    # 第六行：立即扫描按钮
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {'cols': 12},
                                'content': [
                                    {
                                        'component': 'VAlert',
                                        'props': {
                                            'type': 'info',
                                            'variant': 'tonal',
                                            'text': '点击下方按钮立即扫描所有电影文件夹并下载预告片'
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
                                'props': {'cols': 12, 'class': 'text-center'},
                                'content': [
                                    {
                                        'component': 'VBtn',
                                        'props': {
                                            'color': 'primary',
                                            'block': True,
                                            'max-width': 300,
                                            'href': '/movie',
                                            'target': '_blank'
                                        },
                                        'content': [
                                            {
                                                'component': 'VIcon',
                                                'props': {'start': True},
                                                'text': 'mdi-movie-search'
                                            },
                                            {
                                                'component': 'span',
                                                'text': '🚀 立即扫描全库'
                                            }
                                        ]
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
        return []

    def stop_service(self):
        """停止插件"""
        self._enabled = False
        self._cancel_schedule()

    def _cancel_schedule(self):
        """取消定时任务"""
        try:
            if self._scheduler:
                self._scheduler.shutdown(wait=False)
                self._scheduler = None
        except Exception:
            pass

    def _scan_all_movies(self):
        """扫描所有电影文件夹"""
        if self._scanning:
            logger.info("正在扫描中，跳过本次扫描")
            return
            
        self._scanning = True
        logger.info("开始全库扫描电影文件夹...")
        
        try:
            if not self._monitor_paths:
                logger.warning("未设置监控路径，请先在插件设置中配置监控路径！")
                return
            
            scan_paths = [p.strip() for p in self._monitor_paths.split(",")]
            
            logger.info(f"开始全库扫描，共 {len(scan_paths)} 个路径...")
            
            total = 0
            success = 0
            skip = 0
            
            for scan_path in scan_paths:
                if not scan_path:
                    continue
                base_path = Path(scan_path)
                if not base_path.exists():
                    logger.warning(f"路径不存在: {scan_path}")
                    continue
                
                logger.info(f"扫描路径: {scan_path}")
                # 遍历所有子文件夹（递归）
                try:
                    for folder in base_path.rglob("*"):  # 递归扫描所有子文件夹
                        if folder.is_dir():
                            total += 1
                            result = self._process_movie_folder(folder)
                            if result == "success":
                                success += 1
                            elif result == "skip":
                                skip += 1
                except Exception as e:
                    logger.error(f"扫描路径失败: {scan_path} - {str(e)}")
            
            logger.info(f"全库扫描完成！共处理 {total} 个文件夹，成功 {success}，跳过 {skip}")
        finally:
            self._scanning = False

    def manual_scan(self, event: Event = None):
        """手动扫描命令"""
        if self._scanning:
            logger.info("正在扫描中，忽略重复请求")
            return
        # 在新线程中执行
        with ThreadPoolExecutor(max_workers=1) as executor:
            executor.submit(self._scan_all_movies)

    @eventmanager.register(EventType.TransferComplete)
    def download_trailer(self, event: Event):
        """监听转移完成事件，自动下载预告片"""
        if not self._enabled:
            return

        event_data = event.event_data
        if not event_data:
            return

        file_path = event_data.get("file_path")
        file_name = event_data.get("file_name")
        media_type = event_data.get("media_type")

        # 如果 media_type 是 None，检查文件是否是视频
        if media_type is None:
            if file_path:
                ext = Path(file_path).suffix.lower()
                video_exts = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.m4v'}
                if ext not in video_exts:
                    return
            else:
                return

        if not file_path:
            return

        movie_folder = Path(file_path).parent
        
        if not self._is_path_monitored(movie_folder):
            return
        
        if self._skip_existing and self._check_existing_trailer(movie_folder):
            return

        movie_name = self._get_movie_name(movie_folder, file_name)
        
        logger.info(f"开始下载预告片: {movie_name}")
        
        success = self._download_trailer(movie_folder, movie_name)
        
        if success:
            logger.info(f"预告片下载成功: {movie_name}")
        else:
            logger.warning(f"预告片下载失败: {movie_name}")

    def _process_movie_folder(self, folder: Path) -> str:
        """
        处理单个电影文件夹
        返回: "success", "skip", "error"
        """
        if not folder.is_dir():
            return "error"
        
        # 检查是否在监控路径内
        if not self._is_path_monitored(folder):
            return "skip"
        
        # 检查是否已存在预告片
        if self._skip_existing and self._check_existing_trailer(folder):
            logger.debug(f"预告片已存在，跳过: {folder.name}")
            return "skip"
        
        # 检查是否有视频文件
        video_files = self._get_video_files(folder)
        if not video_files:
            return "skip"
        
        movie_name = self._get_movie_name(folder)
        
        logger.info(f"扫描到电影，准备下载预告片: {movie_name}")
        
        success = self._download_trailer(folder, movie_name)
        
        if success:
            logger.info(f"预告片下载成功: {movie_name}")
            return "success"
        else:
            logger.warning(f"预告片下载失败: {movie_name}")
            return "error"

    def _get_video_files(self, folder: Path) -> List[Path]:
        """获取文件夹中的视频文件"""
        video_extensions = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.m4v', '.ts', '.m2ts'}
        videos = []
        try:
            for file in folder.iterdir():
                if file.is_file() and file.suffix.lower() in video_extensions:
                    videos.append(file)
        except Exception as e:
            logger.error(f"扫描文件夹失败: {folder} - {str(e)}")
        return videos

    def _is_path_monitored(self, path: Path) -> bool:
        """检查路径是否在监控范围内"""
        if not self._monitor_paths:
            return True
        
        monitored_paths = [p.strip() for p in self._monitor_paths.split(",")]
        path_str = str(path)
        
        for monitored in monitored_paths:
            if monitored and monitored in path_str:
                return True
        return False

    def _check_existing_trailer(self, folder: Path) -> bool:
        """检查是否已存在预告片"""
        trailer_patterns = ['-trailer', '_trailer', ' trailer', '预告片', '预告']
        video_extensions = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.m4v'}
        
        try:
            for file in folder.iterdir():
                if file.is_file():
                    file_lower = file.name.lower()
                    if any(pattern in file_lower for pattern in trailer_patterns):
                        if file.suffix.lower() in video_extensions:
                            return True
        except Exception as e:
            logger.error(f"检查预告片失败: {str(e)}")
        return False

    def _get_movie_name(self, folder: Path, file_name: str = None) -> str:
        """从文件夹名或文件名提取电影名称"""
        folder_name = folder.name
        
        # 清理名称
        clean_name = re.sub(r'[\(\[\.\s]\d{4}[\)\]\.\s].*$', '', folder_name)
        clean_name = re.sub(r'[\(\[\s]\d{3,4}[pP][\)\]\s].*$', '', clean_name)
        clean_name = re.sub(r'[\.\-_]', ' ', clean_name)
        clean_name = clean_name.strip()
        
        return clean_name or folder_name

    def _download_trailer(self, movie_folder: Path, movie_name: str) -> bool:
        """使用 yt-dlp 下载预告片"""
        trailer_file = movie_folder / f"{movie_folder.name}-trailer.mp4"
        
        # 语言设置
        lang_suffix = ""
        if self._trailer_language == "zh":
            lang_suffix = " 中文预告片"
        elif self._trailer_language == "en":
            lang_suffix = " official trailer"
        else:
            lang_suffix = " trailer"
        
        search_query = f"{movie_name}{lang_suffix}"
        
        # yt-dlp 命令 - 使用 ytsearch1: 进行搜索，只取第一个结果
        cmd = [
            "yt-dlp",
            "--flat-playlist",  # 只处理播放列表第一个视频
            "--no-playlist",
            "--quiet",
            "--no-warnings",
            "--match-filter", "duration < 300",
            "--max-filesize", f"{self._max_size_mb}M",
            "-f", self._video_quality,
            "-o", str(trailer_file),
            "--", f"ytsearch1:{search_query}"
        ]
        
        # 设置代理
        import os
        env = os.environ.copy()
        if self._proxy:
            # 用户手动填写了代理，优先使用
            cmd.extend(["--proxy", self._proxy])
            env["HTTP_PROXY"] = self._proxy
            env["HTTPS_PROXY"] = self._proxy
            env["http_proxy"] = self._proxy
            env["https_proxy"] = self._proxy
            logger.info(f"使用手动代理: {self._proxy}")
        else:
            # 未填写代理，检查系统环境变量
            sys_proxy = (env.get("HTTP_PROXY") or env.get("http_proxy") or
                         env.get("HTTPS_PROXY") or env.get("https_proxy") or "")
            if sys_proxy:
                cmd.extend(["--proxy", sys_proxy])
                logger.info(f"使用系统代理: {sys_proxy}")
            else:
                logger.warning("未设置任何代理，直连可能失败")
        
        try:
            logger.info(f"正在搜索下载: {search_query}")
            # 调试：打印完整命令
            logger.debug(f"执行命令: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                env=env
            )
            
            if result.returncode == 0 and trailer_file.exists():
                size_mb = trailer_file.stat().st_size / (1024 * 1024)
                logger.info(f"预告片下载成功: {movie_name} ({size_mb:.1f}MB)")
                return True
            else:
                error_msg = result.stderr[:300] if result.stderr else "未知错误"
                logger.error(f"下载失败: {movie_name} - {error_msg}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error(f"下载超时: {movie_name}")
            return False
        except Exception as e:
            logger.error(f"下载异常: {movie_name} - {str(e)}")
            return False
