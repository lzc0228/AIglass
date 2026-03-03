# -*- coding: utf-8 -*-
"""
文本生成器模块

实现三种输出模式的文本生成器：
1. 关键词模式（Keyword）：极简输出，仅物体名称
2. 短句模式（Phrase）：平衡输出，方向+距离+物体+建议
3. 段落模式（Paragraph）：详细输出，完整场景描述

设计模式：策略模式 + 工厂模式
- 每种模式封装为独立的生成器类
- 通过工厂函数统一创建生成器
- 易于扩展新的文本生成方式
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from output_mode_strategy import OutputMode


@dataclass
class SemanticObject:
    """语义对象数据类"""
    name: str
    name_zh: str
    clock: int
    clock_zh: str
    lr: str
    lr_zh: str
    distance_m: float
    urgency: str
    avoidance_action: str
    relations: List[str] = None

    def __post_init__(self):
        if self.relations is None:
            self.relations = []


# 物体名称中文映射（从 semantic_output.py 同步）
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
    "cat": "猫",
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
    "traffic light": "红绿灯",
    "crosswalk": "斑马线",
    "stairs": "楼梯",
    "stair": "楼梯",
    "handrail": "扶手",
    "elevator": "电梯",
    "escalator": "扶梯",
    "door": "门",
    "window": "窗户",
    "bed": "床",
    "table": "桌子",
    "desk": "书桌",
    "sofa": "沙发",
    "couch": "长沙发",
    "tv": "电视",
    "monitor": "显示器",
    "laptop": "笔记本电脑",
    "computer": "电脑",
    "backpack": "背包",
    "handbag": "手提包",
    "suitcase": "行李箱",
    "umbrella": "雨伞",
    "cell phone": "手机",
    "cup": "杯子",
    "bottle": "瓶子",
}

# 场景中文映射
SCENE_ZH_MAP = {
    "street": "街道环境",
    "sidewalk": "人行道上",
    "crossroad": "十字路口",
    "crosswalk": "斑马线",
    "traffic_light": "红绿灯前",
    "hospital": "医院环境",
    "supermarket": "超市通道",
    "mall": "商场内",
    "office": "办公楼",
    "school": "学校",
    "bank": "银行",
    "restaurant": "餐厅",
    "elevator": "电梯里",
    "stairs": "楼梯上",
    "corridor": "走廊",
    "room": "房间内",
    "restroom": "卫生间",
    "park": "公园里",
    "indoor": "室内环境",
    "outdoor": "户外环境",
}


def _zh_name(name: str) -> str:
    """获取物体中文名称"""
    if not name:
        return "物体"
    k = name.strip().lower()
    return NAME_ZH.get(k, name)


def _scene_zh(scene: str) -> str:
    """获取场景中文名称"""
    if not scene:
        return ""
    return SCENE_ZH_MAP.get(scene, "")


class TextGenerator(ABC):
    """文本生成器基类"""

    @abstractmethod
    def generate(self, objects: List[SemanticObject], scene: str) -> str:
        """
        生成播报文本

        Args:
            objects: 语义对象列表
            scene: 场景类型

        Returns:
            生成的播报文本
        """
        pass


class KeywordTextGenerator(TextGenerator):
    """
    关键词模式生成器

    输出格式：仅物体中文名称，用逗号分隔
    示例："人，汽车，柱子"
    """

    def generate(self, objects: List[SemanticObject], scene: str) -> str:
        if not objects:
            return "前方安全"

        # 只取前3个物体
        names = [_zh_name(o.name) for o in objects[:3]]
        return "，".join(names)


class PhraseTextGenerator(TextGenerator):
    """
    短句模式生成器

    输出格式：[紧急度]，[方向][距离]有[物体]，[建议]
    示例："5点方向约4步有床，从左侧绕开"
    """

    def generate(self, objects: List[SemanticObject], scene: str) -> str:
        if not objects:
            return "前方安全"

        # 只描述第一个（最重要的）物体
        top = objects[0]

        # 距离描述（使用步数）
        steps = int(round(top.distance_m / 0.6))
        dist_txt = f"约{steps}步"

        # 方向描述
        direction = f"{top.clock}点方向"
        if top.lr_zh and top.lr_zh != "前方":
            direction += f"({top.lr_zh})"

        # 紧急度前缀
        urgency_word = {"HIGH": "注意", "MEDIUM": "注意", "LOW": ""}
        prefix = urgency_word.get(top.urgency, "")
        if prefix:
            prefix += "，"

        # 避让建议
        action = top.avoidance_action.rstrip("。") if top.avoidance_action else ""

        return f"{prefix}{direction}{dist_txt}有{_zh_name(top.name)}，{action}"


class ParagraphTextGenerator(TextGenerator):
    """
    段落模式生成器

    输出格式：场景前缀 + 详细物体描述（编号、方向、距离、建议）
    示例："当前处于室内环境。第1个物体：5点方向前方的床，距离约2.4米，建议从左侧绕开。第2个物体：..."
    """

    def generate(self, objects: List[SemanticObject], scene: str) -> str:
        if not objects:
            return "当前环境看起来比较安全，前方没有明显障碍物。"

        parts = []

        # 场景前缀
        scene_zh = _scene_zh(scene)
        if scene_zh:
            parts.append(f"当前处于{scene_zh}。")
        else:
            parts.append("当前环境扫描结果：")

        # 详细描述每个物体（最多3个）
        for i, o in enumerate(objects[:3], 1):
            # 方向描述
            direction = f"{o.clock}点方向"
            if o.lr_zh:
                direction += o.lr_zh

            # 距离（米）
            dist_m = o.distance_m

            # 避让建议
            action = o.avoidance_action.rstrip("。") if o.avoidance_action else "注意安全"

            # 紧急度
            urgency_txt = ""
            if o.urgency == "HIGH":
                urgency_txt = "【紧急】"
            elif o.urgency == "MEDIUM":
                urgency_txt = "【注意】"

            parts.append(
                f"第{i}个物体：{urgency_txt}{direction}的{_zh_name(o.name)}，"
                f"距离约{dist_m:.1f}米，建议{action}。"
            )

        return " ".join(parts)


# 工厂函数：模式到生成器的映射
_GENERATORS = {
    OutputMode.KEYWORD: KeywordTextGenerator(),
    OutputMode.PHRASE: PhraseTextGenerator(),
    OutputMode.PARAGRAPH: ParagraphTextGenerator(),
}


def get_generator(mode: OutputMode) -> TextGenerator:
    """
    获取指定模式的文本生成器

    Args:
        mode: 输出模式

    Returns:
        对应的文本生成器
    """
    return _GENERATORS.get(mode, _GENERATORS[OutputMode.PHRASE])


def generate_text(mode: OutputMode, objects: List[SemanticObject], scene: str) -> str:
    """
    根据模式生成播报文本

    Args:
        mode: 输出模式
        objects: 语义对象列表
        scene: 场景类型

    Returns:
        生成的播报文本
    """
    generator = get_generator(mode)
    return generator.generate(objects, scene)


def generate_text_from_raw(
    mode: OutputMode,
    raw_objects: List[Dict[str, Any]],
    scene: str
) -> str:
    """
    从原始数据生成播报文本（便捷函数）

    Args:
        mode: 输出模式
        raw_objects: 原始物体数据列表
        scene: 场景类型

    Returns:
        生成的播报文本
    """
    # 转换为 SemanticObject
    objects = []
    for o in raw_objects:
        direction = o.get("direction") if isinstance(o.get("direction"), dict) else {}
        distance = o.get("distance") if isinstance(o.get("distance"), dict) else {}

        clock = o.get("clock")
        if clock is None:
            clock = o.get("clock_dir")
        if clock is None:
            clock = direction.get("clock", 12)

        clock_zh = o.get("clock_zh") or o.get("clock_dir_zh") or direction.get("clock_zh", "")
        lr = o.get("lr") or direction.get("lr", "center")
        lr_zh = o.get("lr_zh") or direction.get("lr_zh", "前方")
        distance_m = o.get("distance_m")
        if distance_m is None:
            distance_m = distance.get("meters", 0.0)
        action = o.get("avoidance_action") or o.get("action") or ""

        obj = SemanticObject(
            name=o.get("name", ""),
            name_zh=o.get("name_zh", _zh_name(o.get("name", ""))),
            clock=int(clock or 12),
            clock_zh=clock_zh,
            lr=lr,
            lr_zh=lr_zh,
            distance_m=float(distance_m or 0.0),
            urgency=o.get("urgency", "LOW"),
            avoidance_action=action,
            relations=o.get("relations", [])
        )
        objects.append(obj)

    return generate_text(mode, objects, scene)


if __name__ == "__main__":
    # 测试代码
    print("测试文本生成器模块")
    print("=" * 50)

    # 测试数据
    test_objects = [
        SemanticObject(
            name="bed",
            name_zh="床",
            clock=5,
            clock_zh="右前方",
            lr="right",
            lr_zh="右侧",
            distance_m=2.4,
            urgency="LOW",
            avoidance_action="从左侧绕开。"
        ),
        SemanticObject(
            name="chair",
            name_zh="椅子",
            clock=3,
            clock_zh="正右方",
            lr="right",
            lr_zh="右侧",
            distance_m=1.8,
            urgency="MEDIUM",
            avoidance_action="注意避让。"
        ),
        SemanticObject(
            name="person",
            name_zh="人",
            clock=12,
            clock_zh="正前方",
            lr="center",
            lr_zh="前方",
            distance_m=3.0,
            urgency="HIGH",
            avoidance_action="先停一下，注意避让。"
        ),
    ]

    test_scene = "indoor"

    print("\n1. 关键词模式：")
    keyword_gen = KeywordTextGenerator()
    print(f"   输出: {keyword_gen.generate(test_objects, test_scene)}")

    print("\n2. 短句模式：")
    phrase_gen = PhraseTextGenerator()
    print(f"   输出: {phrase_gen.generate(test_objects, test_scene)}")

    print("\n3. 段落模式：")
    paragraph_gen = ParagraphTextGenerator()
    print(f"   输出: {paragraph_gen.generate(test_objects, test_scene)}")

    print("\n4. 工厂函数测试：")
    for mode in OutputMode:
        text = generate_text(mode, test_objects, test_scene)
        print(f"   {mode.value}: {text[:50]}...")
