# audio_player.py
# 处理预录音频文件的播放，���持 ESP32 扬声器、蓝牙、本地音频输出

import os
import sys
import wave
import json
import asyncio
import threading
import queue
import time
import hashlib
import re
import platform
from audio_stream import broadcast_pcm16_realtime
from audio_compressor import compressed_audio_cache, AudioCompressor

# 蓝牙音频支持
_bluetooth_manager = None
_piper_tts = None
_tts_enabled = False
_output_mode = "local"  # local/bluetooth/esp32
_local_fallback_enabled = False
_local_audio_lock = threading.Lock()
_local_audio = None
_local_audio_stream = None
_local_audio_backend = ""
_local_audio_failed = False
_last_audio_resolve_source = "none"

_audio_metrics_lock = threading.Lock()
_audio_metrics = {
    "requested": 0,
    "resolved": 0,
    "enqueued": 0,
    "dropped": 0,
    "played": 0,
    "suppressed_empty": 0,
    "suppressed_cooldown": 0,
    "failed_no_audio": 0,
    "resolve_ms_total": 0.0,
    "resolve_samples": 0,
    "last_report_ts": time.monotonic(),
}


def _bump_audio_metric(key: str, amount: float = 1.0):
    with _audio_metrics_lock:
        if key not in _audio_metrics:
            _audio_metrics[key] = 0
        _audio_metrics[key] += amount


def _maybe_report_audio_metrics(force: bool = False):
    try:
        interval = float(os.getenv("AIGLASS_AUDIO_METRICS_LOG_INTERVAL_SEC", "5.0"))
    except Exception:
        interval = 5.0
    if interval <= 0:
        return

    now = time.monotonic()
    with _audio_metrics_lock:
        last_ts = float(_audio_metrics.get("last_report_ts", now))
        if (not force) and (now - last_ts < interval):
            return
        _audio_metrics["last_report_ts"] = now
        snap = dict(_audio_metrics)

    samples = int(snap.get("resolve_samples", 0) or 0)
    avg_resolve_ms = (float(snap.get("resolve_ms_total", 0.0)) / samples) if samples > 0 else 0.0
    _force_audio_log(
        "audio_metrics",
        requested=int(snap.get("requested", 0)),
        resolved=int(snap.get("resolved", 0)),
        enqueued=int(snap.get("enqueued", 0)),
        dropped=int(snap.get("dropped", 0)),
        played=int(snap.get("played", 0)),
        suppressed_empty=int(snap.get("suppressed_empty", 0)),
        suppressed_cooldown=int(snap.get("suppressed_cooldown", 0)),
        failed_no_audio=int(snap.get("failed_no_audio", 0)),
        avg_resolve_ms=f"{avg_resolve_ms:.1f}",
    )


def get_audio_runtime_metrics() -> dict:
    """导出音频运行指标快照（供主流程做自适应降载决策）。"""
    with _audio_metrics_lock:
        snap = dict(_audio_metrics)
    try:
        snap["queue_size"] = int(_audio_queue.qsize())
    except Exception:
        snap["queue_size"] = 0
    return snap


def get_audio_playback_state() -> dict:
    """
    导出播放状态（供主流程做“播报完成后再触发检测/播报”门控）。

    字段说明：
    - busy: 是否忙碌（正在播放或队列中有待播报数据）
    - queue_size: 当前播放队列长度
    - is_playing: 当前是否处于播放中
    - last_finish_ts: 最近一次播放结束的 monotonic 时间戳
    - active_utterance_id: 当前/最近一次播放序号
    """
    with _playing_lock:
        is_playing = bool(_is_playing)
        last_finish_ts = float(_last_audio_finish_ts or 0.0)
        utterance_id = int(_active_utterance_id)

    try:
        queue_size = int(_audio_queue.qsize())
    except Exception:
        queue_size = 0

    return {
        "busy": bool(is_playing or queue_size > 0),
        "queue_size": queue_size,
        "is_playing": is_playing,
        "last_finish_ts": last_finish_ts,
        "active_utterance_id": utterance_id,
    }


def _is_critical_text(text: str) -> bool:
    t = str(text or "")
    return any(k in t for k in ("紧急", "危险", "警告", "先停", "停下"))


def _sanitize_tts_text(text: str) -> str:
    t = str(text or "").strip()
    if not t:
        return ""

    # 压缩停顿与重复标点
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"([，。！？；、,.!?;:：])\1+", r"\1", t)

    # 修复常见口吃重复（尤其是“的的的的”）
    t = re.sub(r"(的|了|啊|嗯|呃)(?:\s*\1){1,}", r"\1", t)

    return t.strip()


def _force_audio_log(event: str, **fields):
    """统一强制播报日志，便于现场排障。"""
    if os.getenv("AIGLASS_FORCE_AUDIO_LOG", "1") != "1":
        return

    parts = [f"event={event}"]
    for key, value in (fields or {}).items():
        if value is None:
            continue
        txt = str(value).replace("\n", " ").strip()
        if len(txt) > 90:
            txt = txt[:87] + "..."
        parts.append(f"{key}={txt}")
    print("[AUDIO-FORCE] " + " ".join(parts))


def _init_local_audio_if_needed(force: bool = False) -> bool:
    """延迟初始化本地扬声器输出（pyaudio）。"""
    global _local_audio, _local_audio_stream, _local_audio_backend, _local_audio_failed

    if (not force) and (not _local_fallback_enabled):
        return False

    with _local_audio_lock:
        if _local_audio_stream is not None:
            return True
        if _local_audio_failed:
            return False

        try:
            import pyaudio

            _local_audio = pyaudio.PyAudio()
            _local_audio_stream = _local_audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=8000,
                output=True,
                frames_per_buffer=1024,
            )
            _local_audio_backend = "pyaudio"
            print("[AUDIO] 已启用本地扬声器兜底输出（pyaudio）")
            return True
        except Exception as e:
            _local_audio_failed = True
            print(f"[AUDIO] 本地扬声器兜底初始化失败: {e}")
            return False


def _play_pcm_local_fallback(pcm_data: bytes, force: bool = False) -> bool:
    if not pcm_data:
        return False
    if not _init_local_audio_if_needed(force=force):
        return False

    try:
        with _local_audio_lock:
            if _local_audio_stream is None:
                return False
            _local_audio_stream.write(pcm_data)
        return True
    except Exception as e:
        print(f"[AUDIO] 本地扬声器兜底播放失败: {e}")
        return False


def _refresh_output_mode_from_bluetooth() -> bool:
    """
    根据蓝牙连接状态刷新输出模式。
    返回值表示当前是否检测到蓝牙音频可用。
    """
    global _output_mode

    auto_switch = os.getenv("AIGLASS_AUDIO_AUTO_SWITCH", "1") == "1"
    if not auto_switch or not _bluetooth_manager:
        return False

    try:
        is_bluetooth_connected = bool(_bluetooth_manager.check_connection())
    except Exception as e:
        print(f"[AUDIO] 蓝牙状态检测失败: {e}")
        return False

    if is_bluetooth_connected:
        if _output_mode != "bluetooth":
            _output_mode = "bluetooth"
            print("[AUDIO] 检测到蓝牙已连接，切换音频输出到蓝牙")
        return True

    if _output_mode == "bluetooth":
        configured_mode = os.getenv("AIGLASS_AUDIO_OUTPUT", "local").strip().lower() or "local"
        fallback_mode = configured_mode if configured_mode in ("local", "esp32") else "local"
        _output_mode = fallback_mode
        print(f"[AUDIO] 蓝牙未连接，回退音频输出模式到 {fallback_mode}")
    return False


