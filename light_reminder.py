# -*- coding: utf-8 -*-
"""
灯光关闭提醒（轻量启发式）

目标：
- 在室内场景下，通过“局部高亮区域 + 整体亮度”判断灯可能是否仍开启
- 支持两种使用方式：
  1) 一次性检查（"灯关了吗/检查灯"）
  2) 常驻提醒（用户先说 "提醒我关灯" 开启；检测到灯一直开着则节流提醒）

注意：这是科研原型的启发式估计，不能保证准确。
"""

from __future__ import annotations

import os
import time
from collections import deque
from typing import Any, Dict, Optional

import cv2
import numpy as np


class LightReminderDetector:
    DEFAULT_CONFIG = {
        "SAMPLE_EVERY_N_FRAMES": 10,
        "BRIGHT_V_THRESH": 235,
        "BRIGHT_AREA_ON": 0.0025,   # 0.25%
        "BRIGHT_AREA_OFF": 0.0015,  # 0.15%（滞回）
        "MEAN_LUMA_MAX_FOR_INDOOR": 175,  # 过亮更可能户外/阳光直射
        "STABLE_FRAMES": 5,
        "REMIND_COOLDOWN_SEC": 60.0,
        "HISTORY_SIZE": 20,
        "DOWNSCALE_MAX": 320,
    }

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = {**self.DEFAULT_CONFIG, **(config or {})}
        self.frame_count = 0
        self.is_light_on = False
        self.stable_count = 0
        self.last_remind_time = 0.0
        self.history = deque(maxlen=int(self.config["HISTORY_SIZE"]))

    def _downscale(self, bgr: np.ndarray) -> np.ndarray:
        h, w = bgr.shape[:2]
        m = int(self.config["DOWNSCALE_MAX"])
        if max(h, w) <= m:
            return bgr
        scale = m / max(h, w)
        return cv2.resize(bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

    @staticmethod
    def _mean_luma(bgr: np.ndarray) -> float:
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        return float(np.mean(gray))

    def _measure(self, bgr: np.ndarray) -> Dict[str, Any]:
        small = self._downscale(bgr)
        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
        v = hsv[:, :, 2]
        bright_thr = int(self.config["BRIGHT_V_THRESH"])
        bright = v >= bright_thr
        bright_area_ratio = float(np.mean(bright)) if bright.size else 0.0
        v_max = float(np.max(v)) if v.size else 0.0

        # 亮点“集中度”：用最大连通域面积近似（可区分均匀高亮 vs 灯泡/灯带）
        blob_ratio = 0.0
        try:
            mask = (bright.astype(np.uint8) * 255)
            num, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
            if num > 1:
                # stats[0] 是背景；其余取最大
                max_area = int(np.max(stats[1:, cv2.CC_STAT_AREA]))
                blob_ratio = max_area / float(mask.size)
        except Exception:
            blob_ratio = 0.0

        mean_luma = self._mean_luma(small)

        return {
            "mean_luma": mean_luma,
            "bright_area_ratio": bright_area_ratio,
            "bright_blob_ratio": blob_ratio,
            "v_max": v_max,
        }

    def _should_be_on(self, m: Dict[str, Any]) -> bool:
        mean_luma = float(m.get("mean_luma", 0.0))
        bright_area = float(m.get("bright_area_ratio", 0.0))
        blob_ratio = float(m.get("bright_blob_ratio", 0.0))
        v_max = float(m.get("v_max", 0.0))

        # 过亮更可能室外/强阳光直射，降低误报
        if mean_luma >= float(self.config["MEAN_LUMA_MAX_FOR_INDOOR"]):
            return False

        # 同时考虑亮区域占比与亮点集中度
        area_on = float(self.config["BRIGHT_AREA_ON"])
        area_off = float(self.config["BRIGHT_AREA_OFF"])

        if self.is_light_on:
            return (bright_area >= area_off) and (v_max >= 240.0) and (blob_ratio >= area_off * 0.5)
        return (bright_area >= area_on) and (v_max >= 245.0) and (blob_ratio >= area_on * 0.5)

    def process_frame(self, bgr: np.ndarray) -> Dict[str, Any]:
        """
        常驻检测：按间隔采样 + 稳定帧数 + 提醒节流
        """
        if bgr is None or bgr.size == 0:
            return {"is_on": self.is_light_on, "changed": False, "should_remind": False}

        self.frame_count += 1
        if self.frame_count % int(self.config["SAMPLE_EVERY_N_FRAMES"]) != 0:
            return {"is_on": self.is_light_on, "changed": False, "should_remind": False}

        meas = self._measure(bgr)
        self.history.append(meas)
        should_on = self._should_be_on(meas)

        if should_on != self.is_light_on:
            self.stable_count += 1
        else:
            self.stable_count = 0

        changed = False
        if self.stable_count >= int(self.config["STABLE_FRAMES"]):
            self.is_light_on = should_on
            self.stable_count = 0
            changed = True

        should_remind = False
        now = time.time()
        if self.is_light_on and (now - self.last_remind_time) >= float(self.config["REMIND_COOLDOWN_SEC"]):
            should_remind = True
            self.last_remind_time = now

        return {
            "is_on": self.is_light_on,
            "changed": changed,
            "should_remind": should_remind,
            **meas,
        }

    def check_once(self, bgr: np.ndarray) -> Dict[str, Any]:
        """一次性检查：不依赖历史/稳定性，直接给出估计结果"""
        if bgr is None or bgr.size == 0:
            return {"ok": False, "message": "没有画面，无法检查灯光。"}

        meas = self._measure(bgr)
        # 临时以当前状态为基准跑一次 should_be_on
        prev = self.is_light_on
        try:
            self.is_light_on = False
            on = self._should_be_on(meas)
        finally:
            self.is_light_on = prev

        mean_luma = float(meas.get("mean_luma", 0.0))
        bright_area = float(meas.get("bright_area_ratio", 0.0))
        blob_ratio = float(meas.get("bright_blob_ratio", 0.0))

        if on:
            msg = "我感觉灯可能还开着，建议检查并关闭。"
        else:
            # 低亮度也可能是关灯/暗环境
            if mean_luma < 50:
                msg = "环境比较暗，看起来灯应该关了。"
            else:
                msg = "看起来灯已经关了。"

        return {
            "ok": True,
            "is_on": on,
            "message": msg,
            "meta": {
                "mean_luma": mean_luma,
                "bright_area_ratio": bright_area,
                "bright_blob_ratio": blob_ratio,
            },
        }


# 全局单例（可选）
_instance: Optional[LightReminderDetector] = None


def get_light_detector() -> LightReminderDetector:
    global _instance
    if _instance is None:
        # 支持通过环境变量覆盖部分阈值
        cfg = {}
        for k in (
            "SAMPLE_EVERY_N_FRAMES",
            "BRIGHT_V_THRESH",
            "BRIGHT_AREA_ON",
            "BRIGHT_AREA_OFF",
            "MEAN_LUMA_MAX_FOR_INDOOR",
            "STABLE_FRAMES",
            "REMIND_COOLDOWN_SEC",
        ):
            env_key = f"AIGLASS_LIGHT_{k}"
            if env_key in os.environ:
                v = os.environ.get(env_key)
                try:
                    cfg[k] = float(v) if "." in str(v) else int(v)
                except Exception:
                    pass
        _instance = LightReminderDetector(cfg)
    return _instance

