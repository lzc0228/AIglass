# -*- coding: utf-8 -*-
"""
颜色识别模块
基于 HSV/Lab 颜色空间的颜色分类
采用一次性推理模式，按命令抓取最新帧
"""
import cv2
import numpy as np
from typing import Dict, Tuple, List, Optional
import logging

logger = logging.getLogger(__name__)


class ColorRecognizer:
    """颜色识别器 - 轻量级、鲁棒的颜色分类"""

    # 中文颜色名称
    COLOR_NAMES_ZH = {
        'red': '红色',
        'orange': '橙色',
        'yellow': '黄色',
        'green': '绿色',
        'cyan': '青色',
        'blue': '蓝色',
        'purple': '紫色',
        'pink': '粉色',
        'brown': '棕色',
        'black': '黑色',
        'white': '白色',
        'gray': '灰色',
    }

    # HSV 颜色范围定义（BGR转HSV后使用）
    HSV_RANGES = {
        'red': [
            ((0, 70, 50), (10, 255, 255)),      # 红色下限
            ((170, 70, 50), (180, 255, 255)),    # 红色上限
        ],
        'orange': [((11, 100, 50), (25, 255, 255))],
        'yellow': [((26, 100, 50), (35, 255, 255))],
        'green': [((36, 50, 50), (85, 255, 255))],
        'cyan': [((86, 50, 50), (100, 255, 255))],
        'blue': [((101, 50, 50), (130, 255, 255))],
        'purple': [((131, 50, 50), (160, 255, 255))],
        'pink': [((161, 50, 100), (175, 255, 255))],
        'brown': [((8, 50, 20), (22, 255, 200))],
        'black': [((0, 0, 0), (180, 255, 50))],
        'white': [((0, 0, 200), (180, 30, 255))],
        'gray': [((0, 0, 51), (180, 30, 199))],
    }

    # Lab 颜色中心点（用于欧氏距离最近邻）
    LAB_CENTERS = {
        'red': np.array([120, 130, 130]),
        'orange': np.array([60, 140, 150]),
        'yellow': np.array([97, -21, 94]),
        'green': np.array([60, -50, 50]),
        'cyan': np.array([80, -70, 60]),
        'blue': np.array([50, 40, -60]),
        'purple': np.array([70, 60, -50]),
        'pink': np.array([200, 30, 20]),
        'brown': np.array([50, 40, 30]),
        'black': np.array([20, 0, 0]),
        'white': np.array([240, 0, 0]),
        'gray': np.array([128, 0, 0]),
    }

    def __init__(self, roi_ratio: float = 0.3):
        """
        初始化颜色识别器
        :param roi_ratio: 中心ROI比例（默认0.3，即30%x30%）
        """
        self.roi_ratio = roi_ratio

    def detect_color(self, bgr_image: np.ndarray) -> Dict[str, any]:
        """
        检测图像主要颜色
        :param bgr_image: BGR格式图像
        :return: {
            'name_zh': '红色',
            'name_en': 'red',
            'rgb': (255, 0, 0),
            'confidence': 0.85,
            'method': 'hsv_lab',
            'message': '我看到主要是：红色。'
        }
        """
        if bgr_image is None or bgr_image.size == 0:
            return self._empty_result()

        try:
            # 1. 提取中心ROI
            roi = self._extract_center_roi(bgr_image)

            # 2. 多方法颜色检测
            hsv_result = self._detect_by_hsv(roi)
            lab_result = self._detect_by_lab(roi)

            # 3. 融合结果
            final_result = self._merge_results(hsv_result, lab_result, roi)

            # 4. 生成输出消息
            final_result['message'] = self._generate_message(final_result)

            return final_result

        except Exception as e:
            logger.error(f"颜色识别失败: {e}")
            return self._empty_result()

    def _extract_center_roi(self, image: np.ndarray) -> np.ndarray:
        """提取图像中心区域"""
        h, w = image.shape[:2]
        roi_h = int(h * self.roi_ratio)
        roi_w = int(w * self.roi_ratio)
        start_y = (h - roi_h) // 2
        start_x = (w - roi_w) // 2
        return image[start_y:start_y + roi_h, start_x:start_x + roi_w]

    def _detect_by_hsv(self, roi: np.ndarray) -> Dict[str, any]:
        """基于HSV颜色空间检测"""
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        color_scores = {}

        for color_name, ranges in self.HSV_RANGES.items():
            total_pixels = 0
            for lower, upper in ranges:
                lower = np.array(lower)
                upper = np.array(upper)
                mask = cv2.inRange(hsv, lower, upper)
                total_pixels += cv2.countNonZero(mask)

            score = total_pixels / (roi.shape[0] * roi.shape[1])
            color_scores[color_name] = score

        # 找得分最高的颜色
        best_color = max(color_scores, key=color_scores.get)
        confidence = color_scores[best_color]

        # 计算平均RGB
        avg_rgb = tuple(map(int, cv2.mean(roi)[:3]))

        return {
            'name_en': best_color,
            'name_zh': self.COLOR_NAMES_ZH.get(best_color, best_color),
            'rgb': avg_rgb,
            'confidence': confidence,
            'method': 'hsv'
        }

    def _detect_by_lab(self, roi: np.ndarray) -> Dict[str, any]:
        """基于Lab颜色空间和最近邻检测"""
        lab = cv2.cvtColor(roi, cv2.COLOR_BGR2LAB)
        avg_lab = cv2.mean(lab)[:3]

        min_dist = float('inf')
        best_color = 'gray'

        for color_name, center in self.LAB_CENTERS.items():
            dist = np.linalg.norm(avg_lab - center)
            if dist < min_dist:
                min_dist = dist
                best_color = color_name

        # 转换距离为置信度（距离越小置信度越高）
        confidence = max(0, 1 - min_dist / 200)

        # 计算平均RGB
        avg_rgb = tuple(map(int, cv2.mean(roi)[:3]))

        return {
            'name_en': best_color,
            'name_zh': self.COLOR_NAMES_ZH.get(best_color, best_color),
            'rgb': avg_rgb,
            'confidence': confidence,
            'method': 'lab'
        }

    def _merge_results(self, hsv_result: Dict, lab_result: Dict, roi: np.ndarray) -> Dict[str, any]:
        """融合HSV和Lab两种方法的结果"""

        # 如果两种方法结果一致，置信度取高
        if hsv_result['name_en'] == lab_result['name_en']:
            return {
                'name_en': hsv_result['name_en'],
                'name_zh': hsv_result['name_zh'],
                'rgb': hsv_result['rgb'],
                'confidence': max(hsv_result['confidence'], lab_result['confidence']),
                'method': 'hsv_lab'
            }

        # 结果不一致时，取置信度高的
        if hsv_result['confidence'] > lab_result['confidence']:
            base_result = hsv_result
        else:
            base_result = lab_result

        # 检查是否为相近颜色（如蓝绿、紫红等）
        color1 = base_result['name_en']
        color2 = lab_result['name_en'] if base_result['name_en'] == hsv_result['name_en'] else hsv_result['name_en']

        combined_name = self._combine_colors(color1, color2)

        return {
            'name_en': combined_name,
            'name_zh': self._get_combined_zh_name(combined_name, color1, color2),
            'rgb': base_result['rgb'],
            'confidence': max(hsv_result['confidence'], lab_result['confidence']) * 0.8,
            'method': 'hsv_lab'
        }

    def _combine_colors(self, color1: str, color2: str) -> str:
        """合并两个相近的颜色"""
        # 定义可合并的颜色对
        mergeable = {
            ('blue', 'green'): 'cyan',
            ('green', 'blue'): 'cyan',
            ('red', 'purple'): 'magenta',
            ('purple', 'red'): 'magenta',
            ('red', 'orange'): 'orange',
            ('orange', 'red'): 'orange',
            ('blue', 'purple'): 'violet',
            ('purple', 'blue'): 'violet',
        }

        key = (color1, color2)
        if key in mergeable:
            return mergeable[key]

        # 默认返回第一个颜色
        return color1

    def _get_combined_zh_name(self, combined_en: str, color1: str, color2: str) -> str:
        """获取合并后的中文名称"""
        if combined_en in self.COLOR_NAMES_ZH:
            return self.COLOR_NAMES_ZH[combined_en]

        # 如果没有预定义的合并名称，用组合方式
        zh1 = self.COLOR_NAMES_ZH.get(color1, color1)
        zh2 = self.COLOR_NAMES_ZH.get(color2, color2)

        # 简化组合名称
        if '蓝' in zh1 and '绿' in zh2:
            return '蓝绿色'
        if '绿' in zh1 and '蓝' in zh2:
            return '蓝绿色'
        if '红' in zh1 and '紫' in zh2:
            return '紫红色'
        if '紫' in zh1 and '红' in zh2:
            return '紫红色'

        return zh1

    def _generate_message(self, result: Dict) -> str:
        """生成输出消息"""
        confidence = result['confidence']
        name_zh = result['name_zh']

        if confidence >= 0.6:
            return f"我看到主要是：{name_zh}。"
        elif confidence >= 0.3:
            return f"可能是：{name_zh}。你可以把镜头再对准一点。"
        else:
            return f"颜色不太确定，可能是：{name_zh}。"

    def _empty_result(self) -> Dict[str, any]:
        """返回空结果"""
        return {
            'name_en': 'unknown',
            'name_zh': '未知',
            'rgb': (0, 0, 0),
            'confidence': 0.0,
            'method': 'none',
            'message': '无法识别颜色，请确保画面有足够光线。'
        }


