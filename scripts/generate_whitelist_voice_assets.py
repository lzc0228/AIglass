#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate practical pre-recorded voice assets for all obstacle whitelist classes.

This script focuses on high-value phrases for realtime obstacle announcements,
instead of generating huge combinational corpora.
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
from typing import Dict, Iterable, List, Set


def _load_literal_value(path: Path, var_name: str):
    try:
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(path))
    except Exception:
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        for target in targets:
            if isinstance(target, ast.Name) and target.id == var_name:
                try:
                    return ast.literal_eval(node.value)
                except Exception:
                    return None
    return None


def _safe_filename(phrase: str) -> str:
    text = phrase.strip()
    text = re.sub(r"\s+", " ", text)
    text = text.replace("/", "_").replace("\\", "_")
    text = text.replace(":", "：").replace("*", "").replace("?", "？")
    text = text.replace('"', "＂").replace("<", "＜").replace(">", "＞").replace("|", "｜")
    text = text.replace("\n", " ").replace("\r", " ").strip()
    if len(text) > 80:
        digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]
        text = text[:40] + "_" + digest
    return f"{text}.wav"


def _piper_speak(piper_bin: str, model_path: Path, text: str, out_wav: Path, timeout_sec: int = 90) -> None:
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as fh:
        fh.write(text)
        in_txt = fh.name
    try:
        result = subprocess.run(
            [piper_bin, "--model", str(model_path), "--input_file", in_txt, "--output_file", str(out_wav)],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
        if result.returncode != 0:
            raise RuntimeError(f"piper failed rc={result.returncode}: {result.stderr.strip() or result.stdout.strip()}")
        if not out_wav.exists() or out_wav.stat().st_size <= 44:
            raise RuntimeError("piper produced empty wav")
    finally:
        try:
            os.unlink(in_txt)
        except Exception:
            pass


def _load_map(path: Path) -> Dict[str, Dict[str, List[str]]]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_map(path: Path, mapping: Dict[str, Dict[str, List[str]]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _build_phrases(classes: Iterable[str], zh_map: Dict[str, str]) -> List[str]:
    classes_norm = [str(item or "").strip().lower() for item in classes]
    classes_norm = [item for item in classes_norm if item]

    dynamic_set = {
        "person", "bicycle", "car", "motorcycle", "bus", "truck", "scooter",
        "dog", "cat", "animal", "taxi", "train", "police car", "ambulance",
    }
    hazard_set = {
        "crosswalk", "traffic light", "stop sign", "stairs", "stair", "escalator",
        "elevator", "cone", "barrier", "fence", "stone", "box",
    }

    directions = ["前方", "左侧", "右侧", "12点方向", "3点方向", "9点方向"]
    distances = ["约一步", "约两步", "约三步", "1米", "2米"]
    actions = ["保持直行", "请从侧面绕开", "注意避让", "先停一下"]

    phrases: List[str] = [
        "已开启实时物体播报",
        "已关闭实时物体播报",
        "实时物体播报已启动",
        "当前画面未检测到白名单物体",
    ]

    for key in classes_norm:
        name_zh = str(zh_map.get(key, key))
        phrases.extend([
            f"检测到{name_zh}",
            f"前方有{name_zh}",
            f"{name_zh}在附近",
            f"发现{name_zh}，保持直行",
            f"发现{name_zh}，注意避让",
        ])

        for direction in directions:
            phrases.append(f"{direction}有{name_zh}")

        for distance in distances:
            phrases.append(f"前方{distance}有{name_zh}")

        if key in dynamic_set:
            phrases.extend([
                f"注意，{name_zh}正在靠近",
                f"{name_zh}靠近，请注意避让",
                f"{name_zh}在移动，注意安全",
            ])

        if key in hazard_set:
            phrases.extend([
                f"注意{name_zh}，请减速",
                f"{name_zh}在前方，请谨慎通行",
            ])

        for action in actions:
            phrases.append(f"前方有{name_zh}，{action}")

    # 去重且保序
    seen: Set[str] = set()
    uniq: List[str] = []
    for phrase in phrases:
        item = phrase.strip()
        if not item or item in seen:
            continue
        seen.add(item)
        uniq.append(item)
    return uniq


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=os.getenv("AIGLASS_TTS_MODEL", "model/piper/zh_CN-huayan-medium.onnx"))
    parser.add_argument("--piper", default=os.getenv("AIGLASS_PIPER_BIN", "piper"))
    parser.add_argument("--voice-dir", default="voice")
    parser.add_argument("--map", default="voice/map.zh-CN.json")
    parser.add_argument("--max-phrases", type=int, default=2000)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[1]
    model_path = (repo_root / args.model).resolve() if not Path(args.model).is_absolute() else Path(args.model)
    voice_dir = (repo_root / args.voice_dir).resolve()
    map_path = (repo_root / args.map).resolve()

    if not model_path.exists():
        raise SystemExit(f"Model not found: {model_path}")

    classes = _load_literal_value(repo_root / "obstacle_detector_client.py", "DEFAULT_WHITELIST_CLASSES")
    if not isinstance(classes, list):
        raise SystemExit("Cannot load DEFAULT_WHITELIST_CLASSES from obstacle_detector_client.py")

    zh_map = _load_literal_value(repo_root / "structured_voice.py", "NAME_ZH")
    if not isinstance(zh_map, dict):
        zh_map = {}

    phrases = _build_phrases(classes, zh_map)
    if args.max_phrases > 0:
        phrases = phrases[: args.max_phrases]

    mapping = _load_map(map_path)

    generated = 0
    skipped = 0
    for phrase in phrases:
        filename = _safe_filename(phrase)
        out_wav = voice_dir / filename
        if out_wav.exists() and not args.force:
            skipped += 1
        else:
            _piper_speak(args.piper, model_path, phrase, out_wav)
            generated += 1

        mapping[phrase] = {"files": [filename]}

    _write_map(map_path, mapping)
    print(f"[OK] whitelist_phrases={len(phrases)} generated={generated} skipped={skipped}")
    print(f"[OK] voice_dir={voice_dir}")
    print(f"[OK] map={map_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

