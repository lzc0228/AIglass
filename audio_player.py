# audio_player.py
# 处理预录音频文件的播放，���持 ESP32 扬声器、蓝牙、本地音频输出

import os
import wave
import json
import asyncio
import threading
import queue
import time
from audio_stream import broadcast_pcm16_realtime
from audio_compressor import compressed_audio_cache, AudioCompressor

# 蓝牙音频支持
_bluetooth_manager = None
_piper_tts = None
_tts_enabled = False
_output_mode = "local"  # local/bluetooth/esp32

def _init_audio_output():
    """初始化音频输出系统（蓝牙、TTS）"""
    global _bluetooth_manager, _piper_tts, _tts_enabled, _output_mode

    # 读取输出模式配置
    _output_mode = os.getenv("AIGLASS_AUDIO_OUTPUT", "local")
    auto_switch = os.getenv("AIGLASS_AUDIO_AUTO_SWITCH", "1") == "1"

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
    _tts_enabled = os.getenv("AIGLASS_TTS_ENABLED", "0") == "1"
    if _tts_enabled:
        try:
            from piper_tts import get_piper_tts
            _piper_tts = get_piper_tts()
            if _piper_tts.is_available():
                print("[AUDIO] Piper-TTS 已启用")
            else:
                print("[AUDIO] Piper-TTS 不可用，将仅使用预录音频")
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

# 音频播放队列和工作线程 - 使用优先级队列
_audio_queue = queue.PriorityQueue(maxsize=10)
_audio_priority = 0  # 递增的优先级计数器
_worker_thread = None
_worker_loop = None
_is_playing = False  # 标记是否正在播放音频
_playing_lock = threading.Lock()  # 播放锁
_initialized = False
_last_play_ts = 0.0  # 记录上次播放结束时间，用于决定预热静音长度

def load_wav_file(filepath):
    """加载WAV文件并返回PCM数据（自动转换为8kHz）"""
    if filepath in _audio_cache:
        return _audio_cache[filepath]
    
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
        print(f"[AUDIO] 加载音频文件失败 {filepath}: {e}")
        return None

def _merge_voice_map():
    """读取 voice/map.zh-CN.json 并合并到 AUDIO_MAP"""
    try:
        # 兼容：map 文件可放在 VOICE_DIR、AIGLASS_AUDIO_DIR 或由环境变量直接指定
        map_candidates = [
            VOICE_MAP_FILE,
            os.path.join(VOICE_DIR, "map.zh-CN.json"),
            os.path.join(AUDIO_BASE_DIR, "map.zh-CN.json"),
            os.path.join(_BASE_DIR, "voice", "map.zh-CN.json"),
        ]
        map_path = next((p for p in map_candidates if p and os.path.exists(p)), None)
        if not map_path:
            print(f"[AUDIO] 未找到 voice 映射文件（可选）: {VOICE_MAP_FILE}")
            print(f"[AUDIO] 提示：可在 .env 设置 VOICE_DIR 或 AIGLASS_VOICE_MAP_FILE 来指定映射文件路径")
            return

        with open(map_path, "r", encoding="utf-8") as f:
            m = json.load(f)
        map_dir = os.path.dirname(map_path)
        added = 0
        for text, info in (m or {}).items():
            files = (info or {}).get("files") or []
            if not files:
                continue
            # files 支持：相对 map 文件目录的相对路径、或绝对路径
            for fname in files:
                raw = os.path.expandvars(os.path.expanduser(str(fname or ""))).strip()
                if not raw:
                    continue
                fpath = raw if os.path.isabs(raw) else os.path.join(map_dir, raw)
                if os.path.exists(fpath):
                    AUDIO_MAP[text] = fpath
                    added += 1
                    break
        print(f"[AUDIO] 已合并 voice 映射 {added} 条（map={map_path}）")
    except Exception as e:
        print(f"[AUDIO] 读取 voice 映射失败: {e}")