def _resolve_output_route_policy(
    *,
    output_mode: str,
    stream_client_count: int,
    loop_ready: bool,
    bluetooth_connected: bool,
    speaker_fallback_enabled: bool,
) -> str:
    """
    统一输出路由策略:
    - 蓝牙连接且当前模式为 bluetooth：优先本地输出（由系统蓝牙 sink 承接）
    - 否则优先 stream
    - stream 不可用时，仅在显式允许时才使用本地扬声器兜底
    """
    mode = str(output_mode or "local").strip().lower()
    if mode == "bluetooth" and bluetooth_connected:
        return "bluetooth_local_preferred"
    if stream_client_count > 0 and loop_ready:
        return "stream"
    if speaker_fallback_enabled:
        return "speaker_local_fallback"
    return "no_route"


def _snapshot_output_state() -> dict:
    """采样当前输出链路状态。"""
    stream_clients = 0
    server_loop_running = False
    try:
        import audio_stream as _as
        clients = getattr(_as, "stream_clients", set())
        stream_clients = len(clients) if clients is not None else 0
        srv_loop = getattr(_as, "server_loop", None)
        if srv_loop is not None and hasattr(srv_loop, "is_running"):
            server_loop_running = bool(srv_loop.is_running())
    except Exception:
        pass

    tts_ok = bool(_tts_enabled and _piper_tts and _piper_tts.is_available())
    return {
        "stream_clients": stream_clients,
        "server_loop_running": server_loop_running,
        "local_fallback_enabled": bool(_local_fallback_enabled),
        "local_audio_ready": bool(_local_audio_stream is not None),
        "local_audio_failed": bool(_local_audio_failed),
        "tts_available": tts_ok,
        "output_mode": _output_mode,
    }


def run_startup_audio_selfcheck(play_probe: bool = True, probe_text: str = "音频链路自检完成") -> dict:
    """
    启动自检：检查播报路径并可选播放一条自检语音。

    输出优先级固定为：
    1) /stream.wav（有客户端且主 loop 可用）
    2) 本地扬声器兜底
    """
    if not _initialized:
        initialize_audio_system()

    state = _snapshot_output_state()
    bluetooth_connected = _refresh_output_mode_from_bluetooth()
    route_policy = _resolve_output_route_policy(
        output_mode=_output_mode,
        stream_client_count=int(state.get("stream_clients", 0) or 0),
        loop_ready=bool(state.get("server_loop_running", False)),
        bluetooth_connected=bluetooth_connected,
        speaker_fallback_enabled=bool(state.get("local_fallback_enabled", False)),
    )
    route = "no_route"

    if route_policy == "stream":
        route = "stream"
    elif route_policy == "bluetooth_local_preferred":
        ready = _init_local_audio_if_needed(force=True)
        state["local_audio_ready"] = bool(ready)
        route = "bluetooth_local" if ready else "bluetooth_local_unavailable"
    elif route_policy == "speaker_local_fallback":
        ready = _init_local_audio_if_needed()
        state["local_audio_ready"] = bool(ready)
        route = "local_fallback" if ready else "local_fallback_unavailable"

    state["preferred_route"] = route
    state["route_policy"] = route_policy
    state["bluetooth_connected"] = bluetooth_connected

    probe_pcm = _get_pcm_for_text(probe_text, allow_tts=True, save_generated=True)
    state["probe_source"] = _last_audio_resolve_source
    state["probe_bytes"] = len(probe_pcm) if probe_pcm else 0

    played = False
    if play_probe and probe_pcm and route in ("stream", "local_fallback", "bluetooth_local"):
        _enqueue_pcm_threadsafe(probe_pcm)
        played = True

    state["probe_played"] = played

    _force_audio_log(
        "startup_selfcheck",
        route=route,
        stream_clients=state.get("stream_clients"),
        loop=state.get("server_loop_running"),
        local_ready=state.get("local_audio_ready"),
        tts=state.get("tts_available"),
        probe_source=state.get("probe_source"),
        probe_played=played,
    )
    print(
        f"[AUDIO] 启动自检: route={route}, stream_clients={state.get('stream_clients')}, "
        f"local_ready={state.get('local_audio_ready')}, tts={state.get('tts_available')}, "
        f"probe_source={state.get('probe_source')}, probe_played={played}"
    )
    return state

def _init_audio_output():
    """初始化音频输出系统（蓝牙、TTS）"""
    global _bluetooth_manager, _piper_tts, _tts_enabled, _output_mode, _local_fallback_enabled

    # 读取输出模式配置
    _output_mode = os.getenv("AIGLASS_AUDIO_OUTPUT", "local")
    auto_switch = os.getenv("AIGLASS_AUDIO_AUTO_SWITCH", "1") == "1"
    _local_fallback_enabled = os.getenv("AIGLASS_LOCAL_FALLBACK_PLAYBACK", "0") == "1"
    _force_audio_log(
        "audio_init",
        output_mode=_output_mode,
        auto_switch=auto_switch,
        local_fallback=_local_fallback_enabled,
    )

    # 初始化蓝牙（输出为 bluetooth 或启用自动切换时都需要初始化管理器用于检测）
    if _output_mode == "bluetooth" or auto_switch:
        try:
            from bluetooth_audio import get_bluetooth_manager
            _bluetooth_manager = get_bluetooth_manager()
            if getattr(_bluetooth_manager, "enabled", False):
                print(f"[AUDIO] 蓝牙音频管理器已启用，模式: {_output_mode}")
                # 仅在明确使用蓝牙输出时尝试自动连接
                if _output_mode == "bluetooth" and getattr(_bluetooth_manager, "auto_connect", False):
                    _bluetooth_manager.auto_connect_device()
            else:
                if auto_switch:
                    print("[AUDIO] 蓝牙自动切换已启用：将按播放前检测 bluez sink 来动态路由")
        except ImportError:
            print("[AUDIO] 警告: bluetooth_audio 模块未找到，蓝牙功能不可用")
        except Exception as e:
            print(f"[AUDIO] 蓝牙初始化失败: {e}")

    # 初始化 TTS
    _tts_enabled = os.getenv("AIGLASS_TTS_ENABLED", "1") == "1"
    if _tts_enabled:
        try:
            from piper_tts import get_piper_tts
            _piper_tts = get_piper_tts()
            if _piper_tts.is_available():
                print("[AUDIO] Piper-TTS 已启用")
                _pre_generate_voice_corpus()
            else:
                print("[AUDIO] Piper-TTS 不可用，将仅使用预录音频")
                model_path = getattr(_piper_tts, "model_path", "")
                model_exists = bool(model_path and os.path.exists(model_path))
                print(
                    f"[AUDIO] TTS诊断: python={sys.executable}, model={model_path}, "
                    f"model_exists={model_exists}"
                )
                print("[AUDIO] 建议：激活正确虚拟环境并安装 piper-tts/pathvalidate（已在 requirements.txt）")
        except ImportError:
            print("[AUDIO] 警告: piper_tts 模块未找到，TTS 功能不可用")
        except Exception as e:
            print(f"[AUDIO] TTS 初始化失败: {e}")

# 导入录制器（避免循环导入，在需要时动态导入）
_recorder_imported = False
_sync_recorder = None

def _get_recorder():
    """延迟导入录制器"""
    global _recorder_imported, _sync_recorder
    if not _recorder_imported:
        try:
            import sync_recorder as sr
            _sync_recorder = sr
            _recorder_imported = True
        except Exception as e:
            print(f"[AUDIO] 无法导入录制器: {e}")
            _recorder_imported = True  # 标记已尝试，避免重复
    return _sync_recorder

