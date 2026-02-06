# -*- coding: utf-8 -*-
"""
语义输出生成模块（WP1/WP2/WP3/WP4 的完整实现 + 全场景覆盖）

实现要点：
- 全场景识别（20+场景类型）：交通、建��、室内、自然、特殊场景
- 结构化中间表示：name / clock_dir / distance_m / distance_steps / relations / avoidance_action / urgency
- Top-K 关键物体筛选：Conf × TaskWeight × SceneWeight × UserPref × Proximity × Dynamic
- 生成自然口语输出：动态场景简洁，稳定场景更���整
- JSON Stream Optimizer：同类/重叠目标去冗余，输出节流与去重复播报
- IMU 闭环：转头时抑制冗余播报（除非 HIGH 紧急项）

说明：
- 整合 structured_voice.py 模块实现 schema_version=2 的结构化输出
- 支持步数输出（一步约0.6米）
- 支持左中右方向描述
- 主动播报机制
"""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

# 导入结构化语音模块（schema_version=2）
try:
    from structured_voice import (
        StructuredVoiceOutput,
        SceneType,
        UrgencyLevel,
        ActionType,
        DirectionInfo,
        DistanceInfo,
        StructuredObject,
        VoiceTemplate,
        infer_scene_from_objects,
        NAME_ZH as STRUCTURED_NAME_ZH,
        SCENE_ZH_MAP,
        clock_to_zh,
        calculate_clock_dir,
        calculate_lr_dir,
        lr_to_zh,
        estimate_distance_m as sv_estimate_distance_m,
        distance_to_steps,
    )
    STRUCTURED_VOICE_AVAILABLE = True
