#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate offline Chinese voice WAV files using Piper and update voice/map.zh-CN.json.

Default behavior:
- Collect a curated phrase list (including common navigation prompts)
- Optionally auto-extract more phrases from repo Python files (heuristic filter)
- Synthesize each phrase into voice/<phrase>.wav (sanitized filename if needed)
- Add/update mappings in voice/map.zh-CN.json
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Iterable, Set


CH_RE = re.compile(r"[\u4e00-\u9fff]")

# Heuristic keywords for "likely spoken" phrases
KEYWORDS = [
    "系统", "启动", "模式", "导航", "停止", "取消",
    "盲道", "斑马线", "过马路", "红灯", "绿灯", "黄灯", "红绿灯",
    "左", "右", "向左", "向右", "左转", "右转", "左移", "右移", "平移", "微调",
    "对准", "校准", "保持直行", "直行", "继续", "开始", "结束", "等待",
    "障碍物", "避让", "注意", "安全",
    "丢失", "搜索", "靠近",
    "颜色", "文字", "公交", "朋友", "人脸", "灯", "夜间", "盲人",
    "音乐", "点歌", "播放", "暂停", "继续播放",
    "识别", "汉字", "路线", "路",
    "物品", "寻找", "找",
]

# Short UI-only keys that shouldn't be synthesized
STOPWORDS = {
    "状态", "角度", "偏移", "检测", "提示", "方位", "面积",
    "对准斑马线", "寻找斑马线", "等待绿灯...", "等待绿灯…", "过马路中...",
}


def _looks_like_spoken(s: str) -> bool:
    if not s:
        return False
    s0 = s.strip()
    # Filter out typical log prefixes / debug strings
    if s0.startswith("["):
        return False
    if "====" in s0 or "=" in s0:
        return False
    if any(x in s0 for x in ("YOLO", "Frame", "logger", "DEBUG", "ERROR", "WARNING")):
        return False
    if not CH_RE.search(s):
        return False
    if len(s) <= 1:
        return False
    if s in STOPWORDS:
        return False
    if len(s) > 100:
        return False
    return any(k in s for k in KEYWORDS)


def _safe_filename(phrase: str) -> str:
    t = phrase.strip()
    t = re.sub(r"\s+", " ", t)
    # avoid path separators
    t = t.replace("/", "_").replace("\\", "_")
    # keep Windows-unfriendly characters out (even if target is Linux)
    t = t.replace(":", "：").replace("*", "").replace("?", "？").replace("\"", "＂")
    t = t.replace("<", "＜").replace(">", "＞").replace("|", "｜")
    t = t.replace("\n", " ").replace("\r", " ").strip()
    if len(t) > 80:
        h = hashlib.sha1(t.encode("utf-8")).hexdigest()[:10]
        t = t[:40] + "_" + h
    return f"{t}.wav"


