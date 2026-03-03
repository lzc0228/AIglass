# qwen_extractor.py
# -*- coding: utf-8 -*-
"""
中文物品名称 -> 英文检测类名提取器

当前版本：仅使用本地映射，不调用大模型 API
如需使用大模型，请取消注释相关代码
"""
from typing import List, Tuple

# —— 本地优先映射（可随时扩充/改名）——
LOCAL_CN2EN = {
    "红牛": "Red_Bull",
    "ad钙奶": "AD_milk",
    "ad 钙奶": "AD_milk",
    "ad": "AD_milk",
    "钙奶": "AD_milk",
    "矿泉水": "bottle",
    "水瓶": "bottle",
    "可乐": "coke",
    "雪碧": "sprite",
    "水杯": "cup",
    "杯子": "cup",
    "手机": "cell phone",
    "钥匙": "key",
    "眼镜": "sunglasses",
    "书包": "backpack",
    "包": "handbag",
    "钱包": "wallet",
    "遥控器": "remote",
    "鼠标": "mouse",
    "键盘": "keyboard",
    "笔": "pen",
    "笔记本": "book",
    "书": "book",
    "桌子": "table",
    "椅子": "chair",
    "门": "door",
    "窗户": "window",
    "电视": "tv",
    "电脑": "laptop",
    "平板": "ipad",
}

# ========== 大模型相关代码（已禁用）==========
# 以下代码已注释，当前版本不使用大模型
# 取消注释需要同时安装 openai 包并设置 DASHSCOPE_API_KEY
#
# import os
# from openai import OpenAI
#
# def _make_client() -> OpenAI:
#     base_url = os.getenv("DASHSCOPE_COMPAT_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1")
#     api_key = os.getenv("DASHSCOPE_API_KEY")
#     if not api_key:
#         raise RuntimeError("未设置 DASHSCOPE_API_KEY（请在环境变量或 .env 中配置）")
#     return OpenAI(api_key=api_key, base_url=base_url)
#
# PROMPT_SYS = (
#     "You are a label normalizer. Convert the given Chinese object "
#     "description into a short, lowercase English YOLO/vision class name "
#     "(1~3 words). If multiple are given, return the single most likely one. "
#     "Output ONLY the label, no punctuation."
# )
# ================================================

def extract_english_label(query_cn: str) -> Tuple[str, str]:
    """
    返回 (label_en, source)；source ∈ {'local', 'fallback'}

    当前版本：仅使用本地映射，不调用大模型
    """
    q = (query_cn or "").strip().lower()

    # 精确匹配
    if q in LOCAL_CN2EN:
        return LOCAL_CN2EN[q], "local"

    # 简单规则：包含匹配
    for k, v in LOCAL_CN2EN.items():
        if k in q:
            return v, "local"

    # 兜底：返回通用类别
    return "object", "fallback"