# 兼容旧工程中的示例音频（保留）
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def _resolve_path(path: str) -> str:
    """Resolve env-provided paths: expand vars, and treat relative paths as repo-relative."""
    p = os.path.expandvars(os.path.expanduser(path or ""))
    if not p:
        return p
    if os.path.isabs(p):
        return p
    return os.path.join(_BASE_DIR, p)

# AIGLASS_AUDIO_DIR/VOICE_DIR may be relative; anchor them to repo root for stability
AUDIO_BASE_DIR = _resolve_path(os.getenv("AIGLASS_AUDIO_DIR", os.path.join(_BASE_DIR, "music")))

# 新增：voice 目录与映射表
# 使用脚本所在目录的 voice 文件夹，避免工作目录问题
VOICE_DIR = _resolve_path(os.getenv("VOICE_DIR", os.path.join(_BASE_DIR, "voice")))
VOICE_MAP_FILE = _resolve_path(
    os.getenv("AIGLASS_VOICE_MAP_FILE") or os.getenv("VOICE_MAP_FILE") or os.path.join(VOICE_DIR, "map.zh-CN.json")
)
VOICE_GEN_DIR = _resolve_path(os.getenv("AIGLASS_VOICE_GEN_DIR", os.path.join(VOICE_DIR, "generated")))
VOICE_GEN_MAP_FILE = _resolve_path(os.getenv("AIGLASS_VOICE_GEN_MAP_FILE", os.path.join(VOICE_DIR, "map.generated.json")))
_voice_map_lock = threading.Lock()
_fragment_cache_lock = threading.Lock()
_fragment_cache_path = ""
_fragment_cache_mtime = -1.0
_fragment_cache_phrases = []
_punct_silence_tokens = {"，", "。", "、", "；", ",", ".", ";", "：", ":", "！", "!", "?", "？"}

# 音频文件映射（将合并 voice 映射）
AUDIO_MAP = {
    "检测到物体": os.path.join(AUDIO_BASE_DIR, "converted_音频1.WAV"),
    "向上": os.path.join(AUDIO_BASE_DIR, "converted_向上.wav"),
    "向下": os.path.join(AUDIO_BASE_DIR, "converted_向下.wav"),
    "向左": os.path.join(AUDIO_BASE_DIR, "converted_向左.wav"),
    "向右": os.path.join(AUDIO_BASE_DIR, "converted_向右.wav"),
    "OK": os.path.join(AUDIO_BASE_DIR, "converted_已对中.wav"),
    "向前": os.path.join(AUDIO_BASE_DIR, "converted_向前.wav"),
    "后退": os.path.join(AUDIO_BASE_DIR, "converted_向后.wav"),
    "拿到物体": os.path.join(AUDIO_BASE_DIR, "converted_拿到啦.wav"),
    "学长好帅啊": os.path.join(AUDIO_BASE_DIR, "converted_学长好帅啊.wav"),
}

# 音频缓存，避免重复读取
_audio_cache = {}
_audio_bad_files = set()

# 音频播放队列和工作线程 - 使用优先级队列
_audio_queue = queue.PriorityQueue(maxsize=10)
_audio_priority = 0  # 递增的优先级计数器
_worker_thread = None
_worker_loop = None
_is_playing = False  # 标记是否正在播放音频
_playing_lock = threading.Lock()  # 播放锁
_initialized = False
_init_lock = threading.Lock()
_last_play_ts = 0.0  # 记录上次播放结束时间，用于决定预热静音长度
_last_audio_finish_ts = 0.0  # 最近一次完整播放结束时间（monotonic）
_active_utterance_id = 0  # 播报序号（用于外部观察播放进度）

def load_wav_file(filepath):
    """加载WAV文件并返回PCM数据（自动转换为8kHz）"""
    if filepath in _audio_cache:
        return _audio_cache[filepath]
    if filepath in _audio_bad_files:
        return None
    if not filepath or (not os.path.exists(filepath)):
        _audio_bad_files.add(filepath)
        return None
    
    # 先做轻量 header 检查，避免对损坏文件反复触发 wave 异常
    try:
        with open(filepath, "rb") as f:
            magic = f.read(4)
        if magic not in (b"RIFF", b"RIFX"):
            _audio_bad_files.add(filepath)
            print(f"[AUDIO] 跳过损坏音频文件 {filepath}: missing RIFF header")
            return None
    except Exception as e:
        _audio_bad_files.add(filepath)
        print(f"[AUDIO] 无法读取音频文件 {filepath}: {e}")
        return None
    
    # 使用压缩缓存
    if os.getenv("AIGLASS_COMPRESS_AUDIO", "1") == "1":
        compressed_data = compressed_audio_cache.load_and_compress(filepath)
        if compressed_data:
            # 存储压缩后的数据
            _audio_cache[filepath] = compressed_data
            return compressed_data
    
    # 原始加载方式（不压缩）
    try:
        with wave.open(filepath, 'rb') as wav:
            # 检查音频格式
            channels = wav.getnchannels()
            sampwidth = wav.getsampwidth()
            framerate = wav.getframerate()
            
            if channels != 1:
                print(f"[AUDIO] 警告: {filepath} 不是单声道，将只使用第一个声道")
            if sampwidth != 2:
                print(f"[AUDIO] 警告: {filepath} 不是16位音频")
            
            # 读取所有帧
            frames = wav.readframes(wav.getnframes())
            
            # 如果是立体声，只取左声道
            if channels == 2:
                import audioop
                frames = audioop.tomono(frames, sampwidth, 1, 0)
            
            # 统一转换为8kHz（使用ratecv保证音调和速度不变）
            if framerate != 8000:
                import audioop
                frames, _ = audioop.ratecv(frames, sampwidth, 1, framerate, 8000, None)
                print(f"[AUDIO] 重采样: {filepath} {framerate}Hz -> 8000Hz")
            
            _audio_cache[filepath] = frames
            return frames
            
    except Exception as e:
        _audio_bad_files.add(filepath)
        print(f"[AUDIO] 加载音频文件失败 {filepath}: {e}")
        return None

def _merge_voice_map():
    """读取 voice/map.zh-CN.json 并合并到 AUDIO_MAP"""
    try:
        map_candidates = [
            VOICE_MAP_FILE,
            VOICE_GEN_MAP_FILE,
            os.path.join(VOICE_DIR, "map.zh-CN.json"),
            os.path.join(VOICE_DIR, "map.generated.json"),
            os.path.join(AUDIO_BASE_DIR, "map.zh-CN.json"),
            os.path.join(AUDIO_BASE_DIR, "map.generated.json"),
            os.path.join(_BASE_DIR, "voice", "map.zh-CN.json"),
            os.path.join(_BASE_DIR, "voice", "map.generated.json"),
        ]
        seen_paths = set()
        existing_paths = []
        for candidate in map_candidates:
            p = (candidate or "").strip()
            if not p:
                continue
            if p in seen_paths:
                continue
            seen_paths.add(p)
            if os.path.exists(p):
                existing_paths.append(p)

        if not existing_paths:
            print(f"[AUDIO] 未找到 voice 映射文件（可选）: {VOICE_MAP_FILE}")
            print(f"[AUDIO] 提示：可在 .env 设置 VOICE_DIR 或 AIGLASS_VOICE_MAP_FILE 来指定映射文件路径")
            return

        added = 0
        merged_files = 0
        for map_path in existing_paths:
            try:
                with open(map_path, "r", encoding="utf-8") as f:
                    m = json.load(f) or {}
            except Exception as e:
                print(f"[AUDIO] 跳过损坏映射文件: {map_path}, err={e}")
                continue

            map_dir = os.path.dirname(map_path)
            for text, info in (m or {}).items():
                files = (info or {}).get("files") or []
                if not files:
                    continue
                for fname in files:
                    raw = os.path.expandvars(os.path.expanduser(str(fname or ""))).strip()
                    if not raw:
                        continue
                    fpath = raw if os.path.isabs(raw) else os.path.join(map_dir, raw)
                    if os.path.exists(fpath):
                        AUDIO_MAP[text] = fpath
                        added += 1
                        break
            merged_files += 1

        print(f"[AUDIO] 已合并 voice 映射 {added} 条（files={merged_files}）")
    except Exception as e:
        print(f"[AUDIO] 读取 voice 映射失败: {e}")