def preload_all_audio():
    """预加载所有音频文件到内存"""
    print("[AUDIO] 开始预加载音频文件...")
    loaded_count = 0
    
    # 【暂时禁用变速】因为需要修改缓存机制
    # 需要加速的音频列表（斑马线相关）
    # speedup_keywords = ["斑马线", "画面"]
    # speedup_factor = 1.3  # 加速30%
    
    for audio_key, filepath in AUDIO_MAP.items():
        if os.path.exists(filepath):
            # 【修复】暂时使用默认速度加载
            # need_speedup = any(keyword in audio_key for keyword in speedup_keywords)
            # speed = speedup_factor if need_speedup else 1.0
            
            data = load_wav_file(filepath)  # 使用默认参数
            if data:
                loaded_count += 1
                # if need_speedup:
                #     print(f"[AUDIO] 加载（加速{speedup_factor}x）: {audio_key}")
        else:
            # 降低噪声输出
            pass
    print(f"[AUDIO] 预加载完成，共加载 {loaded_count} 个音频文件")

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
    
    _worker_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_worker_loop)
    
    async def process_queue():
        while True:
            try:
                # 从优先级队列获取数据
                priority_data = await asyncio.get_event_loop().run_in_executor(None, _audio_queue.get, True)
                if priority_data is None:
                    break
                # 解包优先级和实际音频数据
                if isinstance(priority_data, tuple) and len(priority_data) == 2:
                    _, audio_data = priority_data
                else:
                    audio_data = priority_data
                await _broadcast_audio_optimized(audio_data)
            except Exception as e:
                print(f"[AUDIO] 工作线程错误: {e}")
    
    _worker_loop.run_until_complete(process_queue())

