# -*- coding: utf-8 -*-
"""
结构化语音输出模块（Phase 1 核心）

实现统一的语音播报格式：
[场景前缀] + [方向] + [距离] + [物体] + [危险等级] + [行动建议]

输出数据结构（schema_version=2）：
{
    "schema_version": 2,
    "timestamp": float,
    "scene": str,              # 场景类型
    "scene_confidence": float, # 场景置信度
    "objects": [...],          # 物体列表
    "text": str,               # 自然语言描述
    "should_speak": bool,      # 是否应该播报
    "priority": int            # 播���优先级
}
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum


_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
_FRAGMENTS_CACHE: Optional[Dict[str, Any]] = None
_TEMPLATES_CACHE: Optional[Dict[str, Any]] = None


def _load_json(path: str) -> Optional[Dict[str, Any]]:
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _load_fragments() -> Optional[Dict[str, Any]]:
    global _FRAGMENTS_CACHE
    if _FRAGMENTS_CACHE is not None:
        return _FRAGMENTS_CACHE
    path = os.getenv("AIGLASS_VOICE_FRAGMENTS", os.path.join(_REPO_ROOT, "voice", "fragments.json"))
    _FRAGMENTS_CACHE = _load_json(path) or {}
    return _FRAGMENTS_CACHE


def _load_templates() -> Optional[Dict[str, Any]]:
    global _TEMPLATES_CACHE
    if _TEMPLATES_CACHE is not None:
        return _TEMPLATES_CACHE
    path = os.getenv("AIGLASS_VOICE_TEMPLATES", os.path.join(_REPO_ROOT, "voice", "templates.json"))
    _TEMPLATES_CACHE = _load_json(path) or {}
    return _TEMPLATES_CACHE


# ==================== 枚举定义 ====================

class UrgencyLevel(Enum):
    """危险等级"""
    HIGH = "HIGH"       # 紧急危险 - 立即播报
    MEDIUM = "MEDIUM"   # 一般障碍 - 需要注意
    LOW = "LOW"         # 安全环境 - 定期更新


class ActionType(Enum):
    """行动类型"""
    STOP = "stop"           # 停下
    AVOID = "avoid"         # 避让
    CONTINUE = "continue"   # 继续前进
    WARNING = "warning"     # 警告


class DirectionType(Enum):
    """方向类型"""
    CLOCK = "clock"     # 钟点方向 (1-12)
    LR = "lr"           # 左中右 (left/center/right)


class DistanceType(Enum):
    """距离类型"""
    METERS = "meters"   # 米
    STEPS = "steps"     # 步数


# ==================== 场景定义 ====================

class SceneType(Enum):
    """场景类型（全场景覆盖）"""
    # 交通场景
    STREET = "street"                 # 街道
    SIDEWALK = "sidewalk"             # 人行道
    CROSSROAD = "crossroad"           # 十字路口
    CROSSWALK = "crosswalk"           # 斑马线
    TRAFFIC_LIGHT = "traffic_light"   # 红绿灯
    BUS_STOP = "bus_stop"             # 公交站
    SUBWAY = "subway"                 # 地铁站

    # 建筑场景
    HOSPITAL = "hospital"             # 医院
    SUPERMARKET = "supermarket"       # 超市
    MALL = "mall"                     # 商场
    OFFICE = "office"                 # 办公楼
    SCHOOL = "school"                 # 学校
    BANK = "bank"                     # 银行
    RESTAURANT = "restaurant"         # 餐厅

    # 室内场景
    ELEVATOR = "elevator"             # 电梯
    STAIRS = "stairs"                 # 楼梯
    CORRIDOR = "corridor"             # 走廊
    LOBBY = "lobby"                   # 大厅
    ROOM = "room"                     # 房间
    RESTROOM = "restroom"             # 卫生间

    # 自然环境
    PARK = "park"                     # 公园
    SQUARE = "square"                 # 广场
    LAWN = "lawn"                     # 草坪
    FLOWERBED = "flowerbed"           # 花坛
    POND = "pond"                     # 水池

    # 特殊场景
    CONSTRUCTION = "construction"     # 施工区域
    UNDERPASS = "underpass"           # 地下通道
    BRIDGE = "bridge"                 # 天桥
    PARKING = "parking"               # 停车场

    # 室内/户外通用
    INDOOR = "indoor"                 # 室内（默认）
    OUTDOOR = "outdoor"               # 户外（默认）
    UNKNOWN = "unknown"               # 未知


# 场景中文映射
SCENE_ZH_MAP = {
    SceneType.STREET: "街道环境",
    SceneType.SIDEWALK: "人行道上",
    SceneType.CROSSROAD: "十字路口",
    SceneType.CROSSWALK: "斑马线",
    SceneType.TRAFFIC_LIGHT: "红绿灯前",
    SceneType.BUS_STOP: "公交车站",
    SceneType.SUBWAY: "地铁站",
    SceneType.HOSPITAL: "医院环境",
    SceneType.SUPERMARKET: "超市通道",
    SceneType.MALL: "商场内",
    SceneType.OFFICE: "办公楼",
    SceneType.SCHOOL: "学校",
    SceneType.BANK: "银行",
    SceneType.RESTAURANT: "餐厅",
    SceneType.ELEVATOR: "电梯里",
    SceneType.STAIRS: "楼梯上",
    SceneType.CORRIDOR: "走廊",
    SceneType.LOBBY: "大厅",
    SceneType.ROOM: "房间内",
    SceneType.RESTROOM: "卫生间",
    SceneType.PARK: "公园里",
    SceneType.SQUARE: "广场上",
    SceneType.LAWN: "草坪上",
    SceneType.FLOWERBED: "花坛旁",
    SceneType.POND: "水池边",
    SceneType.CONSTRUCTION: "施工区域",
    SceneType.UNDERPASS: "地下通道",
    SceneType.BRIDGE: "天桥上",
    SceneType.PARKING: "停车场",
    SceneType.INDOOR: "室内环境",
    SceneType.OUTDOOR: "户外环境",
    SceneType.UNKNOWN: "",
}


# 场景特征关键词（用于场景识别）
SCENE_KEYWORDS = {
    # 交通场景
    SceneType.STREET: [
        "street", "road", "lane", "car", "bus", "truck", "bicycle",
        "motorcycle", "traffic light", "crosswalk", "zebra crossing"
    ],
    SceneType.SIDEWALK: [
        "sidewalk", "pedestrian", "curb", "crossing", "bench", "pole"
    ],
    SceneType.CROSSROAD: [
        "intersection", "crossroad", "crosswalk", "traffic light", "stop line"
    ],
    SceneType.CROSSWALK: [
        "crosswalk", "zebra crossing", "zebra"
    ],
    SceneType.TRAFFIC_LIGHT: [
        "traffic light", "signal", "red light", "green light", "yellow light"
    ],
    SceneType.BUS_STOP: [
        "bus stop", "bus stop sign", "bus shelter", "bus station"
    ],
    SceneType.SUBWAY: [
        "subway", "metro", "turnstile", "ticket machine", "fare gate",
        "platform", "line sign", "metro train"
    ],

    # 建筑场景
    SceneType.HOSPITAL: [
        "hospital bed", "wheelchair", "iv drip", "doctor", "nurse",
        "gurney", "stretcher", "medical", "hospital", "clinic"
    ],
    SceneType.SUPERMARKET: [
        "shelf", "shopping cart", "aisle", "checkout", "product",
        "grocery", "price tag", "supermarket", "cart"
    ],
    SceneType.MALL: [
        "escalator", "mannequin", "storefront", "display", "mall",
        "brand", "fashion"
    ],
    SceneType.OFFICE: [
        "office", "desk", "computer", "printer", "conference", "cubicle"
    ],
    SceneType.SCHOOL: [
        "school", "classroom", "student", "blackboard", "desk", "campus"
    ],
    SceneType.BANK: [
        "counter", "atm", "queue", "bank", "teller", "vault"
    ],
    SceneType.RESTAURANT: [
        "table", "chair", "counter", "menu", "waiter", "dining", "restaurant"
    ],

    # 室内场景
    SceneType.ELEVATOR: [
        "elevator", "lift", "button panel", "floor button", "call button"
    ],
    SceneType.STAIRS: [
        "stairs", "staircase", "handrail", "steps", "stair"
    ],
    SceneType.CORRIDOR: [
        "corridor", "hallway", "door", "room number", "exit sign"
    ],
    SceneType.LOBBY: [
        "lobby", "reception", "info desk"
    ],
    SceneType.ROOM: [
        "room", "bed", "sofa", "tv", "table"
    ],
    SceneType.RESTROOM: [
        "restroom", "toilet", "sink", "mirror", "hand dryer"
    ],

    # 自然环境
    SceneType.PARK: [
        "tree", "bench", "grass", "path", "park", "garden"
    ],
    SceneType.SQUARE: [
        "square", "plaza", "fountain", "statue", "open area"
    ],
    SceneType.LAWN: [
        "lawn", "grass", "green"
    ],
    SceneType.FLOWERBED: [
        "flower bed", "flower", "flowerbed"
    ],
    SceneType.POND: [
        "pond", "water", "fountain", "lake"
    ],

    # 特殊场景
    SceneType.CONSTRUCTION: [
        "cone", "barrier", "fence", "construction", "warning sign",
        "safety vest", "hard hat"
    ],
    SceneType.UNDERPASS: [
        "underpass", "tunnel", "passage", "dark", "stairs"
    ],
    SceneType.BRIDGE: [
        "bridge", "overpass", "railing", "handrail"
    ],
    SceneType.PARKING: [
        "parking meter", "car", "parking lot", "vehicle"
    ],
}


# ==================== 物体信息结构 ====================

@dataclass
class DirectionInfo:
    """方向信息"""
    clock: int              # 钟点方向 (1-12)
    clock_zh: str           # 中文描述（左前方、右前方等）
    lr: str                 # 左中右 (left/center/right)
    lr_zh: str              # 中文描述（左侧、前方、右侧）

    def to_dict(self) -> Dict[str, Any]:
        return {
            "clock": self.clock,
            "clock_zh": self.clock_zh,
            "lr": self.lr,
            "lr_zh": self.lr_zh,
        }


@dataclass
class DistanceInfo:
    """距离信息"""
    meters: float          # 米
    steps: int             # 步数

    def to_dict(self) -> Dict[str, Any]:
        return {
            "meters": self.meters,
            "steps": self.steps,
        }

    def format(self, use_steps: Optional[bool] = None) -> str:
        """格式化距离描述"""
        if use_steps is None:
            use_steps = os.getenv("AIGLASS_DISTANCE_FORMAT", "steps").lower() == "steps"

        frags = _load_fragments() or {}
        dist_frags = (frags.get("distance") or {}) if isinstance(frags, dict) else {}

        if use_steps:
            steps = max(1, int(self.steps))
            step_map = dist_frags.get("steps") if isinstance(dist_frags, dict) else {}
            step_txt = step_map.get(str(min(steps, 10))) if isinstance(step_map, dict) else None
            if step_txt:
                return f"约{step_txt}" if not str(step_txt).startswith("约") else str(step_txt)
            return f"约{steps}步"

        meters = float(self.meters)
        meter_map = dist_frags.get("meters") if isinstance(dist_frags, dict) else {}
        if isinstance(meter_map, dict):
            key = str(int(round(meters)))
            if key in meter_map:
                return str(meter_map[key])
        if meters >= 1.0:
            return f"{meters:.0f}米"
        return f"{meters:.1f}米"


@dataclass
class StructuredObject:
    """结构化物体信息"""
    id: int
    name: str                # 英文名称
    name_zh: str             # 中文名称
    conf: float              # 置信度

    # 方向信息
    direction: DirectionInfo

    # 距离信息
    distance: DistanceInfo

    # 危险评估
    urgency: UrgencyLevel
    is_moving: bool
    is_approaching: bool

    # 行动建议
    action: str              # 行动描述
    action_type: ActionType

    # 关系信息
    relations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "name_zh": self.name_zh,
            "conf": self.conf,
            "direction": self.direction.to_dict(),
            "distance": self.distance.to_dict(),
            "urgency": self.urgency.value,
            "is_moving": self.is_moving,
            "is_approaching": self.is_approaching,
            "action": self.action,
            "action_type": self.action_type.value,
            "relations": self.relations,
        }


# ==================== 语音模板 ====================

class VoiceTemplate:
    """语音播报模板"""

    # 危险场景模板（HIGH优先级）
    HIGH_TEMPLATES = [
        "紧急，{clock}点方向{distance}有{object}，先停下",
        "注意，{lr_zh}{distance}有{object}靠近",
        "危险，前方{distance}有{object}",
    ]

    # 一般障碍模板（MEDIUM优先级）
    MEDIUM_TEMPLATES = [
        "{scene_prefix}{lr_zh}{distance}有{object}，{action}",
        "{clock}点方向{distance}有{object}，{action}",
        "注意{lr_zh}{distance}有{object}",
    ]

    # 安全环境模板（LOW优先级）
    LOW_TEMPLATES = [
        "{scene_prefix}{lr_zh}{distance}有{object}",
        "前方{lr_zh}{distance}是{object}",
    ]

    @classmethod
    def _get_templates(cls) -> Dict[str, List[str]]:
        t = _load_templates()
        if isinstance(t, dict) and t:
            out: Dict[str, List[str]] = {}
            for k, v in t.items():
                if isinstance(v, list) and v:
                    out[str(k).upper()] = [str(x) for x in v if str(x).strip()]
            if out:
                return out
        return {
            "HIGH": cls.HIGH_TEMPLATES,
            "MEDIUM": cls.MEDIUM_TEMPLATES,
            "LOW": cls.LOW_TEMPLATES,
        }

    @classmethod
    def get_template(cls, urgency: UrgencyLevel, index: int = 0) -> str:
        """获取对应危险等级的模板"""
        key = urgency.value if isinstance(urgency, UrgencyLevel) else str(urgency)
        templates = cls._get_templates().get(str(key).upper()) or cls.LOW_TEMPLATES
        return templates[index % max(1, len(templates))]

    @classmethod
    def render(cls, obj: StructuredObject, scene_zh: str = "",
               index: int = 0, use_steps: bool = True) -> str:
        """渲染模板"""
        urgency = obj.urgency
        template = cls.get_template(urgency, index)

        # 格式化距离（优先使用步数）
        distance_str = obj.distance.format(use_steps=use_steps)

        scene_prefix = f"{scene_zh}，" if scene_zh else ""
        return template.format(
            scene_zh=scene_zh,
            scene_prefix=scene_prefix,
            clock=obj.direction.clock,
            clock_zh=obj.direction.clock_zh,
            lr=obj.direction.lr,
            lr_zh=obj.direction.lr_zh,
            distance=distance_str,
            object=obj.name_zh,
            action=obj.action.rstrip("。"),
        )


# ==================== 工具函数 ====================

def _parse_front_clock_hours(raw: str) -> List[int]:
    out: List[int] = []
    for token in str(raw or "").split(","):
        token = token.strip()
        if not token:
            continue
        try:
            v = int(token)
        except Exception:
            continue
        if 1 <= v <= 12:
            out.append(v)
    return out


def calculate_clock_dir(cx: float, cy: float, w: int, h: int) -> int:
    """
    计算钟点方向。

    默认使用“前视扇区映射”（front_arc）：
    - 只根据水平方向映射，避免把画面下方误解为 5/6/7 点（相机无法看到身后）
    - 默认输出范围：10/11/12/1/2

    可通过环境变量切换到历史 360 映射：
    - AIGLASS_CLOCK_MAPPING=full_360
    """
    mode = os.getenv("AIGLASS_CLOCK_MAPPING", "front_arc").strip().lower()
    if mode in ("full_360", "full360", "full", "legacy", "polar"):
        dx = cx - (w / 2.0)
        dy = cy - (h / 2.0)
        ang = math.atan2(dx, -dy)  # 以"向上"为 0，顺时针为正
        hour = int(round((ang / (2 * math.pi)) * 12)) % 12
        return 12 if hour == 0 else hour

    hours = _parse_front_clock_hours(os.getenv("AIGLASS_FRONT_CLOCK_HOURS", "10,11,12,1,2"))
    if len(hours) < 2:
        hours = [10, 11, 12, 1, 2]

    x_ratio = float(cx) / max(1.0, float(w))
    x_ratio = max(0.0, min(1.0, x_ratio))

    # 某些前置相机或推流链路会左右镜像，提供可选矫正开关
    if os.getenv("AIGLASS_CLOCK_FLIP_LR", "0") == "1":
        x_ratio = 1.0 - x_ratio

    idx = int(x_ratio * len(hours))
    if idx >= len(hours):
        idx = len(hours) - 1
    return int(hours[idx])


def calculate_lr_dir(cx: float, w: int) -> str:
    """计算左中右方向"""
    x_ratio = cx / max(1.0, float(w))
    if x_ratio < 0.4:
        return "left"
    elif x_ratio > 0.6:
        return "right"
    else:
        return "center"


def clock_to_zh(hour: int) -> str:
    """钟点方向转中文"""
    clock_zh_map = {
        12: "正前方", 1: "右前方", 2: "右前方", 3: "右前方",
        4: "右侧", 5: "右侧", 6: "正下方",
        7: "左侧", 8: "左侧", 9: "左前方",
        10: "左前方", 11: "左前方"
    }
    return clock_zh_map.get(hour, "正前方")


def lr_to_zh(lr: str) -> str:
    """左中右转中文"""
    return {"left": "左侧", "center": "前方", "right": "右侧"}.get(lr, "前方")


def estimate_distance_m(area_ratio: float) -> float:
    """基于面积比例估计距离（米）"""
    ar = max(1e-6, float(area_ratio))
    d = 1.2 / math.sqrt(ar)
    return float(max(0.6, min(8.0, d)))


def distance_to_steps(distance_m: float, step_length: float = 0.6) -> int:
    """将距离转换为步数"""
    return max(1, int(round(distance_m / step_length)))


# ==================== 核心输出结构 ====================

@dataclass
class StructuredVoiceOutput:
    """结构化语音输出（schema_version=2）"""
    schema_version: int = 2
    timestamp: float = 0.0
    scene: SceneType = SceneType.UNKNOWN
    scene_confidence: float = 0.0
    objects: List[StructuredObject] = field(default_factory=list)
    text: str = ""
    should_speak: bool = True
    priority: int = 50

    # 元数据
    is_dynamic: bool = False
    jump_count: int = 0
    imu_data: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.timestamp == 0.0:
            import time
            self.timestamp = time.time()

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于序列化和播报）"""
        return {
            "schema_version": self.schema_version,
            "timestamp": self.timestamp,
            "scene": self.scene.value,
            "scene_confidence": self.scene_confidence,
            "scene_zh": SCENE_ZH_MAP.get(self.scene, ""),
            "objects": [obj.to_dict() for obj in self.objects],
            "text": self.text,
            "should_speak": self.should_speak,
            "priority": self.priority,
            "is_dynamic": self.is_dynamic,
            "jump_count": self.jump_count,
            "imu": self.imu_data,
        }

    def render_text(self, use_steps: bool = True) -> str:
        """生成自然语言描述"""
        if not self.objects:
            return "我没看到明显的关键障碍，前方看起来比较空。"

        scene_zh = SCENE_ZH_MAP.get(self.scene, "")
        obj = self.objects[0]

        # 使用模板渲染
        self.text = VoiceTemplate.render(obj, scene_zh, use_steps=use_steps)

        # 添加关系描述
        if obj.relations:
            self.text += f"。另外，{obj.relations[0]}。"
        else:
            self.text += "。"

        return self.text

    def render_text_numbered(self, use_steps: bool = True) -> str:
        """
        生成编号列表格式的播报（不使用 emoji）

        格式：第一、{clock}点方向{distance}处为{name}，{state_description}
               第二、{clock}点方向{distance}处为{name}，{state_description}

        示例：
        第一、12点方向1米处为斑马线，现在是绿灯可以通行
        第二、3点方向2米处有人，注意避让避免碰撞
        """
        if not self.objects:
            return "当前视野内没有检测到重要物体。"

        scene_zh = SCENE_ZH_MAP.get(self.scene, "")

        # 编号列表
        number_words = ["第一", "第二", "第三", "第四", "第五"]

        parts = []
        for idx, obj in enumerate(self.objects[:5]):  # 最多5个
            num_word = number_words[min(idx, 4)]

            # 距离描述
            if use_steps:
                steps = max(1, int(round(obj.distance.steps)))
                if steps <= 10:
                    dist_txt = f"{steps}步"
                else:
                    dist_txt = f"{obj.distance.meters:.0f}米"
            else:
                meters = obj.distance.meters
                dist_txt = f"{meters:.0f}米" if meters >= 1 else f"{meters:.1f}米"

            # 方向描述
            direction = f"{obj.direction.clock}点方向"

            # 物体名称
            name = obj.name_zh

            # 特殊状态描述
            state_desc = self._get_state_description(obj)

            parts.append(f"{num_word}、{direction}{dist_txt}处为{name}，{state_desc}")

        # 组合输出
        if scene_zh:
            return f"{scene_zh}。" + "；".join(parts) + "。"
        return "；".join(parts) + "。"

    def _get_state_description(self, obj: StructuredObject) -> str:
        """获取特殊状态描述（红绿灯状态、行人避让等）"""
        name = obj.name.lower()

        # 红绿灯状态
        if "traffic light" in name or "红绿灯" in name:
            # 这里可以配合 trafficlight_detection.py 获取实际状态
            # 暂时返回通用描述
            return "请注意交通信号"

        # 斑马线
        if "crosswalk" in name or "斑马线" in name:
            return "可以通过"

        # 行人避让
        if obj.urgency == UrgencyLevel.HIGH:
            return "注意避让避免碰撞"
        elif obj.urgency == UrgencyLevel.MEDIUM:
            return "请从侧面绕开"
        else:
            return "注意保持距离"

    @classmethod
    def from_raw_objects(
        cls,
        raw_objects: List[Dict[str, Any]],
        frame_w: int,
        frame_h: int,
        scene: SceneType = SceneType.UNKNOWN,
        scene_confidence: float = 0.5,
        imu_yaw_rate_dps: Optional[float] = None,
    ) -> "StructuredVoiceOutput":
        """从原始检测物体创建结构化输出"""
        import time

        output = cls(
            scene=scene,
            scene_confidence=scene_confidence,
        )

        # 处理每个物体
        for i, raw_obj in enumerate(raw_objects[:3]):  # Top-3
            name = str(raw_obj.get("name", "object")).strip()
            conf = float(raw_obj.get("conf", 0.5))
            cx = float(raw_obj.get("center_x", frame_w / 2.0))
            cy = float(raw_obj.get("center_y", frame_h / 2.0))
            ar = float(raw_obj.get("area_ratio", 0.01))

            # 计算方向
            clock = calculate_clock_dir(cx, cy, frame_w, frame_h)
            lr = calculate_lr_dir(cx, frame_w)

            # 计算距离
            meters = estimate_distance_m(ar)
            steps = distance_to_steps(meters)

            # 判断危险等级
            is_dynamic = name.lower() in ["person", "car", "bus", "truck", "bicycle", "motorcycle"]
            is_close = meters <= 2.0

            if is_dynamic and is_close:
                urgency = UrgencyLevel.HIGH
                action = "先停一下，注意避让"
                action_type = ActionType.STOP
            elif meters <= 1.5:
                urgency = UrgencyLevel.MEDIUM
                action = "从右侧绕开" if lr == "left" else "从左侧绕开"
                action_type = ActionType.AVOID
            else:
                urgency = UrgencyLevel.LOW
                action = "保持直行"
                action_type = ActionType.CONTINUE

            output.objects.append(StructuredObject(
                id=i + 1,
                name=name,
                name_zh=NAME_ZH.get(name.lower(), name),
                conf=conf,
                direction=DirectionInfo(
                    clock=clock,
                    clock_zh=clock_to_zh(clock),
                    lr=lr,
                    lr_zh=lr_to_zh(lr),
                ),
                distance=DistanceInfo(
                    meters=meters,
                    steps=steps,
                ),
                urgency=urgency,
                is_moving=is_dynamic,
                is_approaching=False,
                action=action,
                action_type=action_type,
            ))

        # 渲染文本
        output.render_text()

        # 设置优先级
        output.priority = 100 if any(o.urgency == UrgencyLevel.HIGH for o in output.objects) else 50

        return output


