# -*- coding: utf-8 -*-
"""
物品搜索增强模块
与 yolomedia.py 协作，提供以下增强功能：
- A1. 超时"没找到"提示
- A2. 多目标队列（"找钥匙和钱包"）
- A3. 持续方向/距离提示
- A4. 热冷反馈（越居中越近 → 频率变化）
"""
import time
import re
import logging
from typing import List, Dict, Optional, Callable, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class ItemPhase(Enum):
    """物品搜索阶段"""
    SEARCHING = "SEARCHING"       # 正在搜索
    FOUND = "FOUND"               # 已找到
    CENTERING = "CENTERING"       # 正在居中
    TRACKING = "TRACKING"         # 正在追踪
    GRABBED = "GRABBED"           # 已抓取


@dataclass
class TargetItem:
    """目标物品"""
    name_cn: str          # 中文名称
    name_en: str          # 英文类别名
    index: int            # 在队列中的索引
    total: int            # 队列总数

    def __str__(self):
        return f"{self.name_cn}（{self.index + 1}/{self.total}）"


@dataclass
class DetectionResult:
    """检测结果（来自 yolomedia）"""
    detected: bool                     # 是否检测到
    center_x_ratio: float = 0.5       # 中心X比例（0-1，0.5为正中）
    area_ratio: float = 0.0           # 面积比例（0-1）
    hand_area_ratio: float = 0.0      # 手面积比例
    distance_ratio: float = 0.0       # 物体/手面积比
    phase: ItemPhase = ItemPhase.SEARCHING
    timestamp: float = field(default_factory=time.time)

    @property
    def is_centered(self) -> bool:
        """是否居中（左右偏差小于12%）"""
        return abs(self.center_x_ratio - 0.5) < 0.12

    @property
    def is_at_distance(self) -> bool:
        """是否距离合适（ratio在1±25%范围内）"""
        ratio = self.distance_ratio if self.distance_ratio > 0 else 0.5
        return abs(ratio - 1.0) < 0.25

    @property
    def alignment_quality(self) -> float:
        """对齐质量分数（0-1，越高越接近理想）"""
        # 综合居中程度和距离适当程度
        center_score = 1.0 - abs(self.center_x_ratio - 0.5) * 2  # 0-1
        distance_score = 1.0
        if self.distance_ratio > 0:
            distance_score = 1.0 - abs(self.distance_ratio - 1.0) / 0.5
        return max(0.0, min(1.0, (center_score + distance_score) / 2))


