# -*- coding: utf-8 -*-
"""
音乐搜索��播放模块
支持咪咕音乐搜索（使用公开API）
基于 MusicN 项目 API 重写为 Python 版本
"""
import asyncio
import logging
import aiohttp
import os
import json
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from urllib.parse import quote, unquote, urlparse
import re
import hashlib
import time

logger = logging.getLogger(__name__)


@dataclass
class SongInfo:
    """歌曲信息"""
    name: str              # 歌曲名称
    artists: str           # 歌手
    url: str               # 播放链接
    cover: Optional[str]   # 封面图
    song_id: str           # 歌曲ID
    size: int = 0          # 文件大小
    duration: Optional[int] = None  # 时长(秒)
    source: str = "migu"   # 来源

    def __str__(self):
        return f"{self.artists} - {self.name}"


@dataclass
class DownloadInfo:
    """下载信息"""
    url: str
    file_type: str = "mp3"
    size: int = 0


def _remove_punctuation(text: str) -> str:
    return re.sub(r"[.?/#|$%\\^&*;:{}+=_`'\"~<>]", "", text).strip()


def _join_singers_name(singers: List[Dict[str, Any]]) -> str:
    names = [s.get("name", "") for s in singers if s.get("name")]
    return ",".join(names)


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|]", "_", name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or "unknown"


def _unique_path(dir_path: str, filename: str) -> str:
    base, ext = os.path.splitext(filename)
    candidate = os.path.join(dir_path, filename)
    index = 1
    while os.path.exists(candidate):
        candidate = os.path.join(dir_path, f"{base}({index}){ext}")
        index += 1
    return candidate


def _looks_like_html(chunk: bytes) -> bool:
    probe = chunk.lstrip().lower()
    return probe.startswith(b"<!doctype html") or probe.startswith(b"<html") or b"<head" in probe


async def _read_json_response(resp: aiohttp.ClientResponse) -> Dict[str, Any]:
    try:
        return await resp.json(content_type=None)
    except Exception:
        text = await resp.text()
        return json.loads(text)