# 中文名称映射
NAME_ZH = {
    "person": "人", "people": "人",
    "car": "汽车", "bus": "公交车", "truck": "卡车",
    "bicycle": "自行车", "motorcycle": "摩托车", "scooter": "电动车",
    "stroller": "婴儿车", "dog": "狗", "cat": "猫", "animal": "动物",
    "taxi": "出租车", "police car": "警车", "ambulance": "救护车",
    "train": "列车", "subway train": "地铁列车",
    "traffic light": "红绿灯", "crosswalk": "斑马线",
    "stop sign": "停止标志", "parking meter": "停车计时器", "fire hydrant": "消防栓",
    "pole": "杆子", "post": "柱子", "column": "柱子", "pillar": "柱子", "stanchion": "隔离柱",
    "bench": "长椅", "chair": "椅子",
    "potted plant": "盆栽", "hydrant": "消防栓",
    "cone": "锥桶", "barrier": "路障", "fence": "围栏", "stone": "石头", "box": "箱子",
    "bollard": "路桩", "utility pole": "电线杆", "telegraph pole": "电线杆",
    "light pole": "路灯杆", "street pole": "路灯杆", "support post": "支撑杆", "vertical post": "立柱",
    "stairs": "楼梯", "stair": "楼梯",
    "elevator": "电梯", "escalator": "扶梯",
    "handrail": "扶手", "railing": "栏杆",
    "door": "门", "window": "窗户",
    "wheelchair": "轮椅", "stretcher": "担架",
    "doctor": "医生", "nurse": "护士",
    "shelf": "货架", "cart": "购物车", "shopping cart": "购物车",
    "checkout": "收银台", "counter": "柜台", "cashier": "收银员",
    "table": "桌子", "sofa": "沙发", "couch": "长沙发", "bed": "床", "desk": "书桌",
    "tv": "电视", "monitor": "显示器", "laptop": "笔记本电脑", "computer": "电脑",
    "backpack": "背包", "handbag": "手提包", "suitcase": "行李箱", "umbrella": "雨伞",
    "cell phone": "手机", "cup": "杯子", "bottle": "瓶子",
    "atm": "取款机", "turnstile": "闸机", "ticket machine": "售票机",
    "ticket gate": "闸机", "fare gate": "闸机", "platform": "站台",
    "bus stop": "公交站", "bus stop sign": "公交站牌", "bus shelter": "公交站亭",
    "sign": "指示牌", "signpost": "指示牌",
    "lamp": "灯", "light": "灯",
}