except ImportError:
    STRUCTURED_VOICE_AVAILABLE = False
    STRUCTURED_NAME_ZH = {}
    SCENE_ZH_MAP = {}


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
    "wheelchair": "轮椅",
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
    "traffic light": "红绿灯",
    "crosswalk": "斑马线",
    "stairs": "楼梯",
    "stair": "楼梯",
    "handrail": "扶手",
    "elevator": "电梯",
    "escalator": "扶梯",
    "door": "门",
    "window": "窗户",
    "doctor": "医生",
    "nurse": "护士",
    "hospital bed": "病床",
    "shelf": "货架",
    "cart": "购物车",
    "shopping cart": "购物车",
    "checkout": "收银台",
    "counter": "柜台",
    "atm": "取款机",
    "turnstile": "闸机",
    "ticket machine": "售票机",
    "ticket gate": "闸机",
    "fare gate": "闸机",
    "table": "桌子",
    "chair": "椅子",
    # === 新增户外导航类别 ===
    "traffic light": "红绿灯",
    "crosswalk": "斑马线",
    "stop sign": "停止标志",
    "parking meter": "停车计时器",
    # === 交通工具扩展 ===
    "taxi": "出租车",
    "train": "列车",
    "police car": "警车",
    "ambulance": "救护车",
    # === 动物扩展 ===
    "cat": "猫",
    # === 室内场景 ===
    "door": "门",
    "stairs": "楼梯",
    "stair": "楼梯",
    "escalator": "扶梯",
    "elevator": "电梯",
    "handrail": "扶手",
    "railing": "栏杆",
    # === 家居物品 ===
    "sofa": "沙发",
    "couch": "长沙发",
    "bed": "床",
    "desk": "书桌",
    "tv": "电视",
    "monitor": "显示器",
    "laptop": "笔记本电脑",
    "computer": "电脑",
    # === 个人物品 ===
    "backpack": "背包",
    "handbag": "手提包",
    "suitcase": "行李箱",
    "umbrella": "雨伞",
    "cell phone": "手机",
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
    lr: str
    lr_zh: str
    distance_m: float
    urgency: str
    avoidance_action: str
    relations: List[str]
    frame_w: Optional[int] = None
    frame_h: Optional[int] = None

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
            "lr": self.lr,
            "lr_zh": self.lr_zh,
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

        self.task_weights: Dict[str, float] = {}
        self.scene_weights: Dict[str, Dict[str, float]] = {}
        self.user_prefs: Dict[str, float] = {}
        self.reload_weights()

        self.iou_dedup_thr = float(os.getenv("AIGLASS_SEM_IOU_DEDUP", "0.6"))
        self.deduper = TextDeduper(min_interval_sec=float(os.getenv("AIGLASS_SEM_MIN_INTERVAL", "3.0")))
        self.turn_rate_thr_dps = float(os.getenv("AIGLASS_SEM_TURN_DPS", "25.0"))

        # 稳定性指标（WP4 会进一步结合 IMU）
        self.prev_signature: Optional[str] = None
        self.jump_count: int = 0

    def reload_weights(self):
        """加载所有权重文件（包括新增的场景权重文件）"""
        self.task_weights = _load_txt_weights(os.path.join(self.weights_dir, "task_navigation.txt"))
        self.scene_weights = {}
        if os.path.isdir(self.weights_dir):
            for fname in os.listdir(self.weights_dir):
                if not (fname.startswith("scene_") and fname.endswith(".txt")):
                    continue
                scene = fname[len("scene_"):-4]
                path = os.path.join(self.weights_dir, fname)
                self.scene_weights[scene] = _load_txt_weights(path)
        if not self.scene_weights:
            # 回退到最小集合
            self.scene_weights["street"] = _load_txt_weights(os.path.join(self.weights_dir, "scene_street.txt"))
            self.scene_weights["indoor"] = _load_txt_weights(os.path.join(self.weights_dir, "scene_indoor.txt"))

        self.user_prefs = _load_user_prefs(self.user_prefs_path)

        print(f"[SEMANTIC] 已加载场景权重: {list(self.scene_weights.keys())}")

    def infer_scene_with_confidence(self, names: List[str], mean_luma: Optional[float] = None) -> Tuple[str, float]:
        """扩展的场景识别（支持20+场景类型）"""
        nset = {str(n).strip().lower() for n in (names or [])}
        joined = " ".join(nset)

        if STRUCTURED_VOICE_AVAILABLE:
            try:
                scene_enum, conf = infer_scene_from_objects(
                    [{"name": n} for n in nset], mean_luma=mean_luma
                )
                if scene_enum and getattr(scene_enum, "value", "unknown") != "unknown":
                    return scene_enum.value, float(conf)
            except Exception:
                pass

        # 交通细分场景
        if any(kw in joined for kw in {"traffic light", "signal"}):
            return "traffic_light", 0.9
        if any(kw in joined for kw in {"crosswalk", "zebra crossing", "zebra"}):
            return "crosswalk", 0.8
        if any(kw in joined for kw in {"sidewalk", "pedestrian"}):
            return "sidewalk", 0.7
        if any(kw in joined for kw in {"crossroad", "intersection"}):
            return "crossroad", 0.7

        # 医院场景特征
        hospital_keywords = {"hospital", "clinic", "doctor", "nurse", "wheelchair",
                             "stretcher", "gurney", "medical", "iv drip", "hospital bed"}
        if any(kw in joined for kw in hospital_keywords):
            return "hospital", 0.8

        # 超市场景特征
        supermarket_keywords = {"supermarket", "shelf", "shopping cart", "aisle",
                                "checkout", "grocery", "price tag", "cart"}
        if any(kw in joined for kw in supermarket_keywords):
            return "supermarket", 0.8

        # 商场场景特征
        mall_keywords = {"mall", "escalator", "mannequin", "storefront", "display", "brand"}
        if any(kw in joined for kw in mall_keywords):
            return "mall", 0.8

        # 施工区域特征
        construction_keywords = {"cone", "barrier", "fence", "construction",
                                 "warning sign", "safety vest", "excavator", "crane"}
        if any(kw in joined for kw in construction_keywords):
            return "construction", 0.9

        # 电梯/楼梯/走廊
        if any(kw in joined for kw in {"elevator", "lift", "floor button"}):
            return "elevator", 0.8
        if any(kw in joined for kw in {"stairs", "stair", "staircase", "handrail", "step"}):
            return "stairs", 0.8
        if any(kw in joined for kw in {"corridor", "hallway", "room number", "exit sign"}):
            return "corridor", 0.7
        if any(kw in joined for kw in {"restroom", "toilet", "sink", "mirror"}):
            return "restroom", 0.7

        # 地铁/公交站
        if any(kw in joined for kw in {"subway", "metro", "turnstile", "ticket machine",
                                       "fare gate", "platform", "metro train"}):
            return "subway", 0.8
        if any(kw in joined for kw in {"bus stop", "bus stop sign", "transit shelter"}):
            return "bus_stop", 0.8

        # 公园/广场
        if any(kw in joined for kw in {"park", "garden", "tree", "bench", "lawn", "grass",
                                       "flower bed", "fountain", "pond"}):
            return "park", 0.7
        if any(kw in joined for kw in {"square", "plaza", "statue", "open area"}):
            return "square", 0.7

        # 餐厅/银行/办公室/学校
        if any(kw in joined for kw in {"restaurant", "table", "chair", "dining", "menu", "waiter", "counter"}):
            return "restaurant", 0.7
        if any(kw in joined for kw in {"bank", "atm", "teller", "vault", "queue"}):
            return "bank", 0.7
        if any(kw in joined for kw in {"office", "desk", "computer", "printer", "cubicle"}):
            return "office", 0.7
        if any(kw in joined for kw in {"school", "classroom", "student", "blackboard", "campus"}):
            return "school", 0.7

        # 原有逻辑（保持兼容）
        if nset & {"car", "bus", "truck", "traffic light", "crosswalk"}:
            return "street", 0.6
        if nset & {"chair", "table", "sofa", "bed", "tv", "monitor"}:
            return "indoor", 0.6
        if mean_luma is not None and mean_luma < 70 and nset & {"chair", "bench", "potted plant"}:
            return "indoor", 0.5

        return "unknown", 0.3

    def infer_scene(self, names: List[str], mean_luma: Optional[float] = None) -> str:
        scene, _conf = self.infer_scene_with_confidence(names, mean_luma=mean_luma)
        return scene

    def get_scene_zh(self, scene: str) -> str:
        """获取场景中文名称"""
        if STRUCTURED_VOICE_AVAILABLE:
            if isinstance(scene, SceneType):
                return SCENE_ZH_MAP.get(scene, "")
            try:
                return SCENE_ZH_MAP.get(SceneType(scene), "")
            except Exception:
                return ""
        # 兼容回退
        scene_zh_map = {
            "street": "街道环境",
            "sidewalk": "人行道上",
            "crossroad": "十字路口",
            "crosswalk": "斑马线",
            "traffic_light": "红绿灯前",
            "bus_stop": "公交车站",
            "hospital": "医院环境",
            "supermarket": "超市通道",
            "mall": "商场内",
            "elevator": "电梯里",
            "stairs": "楼梯上",
            "corridor": "走廊",
            "restroom": "卫生间",
            "park": "公园里",
            "construction": "施工区域",
            "subway": "地铁站",
            "restaurant": "餐厅",
            "bank": "银行",
            "office": "办公楼",
            "school": "学校",
            "square": "广场上",
            "parking": "停车场",
            "underpass": "地下通道",
            "bridge": "天桥上",
            "indoor": "室内环境",
            "outdoor": "户外环境",
            "unknown": "",
        }
        return scene_zh_map.get(scene, "")

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
        scene, scene_confidence = self.infer_scene_with_confidence(names, mean_luma=mean_luma)

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
            if STRUCTURED_VOICE_AVAILABLE:
                lr = calculate_lr_dir(cx, frame_w)
                lr_zh = lr_to_zh(lr)
            else:
                lr = "left" if cx < frame_w * 0.4 else ("right" if cx > frame_w * 0.6 else "center")
                lr_zh = "左侧" if lr == "left" else ("右侧" if lr == "right" else "前方")
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
                    lr=lr,
                    lr_zh=lr_zh,
                    distance_m=dist_m,
                    urgency=urgency,
                    avoidance_action=avoidance,
                    relations=[],
                    frame_w=frame_w,
                    frame_h=frame_h,
                )
            )

        sem_objs = self._relations(sem_objs, frame_w)

        topk = sem_objs[:3]
        is_dynamic = any((o.name or "").strip().lower() in DYNAMIC_CLASSES and o.distance_m <= 3.0 for o in topk)
        if imu_yaw_rate_dps is not None and abs(float(imu_yaw_rate_dps)) >= self.turn_rate_thr_dps:
            is_dynamic = True

        return {
            "scene": scene,
            "scene_confidence": scene_confidence,
            "is_dynamic": is_dynamic,
            "objects": topk,
        }

    def render_text(self, sem: Dict[str, Any], use_steps: bool = True) -> str:
        """
        生成自然语言描述（支持步数输出）

        Args:
            sem: 语义对象字典
            use_steps: 是否使用步数描述（默认True）
        """
        objs: List[SemanticObject] = list(sem.get("objects") or [])
        if not objs:
            return "我没看到明显的关键障碍，前方看起来比较空。"

        dynamic = bool(sem.get("is_dynamic", False))
        scene = str(sem.get("scene") or "unknown")
        scene_zh = self.get_scene_zh(scene)

        # 危险等级前缀
        urgency_word = {"HIGH": "紧急", "MEDIUM": "注意", "LOW": ""}

        # 动态环境：先避险、后补充
        if dynamic:
            o = objs[0]
            if use_steps:
                steps = int(round(o.distance_m / 0.6))
                dist_txt = f"约{steps}步"
            else:
                d = o.distance_m
                dist_txt = f"{d:.0f}米" if d >= 1.0 else f"{d:.1f}米"
            ur = urgency_word.get(o.urgency, "注意")
            prefix = f"{ur}，" if ur else ""
            action = (o.avoidance_action or "").rstrip("。")
            direction = f"{o.clock}点方向({o.lr_zh})"
            scene_prefix = f"{scene_zh}，" if scene_zh else ""
            return f"{prefix}{scene_prefix}{direction}{dist_txt}有{_zh_name(o.name)}，{action}"

        # 稳定环境：先整体（场景），再关键点
        prefix = "前方环境还算稳定。"
        if scene_zh:
            prefix = f"{scene_zh}，"

        parts = []
        for o in objs[:3]:
            # 距离描述（支持米或步数）
            if use_steps:
                steps = int(round(o.distance_m / 0.6))
                dist_txt = f"约{steps}步"
            else:
                d = o.distance_m
                dist_txt = f"{d:.0f}米" if d >= 1.0 else f"{d:.1f}米"

            # 方向描述（钟点 + 左中右）
            lr_dir = o.lr_zh or "前方"
            action = (o.avoidance_action or "").rstrip("。")
            uw = urgency_word.get(o.urgency, "")
            uw_prefix = f"{uw}，" if uw else ""
            parts.append(f"{uw_prefix}{o.clock}点方向({lr_dir})约{dist_txt}有{_zh_name(o.name)}，{action}")

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
        schema_version: int = 2,  # 默认使用 schema_version=2
        use_steps: bool = True,   # 默认使用步数描述
    ) -> Dict[str, Any]:
        """
        生成结构化语义描述（支持 schema_version=2）

        Args:
            raw_objects: 原始物体检测列表
            frame_w: 画面宽度
            frame_h: 画面高度
            mean_luma: 平均亮度（用于场景识别）
            imu_yaw_deg: IMU偏航角
            imu_yaw_rate_dps: IMU偏航角速度
            schema_version: 输出结构版本（1=旧版，2=新版结构化）
            use_steps: 是否使用步数描述
        """
        sem = self.build_semantic_objects(
            raw_objects, frame_w, frame_h, mean_luma=mean_luma, imu_yaw_rate_dps=imu_yaw_rate_dps
        )
        text = self.render_text(sem, use_steps=use_steps)

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

        scene = sem.get("scene", "unknown")
        scene_confidence = float(sem.get("scene_confidence", 0.5) or 0.5)

        use_structured = STRUCTURED_VOICE_AVAILABLE and os.getenv("AIGLASS_USE_STRUCTURED_VOICE", "1") == "1"

        if schema_version >= 2 and use_structured:
            # 结构化语音输出（schema_version=2）
            try:
                scene_enum = SceneType(scene)
            except Exception:
                scene_enum = SceneType.UNKNOWN

            structured_objects: List[StructuredObject] = []
            for idx, o in enumerate(sem.get("objects") or []):
                name = str(getattr(o, "name", "") or "").strip()
                name_lc = name.lower()
                name_zh = STRUCTURED_NAME_ZH.get(name_lc, _zh_name(name))

                clock = int(getattr(o, "clock", 12))
                clock_zh = getattr(o, "clock_zh", "") or (clock_to_zh(clock) if STRUCTURED_VOICE_AVAILABLE else _dir_zh(clock))

                lr = getattr(o, "lr", "") or (calculate_lr_dir(getattr(o, "center_x", frame_w / 2.0), frame_w))
                lr_zh = getattr(o, "lr_zh", "") or (lr_to_zh(lr) if STRUCTURED_VOICE_AVAILABLE else ("左侧" if lr == "left" else ("右侧" if lr == "right" else "前方")))

                meters = float(getattr(o, "distance_m", 0.0) or 0.0)
                steps = max(1, int(round(meters / 0.6)))

                urg = str(getattr(o, "urgency", "LOW") or "LOW").upper()
                urgency = UrgencyLevel.HIGH if urg == "HIGH" else (UrgencyLevel.MEDIUM if urg == "MEDIUM" else UrgencyLevel.LOW)

                is_moving = name_lc in DYNAMIC_CLASSES
                is_approaching = bool(is_moving and meters <= 2.0)

                action_text = str(getattr(o, "avoidance_action", "") or "").rstrip("。")
                if urgency == UrgencyLevel.HIGH:
                    action_type = ActionType.STOP
                elif urgency == UrgencyLevel.MEDIUM:
                    action_type = ActionType.AVOID
                else:
                    action_type = ActionType.CONTINUE

                structured_objects.append(
                    StructuredObject(
                        id=idx + 1,
                        name=name,
                        name_zh=name_zh,
                        conf=float(getattr(o, "conf", 0.5) or 0.5),
                        direction=DirectionInfo(
                            clock=clock,
                            clock_zh=clock_zh,
                            lr=lr,
                            lr_zh=lr_zh,
                        ),
                        distance=DistanceInfo(
                            meters=meters,
                            steps=steps,
                        ),
                        urgency=urgency,
                        is_moving=is_moving,
                        is_approaching=is_approaching,
                        action=action_text,
                        action_type=action_type,
                        relations=list(getattr(o, "relations", []) or []),
                    )
                )

            svo = StructuredVoiceOutput(
                scene=scene_enum,
                scene_confidence=scene_confidence,
                objects=structured_objects,
                is_dynamic=bool(sem.get("is_dynamic", False)),
                jump_count=self.jump_count,
                imu_data={
                    "yaw_deg": imu_yaw_deg,
                    "yaw_rate_dps": imu_yaw_rate_dps,
                    "is_turning": turning,
                },
            )
            svo.should_speak = should_speak
            svo.priority = 100 if any(o.urgency == UrgencyLevel.HIGH for o in structured_objects) else 50
            text = svo.render_text(use_steps=use_steps)
            svo.text = text

            out = svo.to_dict()
            out["text"] = text
            out["should_speak"] = should_speak
            out["priority"] = svo.priority
            out["use_steps"] = use_steps
            return out

        # schema_version=2 的结构化输出
        if schema_version >= 2:
            scene_zh = self.get_scene_zh(scene)

            # 构建对象列表（包含步数信息）
            objects_v2 = []
            for o in (sem.get("objects") or []):
                obj_dict = o.to_dict()
                # 添加步数信息
                obj_dict["distance_steps"] = int(round(o.distance_m / 0.6))
                # 添加场景信息
                obj_dict["scene"] = scene
                obj_dict["scene_zh"] = scene_zh
                objects_v2.append(obj_dict)

            return {
                "schema_version": 2,
                "ts": time.time(),
                "scene": scene,
                "scene_zh": scene_zh,
                "scene_confidence": scene_confidence,
                "is_dynamic": bool(sem.get("is_dynamic", False)),
                "jump_count": self.jump_count,
                "imu": {
                    "yaw_deg": imu_yaw_deg,
                    "yaw_rate_dps": imu_yaw_rate_dps,
                    "is_turning": turning,
                },
                "objects": objects_v2,
                "text": text,
                "should_speak": should_speak,
                "priority": 100 if any(o.get("urgency") == "HIGH" for o in objects_v2) else 50,
                "use_steps": use_steps,
            }

        # schema_version=1 的旧版输出（保持兼容）
        return {
            "schema_version": 1,
            "ts": time.time(),
            "scene": scene,
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
