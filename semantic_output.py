# -*- coding: utf-8 -*-
"""
语义输出生成模块（WP1/WP2/WP3 的最小可用实现）

实现要点（对照 tasks/项目综合文档.md）：
- Top-K 关键物体筛选：Conf × TaskWeight × SceneWeight × UserPref × Proximity × Dynamic
- 结构化中间表示：name / clock_dir / distance_m / relations / avoidance_action / urgency
- 生成自然口语输出：动态场景简洁，稳定场景更完整
- JSON Stream Optimizer：同类/重叠目标去冗余，输出节流与去重复播报

说明：
- 这是“可跑通/可迭代”的工程骨架；权重与阈值可通过 context/weights 与环境变量调参。
"""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


def _repo_root() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def _load_txt_weights(path: str) -> Dict[str, float]:
    weights: Dict[str, float] = {}
    if not path or not os.path.exists(path):
        return weights
    try:
        with open(path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                # 支持 "name weight" / "name=weight"
                if "=" in line:
                    k, v = line.split("=", 1)
                else:
                    parts = line.split()
                    if len(parts) < 2:
                        continue
                    k, v = parts[0], parts[1]
                k = k.strip().lower()
                try:
                    weights[k] = float(v)
                except Exception:
                    continue
    except Exception:
        return weights
    return weights


def _load_user_prefs(path: str) -> Dict[str, float]:
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
        prefs = data.get("weights") if isinstance(data, dict) else None
        if not isinstance(prefs, dict):
            return {}
        out = {}
        for k, v in prefs.items():
            try:
                out[str(k).strip().lower()] = float(v)
            except Exception:
                continue
        return out
    except Exception:
        return {}


def _iou(a: List[float], b: List[float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)
    iw = max(0.0, inter_x2 - inter_x1)
    ih = max(0.0, inter_y2 - inter_y1)
    inter = iw * ih
    if inter <= 0.0:
        return 0.0
    area_a = max(0.0, (ax2 - ax1)) * max(0.0, (ay2 - ay1))
    area_b = max(0.0, (bx2 - bx1)) * max(0.0, (by2 - by1))
    denom = area_a + area_b - inter
    return inter / denom if denom > 0 else 0.0


def _clock_dir(cx: float, cy: float, w: int, h: int) -> int:
    # 12 点方向为图像上方，顺时针
    dx = cx - (w / 2.0)
    dy = cy - (h / 2.0)
    ang = math.atan2(dx, -dy)  # 以“向上”为 0，顺时针为正
    hour = int(round((ang / (2 * math.pi)) * 12)) % 12
    return 12 if hour == 0 else hour


def _dir_zh(hour: int) -> str:
    # 更口语的方向提示（辅助信息，主信息仍保留钟点）
    if hour in (11, 12, 1):
        return "正前方"
    if hour in (2, 3, 4):
        return "右前方"
    if hour in (8, 9, 10):
        return "左前方"
    if hour in (5, 6, 7):
        return "前方偏下"
    return "前方"


def _estimate_distance_m(area_ratio: float) -> float:
    # 仅用于科研原型：面积越大越近
    ar = max(1e-6, float(area_ratio))
    d = 1.2 / math.sqrt(ar)
    return float(max(0.6, min(8.0, d)))


NAME_ZH = {
    "person": "人",
    "bicycle": "自行车",
    "car": "汽车",
    "motorcycle": "摩托车",
    "bus": "公交车",
    "truck": "卡车",
    "scooter": "电瓶车",
    "stroller": "婴儿车",
    "dog": "狗",
    "animal": "动物",
    "pole": "杆子",
    "post": "柱子",
    "column": "柱子",
    "pillar": "柱子",
    "bollard": "路桩",
    "bench": "长椅",
    "chair": "椅子",
    "potted plant": "盆栽",
    "hydrant": "消防栓",
    "cone": "锥桶",
    "stone": "石头",
    "box": "箱子",
    "signpost": "指示牌",
    "utility pole": "电线杆",
    "light pole": "路灯杆",
    "telegraph pole": "电线杆",
    "street pole": "路灯杆",
    "support post": "支撑杆",
    "vertical post": "立柱",
}


def _zh_name(name: str) -> str:
    k = (name or "").strip().lower()
    return NAME_ZH.get(k, name or "物体")


DYNAMIC_CLASSES = {
    "person",
    "bicycle",
    "car",
    "motorcycle",
    "bus",
    "truck",
    "scooter",
}


@dataclass
class SemanticObject:
    name: str
    score: float
    conf: float
    bbox: Optional[List[float]]
    center_x: float
    center_y: float
    area_ratio: float
    clock: int
    clock_zh: str
    distance_m: float
    urgency: str
    avoidance_action: str
    relations: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "score": self.score,
            "conf": self.conf,
            "bbox": self.bbox,
            "center": [self.center_x, self.center_y],
            "area_ratio": self.area_ratio,
            "clock_dir": self.clock,
            "clock_dir_zh": self.clock_zh,
            "distance_m": self.distance_m,
            "urgency": self.urgency,
            "avoidance_action": self.avoidance_action,
            "relations": self.relations,
        }


class TextDeduper:
    def __init__(self, min_interval_sec: float = 3.0):
        self.min_interval_sec = float(min_interval_sec)
        self.last_sig: Optional[str] = None
        self.last_ts: float = 0.0

    def allow(self, sig: str) -> bool:
        now = time.time()
        if sig == self.last_sig and (now - self.last_ts) < self.min_interval_sec:
            return False
        self.last_sig = sig
        self.last_ts = now
        return True


class SemanticOutputEngine:
    def __init__(self, weights_dir: Optional[str] = None, user_prefs_path: Optional[str] = None):
        self.weights_dir = weights_dir or os.getenv(
            "AIGLASS_WEIGHTS_DIR", os.path.join(_repo_root(), "context", "weights")
        )
        self.user_prefs_path = user_prefs_path or os.getenv(
            "AIGLASS_USER_PREFS", os.path.join(_repo_root(), "context", "user_prefs.json")
        )

        self.task_weights = _load_txt_weights(os.path.join(self.weights_dir, "task_navigation.txt"))
        self.scene_weights = {
            "street": _load_txt_weights(os.path.join(self.weights_dir, "scene_street.txt")),
            "indoor": _load_txt_weights(os.path.join(self.weights_dir, "scene_indoor.txt")),
        }
        self.user_prefs = _load_user_prefs(self.user_prefs_path)

        self.iou_dedup_thr = float(os.getenv("AIGLASS_SEM_IOU_DEDUP", "0.6"))
        self.deduper = TextDeduper(min_interval_sec=float(os.getenv("AIGLASS_SEM_MIN_INTERVAL", "3.0")))
        self.turn_rate_thr_dps = float(os.getenv("AIGLASS_SEM_TURN_DPS", "25.0"))

        # 稳定性指标（WP4 会进一步结合 IMU）
        self.prev_signature: Optional[str] = None
        self.jump_count: int = 0

    def reload_weights(self):
        self.task_weights = _load_txt_weights(os.path.join(self.weights_dir, "task_navigation.txt"))
        self.scene_weights["street"] = _load_txt_weights(os.path.join(self.weights_dir, "scene_street.txt"))
        self.scene_weights["indoor"] = _load_txt_weights(os.path.join(self.weights_dir, "scene_indoor.txt"))
        self.user_prefs = _load_user_prefs(self.user_prefs_path)

    def infer_scene(self, names: List[str], mean_luma: Optional[float] = None) -> str:
        nset = {str(n).strip().lower() for n in (names or [])}
        if nset & {"car", "bus", "truck", "traffic light", "crosswalk"}:
            return "street"
        if nset & {"chair", "table", "sofa", "bed", "tv", "monitor"}:
            return "indoor"
        if mean_luma is not None and mean_luma < 70 and nset & {"chair", "bench", "potted plant"}:
            return "indoor"
        return "unknown"

    def _dedup_objects(self, objs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # 仅对同名且 bbox 重叠较大的做去重
        out: List[Dict[str, Any]] = []
        for o in sorted(objs, key=lambda x: float(x.get("score", 0.0)), reverse=True):
            bbox = o.get("bbox")
            name = str(o.get("name", "")).strip().lower()
            if not bbox or len(bbox) != 4:
                out.append(o)
                continue
            keep = True
            for kept in out:
                if str(kept.get("name", "")).strip().lower() != name:
                    continue
                kb = kept.get("bbox")
                if kb and len(kb) == 4 and _iou([float(x) for x in bbox], [float(x) for x in kb]) >= self.iou_dedup_thr:
                    keep = False
                    break
            if keep:
                out.append(o)
        return out

    def _compute_score(self, name: str, conf: float, area_ratio: float, scene: str) -> float:
        k = (name or "").strip().lower()
        base = max(0.05, min(1.0, float(conf)))
        tw = float(self.task_weights.get(k, 1.0))
        sw = float((self.scene_weights.get(scene) or {}).get(k, 1.0))
        up = float(self.user_prefs.get(k, 1.0))
        prox = 1.0 + min(2.0, float(area_ratio) * 8.0)
        dyn = 1.5 if k in DYNAMIC_CLASSES else 1.0
        return base * tw * sw * up * prox * dyn

    def _avoidance(self, name: str, cx: float, w: int, distance_m: float) -> Tuple[str, str]:
        k = (name or "").strip().lower()
        x_ratio = cx / max(1.0, float(w))
        side = "center"
        if x_ratio < 0.4:
            side = "left"
        elif x_ratio > 0.6:
            side = "right"

        urgent = "LOW"
        if k in DYNAMIC_CLASSES and distance_m <= 2.5:
            urgent = "HIGH"
        elif distance_m <= 1.5:
            urgent = "MEDIUM"

        if urgent == "HIGH":
            return "先停一下，注意避让。", urgent
        if side == "left":
            return "从右侧绕开。", urgent
        if side == "right":
            return "从左侧绕开。", urgent
        return "稍微向右侧避让。", urgent

    def _relations(self, objs: List[SemanticObject], w: int) -> List[SemanticObject]:
        if len(objs) < 2:
            return objs
        # 只给 Top1 附加与 Top2 的关系，避免啰嗦
        a = objs[0]
        b = objs[1]
        dx = a.center_x - b.center_x
        if abs(dx) > 0.18 * w:
            rel = f"{_zh_name(a.name)}在{_zh_name(b.name)}的{'左侧' if dx < 0 else '右侧'}"
            a.relations = [rel]
        return objs

    def build_semantic_objects(
        self,
        raw_objects: List[Dict[str, Any]],
        frame_w: int,
        frame_h: int,
        mean_luma: Optional[float] = None,
        imu_yaw_rate_dps: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        输入 raw_objects（推荐来自 obstacle_detector_client.detect）：
        {'name','conf','bbox','area_ratio','center_x','center_y',...}
        """
        names = [str(o.get("name", "")).strip().lower() for o in (raw_objects or [])]
        scene = self.infer_scene(names, mean_luma=mean_luma)

        scored = []
        for o in raw_objects or []:
            name = str(o.get("name", "")).strip()
            if not name:
                continue
            conf = o.get("conf")
            try:
                conf_f = float(conf) if conf is not None else 0.5
            except Exception:
                conf_f = 0.5
            ar = float(o.get("area_ratio", 0.0) or 0.0)
            score = self._compute_score(name, conf_f, ar, scene)
            scored.append({**o, "score": score})

        scored = self._dedup_objects(scored)
        scored.sort(key=lambda x: float(x.get("score", 0.0)), reverse=True)

        sem_objs: List[SemanticObject] = []
        for o in scored[:10]:
            name = str(o.get("name", "")).strip()
            cx = float(o.get("center_x", frame_w / 2.0))
            cy = float(o.get("center_y", frame_h / 2.0))
            ar = float(o.get("area_ratio", 0.0) or 0.0)
            conf_f = float(o.get("conf", 0.5) or 0.5)
            clock = _clock_dir(cx, cy, frame_w, frame_h)
            dist_m = _estimate_distance_m(ar)
            avoidance, urgency = self._avoidance(name, cx, frame_w, dist_m)
            sem_objs.append(
                SemanticObject(
                    name=name,
                    score=float(o.get("score", 0.0) or 0.0),
                    conf=conf_f,
                    bbox=(list(o.get("bbox")) if isinstance(o.get("bbox"), (list, tuple)) else None),
                    center_x=cx,
                    center_y=cy,
                    area_ratio=ar,
                    clock=clock,
                    clock_zh=_dir_zh(clock),
                    distance_m=dist_m,
                    urgency=urgency,
                    avoidance_action=avoidance,
                    relations=[],
                )
            )

        sem_objs = self._relations(sem_objs, frame_w)

        topk = sem_objs[:3]
        is_dynamic = any((o.name or "").strip().lower() in DYNAMIC_CLASSES and o.distance_m <= 3.0 for o in topk)
        if imu_yaw_rate_dps is not None and abs(float(imu_yaw_rate_dps)) >= self.turn_rate_thr_dps:
            is_dynamic = True

        return {
            "scene": scene,
            "is_dynamic": is_dynamic,
            "objects": topk,
        }

    def render_text(self, sem: Dict[str, Any]) -> str:
        objs: List[SemanticObject] = list(sem.get("objects") or [])
        if not objs:
            return "我没看到明显的关键障碍，前方看起来比较空。"

        dynamic = bool(sem.get("is_dynamic", False))
        scene = str(sem.get("scene") or "unknown")

        # 动态环境：先避险、后补充
        if dynamic:
            o = objs[0]
            d = o.distance_m
            dist_txt = f"{d:.0f}米" if d >= 1.0 else f"{d:.1f}米"
            return f"注意，{o.clock}点方向大概{dist_txt}有{_zh_name(o.name)}，{o.avoidance_action}"

        # 稳定环境：先整体、再关键点
        prefix = "前方环境还算稳定。"
        if scene == "indoor":
            prefix = "看起来像室内环境。"
        elif scene == "street":
            prefix = "看起来像户外道路环境。"

        parts = []
        for o in objs[:3]:
            d = o.distance_m
            dist_txt = f"{d:.0f}米" if d >= 1.0 else f"{d:.1f}米"
            parts.append(f"{o.clock}点方向约{dist_txt}有{_zh_name(o.name)}，{o.avoidance_action}")

        rel = ""
        if objs and objs[0].relations:
            rel = f"另外，{objs[0].relations[0]}。"
        return prefix + " " + "；".join(parts) + "。" + rel

    def describe(
        self,
        raw_objects: List[Dict[str, Any]],
        frame_w: int,
        frame_h: int,
        mean_luma: Optional[float] = None,
        imu_yaw_deg: Optional[float] = None,
        imu_yaw_rate_dps: Optional[float] = None,
    ) -> Dict[str, Any]:
        sem = self.build_semantic_objects(
            raw_objects, frame_w, frame_h, mean_luma=mean_luma, imu_yaw_rate_dps=imu_yaw_rate_dps
        )
        text = self.render_text(sem)

        sig = "|".join([f"{o.name}:{o.clock}:{int(o.distance_m*10)}" for o in (sem.get("objects") or [])]) or "empty"
        if self.prev_signature is not None and sig != self.prev_signature:
            self.jump_count += 1
        self.prev_signature = sig

        should_speak = self.deduper.allow(sig)

        # IMU 闭环：转头/转身时减少冗余播报（除非有 HIGH 紧急项）
        turning = False
        if imu_yaw_rate_dps is not None and abs(float(imu_yaw_rate_dps)) >= self.turn_rate_thr_dps:
            turning = True
            has_high = any((o.get("urgency") == "HIGH") for o in (sem.get("objects") or []))
            if not has_high:
                should_speak = False

        return {
            "schema_version": 1,
            "ts": time.time(),
            "scene": sem.get("scene"),
            "is_dynamic": bool(sem.get("is_dynamic", False)),
            "jump_count": self.jump_count,
            "imu": {
                "yaw_deg": imu_yaw_deg,
                "yaw_rate_dps": imu_yaw_rate_dps,
                "is_turning": turning,
            },
            "objects": [o.to_dict() for o in (sem.get("objects") or [])],
            "text": text,
            "should_speak": should_speak,
        }


_engine: Optional[SemanticOutputEngine] = None


def get_semantic_engine() -> SemanticOutputEngine:
    global _engine
    if _engine is None:
        _engine = SemanticOutputEngine()
    return _engine