class ItemSearchEnhancer:
    """
    物品搜索增强器

    配置参数：
    - not_found_timeout_sec: 找不到的超时时间（默认30秒）
    - not_found_cooldown_sec: 提示冷却时间（默认10秒）
    - guidance_interval_base_sec: 基础引导间隔（默认1.5秒）
    - hot_cold_factor: 热冷反馈因子（越大，接近目标时频率越高）
    """

    def __init__(self,
                 not_found_timeout_sec: float = 30.0,
                 not_found_cooldown_sec: float = 10.0,
                 guidance_interval_base_sec: float = 1.5,
                 hot_cold_factor: float = 0.5):
        """
        初始化物品搜索增强器
        :param not_found_timeout_sec: 找不到的超时时间
        :param not_found_cooldown_sec: 提示冷却时间
        :param guidance_interval_base_sec: 基础引导间隔
        :param hot_cold_factor: 热冷反馈因子
        """
        self.not_found_timeout_sec = not_found_timeout_sec
        self.not_found_cooldown_sec = not_found_cooldown_sec
        self.guidance_interval_base_sec = guidance_interval_base_sec
        self.hot_cold_factor = hot_cold_factor

        # 状态
        self.is_active = False
        self.target_queue: List[TargetItem] = []
        self.current_target: Optional[TargetItem] = None

        # 时间追踪
        self.search_start_time = 0.0
        self.last_seen_time = 0.0
        self.last_guidance_time = 0.0
        self.last_not_found_warn_time = 0.0

        # 检测历史
        self.detection_history: List[DetectionResult] = []
        self.history_size = 10

        # 回调
        self.on_guidance_callback: Optional[Callable[[str], None]] = None
        self.on_target_found_callback: Optional[Callable[[TargetItem], None]] = None
        self.on_target_complete_callback: Optional[Callable[[TargetItem], None]] = None

        logger.info("[ItemSearch] 物品搜索增强器已初始化")

    def set_guidance_callback(self, callback: Callable[[str], None]):
        """设置引导语音回调"""
        self.on_guidance_callback = callback

    def set_target_found_callback(self, callback: Callable[[TargetItem], None]):
        """设置找到目标回调"""
        self.on_target_found_callback = callback

    def set_target_complete_callback(self, callback: Callable[[TargetItem], None]):
        """设置目标完成回调"""
        self.on_target_complete_callback = callback

    def start_search(self, items: List[str], label_ens: List[str]):
        """
        开始搜索（支持多目标队列）
        :param items: 中文物品名列表
        :param label_ens: 英文类别名列表
        """
        if len(items) != len(label_ens):
            logger.warning("[ItemSearch] 物品数量与类别数量不匹配")
            items = items[:len(label_ens)]

        self.target_queue = [
            TargetItem(name_cn=items[i], name_en=label_ens[i], index=i, total=len(items))
            for i in range(len(items))
        ]
        self.current_target = self.target_queue[0] if self.target_queue else None
        self.search_start_time = time.time()
        self.last_seen_time = 0.0
        self.last_guidance_time = 0.0
        self.last_not_found_warn_time = time.time()
        self.detection_history.clear()
        self.is_active = True

        logger.info(f"[ItemSearch] 开始搜索，目标: {[str(t) for t in self.target_queue]}")

        # 播报开始
        if self.on_guidance_callback:
            self.on_guidance_callback(f"现在开始找：{self.current_target.name_cn}")

    def stop_search(self):
        """停止搜索"""
        self.is_active = False
        self.current_target = None
        self.target_queue.clear()
        self.detection_history.clear()
        logger.info("[ItemSearch] 搜索已停止")

    def mark_found(self):
        """标记当前目标为已找到"""
        if self.current_target and self.on_target_complete_callback:
            self.on_target_complete_callback(self.current_target)

        # 移除当前目标，处理下一个
        if self.target_queue:
            self.target_queue.pop(0)

        if self.target_queue:
            self.current_target = self.target_queue[0]
            logger.info(f"[ItemSearch] 切换到下一个目标: {self.current_target}")

            if self.on_guidance_callback:
                self.on_guidance_callback(
                    f"现在开始找：{self.current_target.name_cn} "
                    f"（{self.current_target.index + 1}/{self.current_target.total}）"
                )

            # 重置时间
            self.search_start_time = time.time()
            self.last_seen_time = time.time() if self.detection_history else 0.0
            self.detection_history.clear()
        else:
            self.current_target = None
            self.is_active = False
            logger.info("[ItemSearch] 所有目标已完成")

    def update_detection(self, result: DetectionResult):
        """
        更新检测结果
        :param result: 来自 yolomedia 的检测结果
        """
        if not self.is_active or not self.current_target:
            return

        now = time.time()

        # 更新历史记录
        self.detection_history.append(result)
        if len(self.detection_history) > self.history_size:
            self.detection_history.pop(0)

        # 更新时间
        if result.detected:
            self.last_seen_time = now

        # 触发找到事件（首次检测到）
        if result.detected and len(self.detection_history) == 1:
            if self.on_target_found_callback:
                self.on_target_found_callback(self.current_target)

        # 生成引导
        self._generate_guidance(result, now)

        # 检查超时
        self._check_timeout(now)

    def _generate_guidance(self, result: DetectionResult, now: float):
        """生成引导语音"""
        if not self.on_guidance_callback:
            return

        # 计算自适应间隔（热冷反馈：越接近目标，频率越高）
        quality = result.alignment_quality if result.detected else 0.0
        interval = self.guidance_interval_base_sec * (1.0 - self.hot_cold_factor * quality)
        interval = max(0.5, interval)  # 最小0.5秒

        if now - self.last_guidance_time < interval:
            return

        self.last_guidance_time = now

        if not result.detected:
            # 未检测到，提示方向
            # 根据历史记录判断大概方向
            if self.detection_history:
                last = self.detection_history[-1]
                direction = self._get_direction_text(last.center_x_ratio)
                self.on_guidance_callback(f"请{direction}移动一下镜头")
            return

        # 检测到了，生成引导
        guidance = []

        # 方向引导
        if not result.is_centered:
            direction = self._get_direction_text(result.center_x_ratio)
            guidance.append(direction)

        # 距离引导
        if result.distance_ratio > 0:
            ratio = result.distance_ratio
            if ratio < 0.75:
                guidance.append("向前靠近")
            elif ratio > 1.25:
                guidance.append("向后一点")
            elif result.is_at_distance:
                guidance.append("保持这个距离")

        # 质量反馈（热冷）
        if quality >= 0.8:
            guidance.append("很好，保持")
        elif quality >= 0.5:
            pass  # 中等质量不说话
        else:
            guidance.append("再调整一下")

        if guidance:
            text = "，".join(guidance) + "。"
            self.on_guidance_callback(text)

    def _get_direction_text(self, center_x_ratio: float) -> str:
        """获取方向文本（三分法）"""
        if center_x_ratio < 0.38:
            return "向右"
        elif center_x_ratio > 0.62:
            return "向左"
        else:
            return "向中"

    def _check_timeout(self, now: float):
        """检查超时"""
        if not self.on_guidance_callback:
            return

        # 检查"没找到"超时
        time_since_seen = now - self.last_seen_time if self.last_seen_time > 0 else (now - self.search_start_time)

        if time_since_seen > self.not_found_timeout_sec:
            # 检查冷却时间
            if now - self.last_not_found_warn_time >= self.not_found_cooldown_sec:
                self.last_not_found_warn_time = now
                target_name = self.current_target.name_cn if self.current_target else "目标"
                self.on_guidance_callback(
                    f"我没找到{target_name}，请把镜头换个角度或走近一点。"
                )

    def get_status(self) -> Dict[str, Any]:
        """获取当前状态"""
        return {
            'is_active': self.is_active,
            'current_target': str(self.current_target) if self.current_target else None,
            'queue_length': len(self.target_queue),
            'time_since_seen': time.time() - self.last_seen_time if self.last_seen_time > 0 else 0.0,
            'recent_detections': [
                {
                    'detected': r.detected,
                    'center_x_ratio': r.center_x_ratio,
                    'distance_ratio': r.distance_ratio,
                    'quality': r.alignment_quality
                }
                for r in self.detection_history[-5:]
            ]
        }