class MusicSearcher:
    """
    音乐搜索器
    使用咪咕音乐公开API
    """

    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建 HTTP 会话"""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            connector = aiohttp.TCPConnector(limit=5, ssl=False)
            self._session = aiohttp.ClientSession(timeout=timeout, connector=connector)
        return self._session

    async def close(self):
        """关闭会话"""
        if self._session and not self._session.closed:
            await self._session.close()

    async def _fetch_resource_info(self, copyright_id: str, resource_type: int) -> Optional[Dict[str, Any]]:
        session = await self._get_session()
        detail_url = (
            f"https://c.musicapp.migu.cn/MIGUM2.0/v1.0/content/resourceinfo.do"
            f"?copyrightId={copyright_id}"
            f"&resourceType={resource_type}"
        )
        headers = {
            "User-Agent": "okhttp/3.10.0",
            "Referer": "http://music.migu.cn/",
        }

        async with session.get(detail_url, headers=headers) as resp:
            if resp.status != 200:
                logger.error(f"[MIGU] 获取资源信息失败: HTTP {resp.status}")
                return None
            return await resp.json()

    @staticmethod
    def _parse_int(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _file_type_from_url(url: str) -> str:
        match = re.search(r"\.(mp3|flac|wav)$", url, re.IGNORECASE)
        return match.group(1).lower() if match else "mp3"

    @staticmethod
    def _build_freetyst_url(raw_url: str, upgrade_quality: bool = False) -> Optional[str]:
        if not raw_url:
            return None
        parsed = urlparse(raw_url)
        pathname = unquote(parsed.path)
        if not pathname:
            return None
        if upgrade_quality:
            pathname = pathname.replace("彩铃/6_mp3-128kbps", "标清高清/MP3_320_16_Stero")
        return f"https://freetyst.nf.migu.cn{pathname}"

    def _extract_download_info(self, detail: Optional[Dict[str, Any]]) -> Optional[DownloadInfo]:
        if not detail:
            return None
        resource_list = detail.get("resource") or []
        if not resource_list:
            return None

        resource = resource_list[0] or {}
        rate_formats = resource.get("newRateFormats") or resource.get("rateFormats") or []
        if isinstance(rate_formats, list) and rate_formats:
            fmt = rate_formats[-1] or {}
            raw_url = fmt.get("url") or fmt.get("androidUrl")
            if raw_url:
                download_url = self._build_freetyst_url(raw_url)
                if download_url:
                    file_type = (
                        fmt.get("fileType")
                        or fmt.get("androidFileType")
                        or self._file_type_from_url(raw_url)
                    )
                    size = self._parse_int(fmt.get("size") or fmt.get("androidSize"))
                    return DownloadInfo(url=download_url, file_type=file_type, size=size)

        audio_url = resource.get("audioUrl")
        if audio_url:
            download_url = self._build_freetyst_url(audio_url, upgrade_quality=True)
            if download_url:
                return DownloadInfo(
                    url=download_url,
                    file_type=self._file_type_from_url(audio_url),
                    size=0,
                )

        return None

    async def search_migu(self, text: str, page_num: int = 1, page_size: int = 20) -> List[SongInfo]:
        """
        搜索咪咕音乐
        API: https://pd.musicapp.migu.cn/MIGUM3.0/v1.0/content/search_all.do
        """
        session = await self._get_session()
        songs = []

        try:
            url = (
                f"https://pd.musicapp.migu.cn/MIGUM3.0/v1.0/content/search_all.do"
                f"?text={quote(text)}"
                f"&pageNo={page_num}"
                f"&pageSize={page_size}"
                f"&searchSwitch=%7Bsong%3A1%7D"
            )

            headers = {
                "User-Agent": "okhttp/3.10.0",
                "Referer": "http://music.migu.cn/",
                "Accept": "application/json",
            }

            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    logger.error(f"[MIGU] 搜索失败: HTTP {resp.status}")
                    return []

                data = await resp.json()

            song_result_data = data.get("songResultData", {})
            result_list = song_result_data.get("result", [])

            if not result_list:
                logger.warning(f"[MIGU] 未找到歌曲: {text}")
                return []

            total_count = song_result_data.get("totalCount", "0")
            logger.info(f"[MIGU] 搜索 '{text}': 找到 {total_count} 首歌")

            # 处理每首歌
            for song in result_list[:page_size]:
                try:
                    # 获取基本信息
                    song_name = song.get("name") or "未知歌曲"
                    copyright_id = song.get("copyrightId") or song.get("id")
                    song_id = song.get("id") or copyright_id

                    # 获取歌手
                    singers = song.get("singers") or song.get("artists") or []
                    if isinstance(singers, list) and singers:
                        artist_names = [s.get("name", "") for s in singers if s.get("name")]
                        artists = "、".join(artist_names)
                    else:
                        artists = "未知歌手"

                    # 获取封面
                    img_items = song.get("imgItems") or []
                    cover = None
                    if img_items and len(img_items) > 0:
                        cover = img_items[0].get("img")

                    # 构造播放链接
                    # 方式1: 使用新密钥格式
                    # http://freetyst.nf.migu.cn/#/?key=xxx
                    # 方式2: 直接使用标准URL格式
                    play_url = self._build_migu_play_url(copyright_id, song_id)

                    # 获取时长（如果有）
                    duration = None
                    if "toneCount" in song:
                        try:
                            duration = int(song.get("toneCount", "0")) // 1000  # 毫秒转秒
                        except:
                            pass

                    song_info = SongInfo(
                        name=song_name,
                        artists=artists,
                        url=play_url,
                        cover=cover,
                        song_id=str(song_id),
                        duration=duration,
                        source="migu"
                    )
                    songs.append(song_info)

                except Exception as e:
                    logger.debug(f"[MIGU] 处理歌曲失败: {e}")
                    continue

            return songs

        except asyncio.TimeoutError:
            logger.error("[MIGU] 请求超时")
            return []
        except Exception as e:
            logger.error(f"[MIGU] 搜索失败: {e}")
            return []

    async def _get_wangyi_play_url(self, song_id: str) -> DownloadInfo:
        session = await self._get_session()
        detail_url = (
            "https://music.163.com/api/song/enhance/player/url/v1"
            f"?id={song_id}&ids=[{song_id}]&level=standard&encodeType=mp3"
        )
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
            "Referer": f"https://music.163.com/song?id={song_id}",
            "Origin": "https://music.163.com",
        }
        async with session.get(detail_url, headers=headers) as resp:
            if resp.status != 200:
                return DownloadInfo(url="", file_type="mp3", size=0)
            data = await _read_json_response(resp)
        items = data.get("data") or []
        if not items:
            return DownloadInfo(url="", file_type="mp3", size=0)
        item = items[0] or {}
        url = item.get("url") or ""
        file_type = item.get("type") or self._file_type_from_url(url)
        size = self._parse_int(item.get("size"))
        return DownloadInfo(url=url, file_type=file_type, size=size)

    async def search_wangyi(
        self,
        text: str,
        page_num: int = 1,
        page_size: int = 20,
        song_list_id: Optional[str] = None
    ) -> List[SongInfo]:
        """
        搜索网易云音乐
        API: https://music.163.com/api/search/get/web
        """
        session = await self._get_session()
        songs: List[SongInfo] = []

        if song_list_id:
            logger.warning("[MUSIC] 网易云暂不支持歌单下载")
            return []

        try:
            fetch_size = max(page_size, 5)
            offset = (page_num - 1) * fetch_size
            url = (
                "https://music.163.com/api/search/get/web"
                f"?s={quote(text)}"
                "&type=1"
                f"&limit={fetch_size}"
                f"&offset={offset}"
            )
            headers = {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
                "Referer": "https://music.163.com/",
                "Origin": "https://music.163.com",
            }
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    logger.error(f"[NETEASE] 搜索失败: HTTP {resp.status}")
                    return []
                data = await _read_json_response(resp)

            results = (data.get("result") or {}).get("songs") or []
            if not results:
                logger.warning(f"[NETEASE] 未找到歌曲: {text}")
                return []

            for song in results:
                song_id = song.get("id")
                if not song_id:
                    continue
                song_name = song.get("name") or "未知歌曲"
                artists_info = song.get("artists") or song.get("ar") or []
                artists = _join_singers_name(artists_info) or "未知歌手"
                album = song.get("album") or song.get("al") or {}
                cover = album.get("picUrl")

                download_info = await self._get_wangyi_play_url(str(song_id))
                if not download_info.url:
                    logger.debug(f"[NETEASE] 无可播放链接: {song_name}")
                    continue

                songs.append(
                    SongInfo(
                        name=song_name,
                        artists=artists,
                        url=download_info.url,
                        cover=cover,
                        song_id=str(song_id),
                        size=download_info.size,
                        source="wangyi",
                    )
                )
                if len(songs) >= page_size:
                    break

            return songs

        except Exception as e:
            logger.error(f"[NETEASE] 搜索失败: {e}")
            return []

    async def _get_kugou_download(self, song_hash: str) -> DownloadInfo:
        session = await self._get_session()
        key = hashlib.md5(f"{song_hash}kgcloudv2".encode("utf-8")).hexdigest()
        detail_url = (
            "http://trackercdn.kugou.com/i/v2/"
            f"?key={key}&hash={song_hash}&br=hq&appid=1005&pid=2&cmd=25&behavior=play"
        )
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.kugou.com/",
        }
        async with session.get(detail_url, headers=headers) as resp:
            if resp.status != 200:
                return DownloadInfo(url="", file_type="mp3", size=0)
            data = await _read_json_response(resp)
        urls = data.get("url") or []
        url = urls[0] if urls else ""
        file_type = self._file_type_from_url(url)
        size = self._parse_int(data.get("fileSize"))
        return DownloadInfo(url=url, file_type=file_type, size=size)

    async def search_kugou(self, text: str, page_num: int = 1, page_size: int = 20) -> List[SongInfo]:
        """
        搜索酷狗音乐
        API: http://msearchcdn.kugou.com/api/v3/search/song
        """
        session = await self._get_session()
        songs: List[SongInfo] = []

        try:
            fetch_size = max(page_size, 10)
            url = (
                "http://msearchcdn.kugou.com/api/v3/search/song"
                f"?pagesize={fetch_size}"
                f"&keyword={quote(text)}"
                f"&page={page_num}"
            )
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://www.kugou.com/",
            }
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    logger.error(f"[KUGOU] 搜索失败: HTTP {resp.status}")
                    return []
                data = await _read_json_response(resp)

            info_list = (data.get("data") or {}).get("info") or []
            if not info_list:
                logger.warning(f"[KUGOU] 未找到歌曲: {text}")
                return []

            for item in info_list:
                song_hash = item.get("hash")
                filename = item.get("filename") or ""
                if not song_hash or not filename:
                    continue

                download_info = await self._get_kugou_download(song_hash)
                if not download_info.url:
                    logger.debug(f"[KUGOU] 无可播放链接: {filename}")
                    continue

                cleaned = _remove_punctuation(filename.replace("、", ","))
                parts = cleaned.split(" - ", 1)
                if len(parts) == 2:
                    artists, song_name = parts[0], parts[1]
                else:
                    artists, song_name = "未知歌手", cleaned

                songs.append(
                    SongInfo(
                        name=song_name or "未知歌曲",
                        artists=artists or "未知歌手",
                        url=download_info.url,
                        cover=None,
                        song_id=song_hash,
                        size=download_info.size,
                        source="kugou",
                    )
                )
                if len(songs) >= page_size:
                    break

            return songs

        except Exception as e:
            logger.error(f"[KUGOU] 搜索失败: {e}")
            return []

    def _build_migu_play_url(self, copyright_id: str, song_id: str) -> str:
        """
        构造咪咕播放链接
        使用标准的咪咕URL格式
        """
        # 方法1: 使用通用播放链接格式
        # http://music.migu.cn/v3/music/song/{copyrightId}

        # 方法2: 使用新的流媒体链接（需要加密）
        # 这里使用网页播放器链接作为备选

        # 返回一个可以用的链接（ESP32端需要处理）
        return f"http://music.migu.cn/v3/music/song/{copyright_id}"

    async def get_download_info(
        self,
        copyright_id: str,
        song_id: str,
        song_name: str
    ) -> Optional[DownloadInfo]:
        """
        获取咪咕歌曲下载信息
        优先使用 resourceType=2 的 rateFormats/newRateFormats 字段
        """
        try:
            detail = await self._fetch_resource_info(copyright_id, resource_type=2)
            info = self._extract_download_info(detail)
            if info:
                return info

            detail = await self._fetch_resource_info(copyright_id, resource_type=0)
            info = self._extract_download_info(detail)
            if info:
                return info

            logger.warning(f"[MIGU] 未获取到下载信息: {song_name}")
            return None

        except Exception as e:
            logger.error(f"[MIGU] 获取下载信息异常: {e}")
            return None

    async def get_download_url(self, copyright_id: str, song_id: str, song_name: str) -> Optional[str]:
        """
        获取咪咕歌曲的实际下载链接
        按照 MusicN 项目的逻辑:
        1. 调用 resourceinfo.do 获取 audioUrl
        2. 提取 pathname 构造 freetyst.nf.migu.cn 链接
        3. 替换质量标识获取高质量版本
        """
        info = await self.get_download_info(copyright_id, song_id, song_name)
        if info:
            logger.info(f"[MIGU] 获取下载链接成功: {song_name}")
            return info.url
        return None

    async def search(
        self,
        text: str,
        source: str = "migu",
        page_num: int = 1,
        page_size: int = 10
    ) -> List[SongInfo]:
        """
        统一搜索入口
        :param text: 搜索关键词
        :param source: 音乐来源 (migu/netease/kugou)
        :param page_num: 页码
        :param page_size: 每页数量
        :return: 歌曲列表
        """
        text = text.strip()
        if not text:
            return []

        logger.info(f"[MUSIC] 搜索: {text}, 来源: {source}")

        source = source.lower()

        if source == "migu":
            return await self.search_migu(text, page_num, page_size)
        if source in ("wangyi", "netease", "163"):
            return await self.search_wangyi(text, page_num, page_size)
        if source == "kugou":
            return await self.search_kugou(text, page_num, page_size)

        logger.warning(f"[MUSIC] 暂不支持 {source}，使用 migu")
        return await self.search_migu(text, page_num, page_size)


class MusicPlayer:
    """音乐播放器（管理播放状态和队列）"""

    def __init__(self):
        self.queue: List[SongInfo] = []
        self.current_index = 0
        self.is_playing = False
        self.current_song: Optional[SongInfo] = None
        self.play_mode = "cycle"  # cycle: 循环播放, single: 单曲循环

    def set_queue(self, songs: List[SongInfo]):
        """设置播放队列"""
        self.queue = songs
        self.current_index = 0
        logger.info(f"[MUSIC] 设置播放队列: {len(songs)} 首歌")

    def get_current_song(self) -> Optional[SongInfo]:
        """获取当前歌曲"""
        if 0 <= self.current_index < len(self.queue):
            self.current_song = self.queue[self.current_index]
            return self.current_song
        return None

    def next(self):
        """下一首"""
        if not self.queue:
            return None
        self.current_index = (self.current_index + 1) % len(self.queue)
        return self.get_current_song()

    def prev(self):
        """上一首"""
        if not self.queue:
            return None
        self.current_index = (self.current_index - 1) % len(self.queue)
        return self.get_current_song()

    def play_index(self, index: int) -> Optional[SongInfo]:
        """播放指定索引的歌曲"""
        if 0 <= index < len(self.queue):
            self.current_index = index
            return self.get_current_song()
        return None

    def get_status(self) -> Dict[str, Any]:
        """获取播放器状态"""
        return {
            "queue_length": len(self.queue),
            "current_index": self.current_index,
            "is_playing": self.is_playing,
            "current_song": str(self.current_song) if self.current_song else None,
            "play_mode": self.play_mode
        }


# ========== 全局实例 ==========
_searcher_instance: Optional[MusicSearcher] = None
_player_instance: Optional[MusicPlayer] = None


def get_music_searcher() -> MusicSearcher:
    """获取音乐搜索器单例"""
    global _searcher_instance
    if _searcher_instance is None:
        _searcher_instance = MusicSearcher()
    return _searcher_instance


def get_music_player() -> MusicPlayer:
    """获取音乐播放器单例"""
    global _player_instance
    if _player_instance is None:
        _player_instance = MusicPlayer()
    return _player_instance


# ========== 便捷函数 ==========
async def search_music(keyword: str, source: str = "migu", limit: int = 5) -> List[SongInfo]:
    """
    搜索音乐
    :param keyword: 歌名/歌手/歌词
    :param source: 音乐来源 (migu/netease/kugou)
    :param limit: 返回数量限制
    :return: 歌曲列表
    """
    searcher = get_music_searcher()
    results = await searcher.search(keyword, source=source, page_size=limit)
    return results


def format_song_list(songs: List[SongInfo], max_count: int = 10) -> str:
    """
    格式化歌曲列表为语音文本
    :param songs: 歌曲列表
    :param max_count: 最多播报数量
    :return: 语音文本
    """
    if not songs:
        return "没有找到相关歌曲"

    limited_songs = songs[:max_count]

    if len(songs) == 1:
        return f"找到{limited_songs[0].artists}的{limited_songs[0].name}"

    lines = [f"找到 {len(songs)} 首歌。"]

    if len(limited_songs) <= 3:
        # 3首以内全部播报
        song_names = [f"{s.artists}的{s.name}" for s in limited_songs]
        lines.append("、".join(song_names) + "。")
        lines.append("请说播放第几首。")
    else:
        # 超过3首只播报前3首
        song_names = [f"{s.artists}的{s.name}" for s in limited_songs[:3]]
        lines.append("前3首是：" + "、".join(song_names) + "。")
        lines.append("请说播放第几首。")

    return " ".join(lines)


def get_play_url(song: SongInfo) -> str:
    """获取歌曲播放链接"""
    return song.url


async def download_song(song: SongInfo, save_path: str = ".") -> Optional[str]:
    """
    下载歌曲
    :param song: 歌曲信息
    :param save_path: 保存路径
    :return: 保存的文件路径，失败返回None
    """
    searcher = get_music_searcher()
    session = await searcher._get_session()

    try:
        download_info = None
        if song.source == "migu":
            copyright_id = song.url.split("/")[-1] if song.url else song.song_id
            download_info = await searcher.get_download_info(copyright_id, song.song_id, song.name)

        download_url = download_info.url if download_info else None
        if not download_url:
            download_url = song.url

        if not download_url:
            logger.error(f"[MUSIC] 无可用下载链接: {song}")
            return None

        logger.info(f"[MUSIC] 开始下载: {song}")

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "http://music.migu.cn/",
            "Accept": "*/*",
        }

        async with session.get(download_url, headers=headers) as resp:
            if resp.status != 200:
                logger.error(f"[MUSIC] 下载失败: HTTP {resp.status}")
                return None

            content_type = resp.headers.get("Content-Type", "")
            if "text/html" in content_type:
                logger.error(f"[MUSIC] 下载失败: 返回HTML页面 ({content_type})")
                return None

            content_length = resp.headers.get("Content-Length")
            if content_length:
                file_size = int(content_length)
                logger.info(f"[MUSIC] 文件大小: {file_size / 1024 / 1024:.2f} MB")

            os.makedirs(save_path, exist_ok=True)

            if download_info and download_info.file_type:
                file_ext = download_info.file_type.lower()
            else:
                file_ext = searcher._file_type_from_url(download_url).lower()
            safe_base = _safe_filename(f"{song.artists} - {song.name}")
            filename = f"{safe_base}.{file_ext}"
            file_path = _unique_path(save_path, filename)
            temp_path = f"{file_path}.part"

            with open(temp_path, "wb") as f:
                downloaded = 0
                first_chunk = await resp.content.read(8192)
                if not first_chunk:
                    logger.error("[MUSIC] 下载失败: 空响应")
                    try:
                        os.remove(temp_path)
                    except OSError:
                        pass
                    return None
                if _looks_like_html(first_chunk):
                    logger.error("[MUSIC] 下载失败: 返回HTML内容")
                    try:
                        os.remove(temp_path)
                    except OSError:
                        pass
                    return None
                f.write(first_chunk)
                downloaded += len(first_chunk)

                async for chunk in resp.content.iter_chunked(8192):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if content_length:
                        progress = (downloaded / int(content_length)) * 100
                        print(f"\r下载进度: {progress:.1f}%", end="")

            print()
            os.replace(temp_path, file_path)
            logger.info(f"[MUSIC] 下载完成: {file_path}")
            return file_path

    except Exception as e:
        if "temp_path" in locals() and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        logger.error(f"[MUSIC] 下载异常: {e}")
        return None


# ========== 测试代码 ==========
if __name__ == '__main__':
    import json
    import os

    async def test_search():
        print("=" * 50)
        print("音乐搜索测试")
        print("=" * 50)

        searcher = MusicSearcher()

        # 测试搜索
        print("\n1. 测试搜索 '青花瓷':")
        songs = await searcher.search("青花瓷", source="migu", page_size=5)
        for i, song in enumerate(songs, 1):
            print(f"  {i}. {song.artists} - {song.name}")
            print(f"     ID: {song.song_id}")
            print(f"     链接: {song.url}")

        if not songs:
            print("没有搜索到歌曲，退出测试")
            await searcher.close()
            return

        print("\n2. 测试获取下载链接:")
        first_song = songs[0]
        copyright_id = first_song.url.split("/")[-1]
        download_url = await searcher.get_download_url(copyright_id, first_song.song_id, first_song.name)
        if download_url:
            print(f"  下载链接: {download_url[:100]}...")
        else:
            print("  获取下载链接失败")

        print("\n3. 测试下载:")
        save_dir = "music_downloads"
        os.makedirs(save_dir, exist_ok=True)

        downloaded_path = await download_song(first_song, save_dir)
        if downloaded_path:
            print(f"  下载成功: {downloaded_path}")
            # 显示文件大小
            file_size = os.path.getsize(downloaded_path)
            print(f"  文件大小: {file_size / 1024 / 1024:.2f} MB")
        else:
            print("  下载失败")

        await searcher.close()

    asyncio.run(test_search())
