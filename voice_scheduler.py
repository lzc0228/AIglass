# -*- coding: utf-8 -*-
"""
安全播报调度器
统一管理所有语音播报的优先级和节流
确保紧急避障等高优先级消息不会被阻塞
"""
import time
import logging
from typing import Dict, Optional, Callable
from collections import deque
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class VoiceMessage:
    """语音消息"""
    text: str
    priority: int  # 0-100，越高越优先
    cooldown_key: Optional[str] = None  # 节流键
    min_interval: float = 0.0  # 同类消息最小间隔（秒）
    timestamp: float = field(default_factory=time.time)

    def __post_init__(self):
        if self.cooldown_key is None:
            self.cooldown_key = self.text


class VoiceScheduler:
    """
    语音播报调度器

    优先级体系：
    - P0 (90-100): 紧急避障/头部障碍 - 立即播报，可打断
    - P1 (70-89): 导航转向/对齐 - 高优先级
    - P2 (50-69): 物品查找引导 - 中优先级
    - P3 (0-49): AI闲聊/OCR/颜色 - 低优先级，可被高优先级打断
    """

    # 优先级常量
    P0_EMERGENCY = 100
    P0_HEAD_OBSTACLE = 95
    P1_NAVIGATION = 80
    P2_ITEM_SEARCH = 60
    P3_AI_CHAT = 30

    def __init__(self):
        """初始化调度器"""
        # 待播报队列（优先级队列）
        self.queue: deque[VoiceMessage] = deque()

        # 节流记录 {cooldown_key: last_play_time}
        self.cooldown_history: Dict[str, float] = {}

        # 正在播放的消息
        self.current_message: Optional[VoiceMessage] = None

        # 播报回调
        self.play_callback: Optional[Callable[[str], None]] = None

        # 调度统计
        self.stats = {
            'queued': 0,
            'played': 0,
            'skipped_cooldown': 0,
            'skipped_preempted': 0,
        }

        logger.info("[VoiceScheduler] 语音调度器已初始化")

    def set_play_callback(self, callback: Callable[[str], None]):
        """设置播报回调函数"""
        self.play_callback = callback
        logger.info("[VoiceScheduler] 播报回调已设置")

    def schedule(self, text: str, priority: int = P3_AI_CHAT,
                 cooldown_key: Optional[str] = None,
                 min_interval: float = 0.0) -> bool:
        """
        调度一条语音消息
        :param text: 语音文本
        :param priority: 优先级 (0-100)
        :param cooldown_key: 节流键，相同键的消息需要满足间隔
        :param min_interval: 同类消息最小间隔（秒）
        :return: 是否成功加入队列
        """
        if not text:
            return False

        # 检查节流
        if cooldown_key and cooldown_key in self.cooldown_history:
            last_time = self.cooldown_history[cooldown_key]
            if time.time() - last_time < min_interval:
                logger.debug(f"[VoiceScheduler] 消息被节流: {text[:20]}...")
                self.stats['skipped_cooldown'] += 1
                return False

        message = VoiceMessage(
            text=text,
            priority=priority,
            cooldown_key=cooldown_key,
            min_interval=min_interval
        )

        # 根据优先级决定插入位置
        self._insert_by_priority(message)
        self.stats['queued'] += 1

        logger.debug(f"[VoiceScheduler] 消息已排队 (P{priority}): {text[:30]}...")
        return True

    def _insert_by_priority(self, message: VoiceMessage):
        """按优先级插入队列"""
        # 如果队列为空或消息优先级高于所有现有消息，插入头部
        if not self.queue or message.priority >= self.P1_NAVIGATION:
            self.queue.appendleft(message)
            return

        # 否则找到合适位置插入
        inserted = False
        for i, existing in enumerate(self.queue):
            if message.priority > existing.priority:
                # 插入到该位置
                new_queue = deque(list(self.queue)[:i] + [message] + list(self.queue)[i:])
                self.queue = new_queue
                inserted = True
                break

        if not inserted:
            self.queue.append(message)

    def tick(self) -> Optional[str]:
        """
        处理下一帧（调用此方法来驱动播报）
        :return: 当前应该播报的消息文本，如果无则返回None
        """
        if not self.play_callback:
            return None

        # 如果正在播放，等待播放完成（这里简化处理，实际可能需要回调通知）
        if self.current_message:
            # 假设播放很快完成，清空当前消息
            self.current_message = None

        # 检查队列
        if not self.queue:
            return None

        # 获取队首消息
        message = self.queue[0]

        # 再次检查节流（可能在排队过程中条件变化）
        if message.cooldown_key and message.cooldown_key in self.cooldown_history:
            last_time = self.cooldown_history[message.cooldown_key]
            if time.time() - last_time < message.min_interval:
                # 跳过该消息
                self.queue.popleft()
                self.stats['skipped_cooldown'] += 1
                return None

        # 从队列移除
        self.queue.popleft()
        self.current_message = message

        # 更新节流记录
        if message.cooldown_key:
            self.cooldown_history[message.cooldown_key] = time.time()

        # 播报
        self.stats['played'] += 1
        try:
            self.play_callback(message.text)
        except Exception as e:
            logger.error(f"[VoiceScheduler] 播报失败: {e}")

        logger.debug(f"[VoiceScheduler] 播报 (P{message.priority}): {message.text[:30]}...")
        return message.text

    def clear(self):
        """清空队列"""
        count = len(self.queue)
        self.queue.clear()
        self.current_message = None
        logger.info(f"[VoiceScheduler] 队列已清空，清除了 {count} 条消息")

    def clear_low_priority(self, threshold: int = P2_ITEM_SEARCH):
        """清除低优先级消息"""
        original_size = len(self.queue)
        self.queue = deque([m for m in self.queue if m.priority >= threshold])
        cleared = original_size - len(self.queue)
        if cleared > 0:
            logger.info(f"[VoiceScheduler] 清除了 {cleared} 条低优先级消息")

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            **self.stats,
            'queue_size': len(self.queue),
            'cooldown_keys': len(self.cooldown_history),
        }


