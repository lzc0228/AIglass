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
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

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
    # 优先使用 structured_voice 的统一映射（默认 front_arc：10/11/12/1/2）
    if STRUCTURED_VOICE_AVAILABLE:
        try:
            return int(calculate_clock_dir(cx, cy, w, h))
        except Exception:
            pass

    # fallback：保留与 structured_voice 一致的默认前视扇区映射
    mode = os.getenv("AIGLASS_CLOCK_MAPPING", "front_arc").strip().lower()
    if mode in ("full_360", "full360", "full", "legacy", "polar"):
        dx = cx - (w / 2.0)
        dy = cy - (h / 2.0)
        ang = math.atan2(dx, -dy)
        hour = int(round((ang / (2 * math.pi)) * 12)) % 12
        return 12 if hour == 0 else hour

    hours: List[int] = []
    for token in str(os.getenv("AIGLASS_FRONT_CLOCK_HOURS", "10,11,12,1,2")).split(","):
        token = token.strip()
        if not token:
            continue
        try:
            v = int(token)
        except Exception:
            continue
        if 1 <= v <= 12:
            hours.append(v)
    if len(hours) < 2:
        hours = [10, 11, 12, 1, 2]

    x_ratio = float(cx) / max(1.0, float(w))
    x_ratio = max(0.0, min(1.0, x_ratio))
    if os.getenv("AIGLASS_CLOCK_FLIP_LR", "0") == "1":
        x_ratio = 1.0 - x_ratio

    idx = int(x_ratio * len(hours))
    if idx >= len(hours):
        idx = len(hours) - 1
    return int(hours[idx])


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
    "plant": "植物",
    "hydrant": "消防栓",
    "fire hydrant": "消防栓",
    "cone": "锥桶",
    "stone": "石头",
    "box": "箱子",
    "trash bin": "垃圾桶",
    "trash can": "垃圾桶",
    "signpost": "指示牌",
    "tree": "树",
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
    "glass_door": "玻璃门",
    "glass_window": "玻璃窗",
    "door_handle": "门把手",
    "light_switch": "灯光开关",
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
    "fire hydrant": "消防栓",
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
    "stanchion": "隔离柱",
    "barrier": "路障",
    "fence": "围栏",
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
    "cup": "杯子",
    "bottle": "瓶子",
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

PARKED_BLOCKING_VEHICLE_CLASSES = {
    "car",
    "bus",
    "truck",
    "taxi",
    "police car",
    "ambulance",
    "motorcycle",
    "scooter",
}

ROADSIDE_OBSTACLE_CLASSES = {
    "trash bin",
    "bicycle",
    "scooter",
    "motorcycle",
}
ROADSIDE_PRIORITY_SCENES = {
    "street",
    "sidewalk",
    "crossroad",
    "bus_stop",
    "parking",
    "park",
    "square",
    "construction",
}

LABEL_ALIASES = {
    "stair": "stairs",
    "staircase": "stairs",
    "stairway": "stairs",
    "step": "stairs",
    "steps": "stairs",
    "hand rail": "handrail",
    "rail": "railing",
    "glass door": "glass_door",
    "glassdoor": "glass_door",
    "glass-door": "glass_door",
    "glass window": "glass_window",
    "glasswindow": "glass_window",
    "glass-window": "glass_window",
    "window pane": "glass_window",
    "door handle": "door_handle",
    "doorknob": "door_handle",
    "door knob": "door_handle",
    "handle": "door_handle",
    "switch": "light_switch",
    "light switch": "light_switch",
    "wall switch": "light_switch",
    "flowerpot": "potted plant",
    "flower pot": "potted plant",
    "planter": "potted plant",
    "pottedplant": "potted plant",
    "indoor plant": "potted plant",
    "fire hydrant": "hydrant",
    "hydrant post": "hydrant",
    "street hydrant": "hydrant",
    "sign post": "signpost",
    "sign-post": "signpost",
    "sign pole": "signpost",
    "street sign": "signpost",
    "road sign": "signpost",
    "traffic sign": "signpost",
    "tree trunk": "tree",
    "tree-trunk": "tree",
    "palm tree": "tree",
    "street tree": "tree",
    "trash can": "trash bin",
    "trashcan": "trash bin",
    "garbage can": "trash bin",
    "garbage bin": "trash bin",
    "waste bin": "trash bin",
    "wastebasket": "trash bin",
    "dustbin": "trash bin",
    "recycle bin": "trash bin",
    "recycling bin": "trash bin",
    "rubbish bin": "trash bin",
    "e-bike": "scooter",
    "ebike": "scooter",
    "e bike": "scooter",
    "electric bike": "scooter",
    "electric bicycle": "scooter",
    "bike": "bicycle",
    "motor bike": "motorcycle",
    "low fence": "fence",
    "short fence": "fence",
    "small fence": "fence",
    "low barrier": "fence",
    "guard rail": "fence",
    "guardrail": "fence",
    "safety rail": "fence",
    "fence barrier": "fence",
    "rail barrier": "fence",
    "telephone pole": "utility pole",
    "lamp post": "light pole",
    "lightpost": "light pole",
    "posts": "post",
    "poles": "pole",
    "ticketgate": "ticket gate",
    "faregate": "fare gate",
    "turn stile": "turnstile",
}