# 全局实例（延迟初始化）
_instance: Optional[ColorRecognizer] = None


def get_color_recognizer() -> ColorRecognizer:
    """获取颜色识别器单例"""
    global _instance
    if _instance is None:
        _instance = ColorRecognizer()
        logger.info("[ColorRecognition] 颜色识别器已初始化")
    return _instance


def detect_color_from_frame(bgr_image: np.ndarray) -> Dict[str, any]:
    """
    从帧中检测颜色的便捷函数
    :param bgr_image: BGR格式图像
    :return: 检测结果字典
    """
    recognizer = get_color_recognizer()
    return recognizer.detect_color(bgr_image)


# 测试代码
if __name__ == '__main__':
    import sys

    # 创建测试图像
    def create_test_image(bgr_color):
        img = np.ones((100, 100, 3), dtype=np.uint8)
        img[:, :] = bgr_color
        return img

    recognizer = ColorRecognizer()

    # 测试各种颜色
    test_colors = {
        '红色': (0, 0, 255),
        '绿色': (0, 255, 0),
        '蓝色': (255, 0, 0),
        '黄色': (0, 255, 255),
        '白色': (255, 255, 255),
        '黑色': (0, 0, 0),
    }

    print("=" * 50)
    print("颜色识别测试")
    print("=" * 50)

    for name, bgr in test_colors.items():
        test_img = create_test_image(bgr)
        result = recognizer.detect_color(test_img)
        print(f"输入: {name} {bgr} -> 识别: {result['name_zh']} "
              f"(置信度: {result['confidence']:.2f})")
        print(f"  消息: {result['message']}")
        print()