# 风险评估模块
class RiskAssessor:
    """障碍物风险评估"""

    # 风险等级
    RISK_LOW = 'LOW'
    RISK_MEDIUM = 'MEDIUM'
    RISK_HIGH = 'HIGH'

    # 风险阈值
    NEAR_RATIO = 0.15      # 近距离障碍面积阈值
    CRITICAL_RATIO = 0.25  # 危险距离面积阈值
    HEAD_LEVEL_RATIO = 0.5  # 头部高度判定阈值

    def __init__(self):
        """初始化风险评估器"""
        pass

    def assess(self, obstacle: Dict[str, any], image_shape: tuple) -> Dict[str, any]:
        """
        评估单个障碍物的风险
        :param obstacle: 障碍物信息 {
            'name': str,
            'mask': ndarray,
            'area': int,
            'area_ratio': float,
            'center_x': float,
            'center_y': float,
            'bottom_y_ratio': float
        }
        :param image_shape: 图像尺寸 (h, w)
        :return: {
            'risk_level': 'LOW' | 'MEDIUM' | 'HIGH',
            'direction': 'left' | 'center' | 'right',
            'distance_category': 'near' | 'medium' | 'far',
            'is_head_level': bool,
            'message': str
        }
        """
        h, w = image_shape[:2]
        area_ratio = obstacle.get('area_ratio', 0)
        bottom_y_ratio = obstacle.get('bottom_y_ratio', 0)
        center_x_ratio = obstacle.get('center_x', 0) / w

        # 判断距离
        if area_ratio >= self.CRITICAL_RATIO:
            distance = 'near'
            risk = self.RISK_HIGH
        elif area_ratio >= self.NEAR_RATIO:
            distance = 'near'
            risk = self.RISK_MEDIUM
        else:
            distance = 'far'
            risk = self.RISK_LOW

        # 判断方向（三分法）
        if center_x_ratio < 0.35:
            direction = 'left'
        elif center_x_ratio < 0.65:
            direction = 'center'
        else:
            direction = 'right'

        # 判断是否头部高度
        is_head_level = self._is_head_level_obstacle(obstacle, h, w)

        # 如果是头部高度且风险不是很高，提高风险等级
        if is_head_level and risk == self.RISK_LOW:
            risk = self.RISK_MEDIUM

        # 生成消息
        message = self._generate_risk_message(
            risk, direction, distance, is_head_level, obstacle.get('name', '障碍物')
        )

        return {
            'risk_level': risk,
            'direction': direction,
            'distance_category': distance,
            'is_head_level': is_head_level,
            'message': message
        }

    def _is_head_level_obstacle(self, obstacle: Dict, h: int, w: int) -> bool:
        """判断是否为头部高度障碍"""
        # 获取mask
        mask = obstacle.get('mask')
        if mask is None:
            return False

        # 计算mask的垂直中心
        y_coords = np.where(mask > 0)[0]
        if len(y_coords) == 0:
            return False

        mask_center_y = np.mean(y_coords) / h  # 归一化Y坐标

        # 头部高度判定：
        # 1. 底部不靠近画面底部（不太可能是地面障碍）
        # 2. 中心在画面中上部
        # 3. 面积/宽度达到一定阈值

        bottom_y_ratio = obstacle.get('bottom_y_ratio', 0)
        area_ratio = obstacle.get('area_ratio', 0)

        # 底部不靠近底部（距离底部至少20%）
        bottom_not_near_ground = bottom_y_ratio < 0.8

        # 中心在中上部（Y < 0.6）
        center_in_upper = mask_center_y < 0.6

        # 面积足够大
        large_enough = area_ratio > 0.03

        return bottom_not_near_ground and center_in_upper and large_enough

    def _generate_risk_message(self, risk: str, direction: str,
                               distance: str, is_head_level: bool,
                               name: str) -> str:
        """生成风险提示消息"""
        direction_map = {
            'left': '左侧',
            'center': '前方',
            'right': '右侧'
        }

        dir_zh = direction_map.get(direction, '前方')

        if is_head_level:
            return f"[导航] 注意头部高度有障碍。"

        if risk == self.RISK_HIGH:
            return f"[导航] 前方近距离{dir_zh}有{name}，请停下。"
        elif risk == self.RISK_MEDIUM:
            if distance == 'near':
                return f"[导航] {dir_zh}有{name}靠近，请注意。"
            else:
                return f"[导航] {dir_zh}有{name}。"
        else:
            return f"[导航] {dir_zh}远处有{name}。"

    def assess_batch(self, obstacles: list, image_shape: tuple) -> Dict[str, any]:
        """
        批量评估障碍物，返回最高风险的结果
        :param obstacles: 障碍物列表
        :param image_shape: 图像尺寸
        :return: 最高风险的评估结果
        """
        if not obstacles:
            return {
                'risk_level': self.RISK_LOW,
                'direction': 'center',
                'distance_category': 'far',
                'is_head_level': False,
                'message': ''
            }

        # 评估所有障碍物
        results = []
        for obs in obstacles:
            result = self.assess(obs, image_shape)
            results.append(result)

        # 按风险等级排序（HIGH > MEDIUM > LOW）
        risk_order = {self.RISK_HIGH: 2, self.RISK_MEDIUM: 1, self.RISK_LOW: 0}

        highest = max(results, key=lambda r: (
            risk_order.get(r['risk_level'], 0),
            r['is_head_level']  # 头部障碍优先
        ))

        return highest


# 全局实例
_scheduler_instance: Optional[VoiceScheduler] = None
_assessor_instance: Optional[RiskAssessor] = None


def get_voice_scheduler() -> VoiceScheduler:
    """获取语音调度器单例"""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = VoiceScheduler()
    return _scheduler_instance


def get_risk_assessor() -> RiskAssessor:
    """获取风险评估器单例"""
    global _assessor_instance
    if _assessor_instance is None:
        _assessor_instance = RiskAssessor()
    return _assessor_instance


# 测试代码
if __name__ == '__main__':
    import numpy as np

    print("=" * 50)
    print("语音调度器测试")
    print("=" * 50)

    scheduler = VoiceScheduler()

    # 模拟播报回调
    def mock_play(text):
        print(f"  [播放] {text}")

    scheduler.set_play_callback(mock_play)

    # 测试消息
    messages = [
        ("你好，我是AI助手", 30),
        ("前方有障碍", 80),
        ("左侧有人靠近", 95),
        ("保持直行", 80),
    ]

    for text, priority in messages:
        scheduler.schedule(text, priority=priority)

    print("\n处理队列:")
    while True:
        result = scheduler.tick()
        if result is None:
            break
        time.sleep(0.1)

    print("\n统计:", scheduler.get_stats())