STAIR_LIKE_CLASSES = {"stairs", "escalator"}
STAIR_SUPPORT_CLASSES = {"handrail", "railing"}
GLASS_STRUCTURE_CLASSES = {"glass_door", "glass_window"}
GLASS_SURFACE_BASE_CLASSES = {"door", "window"}
TURNSTILE_CLASSES = {"turnstile", "ticket gate", "fare gate"}
TURNSTILE_SUPPORT_CLASSES = {"ticket machine", "barrier", "stanchion"}
VERTICAL_STATIC_CLASSES = {
    "pole",
    "post",
    "column",
    "pillar",
    "bollard",
    "hydrant",
    "tree",
    "signpost",
    "utility pole",
    "telegraph pole",
    "light pole",
    "street pole",
    "support post",
    "vertical post",
}
VERTICAL_PRIORITY_SCENES = {"street", "sidewalk", "crossroad", "bus_stop", "park", "square", "construction"}
INDOOR_SCENES = {
    "indoor",
    "corridor",
    "restroom",
    "restaurant",
    "office",
    "hospital",
    "mall",
    "supermarket",
    "school",
    "stairs",
    "elevator",
    "subway",
    "bank",
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
    risk_score: float = 0.0
    risk_factors: Optional[Dict[str, float]] = None
    motion_dir: str = "unknown"
    speed_norm: float = 0.0
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
            "risk_score": self.risk_score,
            "risk_factors": dict(self.risk_factors or {}),
            "motion_dir": self.motion_dir,
            "speed_norm": self.speed_norm,
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
        self.conf_threshold = float(os.getenv("AIGLASS_SEM_CONF_THRESHOLD", "0.2"))
        self.stage1_topk = int(os.getenv("AIGLASS_SEM_STAGE1_TOPK", "10"))
        self.stage2_topk = int(os.getenv("AIGLASS_SEM_STAGE2_TOPK", "5"))
        self.output_topk = int(os.getenv("AIGLASS_SEM_OUTPUT_TOPK", "3"))
        self.motion_dt_max = float(os.getenv("AIGLASS_SEM_MOTION_DT_MAX", "1.5"))
        self.motion_px_norm = float(os.getenv("AIGLASS_SEM_MOTION_PX_NORM", "0.35"))
        self.occlusion_iou_thr = float(os.getenv("AIGLASS_SEM_OCCLUSION_IOU", "0.1"))
        self.poster_support_min = float(os.getenv("AIGLASS_POSTER_SUPPORT_MIN", "0.78"))
        self.poster_speed_max = float(os.getenv("AIGLASS_POSTER_SPEED_MAX", "0.05"))
        self.poster_approach_abs_max = float(os.getenv("AIGLASS_POSTER_APPROACH_ABS_MAX", "0.012"))
        self.poster_distance_min_m = float(os.getenv("AIGLASS_POSTER_DISTANCE_MIN_M", "1.6"))
        self.stair_memory_sec = float(os.getenv("AIGLASS_STAIR_MEMORY_SEC", "1.8"))
        self.stair_support_min_conf = float(os.getenv("AIGLASS_STAIR_SUPPORT_MIN_CONF", "0.35"))
        self.stair_hint_min_risk = float(os.getenv("AIGLASS_STAIR_HINT_MIN_RISK", "0.46"))
        self.turnstile_memory_sec = float(os.getenv("AIGLASS_TURNSTILE_MEMORY_SEC", "2.2"))
        self.turnstile_support_min_conf = float(os.getenv("AIGLASS_TURNSTILE_SUPPORT_MIN_CONF", "0.35"))
        self.turnstile_hint_min_risk = float(os.getenv("AIGLASS_TURNSTILE_HINT_MIN_RISK", "0.44"))
        self.far_static_distance_m = float(os.getenv("AIGLASS_FAR_STATIC_DISTANCE_M", "3.2"))
        self.far_static_risk_max = float(os.getenv("AIGLASS_FAR_STATIC_RISK_MAX", "0.52"))
        self.glass_pair_max_dist_norm = float(os.getenv("AIGLASS_GLASS_PAIR_MAX_DIST_NORM", "0.24"))
        self.glass_switch_max_dist_norm = float(os.getenv("AIGLASS_GLASS_SWITCH_MAX_DIST_NORM", "0.32"))
        self.parked_block_distance_m = float(os.getenv("AIGLASS_PARKED_BLOCK_DISTANCE_M", "3.8"))
        self.parked_block_area_min = float(os.getenv("AIGLASS_PARKED_BLOCK_AREA_MIN", "0.035"))
        self.parked_speed_max = float(os.getenv("AIGLASS_PARKED_SPEED_MAX", "0.10"))
        self.parked_approach_abs_max = float(os.getenv("AIGLASS_PARKED_APPROACH_ABS_MAX", "0.015"))
        self.low_fence_center_y_min = float(os.getenv("AIGLASS_LOW_FENCE_CENTER_Y_MIN", "0.56"))
        self.low_fence_height_max_ratio = float(os.getenv("AIGLASS_LOW_FENCE_HEIGHT_MAX_RATIO", "0.42"))
        self.low_fence_risk_floor = float(os.getenv("AIGLASS_LOW_FENCE_RISK_FLOOR", "0.50"))

        # 稳定性指标（WP4 会进一步结合 IMU）
        self.prev_signature: Optional[str] = None
        self.jump_count: int = 0
        self._track_cache: Dict[str, List[Dict[str, float]]] = defaultdict(list)
        self._last_stair_hint: Optional[Dict[str, Any]] = None
        self._last_turnstile_hint: Optional[Dict[str, Any]] = None
        self.scene_strategies = list(self._SCENE_STRATEGIES)
        self._load_scene_strategies()

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

    # 场景识别策略表（替代大量 if-elif，提高可维护性）
    # 格式: (场景名称, {关键词集合}, 基础置信度, 优先级)
    # 优先级用于解决多个场景同时匹配时的冲突（数字越大优先级越高）
    _SCENE_STRATEGIES = [
        # 交通场景（高优先级）
        ("traffic_light", {"traffic light", "signal", "red light", "green light"}, 0.9, 5),
        ("crosswalk", {"crosswalk", "zebra crossing", "zebra"}, 0.8, 4),
        ("sidewalk", {"sidewalk", "pedestrian", "curb"}, 0.7, 3),
        ("crossroad", {"crossroad", "intersection", "stop line"}, 0.7, 3),
        ("bus_stop", {"bus stop", "bus stop sign", "transit shelter", "bus station"}, 0.8, 3),

        # 医疗场景
        ("hospital", {"hospital", "clinic", "doctor", "nurse", "wheelchair",
                      "stretcher", "gurney", "medical", "iv drip", "hospital bed"}, 0.8, 4),

        # 商业场景
        ("supermarket", {"supermarket", "shelf", "shopping cart", "aisle",
                         "checkout", "grocery", "price tag", "cart"}, 0.8, 3),
        ("mall", {"mall", "escalator", "mannequin", "storefront", "display", "brand"}, 0.8, 3),
        ("restaurant", {"restaurant", "table", "chair", "dining", "menu", "waiter"}, 0.7, 2),
        ("bank", {"bank", "atm", "teller", "vault", "queue"}, 0.7, 2),

        # 施工/危险场景（高优先级）
        ("construction", {"cone", "barrier", "fence", "construction",
                          "warning sign", "safety vest", "excavator", "crane"}, 0.9, 5),

        # 室内导航场景
        ("elevator", {"elevator", "lift", "floor button"}, 0.8, 3),
        ("stairs", {"stairs", "stair", "staircase", "handrail", "step"}, 0.8, 3),
        ("corridor", {"corridor", "hallway", "room number", "exit sign"}, 0.7, 2),
        ("restroom", {"restroom", "toilet", "sink", "mirror", "bathroom"}, 0.7, 2),

        # 公共交通
        ("subway", {"subway", "metro", "turnstile", "ticket machine",
                     "fare gate", "platform", "metro train"}, 0.8, 3),

        # 户外场景
        ("park", {"park", "garden", "tree", "bench", "lawn", "grass",
                  "flower bed", "fountain", "pond"}, 0.7, 2),
        ("square", {"square", "plaza", "statue", "open area"}, 0.7, 2),

        # 办公/教育场景
        ("office", {"office", "desk", "computer", "printer", "cubicle"}, 0.7, 2),
        ("school", {"school", "classroom", "student", "blackboard", "campus"}, 0.7, 2),
    ]

    def _load_scene_strategies(self):
        """支持从 JSON 加载场景策略，便于扩展到 100+ 场景而不改代码。"""
        path = os.getenv("AIGLASS_SCENE_STRATEGIES", os.path.join(self.weights_dir, "scene_strategies.json"))
        if not path or not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f) or []
            strategies = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name", "")).strip()
                if not name:
                    continue
                keywords_raw = item.get("keywords") or []
                if not isinstance(keywords_raw, (list, tuple, set)):
                    continue
                keywords = {str(k).strip().lower() for k in keywords_raw if str(k).strip()}
                if not keywords:
                    continue
                base_conf = float(item.get("base_confidence", item.get("base_conf", 0.7)))
                priority = int(item.get("priority", 1))
                strategies.append((name, keywords, base_conf, priority))
            if strategies:
                self.scene_strategies = strategies
                print(f"[SEMANTIC] 已加载外部场景策略: {len(strategies)} 条 ({path})")
        except Exception as e:
            print(f"[SEMANTIC] 外部场景策略加载失败: {e}")

    def infer_scene_with_confidence(self, names: List[str], mean_luma: Optional[float] = None) -> Tuple[str, float]:
        """
        基于策略表的场景识别（替代原有大量 if-elif）

        优势：
        - 可维护性：新增场景只需在策略表中添加一行
        - 可配置性：策略表可以从外部配置文件加载
        - 可测试性：策略表可以独立测试
        - 性能：单次遍历即可完成所有场景匹配
        """
        nset = {str(n).strip().lower() for n in (names or [])}

        # 首先尝试使用结构化语音模块的场景识别
        if STRUCTURED_VOICE_AVAILABLE:
            try:
                scene_enum, conf = infer_scene_from_objects(
                    [{"name": n} for n in nset], mean_luma=mean_luma
                )
                if scene_enum and getattr(scene_enum, "value", "unknown") != "unknown":
                    return scene_enum.value, float(conf)
            except Exception:
                pass

        # 使用策略表进行场景识别
        scores = []
        for scene_name, keywords, base_conf, priority in self.scene_strategies:
            matched = nset & keywords
            if matched:
                # 基于匹配数量和优先级计算得分
                match_score = len(matched) / len(keywords)
                final_conf = base_conf * (0.5 + 0.5 * match_score)
                scores.append((scene_name, final_conf, priority))

        # 按置信度排序，相同置信度时优先级高的胜出
        if scores:
            scores.sort(key=lambda x: (x[1], x[2]), reverse=True)
            return scores[0][0], scores[0][1]

        # 回退逻辑（基于简单启发式规则）
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
        k = self._normalize_object_name(name)
        scene_lc = str(scene or "").strip().lower()
        base = max(0.05, min(1.0, float(conf)))
        tw = float(self.task_weights.get(k, 1.0))
        sw = float((self.scene_weights.get(scene) or {}).get(k, 1.0))
        up = float(self.user_prefs.get(k, 1.0))
        prox = 1.0 + min(2.0, float(area_ratio) * 8.0)
        dyn = 1.5 if k in DYNAMIC_CLASSES else 1.0
        structure_bonus = 1.0
        indoor_plant_boost = 1.0
        vertical_bonus = 1.0
        roadside_bonus = 1.0
        low_fence_bonus = 1.0
        if k == "potted plant" and scene_lc in INDOOR_SCENES:
            indoor_plant_boost = 2.2 + min(1.8, max(0.0, float(area_ratio)) * 18.0)
        if k in VERTICAL_STATIC_CLASSES:
            vertical_bonus = 1.35 + min(0.4, max(0.0, float(area_ratio)) * 8.0)
            if scene_lc in VERTICAL_PRIORITY_SCENES:
                vertical_bonus *= 1.28
        if k in GLASS_STRUCTURE_CLASSES:
            structure_bonus = 1.25
        elif k in {"door_handle", "light_switch"}:
            structure_bonus = 1.08
        if k in ROADSIDE_OBSTACLE_CLASSES:
            roadside_bonus = 1.18 + min(0.50, max(0.0, float(area_ratio)) * 10.0)
            if scene_lc in ROADSIDE_PRIORITY_SCENES:
                roadside_bonus *= 1.25
        if k == "fence":
            low_profile_bonus = max(0.0, min(0.55, (0.18 - max(0.0, float(area_ratio))) * 2.0))
            low_fence_bonus = 1.10 + low_profile_bonus
            if scene_lc in ROADSIDE_PRIORITY_SCENES:
                low_fence_bonus *= 1.18
        return (
            base
            * tw
            * sw
            * up
            * prox
            * dyn
            * structure_bonus
            * indoor_plant_boost
            * vertical_bonus
            * roadside_bonus
            * low_fence_bonus
        )

    def _is_low_fence_geometry(self, bbox: Optional[List[float]], frame_h: int) -> bool:
        if not bbox or len(bbox) != 4 or frame_h <= 0:
            return False
        _, y1, _, y2 = [float(v) for v in bbox]
        center_y = ((y1 + y2) * 0.5) / float(frame_h)
        height_ratio = max(0.0, y2 - y1) / float(frame_h)
        if center_y < self.low_fence_center_y_min:
            return False
        if height_ratio > self.low_fence_height_max_ratio:
            return False
        return True

    def _is_low_fence_candidate(self, item: Dict[str, Any], frame_h: int) -> bool:
        name_lc = self._normalize_object_name(str(item.get("name", "")))
        if name_lc != "fence":
            return False
        bbox = item.get("bbox")
        if not isinstance(bbox, list):
            return False
        return self._is_low_fence_geometry(bbox, frame_h)

    def _best_previous_track(self, name: str, cx: float, cy: float, now_ts: float) -> Optional[Dict[str, float]]:
        name_lc = self._normalize_object_name(name)
        history = self._track_cache.get(name_lc) or []
        best = None
        best_dist = float("inf")
        for item in history:
            dt = now_ts - float(item.get("ts", 0.0) or 0.0)
            if dt <= 0.0 or dt > self.motion_dt_max:
                continue
            dx = cx - float(item.get("cx", cx) or cx)
            dy = cy - float(item.get("cy", cy) or cy)
            d = math.hypot(dx, dy)
            if d < best_dist:
                best_dist = d
                best = item
        return best

    def _estimate_motion_features(
        self, name: str, cx: float, cy: float, area_ratio: float, now_ts: float, frame_w: int, frame_h: int
    ) -> Tuple[float, float, str]:
        prev = self._best_previous_track(name, cx, cy, now_ts)
        if prev is None:
            return 0.0, 0.0, "unknown"

        dt = max(1e-6, now_ts - float(prev.get("ts", now_ts) or now_ts))
        dx = cx - float(prev.get("cx", cx) or cx)
        dy = cy - float(prev.get("cy", cy) or cy)
        da = float(area_ratio) - float(prev.get("area_ratio", area_ratio) or area_ratio)

        diag = max(1.0, math.hypot(float(frame_w), float(frame_h)))
        speed_norm = min(1.0, (math.hypot(dx, dy) / dt) / (diag * max(1e-6, self.motion_px_norm)))
        approach_rate = da / dt

        if abs(dx) >= abs(dy):
            lateral = "right" if dx > 0 else "left"
        else:
            lateral = "down" if dy > 0 else "up"

        if approach_rate > 0.015:
            motion = f"approaching_{lateral}"
        elif approach_rate < -0.015:
            motion = f"receding_{lateral}"
        else:
            motion = lateral

        return speed_norm, approach_rate, motion

    def _estimate_occlusion_factor(self, idx: int, items: List[Dict[str, Any]], frame_w: int, frame_h: int) -> float:
        cur = items[idx]
        bbox = cur.get("bbox")
        if not bbox or len(bbox) != 4:
            return 0.0

        max_iou = 0.0
        for j, other in enumerate(items):
            if j == idx:
                continue
            ob = other.get("bbox")
            if not ob or len(ob) != 4:
                continue
            max_iou = max(max_iou, _iou([float(x) for x in bbox], [float(x) for x in ob]))

        x1, y1, x2, y2 = [float(v) for v in bbox]
        edge_margin = min(x1, y1, max(0.0, frame_w - x2), max(0.0, frame_h - y2))
        clipped_bonus = 0.2 if edge_margin <= 0.01 * max(frame_w, frame_h) else 0.0
        return max(0.0, min(1.0, max_iou + clipped_bonus))

    def _compute_risk_factors(
        self,
        name: str,
        distance_m: float,
        speed_norm: float,
        approach_rate: float,
        bbox: Optional[List[float]],
        frame_h: int,
        occlusion_factor: float,
    ) -> Dict[str, float]:
        distance_factor = max(0.0, min(1.0, 1.0 - min(float(distance_m), 8.0) / 8.0))
        speed_factor = max(0.0, min(1.0, float(speed_norm)))
        approach_factor = max(0.0, min(1.0, max(0.0, float(approach_rate)) / 0.08))

        height_factor = 0.0
        support_factor = 0.0
        if bbox and len(bbox) == 4 and frame_h > 0:
            _, y1, _, y2 = [float(v) for v in bbox]
            center_y = (y1 + y2) * 0.5 / float(frame_h)
            bottom_ratio = y2 / float(frame_h)
            # 中上部物体（头部高度附近）风险更高
            height_factor = max(0.0, min(1.0, 1.0 - abs(center_y - 0.45) / 0.45))
            # 底部离地越远，支撑越弱，风险越高
            support_factor = max(0.0, min(1.0, (0.9 - bottom_ratio) / 0.9))

        dynamic_bonus = 0.12 if (name or "").strip().lower() in DYNAMIC_CLASSES else 0.0
        return {
            "distance": distance_factor,
            "speed": speed_factor,
            "approach": approach_factor,
            "height": height_factor,
            "support": support_factor,
            "occlusion": max(0.0, min(1.0, float(occlusion_factor))),
            "dynamic_bonus": dynamic_bonus,
        }

    def _risk_from_factors(self, factors: Dict[str, float]) -> float:
        risk = (
            0.30 * float(factors.get("distance", 0.0))
            + 0.20 * float(factors.get("approach", 0.0))
            + 0.16 * float(factors.get("speed", 0.0))
            + 0.12 * float(factors.get("height", 0.0))
            + 0.12 * float(factors.get("support", 0.0))
            + 0.10 * float(factors.get("occlusion", 0.0))
            + float(factors.get("dynamic_bonus", 0.0))
        )
        return max(0.0, min(1.0, risk))

    def _infer_urgency(self, name: str, distance_m: float, risk_score: float, motion_dir: str) -> str:
        urgency = "LOW"
        if risk_score >= 0.72:
            urgency = "HIGH"
        elif risk_score >= 0.45:
            urgency = "MEDIUM"

        name_lc = self._normalize_object_name(name)
        if name_lc in DYNAMIC_CLASSES and distance_m <= 2.0 and motion_dir.startswith("approaching_"):
            urgency = "HIGH"
        elif distance_m <= 1.2 and urgency == "LOW":
            urgency = "MEDIUM"
        return urgency

    def _normalize_object_name(self, name: str) -> str:
        k = str(name or "").strip().lower().replace("-", " ").replace("_", " ")
        if not k:
            return ""
        k = " ".join(k.split())
        return LABEL_ALIASES.get(k, k)

    def _is_stair_like_name(self, name: str) -> bool:
        return self._normalize_object_name(name) in STAIR_LIKE_CLASSES

    def _is_stair_support_name(self, name: str) -> bool:
        return self._normalize_object_name(name) in STAIR_SUPPORT_CLASSES

    def _is_turnstile_name(self, name: str) -> bool:
        return self._normalize_object_name(name) in TURNSTILE_CLASSES

    def _is_turnstile_support_name(self, name: str) -> bool:
        return self._normalize_object_name(name) in TURNSTILE_SUPPORT_CLASSES

    def _normalize_scene_object_name(self, name: str, scene: str) -> str:
        name_lc = self._normalize_object_name(name)
        scene_lc = str(scene or "").strip().lower()
        if name_lc == "plant" and scene_lc in INDOOR_SCENES:
            return "potted plant"
        return name_lc

    def _is_parked_blocking_vehicle(self, item: Dict[str, Any]) -> bool:
        name_lc = self._normalize_object_name(str(item.get("name", "")))
        if name_lc not in PARKED_BLOCKING_VEHICLE_CLASSES:
            return False
        if str(item.get("motion_dir", "")).startswith("approaching_"):
            return False
        if float(item.get("speed_norm", 0.0) or 0.0) > self.parked_speed_max:
            return False
        if abs(float(item.get("approach_rate", 0.0) or 0.0)) > self.parked_approach_abs_max:
            return False
        if float(item.get("distance_m", 99.0) or 99.0) <= self.parked_block_distance_m:
            return True
        if float(item.get("area_ratio", 0.0) or 0.0) >= self.parked_block_area_min:
            return True
        return False

    def _infer_parked_vehicle_blocked_sides(
        self,
        candidates: List[Dict[str, Any]],
        frame_w: int,
    ) -> Set[str]:
        blocked: Set[str] = set()
        fw = max(1.0, float(frame_w))
        for item in candidates or []:
            if not self._is_parked_blocking_vehicle(item):
                continue
            bbox = item.get("bbox")
            if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
                x1 = max(0.0, min(fw, float(bbox[0])))
                x2 = max(0.0, min(fw, float(bbox[2])))
            else:
                cx = max(0.0, min(fw, float(item.get("center_x", fw / 2.0) or fw / 2.0)))
                half_w = fw * 0.08
                x1 = max(0.0, cx - half_w)
                x2 = min(fw, cx + half_w)

            if x2 <= fw * 0.54:
                blocked.add("left")
            elif x1 >= fw * 0.46:
                blocked.add("right")
            else:
                blocked.update({"left", "right"})
        return blocked

    def _update_stair_hint_cache(self, candidates: List[Dict[str, Any]], now_ts: float):
        stair_candidates = [c for c in (candidates or []) if self._is_stair_like_name(str(c.get("name", "")))]
        if not stair_candidates:
            return
        best = max(
            stair_candidates,
            key=lambda x: (float(x.get("risk_score", 0.0) or 0.0), float(x.get("score", 0.0) or 0.0)),
        )
        self._last_stair_hint = {
            "ts": now_ts,
            "name": self._normalize_object_name(str(best.get("name", ""))),
            "conf": float(best.get("conf", 0.5) or 0.5),
            "score": float(best.get("score", 0.0) or 0.0),
            "risk_score": float(best.get("risk_score", 0.0) or 0.0),
            "distance_m": float(best.get("distance_m", 2.0) or 2.0),
            "area_ratio": float(best.get("area_ratio", 0.01) or 0.01),
            "center_x": float(best.get("center_x", 0.0) or 0.0),
            "center_y": float(best.get("center_y", 0.0) or 0.0),
        }

    def _maybe_inject_stair_hint(
        self,
        stage2: List[Dict[str, Any]],
        prepared: List[Dict[str, Any]],
        frame_w: int,
        frame_h: int,
        now_ts: float,
    ) -> List[Dict[str, Any]]:
        if any(self._is_stair_like_name(str(o.get("name", ""))) for o in (stage2 or [])):
            return stage2
        hint = self._last_stair_hint or {}
        if not hint:
            return stage2
        if now_ts - float(hint.get("ts", 0.0) or 0.0) > self.stair_memory_sec:
            return stage2

        has_support = any(
            self._is_stair_support_name(str(o.get("name", "")))
            and float(o.get("conf", 0.0) or 0.0) >= self.stair_support_min_conf
            for o in (prepared or [])
        )
        if not has_support:
            return stage2

        dist_m = float(hint.get("distance_m", 2.0) or 2.0)
        synthetic = {
            "name": "stairs",
            "conf": max(0.35, min(0.95, float(hint.get("conf", 0.5) or 0.5) * 0.72)),
            "bbox": None,
            "center_x": float(hint.get("center_x", frame_w / 2.0) or frame_w / 2.0),
            "center_y": float(hint.get("center_y", frame_h * 0.62) or frame_h * 0.62),
            "area_ratio": max(0.006, float(hint.get("area_ratio", 0.01) or 0.01) * 0.85),
            "distance_m": max(0.8, min(8.0, dist_m)),
            "speed_norm": 0.0,
            "approach_rate": 0.0,
            "motion_dir": "hint_memory",
            "score": max(0.35, float(hint.get("score", 0.4) or 0.4) * 0.78),
        }
        factors = self._compute_risk_factors(
            name="stairs",
            distance_m=float(synthetic.get("distance_m", 2.0)),
            speed_norm=0.0,
            approach_rate=0.0,
            bbox=None,
            frame_h=frame_h,
            occlusion_factor=0.0,
        )
        risk_score = max(self.stair_hint_min_risk, self._risk_from_factors(factors))
        action, urgency = self._avoidance(
            name="stairs",
            cx=float(synthetic.get("center_x", frame_w / 2.0)),
            w=frame_w,
            distance_m=float(synthetic.get("distance_m", 2.0)),
            risk_score=risk_score,
            motion_dir="hint_memory",
            support_factor=float(factors.get("support", 0.0)),
            speed_norm=0.0,
            approach_rate=0.0,
        )
        synthetic["risk_factors"] = factors
        synthetic["risk_score"] = risk_score
        synthetic["urgency"] = urgency
        synthetic["avoidance_action"] = action
        synthetic["inferred_from"] = "stair_hint"
        return [*stage2, synthetic]

    def _update_turnstile_hint_cache(self, candidates: List[Dict[str, Any]], now_ts: float):
        turnstile_candidates = [
            c for c in (candidates or []) if self._is_turnstile_name(str(c.get("name", "")))
        ]
        if not turnstile_candidates:
            return
        best = max(
            turnstile_candidates,
            key=lambda x: (float(x.get("risk_score", 0.0) or 0.0), float(x.get("score", 0.0) or 0.0)),
        )
        self._last_turnstile_hint = {
            "ts": now_ts,
            "name": self._normalize_object_name(str(best.get("name", ""))),
            "conf": float(best.get("conf", 0.5) or 0.5),
            "score": float(best.get("score", 0.0) or 0.0),
            "risk_score": float(best.get("risk_score", 0.0) or 0.0),
            "distance_m": float(best.get("distance_m", 2.0) or 2.0),
            "area_ratio": float(best.get("area_ratio", 0.01) or 0.01),
            "center_x": float(best.get("center_x", 0.0) or 0.0),
            "center_y": float(best.get("center_y", 0.0) or 0.0),
        }

    def _maybe_inject_turnstile_hint(
        self,
        stage2: List[Dict[str, Any]],
        prepared: List[Dict[str, Any]],
        frame_w: int,
        frame_h: int,
        now_ts: float,
        scene: str,
    ) -> List[Dict[str, Any]]:
        if any(self._is_turnstile_name(str(o.get("name", ""))) for o in (stage2 or [])):
            return stage2
        hint = self._last_turnstile_hint or {}
        if not hint:
            return stage2
        if now_ts - float(hint.get("ts", 0.0) or 0.0) > self.turnstile_memory_sec:
            return stage2

        support_objs = [
            o
            for o in (prepared or [])
            if self._is_turnstile_support_name(str(o.get("name", "")))
            and float(o.get("conf", 0.0) or 0.0) >= self.turnstile_support_min_conf
        ]
        if not support_objs:
            return stage2

        scene_lc = str(scene or "").strip().lower()
        if scene_lc not in {"subway", "unknown"} and len(support_objs) < 2:
            return stage2

        dist_m = float(hint.get("distance_m", 2.2) or 2.2)
        synthetic = {
            "name": "turnstile",
            "conf": max(0.34, min(0.92, float(hint.get("conf", 0.5) or 0.5) * 0.70)),
            "bbox": None,
            "center_x": float(hint.get("center_x", frame_w / 2.0) or frame_w / 2.0),
            "center_y": float(hint.get("center_y", frame_h * 0.58) or frame_h * 0.58),
            "area_ratio": max(0.006, float(hint.get("area_ratio", 0.01) or 0.01) * 0.82),
            "distance_m": max(0.8, min(8.0, dist_m + 0.2)),
            "speed_norm": 0.0,
            "approach_rate": 0.0,
            "motion_dir": "hint_memory",
            "score": max(0.33, float(hint.get("score", 0.4) or 0.4) * 0.74),
            "inferred_from": "turnstile_hint",
        }
        factors = self._compute_risk_factors(
            name="turnstile",
            distance_m=float(synthetic.get("distance_m", 2.0)),
            speed_norm=0.0,
            approach_rate=0.0,
            bbox=None,
            frame_h=frame_h,
            occlusion_factor=0.0,
        )
        risk_score = max(self.turnstile_hint_min_risk, self._risk_from_factors(factors))
        action, urgency = self._avoidance(
            name="turnstile",
            cx=float(synthetic.get("center_x", frame_w / 2.0)),
            w=frame_w,
            distance_m=float(synthetic.get("distance_m", 2.0)),
            risk_score=risk_score,
            motion_dir="hint_memory",
            support_factor=float(factors.get("support", 0.0)),
            speed_norm=0.0,
            approach_rate=0.0,
        )
        synthetic["risk_factors"] = factors
        synthetic["risk_score"] = risk_score
        synthetic["urgency"] = urgency
        synthetic["avoidance_action"] = action
        return [*stage2, synthetic]

    def _enhance_stair_handrail_context(
        self,
        stage2: List[Dict[str, Any]],
        candidates: List[Dict[str, Any]],
        frame_w: int,
    ) -> List[Dict[str, Any]]:
        stage2 = list(stage2 or [])
        if not stage2:
            return stage2

        has_stair = any(self._is_stair_like_name(str(o.get("name", ""))) for o in stage2)
        if not has_stair:
            return stage2

        stair_risk = max(
            [
                float(o.get("risk_score", 0.0) or 0.0)
                for o in stage2
                if self._is_stair_like_name(str(o.get("name", "")))
            ]
            or [0.56]
        )
        support_items = [o for o in stage2 if self._is_stair_support_name(str(o.get("name", "")))]

        if not support_items:
            best_support = None
            for o in (candidates or []):
                if not self._is_stair_support_name(str(o.get("name", ""))):
                    continue
                if best_support is None:
                    best_support = o
                    continue
                key_cur = (float(o.get("risk_score", 0.0) or 0.0), float(o.get("score", 0.0) or 0.0))
                key_best = (
                    float(best_support.get("risk_score", 0.0) or 0.0),
                    float(best_support.get("score", 0.0) or 0.0),
                )
                if key_cur > key_best:
                    best_support = o
            if best_support is not None:
                support_copy = dict(best_support)
                support_copy["risk_score"] = max(float(support_copy.get("risk_score", 0.0) or 0.0), 0.56)
                stage2.append(support_copy)
                support_items = [support_copy]

        for o in stage2:
            if self._is_stair_like_name(str(o.get("name", ""))):
                o["risk_score"] = max(float(o.get("risk_score", 0.0) or 0.0), 0.60)
                continue
            if not self._is_stair_support_name(str(o.get("name", ""))):
                continue
            o["risk_score"] = max(float(o.get("risk_score", 0.0) or 0.0), min(0.58, max(0.54, stair_risk)))
            action, urgency = self._avoidance(
                name=str(o.get("name", "")),
                cx=float(o.get("center_x", frame_w / 2.0)),
                w=frame_w,
                distance_m=float(o.get("distance_m", 0.0) or 0.0),
                risk_score=float(o.get("risk_score", 0.0) or 0.0),
                motion_dir=str(o.get("motion_dir", "unknown")),
                support_factor=float((o.get("risk_factors") or {}).get("support", 0.0)),
                speed_norm=float(o.get("speed_norm", 0.0) or 0.0),
                approach_rate=float(o.get("approach_rate", 0.0) or 0.0),
                stair_context=True,
            )
            o["avoidance_action"] = action
            o["urgency"] = urgency
        return stage2

    def _force_stair_handrail_topk(
        self,
        topk: List[SemanticObject],
        sem_objs: List[SemanticObject],
    ) -> List[SemanticObject]:
        out = list(topk or [])
        if not out:
            return out
        if not sem_objs:
            return out

        has_stair_any = any(self._is_stair_like_name(o.name) for o in sem_objs)
        has_support_any = any(self._is_stair_support_name(o.name) for o in sem_objs)
        if not (has_stair_any and has_support_any):
            return out

        best_stair = next((o for o in sem_objs if self._is_stair_like_name(o.name)), None)
        best_support = next((o for o in sem_objs if self._is_stair_support_name(o.name)), None)
        if best_stair is None or best_support is None:
            return out

        def _replace_if_missing(
            objs: List[SemanticObject],
            required_obj: SemanticObject,
            checker,
        ) -> List[SemanticObject]:
            if any(checker(o.name) for o in objs):
                return objs
            if required_obj in objs:
                return objs
            replace_idx = None
            for idx in range(len(objs) - 1, -1, -1):
                n = objs[idx].name
                if not self._is_stair_like_name(n) and not self._is_stair_support_name(n):
                    replace_idx = idx
                    break
            if replace_idx is None:
                replace_idx = len(objs) - 1
            objs[replace_idx] = required_obj
            return objs

        out = _replace_if_missing(out, best_stair, self._is_stair_like_name)
        out = _replace_if_missing(out, best_support, self._is_stair_support_name)
        out.sort(key=lambda x: (x.risk_score, x.score), reverse=True)
        return out

    def _force_vertical_static_topk(
        self,
        topk: List[SemanticObject],
        sem_objs: List[SemanticObject],
    ) -> List[SemanticObject]:
        out = list(topk or [])
        if not out or not sem_objs:
            return out

        vertical_pool = [
            o for o in sem_objs if self._normalize_object_name(getattr(o, "name", "")) in VERTICAL_STATIC_CLASSES
        ]
        if len(vertical_pool) < 2:
            return out

        vertical_pool = sorted(vertical_pool, key=lambda x: (x.risk_score, x.score), reverse=True)

        def is_vertical(obj: SemanticObject) -> bool:
            return self._normalize_object_name(getattr(obj, "name", "")) in VERTICAL_STATIC_CLASSES

        vertical_count = sum(1 for o in out if is_vertical(o))
        replace_iter = iter(vertical_pool)
        while vertical_count < 2:
            candidate = None
            for item in replace_iter:
                if item not in out:
                    candidate = item
                    break
            if candidate is None:
                break
            replace_idx = None
            for idx in range(len(out) - 1, -1, -1):
                if not is_vertical(out[idx]):
                    replace_idx = idx
                    break
            if replace_idx is None:
                break
            out[replace_idx] = candidate
            vertical_count = sum(1 for o in out if is_vertical(o))

        out.sort(key=lambda x: (x.risk_score, x.score), reverse=True)
        return out

    def _force_roadside_obstacle_topk(
        self,
        topk: List[SemanticObject],
        sem_objs: List[SemanticObject],
    ) -> List[SemanticObject]:
        out = list(topk or [])
        if not out or not sem_objs:
            return out

        def is_target(obj: SemanticObject) -> bool:
            return self._normalize_object_name(getattr(obj, "name", "")) in ROADSIDE_OBSTACLE_CLASSES

        target_pool = sorted(
            [o for o in sem_objs if is_target(o)],
            key=lambda x: (x.risk_score, x.score),
            reverse=True,
        )
        if not target_pool:
            return out

        desired = 2 if len(target_pool) >= 2 else 1
        current = sum(1 for o in out if is_target(o))
        if current >= desired:
            return out

        def is_protected(name: str) -> bool:
            return (
                self._is_stair_like_name(name)
                or self._is_stair_support_name(name)
                or self._is_turnstile_name(name)
            )

        for candidate in target_pool:
            if current >= desired:
                break
            if candidate in out:
                continue

            replace_idx = None
            for idx in range(len(out) - 1, -1, -1):
                victim = out[idx]
                if is_target(victim):
                    continue
                if is_protected(victim.name):
                    continue
                if str(getattr(victim, "urgency", "LOW")).upper() == "HIGH":
                    continue
                replace_idx = idx
                break
            if replace_idx is None:
                for idx in range(len(out) - 1, -1, -1):
                    victim = out[idx]
                    if not is_target(victim) and not is_protected(victim.name):
                        replace_idx = idx
                        break
            if replace_idx is None:
                break

            out[replace_idx] = candidate
            current = sum(1 for o in out if is_target(o))

        out.sort(key=lambda x: (x.risk_score, x.score), reverse=True)
        return out

    def _force_low_fence_topk(
        self,
        topk: List[SemanticObject],
        sem_objs: List[SemanticObject],
    ) -> List[SemanticObject]:
        out = list(topk or [])
        if not out or not sem_objs:
            return out

        low_fence_pool = [
            o
            for o in sem_objs
            if self._normalize_object_name(getattr(o, "name", "")) == "fence"
            and self._is_low_fence_geometry(getattr(o, "bbox", None), int(getattr(o, "frame_h", 0) or 0))
        ]
        if not low_fence_pool:
            return out

        if any(
            self._normalize_object_name(getattr(o, "name", "")) == "fence"
            and self._is_low_fence_geometry(getattr(o, "bbox", None), int(getattr(o, "frame_h", 0) or 0))
            for o in out
        ):
            return out

        best_fence = sorted(low_fence_pool, key=lambda x: (x.risk_score, x.score), reverse=True)[0]

        replace_idx = None
        for idx in range(len(out) - 1, -1, -1):
            victim = out[idx]
            n = victim.name
            if self._is_stair_like_name(n) or self._is_stair_support_name(n) or self._is_turnstile_name(n):
                continue
            if str(getattr(victim, "urgency", "LOW")).upper() == "HIGH":
                continue
            replace_idx = idx
            break
        if replace_idx is None:
            return out

        out[replace_idx] = best_fence
        out.sort(key=lambda x: (x.risk_score, x.score), reverse=True)
        return out

    def _pair_distance_norm(
        self,
        a: Dict[str, Any],
        b: Dict[str, Any],
        frame_w: int,
        frame_h: int,
    ) -> float:
        ax = float(a.get("center_x", frame_w / 2.0) or frame_w / 2.0)
        ay = float(a.get("center_y", frame_h / 2.0) or frame_h / 2.0)
        bx = float(b.get("center_x", frame_w / 2.0) or frame_w / 2.0)
        by = float(b.get("center_y", frame_h / 2.0) or frame_h / 2.0)
        diag = max(1.0, math.hypot(float(frame_w), float(frame_h)))
        return math.hypot(ax - bx, ay - by) / diag

    def _infer_glass_structure_candidates(
        self,
        prepared: List[Dict[str, Any]],
        frame_w: int,
        frame_h: int,
    ) -> List[Dict[str, Any]]:
        prepared = list(prepared or [])
        if not prepared:
            return []

        explicit_glass = any(
            self._normalize_object_name(str(o.get("name", ""))) in GLASS_STRUCTURE_CLASSES
            for o in prepared
        )
        if explicit_glass:
            return []

        surfaces: List[Dict[str, Any]] = []
        handles: List[Dict[str, Any]] = []
        switches: List[Dict[str, Any]] = []
        for o in prepared:
            name = self._normalize_object_name(str(o.get("name", "")))
            if name in GLASS_SURFACE_BASE_CLASSES:
                surfaces.append(o)
            elif name == "door_handle":
                handles.append(o)
            elif name == "light_switch":
                switches.append(o)

        if not surfaces or not handles:
            return []

        inferred: List[Dict[str, Any]] = []
        for s in surfaces:
            surface_name = self._normalize_object_name(str(s.get("name", "")))
            if surface_name not in GLASS_SURFACE_BASE_CLASSES:
                continue

            best_handle = None
            best_dist = float("inf")
            for h in handles:
                d = self._pair_distance_norm(s, h, frame_w, frame_h)
                if d < best_dist:
                    best_dist = d
                    best_handle = h
            if best_handle is None or best_dist > self.glass_pair_max_dist_norm:
                continue

            has_near_switch = False
            for sw in switches:
                if self._pair_distance_norm(best_handle, sw, frame_w, frame_h) <= self.glass_switch_max_dist_norm:
                    has_near_switch = True
                    break

            target_name = "glass_door" if surface_name == "door" else "glass_window"
            sx = float(s.get("center_x", frame_w / 2.0) or frame_w / 2.0)
            sy = float(s.get("center_y", frame_h / 2.0) or frame_h / 2.0)
            hx = float(best_handle.get("center_x", sx) or sx)
            hy = float(best_handle.get("center_y", sy) or sy)
            s_conf = float(s.get("conf", 0.5) or 0.5)
            h_conf = float(best_handle.get("conf", 0.5) or 0.5)
            conf = max(0.35, min(0.95, max(s_conf, h_conf) * 0.74 + (0.08 if has_near_switch else 0.0)))
            inferred.append(
                {
                    "name": target_name,
                    "raw_name": f"inferred_{target_name}",
                    "conf": conf,
                    "bbox": (list(s.get("bbox")) if isinstance(s.get("bbox"), (list, tuple)) else None),
                    "center_x": sx * 0.72 + hx * 0.28,
                    "center_y": sy * 0.72 + hy * 0.28,
                    "area_ratio": max(
                        float(s.get("area_ratio", 0.0) or 0.0),
                        float(best_handle.get("area_ratio", 0.0) or 0.0) * 2.4,
                    ),
                    "inferred_from": "glass_surface_handle_context",
                    "glass_switch_nearby": has_near_switch,
                }
            )

        # 对同类提示去重，保留置信度更高的一个
        dedup: Dict[str, Dict[str, Any]] = {}
        for it in inferred:
            k = str(it.get("name", ""))
            prev = dedup.get(k)
            if prev is None or float(it.get("conf", 0.0) or 0.0) > float(prev.get("conf", 0.0) or 0.0):
                dedup[k] = it
        return list(dedup.values())

    def _is_static_poster_like_person(
        self,
        *,
        name: str,
        distance_m: float,
        motion_dir: str,
        support_factor: float,
        speed_norm: float,
        approach_rate: float,
    ) -> bool:
        name_lc = self._normalize_object_name(name)
        if name_lc != "person":
            return False
        if float(distance_m) < self.poster_distance_min_m:
            return False
        if str(motion_dir or "").startswith("approaching_"):
            return False
        if float(support_factor) < self.poster_support_min:
            return False
        if float(speed_norm) > self.poster_speed_max:
            return False
        if abs(float(approach_rate)) > self.poster_approach_abs_max:
            return False
        return True

    def _avoidance(
        self,
        name: str,
        cx: float,
        w: int,
        distance_m: float,
        risk_score: float,
        motion_dir: str,
        support_factor: float,
        speed_norm: float = 0.0,
        approach_rate: float = 0.0,
        stair_context: bool = False,
        blocked_sides: Optional[Set[str]] = None,
    ) -> Tuple[str, str]:
        name_lc = self._normalize_object_name(name)
        x_ratio = cx / max(1.0, float(w))
        side = "center"
        if x_ratio < 0.4:
            side = "left"
        elif x_ratio > 0.6:
            side = "right"
        blocked = {str(s).strip().lower() for s in (blocked_sides or set()) if str(s).strip().lower() in {"left", "right"}}

        urgency = self._infer_urgency(name_lc, distance_m, risk_score, motion_dir)
        if name_lc == "glass_door":
            if distance_m <= 1.5:
                return "前方疑似玻璃门，门把手方向已标出，减速确认后通过。", "MEDIUM"
            if distance_m <= 2.8:
                return "前方可能是玻璃门，注意门把手位置并靠近确认。", "LOW"
            return "前方有玻璃门结构，沿提示方向谨慎接近。", "LOW"
        if name_lc == "glass_window":
            if distance_m <= 1.8:
                return "前方有玻璃窗，注意反光并与边缘保持距离。", "MEDIUM"
            return "前方有玻璃窗结构，按方向提示谨慎通行。", "LOW"
        if name_lc == "door_handle":
            return "门把手在该方向，可据此确认入口。", "LOW"
        if name_lc == "light_switch":
            return "附近有灯光开关，可作为门口位置参考。", "LOW"
        if name_lc == "potted plant":
            if distance_m <= 1.6 or risk_score >= 0.55:
                return "前方有盆栽占道，建议从侧边绕过，避免碰倒。", "MEDIUM"
            return "附近有盆栽，注意脚下并从侧边通过。", "LOW"
        if name_lc == "turnstile":
            if distance_m <= 1.6 or risk_score >= 0.56:
                return "前方是闸机通道，减速对准通道中央通过。", "MEDIUM"
            return "前方有闸机区域，沿通道方向继续前行。", "LOW"
        if name_lc in STAIR_SUPPORT_CLASSES and stair_context:
            side_zh = "左侧" if side == "left" else ("右侧" if side == "right" else "前方")
            if distance_m <= 1.8 or risk_score >= 0.52:
                if side == "left":
                    return "左侧有楼梯扶手，建议靠左握稳后再通过。", "MEDIUM"
                if side == "right":
                    return "右侧有楼梯扶手，建议靠右握稳后再通过。", "MEDIUM"
                return "前方有楼梯扶手，靠近后先扶稳再通过。", "MEDIUM"
            return f"{side_zh}有楼梯扶手，可沿扶手方向谨慎通行。", "LOW"
        if name_lc in STAIR_LIKE_CLASSES:
            if distance_m <= 1.2 or risk_score >= 0.72:
                return "前方台阶较近，先停一下，确认后再走。", "HIGH"
            if distance_m <= 2.8 or risk_score >= 0.45:
                return "注意台阶，放慢脚步，建议靠扶手通过。", "MEDIUM"
            return "前方可能有台阶，保持脚下探测并谨慎前行。", "LOW"
        if self._is_static_poster_like_person(
            name=name,
            distance_m=distance_m,
            motion_dir=motion_dir,
            support_factor=support_factor,
            speed_norm=speed_norm,
            approach_rate=approach_rate,
        ):
            return "疑似海报人像，先保持直行并持续观察。", "LOW"

        far_static_allowed = (
            name_lc not in DYNAMIC_CLASSES
            and name_lc not in STAIR_LIKE_CLASSES
            and name_lc not in STAIR_SUPPORT_CLASSES
            and name_lc not in {"glass_door", "glass_window", "door_handle", "light_switch", "turnstile"}
            and not str(motion_dir or "").startswith("approaching_")
            and float(distance_m) >= self.far_static_distance_m
            and float(risk_score) <= self.far_static_risk_max
        )
        if far_static_allowed:
            return f"前方远处有{_zh_name(name_lc)}，先保持直行并留意环境变化。", "LOW"

        if support_factor >= 0.75 and urgency in ("HIGH", "MEDIUM"):
            return "注意头部高度，稍微低头并从侧面绕行。", urgency
        if urgency == "HIGH":
            return "先停一下，注意避让。", urgency

        def _directional_action(preferred_side: str) -> Optional[str]:
            if preferred_side == "left":
                if "left" not in blocked:
                    return "从左侧绕开。"
                if "right" not in blocked:
                    return "从右侧绕开。"
                return None
            if preferred_side == "right":
                if "right" not in blocked:
                    return "从右侧绕开。"
                if "left" not in blocked:
                    return "从左侧绕开。"
                return None
            return None

        preferred_side = ""
        if motion_dir == "approaching_left":
            preferred_side = "right"
        elif motion_dir == "approaching_right":
            preferred_side = "left"
        elif side == "left":
            preferred_side = "right"
        elif side == "right":
            preferred_side = "left"
        if preferred_side:
            directional = _directional_action(preferred_side)
            if directional:
                return directional, urgency

        blocked_urgency = urgency if urgency in ("MEDIUM", "HIGH") else "MEDIUM"
        if "left" in blocked and "right" in blocked:
            return "前方两侧有停靠车辆占道，先停一下，确认可通行空隙后再通过。", blocked_urgency
        if "right" in blocked:
            return "右侧有停靠车辆占道，建议靠左减速通过。", blocked_urgency
        if "left" in blocked:
            return "左侧有停靠车辆占道，建议靠右减速通过。", blocked_urgency
        return "稍微向右侧避让。", urgency

    def _relations(self, objs: List[SemanticObject], w: int, h: int) -> List[SemanticObject]:
        if len(objs) < 2:
            return objs
        # 给 Top1 附加与 Top2/Top3 的方位关系 + 前后关系，避免三物体关系混乱
        a = objs[0]
        relations: List[str] = []
        for b in objs[1:3]:
            dx = a.center_x - b.center_x
            if abs(dx) > 0.18 * w:
                relations.append(f"{_zh_name(a.name)}在{_zh_name(b.name)}的{'左侧' if dx < 0 else '右侧'}")

            if a.bbox and b.bbox and _iou(a.bbox, b.bbox) >= self.occlusion_iou_thr:
                a_front = (a.area_ratio >= b.area_ratio * 1.08) or (a.center_y > b.center_y + 0.04 * h)
                if a_front:
                    relations.append(f"{_zh_name(a.name)}在{_zh_name(b.name)}前方")
                else:
                    relations.append(f"{_zh_name(a.name)}在{_zh_name(b.name)}后方")

        if relations:
            a.relations = relations[:2]
        return objs

    def _update_track_cache(self, items: List[Dict[str, Any]], now_ts: float):
        for o in items:
            name = self._normalize_object_name(str(o.get("name", "")))
            if not name:
                continue
            self._track_cache[name].append(
                {
                    "ts": now_ts,
                    "cx": float(o.get("center_x", 0.0) or 0.0),
                    "cy": float(o.get("center_y", 0.0) or 0.0),
                    "area_ratio": float(o.get("area_ratio", 0.0) or 0.0),
                }
            )
            self._track_cache[name] = self._track_cache[name][-8:]

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
        prepared: List[Dict[str, Any]] = []
        for o in raw_objects or []:
            raw_name = str(o.get("name", "")).strip()
            name = self._normalize_object_name(raw_name)
            if not name:
                continue
            conf = o.get("conf")
            try:
                conf_f = float(conf) if conf is not None else 0.5
            except Exception:
                conf_f = 0.5
            if conf_f < self.conf_threshold:
                continue
            prepared.append({**o, "name": name, "raw_name": raw_name, "conf": conf_f})

        glass_inferred = self._infer_glass_structure_candidates(prepared, frame_w, frame_h)
        if glass_inferred:
            prepared.extend(glass_inferred)

        names = [str(o.get("name", "")).strip().lower() for o in prepared]
        scene, scene_confidence = self.infer_scene_with_confidence(names, mean_luma=mean_luma)

        normalized_prepared: List[Dict[str, Any]] = []
        for o in prepared:
            mapped_name = self._normalize_scene_object_name(str(o.get("name", "")), scene)
            normalized_prepared.append({**o, "name": mapped_name})
        prepared = normalized_prepared

        scored = []
        for o in prepared:
            name = str(o.get("name", "")).strip()
            if not name:
                continue
            conf_f = float(o.get("conf", 0.5) or 0.5)
            ar = float(o.get("area_ratio", 0.0) or 0.0)
            score = self._compute_score(name, conf_f, ar, scene)
            scored.append({**o, "score": score, "risk_score": 0.0})

        scored = self._dedup_objects(scored)
        scored.sort(key=lambda x: float(x.get("score", 0.0)), reverse=True)
        stage1 = scored[: max(1, self.stage1_topk)]

        now_ts = time.time()
        candidates: List[Dict[str, Any]] = []
        for o in stage1:
            name = str(o.get("name", "")).strip()
            cx = float(o.get("center_x", frame_w / 2.0))
            cy = float(o.get("center_y", frame_h / 2.0))
            ar = float(o.get("area_ratio", 0.0) or 0.0)
            conf_f = float(o.get("conf", 0.5) or 0.5)
            bbox = list(o.get("bbox")) if isinstance(o.get("bbox"), (list, tuple)) and len(o.get("bbox")) == 4 else None

            speed_norm, approach_rate, motion_dir = self._estimate_motion_features(
                name=name, cx=cx, cy=cy, area_ratio=ar, now_ts=now_ts, frame_w=frame_w, frame_h=frame_h
            )
            dist_m = _estimate_distance_m(ar)
            candidates.append(
                {
                    **o,
                    "name": name,
                    "conf": conf_f,
                    "bbox": bbox,
                    "center_x": cx,
                    "center_y": cy,
                    "area_ratio": ar,
                    "distance_m": dist_m,
                    "speed_norm": speed_norm,
                    "approach_rate": approach_rate,
                    "motion_dir": motion_dir,
                }
            )

        for i, item in enumerate(candidates):
            item["occlusion_factor"] = self._estimate_occlusion_factor(i, candidates, frame_w, frame_h)

            factors = self._compute_risk_factors(
                name=str(item.get("name", "")),
                distance_m=float(item.get("distance_m", 0.0) or 0.0),
                speed_norm=float(item.get("speed_norm", 0.0) or 0.0),
                approach_rate=float(item.get("approach_rate", 0.0) or 0.0),
                bbox=(item.get("bbox") if isinstance(item.get("bbox"), list) else None),
                frame_h=frame_h,
                occlusion_factor=float(item.get("occlusion_factor", 0.0) or 0.0),
            )
            risk_score = self._risk_from_factors(factors)
            if (
                self._normalize_object_name(str(item.get("name", ""))) == "potted plant"
                and str(scene or "").strip().lower() in INDOOR_SCENES
            ):
                area_ratio = float(item.get("area_ratio", 0.0) or 0.0)
                risk_score = max(risk_score, 0.48 + min(0.22, max(0.0, area_ratio) * 2.4))
            if self._is_low_fence_candidate(item, frame_h):
                area_ratio = float(item.get("area_ratio", 0.0) or 0.0)
                risk_score = max(risk_score, self.low_fence_risk_floor + min(0.16, max(0.0, area_ratio) * 0.6))
            item["risk_factors"] = factors
            item["risk_score"] = risk_score

        blocked_sides = self._infer_parked_vehicle_blocked_sides(candidates, frame_w)
        for item in candidates:
            action, urgency = self._avoidance(
                name=str(item.get("name", "")),
                cx=float(item.get("center_x", frame_w / 2.0)),
                w=frame_w,
                distance_m=float(item.get("distance_m", 0.0) or 0.0),
                risk_score=float(item.get("risk_score", 0.0) or 0.0),
                motion_dir=str(item.get("motion_dir", "unknown")),
                support_factor=float((item.get("risk_factors") or {}).get("support", 0.0)),
                speed_norm=float(item.get("speed_norm", 0.0) or 0.0),
                approach_rate=float(item.get("approach_rate", 0.0) or 0.0),
                blocked_sides=blocked_sides,
            )
            item["urgency"] = urgency
            item["avoidance_action"] = action

        stage2 = sorted(
            candidates,
            key=lambda x: (float(x.get("risk_score", 0.0) or 0.0), float(x.get("score", 0.0) or 0.0)),
            reverse=True,
        )[: max(1, self.stage2_topk)]
        self._update_stair_hint_cache(stage2, now_ts)
        self._update_turnstile_hint_cache(stage2, now_ts)
        stage2 = self._maybe_inject_stair_hint(stage2, prepared, frame_w, frame_h, now_ts)
        stage2 = self._maybe_inject_turnstile_hint(stage2, prepared, frame_w, frame_h, now_ts, scene)
        stage2 = self._enhance_stair_handrail_context(stage2, candidates, frame_w)
        if any(self._normalize_object_name(str(x.get("name", ""))) in VERTICAL_STATIC_CLASSES for x in candidates):
            vertical_best = None
            for x in candidates:
                if self._normalize_object_name(str(x.get("name", ""))) not in VERTICAL_STATIC_CLASSES:
                    continue
                if vertical_best is None:
                    vertical_best = x
                    continue
                key_cur = (float(x.get("risk_score", 0.0) or 0.0), float(x.get("score", 0.0) or 0.0))
                key_best = (
                    float(vertical_best.get("risk_score", 0.0) or 0.0),
                    float(vertical_best.get("score", 0.0) or 0.0),
                )
                if key_cur > key_best:
                    vertical_best = x
            if vertical_best is not None and not any(
                self._normalize_object_name(str(o.get("name", ""))) in VERTICAL_STATIC_CLASSES for o in stage2
            ):
                stage2.append(dict(vertical_best))
        stage2 = sorted(
            stage2,
            key=lambda x: (float(x.get("risk_score", 0.0) or 0.0), float(x.get("score", 0.0) or 0.0)),
            reverse=True,
        )[: max(1, self.stage2_topk)]

        sem_objs: List[SemanticObject] = []
        for o in stage2:
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
            dist_m = float(o.get("distance_m", _estimate_distance_m(ar)) or 0.0)
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
                    urgency=str(o.get("urgency", "LOW")),
                    avoidance_action=str(o.get("avoidance_action", "稍微向右侧避让。")),
                    relations=[],
                    risk_score=float(o.get("risk_score", 0.0) or 0.0),
                    risk_factors=dict(o.get("risk_factors") or {}),
                    motion_dir=str(o.get("motion_dir", "unknown")),
                    speed_norm=float(o.get("speed_norm", 0.0) or 0.0),
                    frame_w=frame_w,
                    frame_h=frame_h,
                )
            )

        sem_objs = self._relations(sem_objs, frame_w, frame_h)
        sem_objs.sort(key=lambda x: (x.risk_score, x.score), reverse=True)

        topk = sem_objs[: max(1, self.output_topk)]
        topk = self._force_stair_handrail_topk(topk, sem_objs)
        topk = self._force_vertical_static_topk(topk, sem_objs)
        topk = self._force_roadside_obstacle_topk(topk, sem_objs)
        topk = self._force_low_fence_topk(topk, sem_objs)
        is_dynamic = any((o.name or "").strip().lower() in DYNAMIC_CLASSES and o.distance_m <= 3.0 for o in topk)
        if imu_yaw_rate_dps is not None and abs(float(imu_yaw_rate_dps)) >= self.turn_rate_thr_dps:
            is_dynamic = True

        self._update_track_cache(stage1, now_ts)

        return {
            "scene": scene,
            "scene_confidence": scene_confidence,
            "is_dynamic": is_dynamic,
            "objects": topk,
            "pipeline": {
                "raw": len(raw_objects or []),
                "conf_filtered": len(prepared),
                "stage1": len(stage1),
                "stage2": len(stage2),
                "output": len(topk),
                "conf_threshold": self.conf_threshold,
            },
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
                dist_txt = f"{max(1, steps)}步"
            else:
                meters_i = max(1, int(round(float(o.distance_m))))
                dist_txt = f"{meters_i}米"
            ur = urgency_word.get(o.urgency, "注意")
            prefix = f"{ur}，" if ur else ""
            action = (o.avoidance_action or "").rstrip("。")
            direction = f"{o.clock}点方向({o.lr_zh})"
            scene_prefix = f"{scene_zh}，" if scene_zh else ""
            sentence = f"{prefix}{scene_prefix}{direction}约{dist_txt}有{_zh_name(o.name)}，{action}"
            has_stair = any(self._is_stair_like_name(str(obj.name)) for obj in objs)
            support_obj = next(
                (obj for obj in objs if self._is_stair_support_name(str(obj.name))),
                None,
            )
            if has_stair and support_obj is not None and "扶手" not in sentence:
                support_side = support_obj.lr_zh or "前方"
                sentence += f"，{support_side}有扶手可辅助通行"
            return sentence

        # 稳定环境：先整体（场景），再关键点
        prefix = "前方环境还算稳定。"
        if scene_zh:
            prefix = f"{scene_zh}，"

        parts = []
        for o in objs[:3]:
            # 距离描述（支持米或步数）
            if use_steps:
                steps = int(round(o.distance_m / 0.6))
                dist_txt = f"{max(1, steps)}步"
            else:
                meters_i = max(1, int(round(float(o.distance_m))))
                dist_txt = f"{meters_i}米"

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
            has_high = any((getattr(o, "urgency", "LOW") == "HIGH") for o in (sem.get("objects") or []))
            if not has_high:
                should_speak = False

        scene = sem.get("scene", "unknown")
        scene_confidence = float(sem.get("scene_confidence", 0.5) or 0.5)
        pipeline = dict(sem.get("pipeline") or {})

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
            use_numbered = os.getenv("AIGLASS_STRUCTURED_NUMBERED", "1") == "1"
            text = svo.render_text_numbered(use_steps=use_steps) if use_numbered else svo.render_text(use_steps=use_steps)
            svo.text = text

            out = svo.to_dict()
            sem_objects = list(sem.get("objects") or [])
            for idx, obj in enumerate(out.get("objects") or []):
                if idx >= len(sem_objects):
                    break
                so = sem_objects[idx]
                obj["risk_score"] = float(getattr(so, "risk_score", 0.0) or 0.0)
                obj["risk_factors"] = dict(getattr(so, "risk_factors", {}) or {})
                obj["motion_dir"] = str(getattr(so, "motion_dir", "unknown") or "unknown")
                obj["speed_norm"] = float(getattr(so, "speed_norm", 0.0) or 0.0)
            out["text"] = text
            out["should_speak"] = should_speak
            out["priority"] = svo.priority
            out["use_steps"] = use_steps
            out["pipeline"] = pipeline
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
                "pipeline": pipeline,
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
            "pipeline": pipeline,
        }


_engine: Optional[SemanticOutputEngine] = None


def get_semantic_engine() -> SemanticOutputEngine:
    global _engine
    if _engine is None:
        _engine = SemanticOutputEngine()
    return _engine