def preload_all_audio():
    """预加载所有音频文件到内存"""
    print("[AUDIO] 开始预加载音频文件...")
    loaded_count = 0
    failed_count = 0
    t0 = time.monotonic()

    # 低算力设备默认限量预加载，避免启动阶段长时间阻塞（如 Jetson Nano）
    preload_mode = os.getenv("AIGLASS_AUDIO_PRELOAD_MODE", "auto").strip().lower()
    machine = platform.machine().lower()
    is_low_power = any(tag in machine for tag in ("aarch64", "armv7", "armv8", "arm64"))

    if preload_mode == "auto":
        preload_mode = "limited" if is_low_power else "full"

    try:
        max_files = int(os.getenv("AIGLASS_AUDIO_PRELOAD_MAX_FILES", "0"))
    except Exception:
        max_files = 0

    if preload_mode == "limited" and max_files <= 0:
        max_files = 120 if is_low_power else 800
    if preload_mode == "off":
        max_files = 0

    # 按路径去重，避免 map 中一条音频被多次重复预加载
    unique_targets = []
    seen_paths = set()
    for _, filepath in AUDIO_MAP.items():
        if not filepath or not os.path.exists(filepath):
            continue
        if filepath in seen_paths:
            continue
        seen_paths.add(filepath)
        unique_targets.append(filepath)

    total_unique = len(unique_targets)
    if preload_mode == "off":
        print(f"[AUDIO] 预加载已关闭（mode=off，可用音频文件={total_unique}）")
        return
    if max_files > 0:
        unique_targets = unique_targets[:max_files]

    total_targets = len(unique_targets)
    print(
        f"[AUDIO] 预加载策略: mode={preload_mode}, device={machine}, "
        f"target={total_targets}/{total_unique}"
    )

    try:
        progress_every = int(os.getenv("AIGLASS_AUDIO_PRELOAD_PROGRESS_EVERY", "200"))
    except Exception:
        progress_every = 200
    progress_every = max(1, progress_every)
    
    # 【暂时禁用变速】因为需要修改缓存机制
    # 需要加速的音频列表（斑马线相关）
    # speedup_keywords = ["斑马线", "画面"]
    # speedup_factor = 1.3  # 加速30%
    
    for idx, filepath in enumerate(unique_targets, start=1):
        # 【修复】暂时使用默认速度加载
        # need_speedup = any(keyword in audio_key for keyword in speedup_keywords)
        # speed = speedup_factor if need_speedup else 1.0
        data = load_wav_file(filepath)  # 使用默认参数
        if data:
            loaded_count += 1
            # if need_speedup:
            #     print(f"[AUDIO] 加载（加速{speedup_factor}x）: {audio_key}")
        else:
            failed_count += 1

        if idx % progress_every == 0 or idx == total_targets:
            elapsed = time.monotonic() - t0
            print(
                f"[AUDIO] 预加载进度: {idx}/{total_targets}, "
                f"loaded={loaded_count}, failed={failed_count}, elapsed={elapsed:.1f}s"
            )

    elapsed_total = time.monotonic() - t0
    print(
        f"[AUDIO] 预加载完成，共加载 {loaded_count} 个音频文件，"
        f"失败 {failed_count}，耗时 {elapsed_total:.1f}s"
    )


def _ensure_pcm_data(pcm_data: bytes) -> bytes:
    if not pcm_data:
        return b""
    if len(pcm_data) > 5 and pcm_data[0] in [0x01, 0x02]:
        return compressed_audio_cache.decompress(pcm_data) or b""
    return pcm_data


def _candidate_texts(text: str) -> list:
    raw = (text or "").strip()
    if not raw:
        return []
    normalized = _sanitize_tts_text(raw)
    t = normalized or raw

    candidates = [t]
    if raw != t:
        candidates.append(raw)

    if t[-1:] not in ("。", "！", "!", "？", "?", "."):
        candidates.append(t + "。")
    else:
        t2 = t.rstrip("。.!！?？")
        if t2 and t2 != t:
            candidates.append(t2)

    if raw and raw != t:
        if raw[-1:] not in ("。", "！", "!", "？", "?", "."):
            candidates.append(raw + "。")
        else:
            raw2 = raw.rstrip("。.!！?？")
            if raw2 and raw2 != raw:
                candidates.append(raw2)

    # 去重保持顺序
    seen = set()
    out = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _flatten_fragment_values(node, out: list):
    if isinstance(node, dict):
        for value in node.values():
            _flatten_fragment_values(value, out)
        return
    if isinstance(node, list):
        for value in node:
            _flatten_fragment_values(value, out)
        return
    value = str(node or "").strip()
    if value:
        out.append(value)


def _load_fragment_phrases() -> list:
    global _fragment_cache_path, _fragment_cache_mtime, _fragment_cache_phrases

    path = os.getenv("AIGLASS_VOICE_FRAGMENTS", os.path.join(VOICE_DIR, "fragments.json"))
    p = os.path.expandvars(os.path.expanduser(path or "")).strip()
    if not p:
        return []

    try:
        mtime = os.path.getmtime(p)
    except Exception:
        return []

    with _fragment_cache_lock:
        if _fragment_cache_path == p and _fragment_cache_mtime == mtime and _fragment_cache_phrases:
            return list(_fragment_cache_phrases)

        phrases = []
        try:
            with open(p, "r", encoding="utf-8") as f:
                fragments = json.load(f) or {}
            _flatten_fragment_values(fragments, phrases)
        except Exception:
            return []

        extra_connectors = ["，", "。", "、", "；", ",", ".", ";", "：", ":", "！", "?", "？"]
        phrases.extend(extra_connectors)

        uniq = []
        seen = set()
        for phrase in phrases:
            token = str(phrase or "").strip()
            if not token or token in seen:
                continue
            seen.add(token)
            uniq.append(token)

        uniq.sort(key=len, reverse=True)

        _fragment_cache_path = p
        _fragment_cache_mtime = mtime
        _fragment_cache_phrases = uniq
        return list(_fragment_cache_phrases)


def _tokenize_text_with_fragments(text: str, phrases: list) -> list:
    source = str(text or "").strip()
    if not source:
        return []

    tokens = []
    index = 0
    max_scan = int(os.getenv("AIGLASS_FRAGMENT_MAX_SCAN", "300"))
    scan_phrases = phrases[:max_scan] if max_scan > 0 else phrases

    while index < len(source):
        matched = None
        for phrase in scan_phrases:
            if source.startswith(phrase, index):
                matched = phrase
                break

        if matched:
            tokens.append(matched)
            index += len(matched)
            continue

        char = source[index]
        if not char.isspace():
            tokens.append(char)
        index += 1

    merged = []
    for tok in tokens:
        if not merged:
            merged.append(tok)
            continue
        prev = merged[-1]
        if len(prev) == 1 and len(tok) == 1 and prev.isascii() and tok.isascii() and prev.isalnum() and tok.isalnum():
            merged[-1] = prev + tok
        else:
            merged.append(tok)
    return merged