# ==================== 便捷函数 ====================

def create_structured_output(
    raw_objects: List[Dict[str, Any]],
    frame_w: int,
    frame_h: int,
    scene: str = "unknown",
    **kwargs
) -> StructuredVoiceOutput:
    """创建结构化输出的便捷函数"""
    scene_enum = SceneType.UNKNOWN
    if scene:
        try:
            scene_enum = SceneType(scene)
        except ValueError:
            pass

    return StructuredVoiceOutput.from_raw_objects(
        raw_objects=raw_objects,
        frame_w=frame_w,
        frame_h=frame_h,
        scene=scene_enum,
        **kwargs
    )


def infer_scene_from_objects(
    raw_objects: List[Dict[str, Any]],
    mean_luma: Optional[float] = None
) -> Tuple[SceneType, float]:
    """从检测物体推断场景类型"""
    names = [str(o.get("name", "")).lower() for o in raw_objects]
    name_set = set(names)

    # 检查每个场景的关键词
    scores = {}
    for scene, keywords in SCENE_KEYWORDS.items():
        score = sum(1 for kw in keywords if any(kw in name for name in names))
        if score > 0:
            scores[scene] = score

    if not scores:
        # 默认判断
        if name_set & {"car", "bus", "truck", "traffic light", "crosswalk"}:
            return SceneType.STREET, 0.6
        if name_set & {"chair", "table", "sofa", "bed", "tv"}:
            return SceneType.INDOOR, 0.6
        if mean_luma is not None and mean_luma < 70:
            return SceneType.INDOOR, 0.5
        return SceneType.UNKNOWN, 0.3

    # 返回得分最高的场景
    best_scene = max(scores, key=scores.get)
    confidence = min(0.9, 0.5 + scores[best_scene] * 0.1)
    return best_scene, confidence


# 导出
__all__ = [
    "StructuredVoiceOutput",
    "StructuredObject",
    "DirectionInfo",
    "DistanceInfo",
    "VoiceTemplate",
    "SceneType",
    "UrgencyLevel",
    "ActionType",
    "create_structured_output",
    "infer_scene_from_objects",
]