def _piper_speak(piper_bin: str, model_path: Path, text: str, out_wav: Path, timeout_sec: int = 60) -> None:
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(text)
        in_txt = f.name
    try:
        r = subprocess.run(
            [piper_bin, "--model", str(model_path), "--input_file", in_txt, "--output_file", str(out_wav)],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
        if r.returncode != 0:
            raise RuntimeError(f"piper failed (rc={r.returncode}): {r.stderr.strip() or r.stdout.strip()}")
        if not out_wav.exists() or out_wav.stat().st_size <= 44:
            raise RuntimeError("piper produced empty wav")
    finally:
        try:
            os.unlink(in_txt)
        except Exception:
            pass


def _collect_strings_from_py(path: Path) -> Set[str]:
    try:
        src = path.read_text(encoding="utf-8")
    except Exception:
        return set()
    try:
        tree = ast.parse(src, filename=str(path))
    except Exception:
        return set()
    out: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            s = node.value.strip()
            if _looks_like_spoken(s):
                out.add(s)
    return out


def _load_literal_dict(path: Path, var_name: str) -> dict:
    try:
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(path))
    except Exception:
        return {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        for t in targets:
            if isinstance(t, ast.Name) and t.id == var_name:
                try:
                    return ast.literal_eval(node.value)
                except Exception:
                    return {}
    return {}


def _load_local_items(repo_root: Path) -> Set[str]:
    data = _load_literal_dict(repo_root / "qwen_extractor.py", "LOCAL_CN2EN")
    if isinstance(data, dict):
        return set(data.keys())
    return set()


def _load_color_names(repo_root: Path) -> Set[str]:
    data = _load_literal_dict(repo_root / "color_recognition.py", "COLOR_NAMES_ZH")
    names = set()
    if isinstance(data, dict):
        names |= set(data.values())
    # 合并/特殊色名
    names |= {"蓝绿色", "紫红色", "未知"}
    return names


def _default_seed_phrases(repo_root: Path) -> Set[str]:
    # User-requested + common system prompts
    phrases = {
        "系统已启动",
        "天色已晚，建议打开指示灯，让别人注意到您。",
        "前方检测到盲道",
        "发现斑马线",
        "前方是红灯",
        "前方是绿灯",
        "前方是黄灯",
        "前方有障碍物，注意安全",
        "过马路模式已启动。",
        "启动过马路模式失败，请稍后重试。",
        "已停止导航。",
        "环境复杂，进入恢复模式。",
        "已到盲道跟前，切换到盲道导航。",
        "正在接近斑马线，为您对准方向。",
        "已到达斑马线，请等待红绿灯。",
        "斑马线已在跟前，进入红绿灯判定模式",
        "绿灯稳定，开始通行。",
        "绿灯稳定，开始通行。",
        "正在等待绿灯…",
        "开始通行",
        "过马路结束，准备上人行道。",
        "远处有盲道，继续前行。",
        "斑马线到了可以过马路",
        # Direction staples
        "左转一点",
        "右转一点",
        "向左平移",
        "向右平移",
        "保持直行",
        "丢失路径，重新搜索。",
        "检测到已移动，开始对准新方向。",
        "避让完成，已回到盲道。",
        "好的，请停下侧移。",
        "路径被挡住，请向右侧平移。",
        "路径被挡住，请向左侧平移。",
        "没看到盲道，请向右侧小幅移动。",
        "没看到盲道，请向左侧小幅移动。",
        "已回到盲道。",
        "已对准新路径，请向前直行。",
        "请向左转动。",
        "请向右转动。",
        "方向已对正！现在校准位置。",
        "方向已对正!现在校准位置。",
        "方向正确，请继续前进。",
        "方向正确，请直行。",
        "校准完成！您已在盲道上，开始前行。",
        "请向右平移。",
        "请向左平移。",
        "请向右微调，对准盲道。",
        "请向左微调，对准盲道。",
        "向前直行几步越过障碍物。然后说‘好了’。",
        "路径太远，请继续靠近。",
        "绿灯快没了",
        # Traffic light short prompts (legacy)
        "红灯",
        "绿灯",
        "黄灯",
        "红灯_原始",
        "绿灯_原始",
        "黄灯_原始",
        # Optional: user-specified “target” phrases
        "导航已被取消。",
        "目标就在前方，请慢慢靠近。",
        "目标消失，请原地等待。",
        "斑马线已对准，继续前行。",
        "保持直行，靠近盲道。",
        "盲道已接近，开始对准盲道。",
        "到达转弯处，向右平移。",
        "到达转弯处，向左平移。",
        "发现斑马线，对准方向。",
    }

    # Crosswalk awareness position variants (only 3*3 = 9)
    positions = ["在画面左侧", "在画面中间", "在画面右侧"]
    for pos in positions:
        phrases.add(f"远处发现斑马线,{pos}")
        phrases.add(f"正在靠近斑马线,{pos}")
        phrases.add(f"接近斑马线,{pos}")

    # ===== 任务覆盖：方向/引导/物品搜索 =====
    phrases |= {
        "向左", "向右", "向上", "向下", "向前", "向后", "向中",
        "向前靠近", "向后一点", "保持这个距离", "很好，保持", "再调整一下",
        "请向左移动一下镜头", "请向右移动一下镜头", "请向中移动一下镜头",
        "请缓慢靠近", "保持", "已居中", "OK", "检测到物体",
    }

    # ===== 任务覆盖：颜色识别 =====
    for cname in sorted(_load_color_names(repo_root)):
        phrases.add(f"我看到主要是：{cname}。")
        phrases.add(f"可能是：{cname}。你可以把镜头再对准一点。")
        phrases.add(f"颜色不太确定，可能是：{cname}。")
    phrases.add("无法识别颜色，请确保画面有足够光线。")

    # ===== 任务覆盖：OCR/汉字识别 =====
    phrases.add("我读到：")
    phrases.add("没有识别到清晰的文字。")

    # ===== 任务覆盖：公交线路识别 =====
    phrases.add("没有识别到清晰的路线号。请确保画面包含公交车头或路线牌。")
    bus_max = int(os.getenv("AIGLASS_BUS_ROUTE_MAX", "120"))
    for n in range(1, bus_max + 1):
        phrases.add(f"这辆车可能是：{n}路。")
        phrases.add(f"可能是：{n}路。你可以把镜头对准路线牌。")

    # ===== 任务覆盖：朋友/人脸识别 =====
    sample_names = ["张三", "李四", "王五"]
    for name in sample_names:
        phrases.add(f"已记住：{name}。")
        phrases.add(f"已记住：{name}，男，30岁。")
        phrases.add(f"我觉得是 {name}。")
        phrases.add(f"我觉得是 {name}，男，30岁。")
        phrases.add(f"已忘记：{name}。")
        phrases.add(f"我还没记住 {name}。")
    phrases |= {
        "没有画面，无法录入。",
        "没有画面，无法识别。",
        "请告诉我要记住的名字，比如：这是张三。",
        "请告诉我要删除的名字，比如：忘记张三。",
        "没有检测到清晰的人脸，请把人脸对准镜头再试。",
        "录入完成，但训练失败（样本不足或损坏）。",
        "我还没有录入任何朋友。你可以说：这是张三。",
        "我看到有人，但还不认识。你可以说：这是某某。",
        "我可能认识这个人，但档案缺失。你可以重新录入。",
        "我认识：张三。",
    }

    # ===== 任务覆盖：夜间提示/盲人提示 =====
    phrases |= {
        "我是盲人，请注意。",
        "请注意前方盲人。",
        "已进入夜间模式。",
        "已进入日间模式。",
    }

    # ===== 任务覆盖：灯光关闭提醒 =====
    phrases |= {
        "我检测到灯可能还开着，记得关灯。",
        "我感觉灯可能还开着，建议检查并关闭。",
        "环境比较暗，看起来灯应该关了。",
        "看起来灯已经关了。",
        "好的，我会帮你留意灯是否忘关。",
        "好的，已关闭关灯提醒。",
        "没有画面，无法检查灯光。",
    }

    # ===== 任务覆盖：点歌/音乐 =====
    phrases |= {
        "正在搜索音乐，请稍候...",
        "抱歉，没有找到相关歌曲。请换个关键词试试。",
        "请告诉我你想听什么歌，比如：我想听周杰伦的稻香。",
        "已暂停播放",
        "继续播放",
        "播放列表为空，请先搜索歌曲。",
        "正在播放：周杰伦的稻香",
    }

    # ===== 任务覆盖：物品/食物搜索 =====
    items = set(_load_local_items(repo_root))
    items |= {
        "苹果", "香蕉", "面包", "牛奶", "矿泉水", "水杯",
        "可乐", "雪碧", "红牛", "AD钙奶", "饼干", "巧克力",
        "钥匙", "钱包", "手机", "眼镜", "遥控器",
    }
    for item in sorted(items):
        phrases.add(f"现在开始找：{item}")
        phrases.add(f"我没找到{item}，请把镜头换个角度或走近一点。")
        phrases.add(f"找到{item}了！")

    # ===== 任务覆盖：头部高度障碍 =====
    phrases |= {
        "注意头部高度有障碍。",
        "注意头顶有障碍物。",
        "[导航] 注意头部高度有障碍。",
    }

    # ===== 任务覆盖：及时避障（通用） =====
    phrases |= {
        "前方近距离有障碍物，请停下。",
        "前方有障碍物靠近，请注意。",
        "前方远处有障碍物。",
    }

    return phrases


def _load_map(map_path: Path) -> dict:
    if not map_path.exists():
        return {}
    try:
        return json.loads(map_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_map(map_path: Path, mapping: dict) -> None:
    map_path.parent.mkdir(parents=True, exist_ok=True)
    map_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=os.getenv("AIGLASS_TTS_MODEL", "model/piper/zh_CN-huayan-medium.onnx"))
    ap.add_argument("--piper", default=os.getenv("AIGLASS_PIPER_BIN", "piper"))
    ap.add_argument("--voice-dir", default="voice")
    ap.add_argument("--map", default="voice/map.zh-CN.json")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-auto-extract", action="store_true")
    args = ap.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[1]
    model_path = (repo_root / args.model).resolve() if not Path(args.model).is_absolute() else Path(args.model)
    voice_dir = (repo_root / args.voice_dir).resolve()
    map_path = (repo_root / args.map).resolve()

    phrases: Set[str] = set(_default_seed_phrases(repo_root))

    if not args.no_auto_extract:
        for rel in [
            "app_main.py",
            "navigation_master.py",
            "workflow_blindpath.py",
            "workflow_crossstreet.py",
            "crosswalk_awareness.py",
        ]:
            phrases |= _collect_strings_from_py(repo_root / rel)

    phrases = {p.strip() for p in phrases if p and p.strip()}

    if not model_path.exists():
        raise SystemExit(f"Model not found: {model_path}")

    mapping = _load_map(map_path)

    generated = 0
    skipped = 0
    for phrase in sorted(phrases):
        filename = _safe_filename(phrase)
        out_wav = voice_dir / filename
        if out_wav.exists() and not args.force:
            skipped += 1
        else:
            _piper_speak(args.piper, model_path, phrase, out_wav)
            generated += 1

        # update mapping (relative to map dir)
        mapping[phrase] = {"files": [filename]}

    _write_map(map_path, mapping)
    print(f"[OK] phrases={len(phrases)} generated={generated} skipped={skipped}")
    print(f"[OK] voice_dir={voice_dir}")
    print(f"[OK] map={map_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