def _find_audio_path_for_text(text: str) -> tuple:
    """返回 (key, filepath) 或 (None, None)"""
    for ck in _candidate_texts(text):
        if ck in AUDIO_MAP:
            path = AUDIO_MAP.get(ck)
            if path and os.path.exists(path):
                return ck, path
    # 直接匹配 VOICE_DIR 同名文件
    for ck in _candidate_texts(text):
        for ext in (".wav", ".WAV"):
            direct = os.path.join(VOICE_DIR, ck + ext)
            if os.path.exists(direct):
                AUDIO_MAP[ck] = direct
                return ck, direct
    return None, None


def _write_wav(path: str, pcm_data: bytes, sr: int = 8000):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm_data)


def _update_voice_map_file(text: str, audio_path: str):
    if not text or not audio_path:
        return
    # 生成相对路径，避免环境路径变化
    rel_path = audio_path
    try:
        if os.path.commonpath([VOICE_DIR, audio_path]) == VOICE_DIR:
            rel_path = os.path.relpath(audio_path, VOICE_DIR)
    except Exception:
        pass

    with _voice_map_lock:
        data = {}
        if os.path.exists(VOICE_GEN_MAP_FILE):
            try:
                with open(VOICE_GEN_MAP_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f) or {}
            except Exception:
                data = {}
        data[text] = {"files": [rel_path]}
        tmp = VOICE_GEN_MAP_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, VOICE_GEN_MAP_FILE)


def _save_generated_audio(text: str, pcm_data: bytes):
    if not text or not pcm_data:
        return None
    if os.getenv("AIGLASS_VOICE_SAVE_TTS", "1") != "1":
        return None
    h = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
    fname = f"tts_{h}.wav"
    path = os.path.join(VOICE_GEN_DIR, fname)
    if not os.path.exists(path):
        _write_wav(path, pcm_data)
    AUDIO_MAP[text] = path
    _update_voice_map_file(text, path)
    return path


