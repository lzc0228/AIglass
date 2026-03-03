# omni_client.py
# -*- coding: utf-8 -*-
import os, base64
from typing import AsyncGenerator, Dict, Any, List, Optional, Tuple

from openai import OpenAI

# ===== OpenAI 兼容（达摩院 DashScope 兼容模式）=====
# API Key 从环境变量读取（也可在 .env 中配置）
API_KEY = os.getenv("DASHSCOPE_API_KEY")
if not API_KEY:
    raise RuntimeError("未设置 DASHSCOPE_API_KEY（请在环境变量或 .env 中配置）")

QWEN_MODEL = "qwen-omni-turbo"

# 兼容模式
oai_client = OpenAI(
    api_key=API_KEY,
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

class OmniStreamPiece:
    """对外的统一增量数据：text/audio 二选一或同时。"""
    def __init__(self, text_delta: Optional[str] = None, audio_b64: Optional[str] = None):
        self.text_delta = text_delta
        self.audio_b64  = audio_b64

async def stream_chat(
    content_list: List[Dict[str, Any]],
    voice: str = "Cherry",
    audio_format: str = "wav",
) -> AsyncGenerator[OmniStreamPiece, None]:
    """
    发起一轮 Omni-Turbo ChatCompletions 流式对话：
    - content_list: OpenAI chat 的 content，多模态（image_url/text）
    - 以 stream=True 返回
    - 增量产出：OmniStreamPiece(text_delta=?, audio_b64=?)
    """
    # 构建请求参数，将 modalities 和 audio 参数放在 extra_body 中
    extra_body = {
        "modalities": ["text", "audio"],
        "audio": {"voice": voice, "format": audio_format}
    }
    
    completion = oai_client.chat.completions.create(
        model=QWEN_MODEL,
        messages=[{"role": "user", "content": content_list}],
        stream=True,
        extra_body=extra_body  # 使用 extra_body 传递达摩院特有参数
    )

    # 注意：OpenAI SDK 的流是同步迭代器；在 async 场景下逐项 yield
    for chunk in completion:
        text_delta: Optional[str] = None
        audio_b64: Optional[str] = None

        if getattr(chunk, "choices", None):
            c0 = chunk.choices[0]
            delta = getattr(c0, "delta", None)
            # 文本增量
            if delta and getattr(delta, "content", None):
                piece = delta.content
                if piece:
                    text_delta = piece
            # 音频分片
            if delta and getattr(delta, "audio", None):
                aud = delta.audio
                audio_b64 = aud.get("data") if isinstance(aud, dict) else getattr(aud, "data", None)
            if audio_b64 is None:
                msg = getattr(c0, "message", None)
                if msg and getattr(msg, "audio", None):
                    ma = msg.audio
                    audio_b64 = ma.get("data") if isinstance(ma, dict) else getattr(ma, "data", None)

        if (text_delta is not None) or (audio_b64 is not None):
            yield OmniStreamPiece(text_delta=text_delta, audio_b64=audio_b64)