async def _broadcast_audio_optimized(pcm_data: bytes):
    """优化的音频广播：单次调用由底层按20ms节拍发送，移除重复节拍和Python层sleep"""
    global _last_play_ts, _is_playing
    try:
        # 设置播放标志
        with _playing_lock:
            _is_playing = True
        # 此时 pcm_data 应该已经是解压后的16位PCM数据了（8kHz）
        now = time.monotonic()
        idle_sec = now - (_last_play_ts or now)
        # 首次或长时间空闲后，预热更长静音；否则小静音
        lead_ms = 160 if idle_sec > 3.0 else 60
        tail_ms = 40

        lead_silence = b'\x00' * (lead_ms * 8000 * 2 // 1000)  # 8k * 2B
        tail_silence = b'\x00' * (tail_ms * 8000 * 2 // 1000)

        # 完整音频数据（包含静音）
        full_audio = lead_silence + pcm_data + tail_silence
        
        # 注意：录制在 broadcast_pcm16_realtime 中统一完成，避免重复

        # 单次调用交给底层 pacing（20ms节拍在 broadcast_pcm16_realtime 内部实现）
        await broadcast_pcm16_realtime(full_audio)

        _last_play_ts = time.monotonic()
    except Exception as e:
        print(f"[AUDIO] 广播音频失败: {e}")
    finally:
        # 清除播放标志
        with _playing_lock:
            _is_playing = False

def initialize_audio_system():
    """初始化音频系统"""
    global _initialized, _worker_thread, _last_play_ts

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
        print(f"[AUDIO] 音频未在缓存中: {audio_key}")
        return

    # 如果是压缩的数据，先解压
    if pcm_data and len(pcm_data) > 5 and pcm_data[0] in [0x01, 0x02]:
        pcm_data = compressed_audio_cache.decompress(pcm_data)
        if not pcm_data:
            print(f"[AUDIO] 解压失败: {audio_key}")
            return

    # 【新增】动态蓝牙检测：如果启用自动切换，每次播放前检查蓝牙状态
    auto_switch = os.getenv("AIGLASS_AUDIO_AUTO_SWITCH", "1") == "1"
    if auto_switch and _bluetooth_manager:
        # 检查当前蓝牙连接状态
        is_bluetooth_connected = _bluetooth_manager.check_connection()
        if is_bluetooth_connected:
            if _output_mode != "bluetooth":
                _output_mode = "bluetooth"
                print(f"[AUDIO] 检测到蓝牙已连接，切换音频输出到蓝牙")
        else:
            if _output_mode == "bluetooth":
                _output_mode = "local"
                print(f"[AUDIO] 蓝牙未连接，切换音频输出到本地扬声器")

    # 【优化】实时播报策略：保持队列最小化，避免积压延迟
    queue_size = _audio_queue.qsize()

    # 检查是否正在播放
    with _playing_lock:
        currently_playing = _is_playing

    # 实时策略：只允许1个积压，超过立即清空
    if queue_size > 0 and not currently_playing:
        # 未播放时立即清空，播放最新语音
        print(f"[AUDIO] 清空队列（当前{queue_size}个），播放最新语音")
        _audio_queue = queue.PriorityQueue(maxsize=10)
    elif queue_size > 1 and currently_playing:
        # 正在播放时，如果积压>1个则清空（保持实时性）
        print(f"[AUDIO] 队列积压({queue_size}个)，清空以保持实时")
        _audio_queue = queue.PriorityQueue(maxsize=10)
    try:
        # 使用优先级队列，确保音频按顺序播放
        _audio_priority += 1
        _audio_queue.put_nowait((_audio_priority, pcm_data))
        if queue_size >= 1:
            print(f"[AUDIO] 播放队列当前大小: {queue_size + 1}")
    except queue.Full:
        # 播放队列满则丢弃，保持实时性
        print(f"[AUDIO] 队列满，丢弃: {audio_key}")
        pass

# 全局语音节流
_last_voice_time = 0
_last_voice_text = ""
_voice_cooldown = 1.0  # 相同语音至少间隔1秒

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

    if not text:
        print(f"[AUDIO] 文本为空，跳过播放")
        return
    if not _initialized:
        print(f"[AUDIO] 音频系统未初始化，正在初始化...")
        initialize_audio_system()
        print(f"[AUDIO] 音频系统初始化完成，_initialized={_initialized}")

    # 全局节流：相同文本短时间内不重复播放
    current_time = time.time()
    if text == _last_voice_text and current_time - _last_voice_time < _voice_cooldown:
        print(f"[AUDIO] 节流跳过: {text} (距离上次 {current_time - _last_voice_time:.2f}秒)")
        return  # 静默跳过

    candidates = []
    t = text.strip()
    candidates.append(t)
    # 尝试补全句号
    if t[-1:] not in ("。", "！", "!", "？", "?", "."):
        candidates.append(t + "。")
    else:
        # 尝试去掉标点
        t2 = t.rstrip("。.!！?？")
        if t2 and t2 != t:
            candidates.append(t2)

    # 逐一尝试匹配
    for ck in candidates:
        if ck in AUDIO_MAP:
            audio_file = AUDIO_MAP[ck]
            print(f"[AUDIO] 找到映射: '{ck}' -> '{audio_file}'")
            if os.path.exists(audio_file):
                print(f"[AUDIO] 音频文件存在，开始播放")
            else:
                print(f"[AUDIO] 警告: 音频文件不存在: {audio_file}")
            play_audio_threadsafe(ck)
            _last_voice_text = text
            _last_voice_time = current_time
            return

    # 针对"前方有…注意避让"降级
    if ("前方有" in t) and ("注意避让" in t):
        fallback = "前方有障碍物，注意避让。"
        if fallback in AUDIO_MAP:
            print(f"[AUDIO] 降级使用: {fallback}")
            play_audio_threadsafe(fallback)
            _last_voice_text = text
            _last_voice_time = current_time
            return

    # 针对"请向…平移/微调/转动"类词条，常见变体尝试
    base = t.rstrip("。.!！?？")
    if base in AUDIO_MAP:
        print(f"[AUDIO] 找到基础映射: '{base}'")
        play_audio_threadsafe(base)
        _last_voice_text = text
        _last_voice_time = current_time
        return
    if base + "。" in AUDIO_MAP:
        print(f"[AUDIO] 找到带句号映射: '{base}。'")
        play_audio_threadsafe(base + "。")
        _last_voice_text = text
        _last_voice_time = current_time
        return

    # ========== TTS 回退（新增）==========
    # 如果没有预录音频，尝试使用 Piper-TTS
    global _piper_tts, _tts_enabled, _worker_loop
    print(f"[AUDIO] TTS状态: enabled={_tts_enabled}, available={_piper_tts.is_available() if _piper_tts else False}")
    if _tts_enabled and _piper_tts and _piper_tts.is_available():
        try:
            wav_path = _piper_tts.text_to_file(text)
            if wav_path and os.path.exists(wav_path):
                print(f"[AUDIO] 使用 TTS 生成语音: {text}")
                # 加载并播放生成的音频
                pcm_data = load_wav_file(wav_path)
                if pcm_data and _worker_loop:
                    # 直接播放（不经过队列，保持低延迟）
                    asyncio.run_coroutine_threadsafe(
                        _broadcast_audio_optimized(pcm_data),
                        _worker_loop
                    )
                    # 清理临时文件
                    try:
                        os.remove(wav_path)
                    except Exception:
                        pass
                    _last_voice_text = text
                    _last_voice_time = current_time
                    return
        except Exception as e:
            print(f"[AUDIO] TTS 生成失败: {e}")

    # 未匹配则输出日志（便于调试）
    print(f"[AUDIO] 未找到匹配语音: {text}, 候选: {candidates}")

# 兼容旧接口
play_audio_on_esp32 = play_audio_threadsafe