def _get_pcm_for_token(text: str, allow_tts: bool = True, save_generated: bool = True) -> bytes:
    global _last_audio_resolve_source

    token = str(text or "").strip()
    if token in _punct_silence_tokens:
        # 纯标点不做 TTS，直接返回短静音，避免无效合成与错误日志
        _last_audio_resolve_source = "punct_silence"
        punct_gap_ms = int(os.getenv("AIGLASS_PUNCT_SILENCE_MS", "25"))
        return b"\x00" * (punct_gap_ms * 8000 * 2 // 1000)

    key, path = _find_audio_path_for_text(text)
    if path:
        pcm = _ensure_pcm_data(load_wav_file(path))
        if pcm:
            _last_audio_resolve_source = "map"
            return pcm

    if allow_tts and _tts_enabled and _piper_tts and _piper_tts.is_available():
        pcm = _piper_tts.text_to_audio(text)
        if pcm:
            if save_generated:
                _save_generated_audio(text, pcm)
            _last_audio_resolve_source = "tts"
            return pcm

    _last_audio_resolve_source = "none"
    return b""


def _get_pcm_from_map_only(text: str) -> bytes:
    global _last_audio_resolve_source

    key, path = _find_audio_path_for_text(text)
    if not path:
        _last_audio_resolve_source = "none"
        return b""
    pcm = _ensure_pcm_data(load_wav_file(path))
    if pcm:
        _last_audio_resolve_source = "map"
    else:
        _last_audio_resolve_source = "none"
    return pcm or b""


def _compose_pcm_from_fragments(text: str, allow_tts: bool = True, save_generated: bool = True) -> bytes:
    global _last_audio_resolve_source

    # 默认关闭文本片段拼接，优先整句 TTS 以提升清晰度稳定性。
    if os.getenv("AIGLASS_TEXT_FRAGMENT_FALLBACK", "0") != "1":
        return b""

    phrases = _load_fragment_phrases()
    if not phrases:
        return b""

    tokens = _tokenize_text_with_fragments(text, phrases)
    if not tokens:
        return b""

    pcm_chunks = []
    miss_count = 0
    for token in tokens:
        tk = str(token or "").strip()
        if not tk:
            continue
        pcm = _get_pcm_for_token(tk, allow_tts=allow_tts, save_generated=save_generated)
        if pcm:
            pcm_chunks.append(pcm)
        else:
            miss_count += 1

    if not pcm_chunks:
        return b""

    gap_ms = int(os.getenv("AIGLASS_TEXT_FRAGMENT_GAP_MS", "25"))
    gap = b"\x00" * (gap_ms * 8000 * 2 // 1000)
    full_pcm = gap.join(pcm_chunks)
    print(f"[AUDIO] 片段拼接回退成功: tokens={len(tokens)}, miss={miss_count}, bytes={len(full_pcm)}")
    _last_audio_resolve_source = "fragments"
    return full_pcm


def _get_pcm_for_text(text: str, allow_tts: bool = True, save_generated: bool = True) -> bytes:
    """
    获取文本对应的 PCM 音频数据

    优先级：预录音频 > TTS缓存 > TTS生成

    Args:
        text: 要播放的文本
        allow_tts: 是否允许使用 TTS 生成
        save_generated: 是否保存 TTS 生成的音频

    Returns:
        PCM16 音频数据，失败返回空字节
    """
    normalized_text = _sanitize_tts_text(text)
    text_for_lookup = normalized_text or str(text or "").strip()

    pcm = _get_pcm_from_map_only(text_for_lookup)
    if not pcm and text_for_lookup != str(text or "").strip():
        pcm = _get_pcm_from_map_only(text)
    if pcm:
        print(f"[AUDIO] 文本命中成功: '{text_for_lookup}' ({len(pcm)} bytes)")
        return pcm

    composed = _compose_pcm_from_fragments(text_for_lookup, allow_tts=allow_tts, save_generated=save_generated)
    if composed:
        if save_generated:
            _save_generated_audio(text_for_lookup, composed)
        return composed

    pcm = _get_pcm_for_token(text_for_lookup, allow_tts=allow_tts, save_generated=save_generated)
    if pcm:
        print(f"[AUDIO] 全文 TTS 成功: '{text_for_lookup}' ({len(pcm)} bytes)")
        return pcm

    if not _tts_enabled:
        print(f"[AUDIO] TTS 未启用，无法生成: '{text_for_lookup}'")
    elif allow_tts and (not _piper_tts or not _piper_tts.is_available()):
        print(f"[AUDIO] TTS 不可用，无法生成: '{text_for_lookup}'")
    elif not allow_tts:
        print(f"[AUDIO] TTS 回退被禁用，无法生成: '{text_for_lookup}'")

    print(f"[AUDIO] 无法获取音频: '{text_for_lookup}'")
    return b""


def _pre_generate_voice_corpus():
    """预生成常用片段到本地语料库（可选）"""
    if not (_tts_enabled and _piper_tts and _piper_tts.is_available()):
        return
    if os.getenv("AIGLASS_TTS_PREGEN", "0") != "1":
        return

    fragments_path = os.getenv("AIGLASS_VOICE_FRAGMENTS", os.path.join(VOICE_DIR, "fragments.json"))
    try:
        with open(fragments_path, "r", encoding="utf-8") as f:
            fragments = json.load(f) or {}
    except Exception:
        fragments = {}

    items = []
    # 方向
    for v in (fragments.get("direction") or {}).get("clock", {}).values():
        items.append(str(v))
    for v in (fragments.get("direction") or {}).get("lr", {}).values():
        items.append(str(v))
    for v in (fragments.get("direction") or {}).get("combined", {}).values():
        items.append(str(v))
    # 距离
    for v in (fragments.get("distance") or {}).get("meters", {}).values():
        items.append(str(v))
    for v in (fragments.get("distance") or {}).get("steps", {}).values():
        items.append("约" + str(v) if not str(v).startswith("约") else str(v))
    # 场景
    for v in (fragments.get("scenes") or {}).values():
        if v:
            items.append(str(v))
    # 动作与告警
    for v in (fragments.get("actions") or {}).values():
        items.append(str(v))
    for v in (fragments.get("urgency") or {}).values():
        items.append(str(v))
    # 物体
    for group in (fragments.get("objects") or {}).values():
        if isinstance(group, dict):
            for v in group.values():
                items.append(str(v))

    # 编号词（新增）
    for v in (fragments.get("numbering") or {}).values():
        items.append(str(v))

    # 连接词（新增）
    for v in (fragments.get("connectors") or {}).values():
        if v:
            items.append(str(v))

    # 状态描述（新增）
    for v in (fragments.get("state_descriptions") or {}).values():
        if v:
            items.append(str(v))

    # 去重 & 限制
    seen = set()
    uniq = []
    for it in items:
        it = (it or "").strip()
        if not it or it in seen:
            continue
        seen.add(it)
        uniq.append(it)

    max_items = int(os.getenv("AIGLASS_TTS_PREGEN_MAX", "200"))
    for it in uniq[:max_items]:
        if not any(ch.isalnum() for ch in it):
            continue
        if _find_audio_path_for_text(it)[1]:
            continue
        pcm = _piper_tts.text_to_audio(it)
        if pcm:
            _save_generated_audio(it, pcm)


def warmup_voice_texts(texts, max_items: int = 800) -> int:
    """
    批量预生成语音文本（用于白名单物体等高频提示语）。

    返回：本次新生成（或缓存写入）的条目数。
    """
    if not texts:
        return 0

    if not _initialized:
        initialize_audio_system()

    # 仅在 TTS 可用时执行预生成
    if not (_tts_enabled and _piper_tts and _piper_tts.is_available()):
        return 0

    generated = 0
    seen = set()

    try:
        limit = int(max_items)
    except Exception:
        limit = 800

    for raw in texts:
        text = str(raw or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)

        # 已有音频则跳过
        if _find_audio_path_for_text(text)[1]:
            continue

        pcm = _get_pcm_for_text(text, allow_tts=True, save_generated=True)
        if pcm:
            generated += 1

        if generated >= limit:
            break

    return generated

def _enqueue_pcm_threadsafe(pcm_data: bytes):
    """将 PCM 数据推入播放队列（复用同一实时队列策略）"""
    global _audio_queue, _audio_priority

    if not pcm_data:
        return

    queue_size = _audio_queue.qsize()

    # 检查是否正在播放
    with _playing_lock:
        currently_playing = _is_playing

    # 实时策略：只允许1个积压，超过立即清空
    if queue_size > 0 and not currently_playing:
        _audio_queue = queue.PriorityQueue(maxsize=10)
    elif queue_size > 1 and currently_playing:
        _audio_queue = queue.PriorityQueue(maxsize=10)

    try:
        _audio_priority += 1
        _audio_queue.put_nowait((_audio_priority, pcm_data))
        _bump_audio_metric("enqueued", 1)
    except queue.Full:
        # 队列满则丢弃，保持实时性
        _bump_audio_metric("dropped", 1)
        pass

def _broadcast_audio_optimized_sync(pcm_data: bytes):
    """在音频工作线程中同步播报：把协程调度到 FastAPI 主事件循环执行。"""
    global _last_play_ts, _is_playing, _last_audio_finish_ts, _active_utterance_id
    try:
        with _playing_lock:
            _is_playing = True
            _active_utterance_id += 1

        now = time.monotonic()
        idle_sec = now - (_last_play_ts or now)
        lead_short = int(os.getenv("AIGLASS_LEAD_SILENCE_MS", "40"))
        lead_long = int(os.getenv("AIGLASS_LEAD_SILENCE_LONG_MS", str(max(lead_short, lead_short * 2))))
        tail_ms = int(os.getenv("AIGLASS_TAIL_SILENCE_MS", "40"))
        lead_ms = lead_long if idle_sec > 3.0 else lead_short

        lead_silence = b"\x00" * (lead_ms * 8000 * 2 // 1000)
        tail_silence = b"\x00" * (tail_ms * 8000 * 2 // 1000)
        full_audio = lead_silence + (pcm_data or b"") + tail_silence

        # 调度到 FastAPI 主事件循环（/stream.wav 的 asyncio.Queue 属于主 loop）
        try:
            import audio_stream as _as
            srv_loop = getattr(_as, "server_loop", None)
            stream_clients = getattr(_as, "stream_clients", set())
            stream_client_count = len(stream_clients) if stream_clients is not None else 0
        except Exception:
            srv_loop = None
            stream_client_count = 0

        loop_ready = bool(srv_loop is not None and (not hasattr(srv_loop, "is_running") or srv_loop.is_running()))
        bluetooth_connected = _refresh_output_mode_from_bluetooth()
        route_policy = _resolve_output_route_policy(
            output_mode=_output_mode,
            stream_client_count=stream_client_count,
            loop_ready=loop_ready,
            bluetooth_connected=bluetooth_connected,
            speaker_fallback_enabled=_local_fallback_enabled,
        )

        if route_policy in ("bluetooth_local_preferred", "speaker_local_fallback"):
            local_fallback_used = _play_pcm_local_fallback(
                full_audio,
                force=(route_policy == "bluetooth_local_preferred"),
            )
            mode_ok = "bluetooth_local_preferred" if route_policy == "bluetooth_local_preferred" else "local_fallback"
            mode_fail = "bluetooth_local_failed" if route_policy == "bluetooth_local_preferred" else "local_fallback_failed"
            _force_audio_log(
                "output_dispatch",
                mode=mode_ok if local_fallback_used else mode_fail,
                stream_clients=stream_client_count,
                output_mode=_output_mode,
                bytes=len(full_audio),
            )
            if local_fallback_used:
                _bump_audio_metric("played", 1)
                _last_play_ts = time.monotonic()
                _maybe_report_audio_metrics()
                return
            if route_policy == "speaker_local_fallback":
                return

        if route_policy == "no_route":
            _force_audio_log(
                "output_dispatch",
                mode="no_route",
                stream_clients=stream_client_count,
                output_mode=_output_mode,
                bytes=len(full_audio),
            )
            return

        if not loop_ready:
            _force_audio_log(
                "output_dispatch",
                mode="loop_missing_no_route",
                stream_clients=stream_client_count,
                output_mode=_output_mode,
                bytes=len(full_audio),
            )
            return

        fut = asyncio.run_coroutine_threadsafe(broadcast_pcm16_realtime(full_audio), srv_loop)
        fut.result()
        _bump_audio_metric("played", 1)

        _force_audio_log(
            "output_dispatch",
            mode="stream",
            stream_clients=stream_client_count,
            bytes=len(full_audio),
        )

        _last_play_ts = time.monotonic()
        _maybe_report_audio_metrics()
    except Exception as e:
        print(f"[AUDIO] 广播音频失败: {e}")
    finally:
        with _playing_lock:
            _is_playing = False
            _last_audio_finish_ts = time.monotonic()

def _audio_worker():
    """音频播放工作线程"""
    global _worker_loop
    
    # 尝试设置线程优先级（Windows特定）
    try:
        import ctypes
        import sys
        if sys.platform == "win32":
            # 设置线程为高优先级
            ctypes.windll.kernel32.SetThreadPriority(
                ctypes.windll.kernel32.GetCurrentThread(),
                1  # THREAD_PRIORITY_ABOVE_NORMAL
            )
            print("[AUDIO] 设置音频线程为高优先级")
    except Exception as e:
        print(f"[AUDIO] 设置线程优先级失败: {e}")

    # 兼容旧逻辑：保留 _worker_loop 变量，但不再在工作线程创建 asyncio loop
    _worker_loop = None

    while True:
        try:
            priority_data = _audio_queue.get(True)
            if priority_data is None:
                break
            if isinstance(priority_data, tuple) and len(priority_data) == 2:
                _, audio_data = priority_data
            else:
                audio_data = priority_data
            _broadcast_audio_optimized_sync(audio_data)
        except Exception as e:
            print(f"[AUDIO] 工作线程错误: {e}")

def initialize_audio_system():
    """初始化音频系统"""
    global _initialized, _worker_thread, _last_play_ts

    if _initialized:
        return

    with _init_lock:
        if _initialized:
            return

        # 初始化音频输出（蓝牙、TTS）
        _init_audio_output()

        # 先合并 voice 映射，再预加载
        _merge_voice_map()
        preload_all_audio()

        _worker_thread = threading.Thread(target=_audio_worker, daemon=True)
        _worker_thread.start()
        _initialized = True
        _last_play_ts = 0.0

        # 显示压缩统计
        if os.getenv("AIGLASS_COMPRESS_AUDIO", "1") == "1":
            stats = compressed_audio_cache.get_compression_stats()
            print(f"[AUDIO] 音频压缩统计:")
            print(f"  - 文件数: {stats['files_cached']}")
            print(f"  - 原始大小: {stats['total_original_size'] / 1024:.1f} KB")
            print(f"  - 压缩后: {stats['total_compressed_size'] / 1024:.1f} KB")
            print(f"  - 压缩率: {stats['compression_ratio']:.1%}")
            print(f"  - 节省: {stats['bytes_saved'] / 1024:.1f} KB")

        print(f"[AUDIO] 音频系统初始化完成（预加载+工作线程，输出模式: {_output_mode}）")

def play_audio_threadsafe(audio_key):
    """线程安全的音频播放函数（支持动态蓝牙路由）"""
    global _audio_queue, _audio_priority, _bluetooth_manager, _output_mode

    if not _initialized:
        initialize_audio_system()

    if audio_key not in AUDIO_MAP:
        print(f"[AUDIO] 未知的音频键: {audio_key}")
        return

    filepath = AUDIO_MAP[audio_key]
    pcm_data = _audio_cache.get(filepath)
    if pcm_data is None:
        pcm_data = load_wav_file(filepath)
        if pcm_data is None:
            print(f"[AUDIO] 音频加载失败: {audio_key} -> {filepath}")
            return

    # 如果是压缩的数据，先解压
    if pcm_data and len(pcm_data) > 5 and pcm_data[0] in [0x01, 0x02]:
        pcm_data = compressed_audio_cache.decompress(pcm_data)
        if not pcm_data:
            print(f"[AUDIO] 解压失败: {audio_key}")
            return

    # 播放前刷新一次蓝牙输出状态，确保与 play_voice_text 等路径一致
    _refresh_output_mode_from_bluetooth()

    _enqueue_pcm_threadsafe(pcm_data)

# 全局语音节流
_last_voice_time = 0
_last_voice_text = ""
try:
    _voice_cooldown = float(os.getenv("AIGLASS_VOICE_TEXT_COOLDOWN_SEC", "0.8"))
except Exception:
    _voice_cooldown = 0.8

# 语音优先级定义
VOICE_PRIORITY = {
    'obstacle': 100,     # 障碍物 - 最高优先级
    'direction': 50,     # 转向/平移 - 中等优先级  
    'straight': 10,      # 保持直行 - 最低优先级
    'other': 30          # 其他 - 默认优先级
}

# 新增：根据中文提示文案直接播放（会做轻度规范化与降级）
def play_voice_text(text: str):
    """
    传入中文提示，自动匹配 voice 映射并播放。
    - 尝试原文
    - 尝试补全/去除句末标点（。.!！?？）
    - 若包含"前方有…注意避让"但未命中，降级到"前方有障碍物，注意避让。"
    """
    global _last_voice_time, _last_voice_text

    print(f"[AUDIO] play_voice_text 被调用: {text}")
    _force_audio_log("play_voice_text_enter", text=text)
    _bump_audio_metric("requested", 1)

    raw_text = str(text or "").strip()
    cleaned_text = _sanitize_tts_text(raw_text)
    final_text = cleaned_text or raw_text

    if cleaned_text and cleaned_text != raw_text:
        _force_audio_log("play_voice_text_sanitized", raw=raw_text, cleaned=cleaned_text)

    if not final_text:
        print(f"[AUDIO] 文本为空，跳过播放")
        _bump_audio_metric("suppressed_empty", 1)
        _maybe_report_audio_metrics()
        return
    if not _initialized:
        print(f"[AUDIO] 音频系统未初始化，正在初始化...")
        initialize_audio_system()
        print(f"[AUDIO] 音频系统初始化完成，_initialized={_initialized}")

    # 全局节流：相同文本短时间内不重复播放
    current_time = time.time()
    delta = current_time - _last_voice_time
    is_critical = _is_critical_text(final_text)
    if final_text == _last_voice_text and delta < _voice_cooldown and not is_critical:
        print(f"[AUDIO] 节流跳过: {final_text} (距离上次 {delta:.2f}秒)")
        _force_audio_log("play_voice_text_suppressed", text=final_text, reason="cooldown", delta=f"{delta:.2f}")
        _bump_audio_metric("suppressed_cooldown", 1)
        _maybe_report_audio_metrics()
        return
    if final_text == _last_voice_text and delta < _voice_cooldown and is_critical:
        _force_audio_log("play_voice_text_cooldown_bypass", text=final_text, delta=f"{delta:.2f}")

    resolve_t0 = time.monotonic()
    pcm_data = _get_pcm_for_text(final_text, allow_tts=True, save_generated=True)
    if not pcm_data:
        # 针对"前方有…注意避让"降级
        t = final_text
        if ("前方有" in t) and ("注意避让" in t):
            fallback = "前方有障碍物，注意避让。"
            print(f"[AUDIO] 使用降级文本: '{fallback}'")
            pcm_data = _get_pcm_for_text(fallback, allow_tts=True, save_generated=True)
    resolve_ms = (time.monotonic() - resolve_t0) * 1000.0
    _bump_audio_metric("resolve_ms_total", resolve_ms)
    _bump_audio_metric("resolve_samples", 1)

    if pcm_data:
        print(f"[AUDIO] 成功获取音频数据: '{final_text}' ({len(pcm_data)} bytes)")
        _bump_audio_metric("resolved", 1)
        _force_audio_log(
            "play_voice_text_resolved",
            text=final_text,
            source=_last_audio_resolve_source,
            bytes=len(pcm_data),
            resolve_ms=f"{resolve_ms:.1f}",
        )
        _enqueue_pcm_threadsafe(pcm_data)
        _last_voice_text = final_text
        _last_voice_time = current_time
        _maybe_report_audio_metrics()
        return

    # 完全失败，输出日志
    print(f"[AUDIO] 播放失败: 未找到音频且 TTS 不可用 - '{final_text}'")
    _force_audio_log("play_voice_text_failed", text=final_text, reason="no_audio", resolve_ms=f"{resolve_ms:.1f}")
    _bump_audio_metric("failed_no_audio", 1)
    _maybe_report_audio_metrics()

# 兼容旧接口
play_audio_on_esp32 = play_audio_threadsafe


def play_structured_voice(payload: dict) -> bool:
    """
    结构化语音播报：
    - 优先用片段拼接（scene + direction + distance + object + action）
    - 片段缺失时，混合使用预录音频 + TTS
    - 全部失败则回退到全文 TTS

    Args:
        payload: schema_version=2 的结构化语音数据

    Returns:
        bool: 是否成功播放
    """
    global _last_voice_time, _last_voice_text

    print(f"[AUDIO] play_structured_voice 被调用, schema_version={payload.get('schema_version')}")
    _force_audio_log("play_structured_voice_enter", schema=payload.get("schema_version"), text=(payload.get("text") or ""))

    if not isinstance(payload, dict):
        print(f"[AUDIO] payload 不是字典类型")
        return False
    if int(payload.get("schema_version", 0) or 0) < 2:
        print(f"[AUDIO] schema_version < 2，不处理")
        return False

    if not _initialized:
        initialize_audio_system()

    text_full = (payload.get("text") or "").strip()
    current_time = time.time()
    if text_full and text_full == _last_voice_text and current_time - _last_voice_time < _voice_cooldown:
        print(f"[AUDIO] 节流跳过（结构化语音）: '{text_full}'")
        return True

    # 检查环境变量，如果禁用片段拼接则直接播放全文
    if os.getenv("AIGLASS_STRUCTURED_FRAGMENT_SPEAK", "1") != "1":
        print(f"[AUDIO] 片段拼接被禁用，直接播放全文")
        if text_full:
            play_voice_text(text_full)
            return True
        return False

    objs = payload.get("objects") or []
    if not objs:
        print(f"[AUDIO] 没有物体信息")
        return False

    obj = objs[0] or {}
    direction = obj.get("direction") or {}
    distance = obj.get("distance") or {}
    scene_zh = (payload.get("scene_zh") or "").strip()

    # 构建片段列表
    parts = []
    urgency = str(obj.get("urgency") or "").upper()
    if urgency == "HIGH":
        parts.append("紧急")
    elif urgency == "MEDIUM":
        parts.append("注意")

    if scene_zh:
        parts.append(scene_zh)

    fmt = os.getenv("AIGLASS_DIRECTION_FORMAT", "clock").lower()
    clock = direction.get("clock")
    lr_zh = direction.get("lr_zh") or direction.get("lr") or ""
    if fmt == "lr":
        if lr_zh:
            parts.append(str(lr_zh))
    elif fmt == "both":
        if clock:
            parts.append(f"{clock}点方向")
        if lr_zh:
            parts.append(str(lr_zh))
    else:
        if clock:
            parts.append(f"{clock}点方向")

    use_steps = os.getenv("AIGLASS_DISTANCE_FORMAT", "steps").lower() == "steps"
    if use_steps:
        steps = distance.get("steps") or obj.get("distance_steps")
        if steps:
            parts.append(f"约{int(steps)}步")
    else:
        meters = distance.get("meters") or obj.get("distance_m")
        if meters is not None:
            m = float(meters)
            parts.append(f"{m:.0f}米" if m >= 1.0 else f"{m:.1f}米")

    name_zh = obj.get("name_zh") or obj.get("name") or ""
    if name_zh:
        parts.append(str(name_zh))

    action = (obj.get("action") or obj.get("avoidance_action") or "").strip()
    if action:
        parts.append(action.rstrip("。"))

    print(f"[AUDIO] 片段列表: {parts}")

    # 片段拼接播放（支持混合模式：部分预录 + 部分 TTS）
    gap_ms = int(os.getenv("AIGLASS_FRAGMENT_GAP_MS", "40"))
    gap = b"\x00" * (gap_ms * 8000 * 2 // 1000)
    pcm_chunks = []
    use_hybrid = os.getenv("AIGLASS_HYBRID_FRAGMENT_MODE", "1") == "1"  # 默认启用混合模式

    for p in parts:
        p = (p or "").strip()
        if not p:
            continue
        pcm = _get_pcm_for_text(p, allow_tts=True, save_generated=True)
        if not pcm:
            if use_hybrid:
                # 混合模式：继续尝试其他片段
                print(f"[AUDIO] 混合模式: 片段 '{p}' 失败，继续下一个")
                continue
            else:
                # 严格模式：任何片段失败都放弃拼接
                print(f"[AUDIO] 严格模式: 片段 '{p}' 失败，放弃拼接")
                pcm_chunks = []
                break
        pcm_chunks.append(pcm)

    if pcm_chunks:
        print(f"[AUDIO] 成功拼接 {len(pcm_chunks)} 个片段")
        pcm = gap.join(pcm_chunks)
        _force_audio_log(
            "play_structured_voice_resolved",
            source="structured_fragments",
            chunks=len(pcm_chunks),
            bytes=len(pcm),
        )
        _enqueue_pcm_threadsafe(pcm)
        if text_full:
            _last_voice_text = text_full
            _last_voice_time = current_time
        return True

    # 片段拼接失败，回退到全文播报
    print(f"[AUDIO] 片段拼接失败，回退到全文播报")
    _force_audio_log("play_structured_voice_fallback", source="full_text")
    if text_full:
        play_voice_text(text_full)
        return True

    # 全文也没有，尝试组合一个基本播报
    fallback_text = "".join(parts)
    if fallback_text:
        print(f"[AUDIO] 使用组合文本回退: '{fallback_text}'")
        play_voice_text(fallback_text)
        return True

    return False


def play_numbered_list_text(text: str) -> bool:
    """
    播放编号列表格式的文本

    支持格式：
    - "第一、12点方向1米处为斑马线，可以通过"
    - "第一、12点方向1米处为斑马线，可以通过；第二、3点方向2米处有人，注意避让"

    会将分号分隔的每个条目独立播报。

    Args:
        text: 编号列表格式的文本

    Returns:
        bool: 是否成功播放
    """
    if not text:
        return False

    print(f"[AUDIO] play_numbered_list_text 被调用: '{text}'")

    # 检查是否包含编号词
    has_numbering = any(text.startswith(f"{num}、") for num in ["第一", "第二", "第三", "第四", "第五"])

    if not has_numbering:
        # 不是编号列表格式，直接播放
        play_voice_text(text)
        return True

    # 按分号分割
    items = [item.strip() for item in text.split("；") if item.strip()]

    if not items:
        play_voice_text(text)
        return True

    # 如果只有一个条目，直接播放
    if len(items) == 1:
        play_voice_text(items[0])
        return True

    # 多个条目时，播放第一个（避免过长）
    # 也可以配置为播放全部，但可能会造成积压
    play_multiple = os.getenv("AIGLASS_PLAY_ALL_NUMBERED_ITEMS", "0") == "1"

    if play_multiple:
        print(f"[AUDIO] 播放所有 {len(items)} 个编号条目")
        for i, item in enumerate(items):
            if i > 0:
                # 条目之间稍作延迟
                time.sleep(0.1)
            play_voice_text(item)
    else:
        print(f"[AUDIO] 播放第一个编号条目（共 {len(items)} 个）")
        play_voice_text(items[0])

    return True