# 全局实例
_enhancer_instance: Optional[ItemSearchEnhancer] = None


def get_item_search_enhancer() -> ItemSearchEnhancer:
    """获取物品搜索增强器单例"""
    global _enhancer_instance
    if _enhancer_instance is None:
        _enhancer_instance = ItemSearchEnhancer()
    return _enhancer_instance


# 便捷函数
def start_item_search(items: List[str], label_ens: List[str]):
    """开始物品搜索"""
    enhancer = get_item_search_enhancer()
    enhancer.start_search(items, label_ens)


def update_item_detection(detected: bool, center_x_ratio: float = 0.5,
                         area_ratio: float = 0.0, hand_area_ratio: float = 0.0,
                         distance_ratio: float = 0.0, phase: str = "SEARCHING"):
    """更新物品检测结果"""
    enhancer = get_item_search_enhancer()
    if enhancer.is_active:
        result = DetectionResult(
            detected=detected,
            center_x_ratio=center_x_ratio,
            area_ratio=area_ratio,
            hand_area_ratio=hand_area_ratio,
            distance_ratio=distance_ratio,
            phase=ItemPhase(phase)
        )
        enhancer.update_detection(result)


def mark_item_found():
    """标记当前物品为已找到"""
    enhancer = get_item_search_enhancer()
    if enhancer.is_active:
        enhancer.mark_found()


def stop_item_search():
    """停止物品搜索"""
    enhancer = get_item_search_enhancer()
    enhancer.stop_search()


# 测试代码
if __name__ == '__main__':
    import asyncio

    print("=" * 50)
    print("物品搜索增强器测试")
    print("=" * 50)

    def mock_guidance(text):
        print(f"  [语音] {text}")

    enhancer = ItemSearchEnhancer(
        not_found_timeout_sec=5.0,  # 测试用5秒
        not_found_cooldown_sec=3.0,
        guidance_interval_base_sec=1.0
    )
    enhancer.set_guidance_callback(mock_guidance)

    # 测试多目标队列
    print("\n1. 测试多目标队列:")
    enhancer.start_search(["钥匙", "钱包", "手机"], ["key", "wallet", "phone"])

    # 模拟检测结果
    print("\n2. 模拟检测到目标（偏左）:")
    enhancer.update_detection(DetectionResult(
        detected=True, center_x_ratio=0.25, distance_ratio=0.8
    ))

    time.sleep(1.5)
    print("\n3. 模拟目标居中:")
    enhancer.update_detection(DetectionResult(
        detected=True, center_x_ratio=0.48, distance_ratio=1.0
    ))

    print("\n4. 标记找到，切换到下一个:")
    enhancer.mark_found()

    print("\n5. 状态:")
    print(enhancer.get_status())
