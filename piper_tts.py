# piper_tts.py
"""
Piper-TTS 轻量级神经 TTS 封装（带预热和缓存优化）

Piper 是一个快速的、本地化的神经网络文本转语音系统，
支持中文语音合成，无需联网。

优化：
- 模型预热：启动时预加载常用短语
- 缓存机制：缓存已生成的语音
- 减少延迟：优化生成流程
"""
import os
import subprocess
import tempfile
import logging
import time
import sys
from typing import Optional, Dict
from pathlib import Path
import wave
import numpy as np
import threading

logger = logging.getLogger(__name__)


# 高频短语缓存列表（启动时预生成）
COMMON_PHRASES = [
    "注意",
    "前方有障碍物",
    "先停一下",
    "保持直行",
    "左转一点",
    "右转一点",
    "从左侧绕开",
    "从右侧绕开",
    "注意安全",
    "小心",
]


class PiperTTS:
    """
    Piper-TTS 封装类（带预热和缓存）

    支持通过命令行或 Python 库调用 Piper 进行语音合成
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        model_name: str = "zh_CN-huayan-medium",
        executable: str = "piper",
    ):
        """
        初始化 Piper-TTS

        Args:
            model_path: 模型文件路径 (.onnx)
            model_name: 模型名称（用于查找默认路径）
            executable: piper 可执行文件路径
        """
        self.enabled = os.getenv("AIGLASS_TTS_ENABLED", "1") == "1"
        self.model_name = model_name

        # 确定模型路径
        if model_path:
            self.model_path = model_path
        else:
            # 默认路径（从环境变量读取，支持 huayan/piper 等模型）
            self.model_path = os.getenv("AIGLASS_TTS_MODEL")
            if not self.model_path:
                base_dir = os.path.dirname(os.path.abspath(__file__))
                self.model_path = os.path.join(base_dir, "model", "piper", f"{model_name}.onnx")

        # 可执行文件路径
        self.executable = executable
        self._use_python_module = False

        # 【新增】缓存和预热相关
        self._cache: Dict[str, bytes] = {}  # 文本 -> PCM 数据缓存
        self._cache_lock = threading.Lock()
        self._warmup_done = False
        self._max_cache_size = int(os.getenv("AIGLASS_TTS_CACHE_SIZE", "50"))

        # 检查模型和可执行文件
        self._available = False
        if self.enabled:
            self._check_availability()
            # 自动预热（如果启用）
            if os.getenv("AIGLASS_TTS_WARMUP", "1") == "1" and self._available:
                self._warmup_async()

    def _wav_to_pcm8k(self, wav_path: str) -> Optional[bytes]:
        """读取 WAV 并统一转换为 8kHz 单声道 PCM16"""
        try:
            with wave.open(wav_path, "rb") as wav_file:
                channels = wav_file.getnchannels()
                sampwidth = wav_file.getsampwidth()
                framerate = wav_file.getframerate()
                frames = wav_file.readframes(wav_file.getnframes())
            if channels == 2:
                import audioop
                frames = audioop.tomono(frames, sampwidth, 1, 0)
            if framerate != 8000:
                import audioop
                frames, _ = audioop.ratecv(frames, sampwidth, 1, framerate, 8000, None)
            return frames
        except Exception as e:
            logger.warning(f"[Piper] 读取/重采样失败: {e}")
            return None

    def _check_availability(self):
        """检查 Piper 是否可用"""
        # 检查模型文件
        if not os.path.exists(self.model_path):
            logger.warning(f"[Piper] 模型文件不存在: {self.model_path}")
            logger.info("[Piper] 要使用 Piper-TTS，请下载中文模型:")
            logger.info("[Piper] bash scripts/download_piper_model.sh")
            logger.info("[Piper] 或: python scripts/download_piper_model.py")
            return

        has_exec = self._check_executable()
        has_pkg = self._check_python_package()

        if has_exec:
            self._use_python_module = False
            self._available = True
            logger.info("[Piper] Piper-TTS 已就绪（命令行）")
            return

        if has_pkg:
            if self._check_python_module_entrypoint():
                self._use_python_module = True
                self._available = True
                logger.info("[Piper] Piper-TTS 已就绪（python -m piper）")
            else:
                logger.warning("[Piper] 已安装 piper 包，但 python -m piper 不可执行")
            return

        logger.warning("[Piper] Piper 不可用，请安装: pip install piper-tts")

    def _check_executable(self) -> bool:
        """检查 piper 可执行文件是否存在"""
        try:
            result = subprocess.run(
                [self.executable, "--help"],
                capture_output=True,
                timeout=2
            )
            return result.returncode == 0 or "--help" in result.stdout.decode()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _check_python_package(self) -> bool:
        """检查 piper Python 包是否可用"""
        try:
            import piper
            return True
        except ImportError:
            return False

    def _check_python_module_entrypoint(self) -> bool:
        """检查 python -m piper 是否可调用。"""
        try:
            result = subprocess.run(
                [sys.executable, "-m", "piper", "--help"],
                capture_output=True,
                timeout=3,
            )
            return result.returncode == 0
        except Exception:
            return False

    def _build_piper_command(self, temp_input: str, output_path: str):
        """构建 Piper 调用命令。"""
        if self._use_python_module:
            return [
                sys.executable,
                "-m",
                "piper",
                "--model",
                self.model_path,
                "--input_file",
                temp_input,
                "--output_file",
                output_path,
            ]

        return [
            self.executable,
            "--model",
            self.model_path,
            "--input_file",
            temp_input,
            "--output_file",
            output_path,
        ]

    def _warmup_async(self):
        """异步预热：在后台线程中预生成高频短语"""
        def warmup_thread():
            try:
                start = time.time()
                for phrase in COMMON_PHRASES:
                    self._ensure_cached(phrase)
                elapsed = time.time() - start
                self._warmup_done = True
                logger.info(f"[Piper] TTS预热完成，耗时 {elapsed:.2f}秒，已缓存 {len(self._cache)} 个短语")
            except Exception as e:
                logger.warning(f"[Piper] TTS预热失败: {e}")

        thread = threading.Thread(target=warmup_thread, daemon=True)
        thread.start()

    def _ensure_cached(self, text: str) -> Optional[bytes]:
        """确保文本已缓存，返回 PCM 数据"""
        text_key = text.strip()

        # 检查缓存
        with self._cache_lock:
            if text_key in self._cache:
                return self._cache[text_key]

        # 未缓存，生成并存储
        wav_path = self.text_to_file(text_key)
        if wav_path and os.path.exists(wav_path):
            try:
                frames = self._wav_to_pcm8k(wav_path)
                if not frames:
                    return None

                # 存入缓存
                with self._cache_lock:
                    # 限制缓存大小
                    if len(self._cache) >= self._max_cache_size:
                        # 移除最旧的条目（简单策略）
                        oldest = next(iter(self._cache))
                        del self._cache[oldest]
                    self._cache[text_key] = frames

                # 清理临时文件
                try:
                    os.remove(wav_path)
                except Exception:
                    pass

                return frames
            except Exception as e:
                logger.warning(f"[Piper] 缓存生成失败: {e}")

        return None

    def is_available(self) -> bool:
        """检查 TTS 是否可用"""
        return self.enabled and self._available

    def is_warmup_done(self) -> bool:
        """检查预热是否完成"""
        return self._warmup_done

    @staticmethod
    def _has_speakable_content(text: str) -> bool:
        """过滤纯标点/空白文本，避免无效 TTS 调用。"""
        if not text:
            return False
        return any(ch.isalnum() for ch in text)

    def get_cache_stats(self) -> Dict[str, any]:
        """获取缓存统计信息"""
        with self._cache_lock:
            return {
                "cached_count": len(self._cache),
                "max_cache_size": self._max_cache_size,
                "warmup_done": self._warmup_done,
                "cached_phrases": list(self._cache.keys()),
            }

    def text_to_file(self, text: str, output_path: Optional[str] = None) -> Optional[str]:
        """
        将文本转换为 WAV 文件

        Args:
            text: 要合成的文本
            output_path: 输出文件路径（可选，默认使用临时文件）

        Returns:
            str: 生成的 WAV 文件路径，失败返回 None
        """
        if not self._available:
            logger.warning("[Piper] TTS 不可用")
            return None

        # 清理文本
        text = text.strip()
        if not text or not self._has_speakable_content(text):
            return None

        # 使用临时文件
        use_temp = output_path is None
        if use_temp:
            output_path = os.path.join(tempfile.gettempdir(), f"tts_{id(text)}.wav")

        try:
            # 方法: 使用 piper 命令行工具
            # 先将文本写入临时文件
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                f.write(text)
                temp_input = f.name

            try:
                cmd = self._build_piper_command(temp_input, output_path)
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
            finally:
                os.unlink(temp_input)

            if result.returncode == 0 and os.path.exists(output_path):
                logger.debug(f"[Piper] 使用命令行生成音频: {output_path}")
                return output_path
            else:
                logger.error(f"[Piper] 生成失败: {result.stderr}")
                return None

        except subprocess.TimeoutExpired:
            logger.error("[Piper] 生成超时")
            return None
        except Exception as e:
            logger.error(f"[Piper] 生成异常: {e}")
            return None

    def text_to_audio(self, text: str) -> Optional[bytes]:
        """
        将文本转换为 PCM16 音频数据（优先使用缓存）

        Args:
            text: 要合成的文本

        Returns:
            bytes: PCM16 音频数据，失败返回 None
        """
        if not self._available:
            return None

        text = (text or "").strip()
        if not text or not self._has_speakable_content(text):
            return None

        # 先尝试从缓存获取（缓存未命中时会生成并写入）
        return self._ensure_cached(text)


# 全局单例
_piper_tts: Optional[PiperTTS] = None


def get_piper_tts() -> PiperTTS:
    """获取 Piper-TTS 单例"""
    global _piper_tts
    if _piper_tts is None:
        _piper_tts = PiperTTS()
    return _piper_tts


def text_to_speech(text: str, output_path: Optional[str] = None) -> Optional[str]:
    """
    便捷函数：文本转语音

    Args:
        text: 要合成的文本
        output_path: 输出文件路径（可选）

    Returns:
        str: 生成的 WAV 文件路径，失败返回 None
    """
    return get_piper_tts().text_to_file(text, output_path)
