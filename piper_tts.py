# piper_tts.py
"""
Piper-TTS 轻量级神经 TTS 封装

Piper 是一个快速的、本地化的神经网络文本转语音系统，
支持中文语音合成，无需联网。
"""
import os
import subprocess
import tempfile
import logging
from typing import Optional
from pathlib import Path
import wave
import numpy as np

logger = logging.getLogger(__name__)


class PiperTTS:
    """
    Piper-TTS 封装类

    支持通过命令行或 Python 库调用 Piper 进行语音合成
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        model_name: str = "zh_CN-huayan-medium",
        executable: str = "piper"
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

        # 检查模型和可执行文件
        self._available = False
        if self.enabled:
            self._check_availability()

    def _check_availability(self):
        """检查 Piper 是否可用"""
        # 检查模型文件
        if not os.path.exists(self.model_path):
            logger.warning(f"[Piper] 模型文件不存在: {self.model_path}")
            logger.info("[Piper] 要使用 Piper-TTS，请下载中文模型:")
            logger.info("[Piper] bash scripts/download_piper_model.sh")
            logger.info("[Piper] 或: python scripts/download_piper_model.py")
            return

        # 检查可执行文件或 Python 包
        if self._check_executable() or self._check_python_package():
            self._available = True
            logger.info("[Piper] Piper-TTS 已就绪")
        else:
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
        # 优先使用 onnxruntime（已安装）
        try:
            import onnxruntime
            return True
        except ImportError:
            pass
        # 备用：检查 piper 包
        try:
            import piper
            return True
        except ImportError:
            return False

    def is_available(self) -> bool:
        """检查 TTS 是否可用"""
        return self.enabled and self._available

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
        if not text:
            return None

        # 使用临时文件
        use_temp = output_path is None
        if use_temp:
            output_path = os.path.join(tempfile.gettempdir(), f"tts_{id(text)}.wav")

        try:
            # 方法1: 使用 onnxruntime 直接运行 ONNX 模型
            try:
                import onnxruntime as ort
                import numpy as np
                import wave
                import json

                # 加载配置
                config_path = self.model_path.replace(".onnx", ".onnx.json")
                with open(config_path, 'r') as f:
                    config = json.load(f)

                sample_rate = config['audio']['sample_rate']
                noise_scale = config['inference']['noise_scale']
                length_scale = config['inference']['length_scale']

                # 创建 ONNX Runtime session
                sess_opts = ort.SessionOptions()
                sess_opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
                session = ort.InferenceSession(self.model_path, sess_opts)

                # 简单的文本转音素编码（这里简化处理，实际需要 piper-phonemize）
                # 对于中文，我们使用一个简单的映射或直接传入
                # 注意：这是简化版本，完整版本需要 piper-phonemize

                # 由于完整 TTS 需要音素编码器，这里使用命令行回退
                raise NotImplementedError("需要 piper 命令行工具")

            except (NotImplementedError, ImportError):
                # 方法2: 使用 piper 命令行工具
                # 先将文本写入临时文件
                with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                    f.write(text)
                    temp_input = f.name

                try:
                    result = subprocess.run(
                        [
                            self.executable,
                            "--model", self.model_path,
                            "--input_file", temp_input,
                            "--output_file", output_path
                        ],
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
        将文本转换为 PCM16 音频数据

        Args:
            text: 要合成的文本

        Returns:
            bytes: PCM16 音频数据，失败返回 None
        """
        if not self._available:
            return None

        # 生成临时文件
        wav_path = self.text_to_file(text)
        if not wav_path:
            return None

        try:
            # 读取 WAV 文件
            import wave
            with wave.open(wav_path, "rb") as wav_file:
                frames = wav_file.readframes(wav_file.getnframes())
                return frames

        except Exception as e:
            logger.error(f"[Piper] 读取音频失败: {e}")
            return None
        finally:
            # 清理临时文件
            if os.path.exists(wav_path):
                try:
                    os.remove(wav_path)
                except Exception:
                    pass


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
