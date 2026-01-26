# -*- coding: utf-8 -*-
"""
夜间模式检测模块
通过亮度阈值检测夜间/暗光环境
触发后可通过WebSocket向ESP32发送LED控制指令
"""
import time
import logging
from typing import Optional, Callable, Dict, Any
from collections import deque
import numpy as np
import cv2

logger = logging.getLogger(__name__)


class NightModeDetector:
    """夜间模式检测器 - 常驻轻量检测"""

    # 默认配置
    DEFAULT_CONFIG = {
        'SAMPLE_EVERY_N_FRAMES': 10,      # 每N帧采样一次
        'LUMA_THRESH': 40,                # 亮度阈值（0-255）
        'LUMA_THRESH_EXIT': 60,           # 退出阈值（滞后，防止抖动）
        'STABLE_FRAMES': 5,               # 连续N帧满足才切换
        'HISTORY_SIZE': 10,               # 亮度历史记录大小
    }

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化夜间模式检测器
        :param config: 配置字典，覆盖默认配置
        """
        self.config = {**self.DEFAULT_CONFIG, **(config or {})}

        # 状态变量
        self.is_night_mode = False
        self.frame_count = 0
        self.luma_history = deque(maxlen=self.config['HISTORY_SIZE'])
        self.stable_count = 0

        # 回调函数
        self.on_mode_change: Optional[Callable[[bool], None]] = None

        # 最近一次状态变化时间
        self.last_change_time = 0
        self.min_change_interval = 2.0  # 最小切换间隔（秒）

        logger.info(f"[NightMode] 夜间检测器已初始化，阈值: {self.config['LUMA_THRESH']}")

    def process_frame(self, bgr_image: np.ndarray) -> Dict[str, Any]:
        """
        处理单帧图像
        :param bgr_image: BGR格式图像
        :return: 状态字典 {
            'is_night': bool,
            'luma': float,
            'changed': bool,
            'luma_history': list
        }
        """
        if bgr_image is None:
            return {'is_night': self.is_night_mode, 'luma': 0, 'changed': False}

        self.frame_count += 1

        # 按间隔采样
        if self.frame_count % self.config['SAMPLE_EVERY_N_FRAMES'] != 0:
            return {
                'is_night': self.is_night_mode,
                'luma': self.luma_history[-1] if self.luma_history else 0,
                'changed': False
            }

        # 计算亮度
        luma = self._calculate_luma(bgr_image)
        self.luma_history.append(luma)

        # 判断是否应该切换模式
        should_be_night = self._should_be_night_mode(luma)

        # 稳定性检查
        if should_be_night != self.is_night_mode:
            self.stable_count += 1
        else:
            self.stable_count = 0

        # 达到稳定帧数后切换
        changed = False
        if self.stable_count >= self.config['STABLE_FRAMES']:
            current_time = time.time()
            # 检查最小切换间隔
            if current_time - self.last_change_time >= self.min_change_interval:
                old_mode = self.is_night_mode
                self.is_night_mode = should_be_night
                self.last_change_time = current_time
                changed = True

                logger.info(f"[NightMode] 模式切换: {old_mode} -> {self.is_night_mode}, "
                           f"亮度: {luma:.1f}")

                # 触发回调
                if self.on_mode_change:
                    try:
                        self.on_mode_change(self.is_night_mode)
                    except Exception as e:
                        logger.error(f"[NightMode] 回调执行失败: {e}")

        return {
            'is_night': self.is_night_mode,
            'luma': luma,
            'changed': changed,
            'luma_history': list(self.luma_history),
            'stable_count': self.stable_count
        }

    def _calculate_luma(self, bgr_image: np.ndarray) -> float:
        """
        计算图像平均亮度
        使用加权平均: Y = 0.299*R + 0.587*G + 0.114*B
        """
        # 可选：先缩小图像加速计算
        h, w = bgr_image.shape[:2]
        if h > 200 or w > 200:
            scale = 200 / max(h, w)
            small = cv2.resize(bgr_image, None, fx=scale, fy=scale)
        else:
            small = bgr_image

        # 转灰度并计算均值
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        return float(np.mean(gray))

    def _should_be_night_mode(self, luma: float) -> bool:
        """
        根据亮度判断是否应为夜间模式
        使用滞后防止抖动
        """
        if self.is_night_mode:
            # 当前是夜间模式，亮度需要超过退出阈值才退出
            return luma < self.config['LUMA_THRESH_EXIT']
        else:
            # 当前是日间模式，亮度低于阈值才进入夜间
            return luma < self.config['LUMA_THRESH']

    def force_mode(self, is_night: bool):
        """
        强制设置模式（用于手动控制）
        :param is_night: True为夜间模式，False为日间模式
        """
        if self.is_night_mode != is_night:
            old_mode = self.is_night_mode
            self.is_night_mode = is_night
            self.stable_count = 0
            self.last_change_time = time.time()

            logger.info(f"[NightMode] 强制切换: {old_mode} -> {self.is_night_mode}")

            if self.on_mode_change:
                try:
                    self.on_mode_change(is_night)
                except Exception as e:
                    logger.error(f"[NightMode] 回调执行失败: {e}")

    def reset(self):
        """重置检测器状态"""
        self.is_night_mode = False
        self.frame_count = 0
        self.luma_history.clear()
        self.stable_count = 0
        logger.info("[NightMode] 检测器已重置")

    def get_status(self) -> Dict[str, Any]:
        """获取当前状态"""
        return {
            'is_night': self.is_night_mode,
            'frame_count': self.frame_count,
            'avg_luma': np.mean(self.luma_history) if self.luma_history else 0,
            'stable_count': self.stable_count,
            'config': self.config
        }


# 全局实例（延迟初始化）
_instance: Optional[NightModeDetector] = None


def get_night_detector() -> NightModeDetector:
    """获取夜间检测器单例"""
    global _instance
    if _instance is None:
        _instance = NightModeDetector()
        logger.info("[NightMode] 夜间检测器已初始化")
    return _instance


def set_night_mode_callback(callback: Callable[[bool], None]):
    """设置模式变化回调"""
    detector = get_night_detector()
    detector.on_mode_change = callback
    logger.info("[NightMode] 回调已设置")


# 测试代码
if __name__ == '__main__':
    import sys

    def test_callback(is_night: bool):
        mode = "夜间" if is_night else "日间"
        print(f">>> 模式切换回调: 进入{mode}模式")

    detector = NightModeDetector({
        'SAMPLE_EVERY_N_FRAMES': 1,
        'LUMA_THRESH': 50,
        'LUMA_THRESH_EXIT': 70,
        'STABLE_FRAMES': 3,
    })
    detector.on_mode_change = test_callback

    print("=" * 50)
    print("夜间模式检测测试")
    print("=" * 50)

    # 模拟亮度变化
    test_sequence = [
        ("亮图像（日间）", 150),
        ("亮图像（日间）", 150),
        ("亮图像（日间）", 150),
        ("暗图像（夜间）", 30),
        ("暗图像（夜间）", 30),
        ("暗图像（夜间）", 30),
        ("暗图像（夜间）", 30),
        ("暗图像（夜间）", 30),
        ("亮图像（恢复）", 150),
        ("亮图像（恢复）", 150),
        ("亮图像（恢复）", 150),
    ]

    for name, brightness in test_sequence:
        # 创建测试图像
        img = np.ones((100, 100, 3), dtype=np.uint8) * brightness
        result = detector.process_frame(img)

        status = "夜间" if result['is_night'] else "日间"
        print(f"{name}: 亮度={brightness}, "
              f"状态={status}, "
              f"变化={'是' if result['changed'] else '否'}, "
              f"稳定计数={result.get('stable_count', 0)}")
