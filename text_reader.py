# -*- coding: utf-8 -*-
"""
OCR/读字模块
支持通用汉字识别和公交车路线识别
"""
import os
import re
import logging
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import cv2

logger = logging.getLogger(__name__)


class OCREngine:
    """OCR引擎封装"""

    def __init__(self):
        """初始化OCR引擎"""
        self.engine = None
        self.engine_type = None
        self._init_engine()

    def _init_engine(self):
        """尝试初始化OCR引擎"""
        # 优先尝试 PaddleOCR
        try:
            from paddleocr import PaddleOCR
            self.engine = PaddleOCR(
                use_angle_cls=True,
                lang='ch',
                use_gpu=False,
                show_log=False
            )
            self.engine_type = 'paddleocr'
            logger.info("[OCR] PaddleOCR 初始化成功")
            return
        except ImportError:
            logger.warning("[OCR] PaddleOCR 未安装")

        # 尝试 EasyOCR
        try:
            import easyocr
            self.engine = easyocr.Reader(['ch_sim', 'en'], gpu=False)
            self.engine_type = 'easyocr'
            logger.info("[OCR] EasyOCR 初始化成功")
            return
        except ImportError:
            logger.warning("[OCR] EasyOCR 未安装")

        # 都没有，使用 Tesseract 作为后备
        try:
            import pytesseract
            self.engine = pytesseract
            self.engine_type = 'tesseract'
            logger.info("[OCR] Tesseract OCR 初始化成功")
            return
        except ImportError:
            logger.warning("[OCR] pytesseract 未安装")

        logger.error("[OCR] 无法初始化任何OCR引擎")

    def is_available(self) -> bool:
        """检查OCR是否可用"""
        return self.engine is not None

    def recognize(self, image: np.ndarray) -> List[Dict[str, Any]]:
        """
        识别图像中的文字
        :param image: BGR格式图像
        :return: 文字列表 [{'text': str, 'bbox': list, 'confidence': float}, ...]
        """
        if not self.is_available():
            return []

        try:
            if self.engine_type == 'paddleocr':
                return self._paddleocr_recognize(image)
            elif self.engine_type == 'easyocr':
                return self._easyocr_recognize(image)
            elif self.engine_type == 'tesseract':
                return self._tesseract_recognize(image)
        except Exception as e:
            logger.error(f"[OCR] 识别失败: {e}")
            return []

        return []

    def _paddleocr_recognize(self, image: np.ndarray) -> List[Dict[str, Any]]:
        """PaddleOCR 识别"""
        result = self.engine.ocr(image, cls=True)
        texts = []

        if result and result[0]:
            for line in result[0]:
                box = line[0]
                text_info = line[1]
                text = text_info[0] if isinstance(text_info, tuple) else str(text_info)
                conf = text_info[1] if isinstance(text_info, tuple) and len(text_info) > 1 else 0.8

                texts.append({
                    'text': text,
                    'bbox': box,
                    'confidence': float(conf)
                })

        return texts

    def _easyocr_recognize(self, image: np.ndarray) -> List[Dict[str, Any]]:
        """EasyOCR 识别"""
        result = self.engine.readtext(image)
        texts = []

        for (bbox, text, conf) in result:
            texts.append({
                'text': text,
                'bbox': bbox,
                'confidence': float(conf)
            })

        return texts

    def _tesseract_recognize(self, image: np.ndarray) -> List[Dict[str, Any]]:
        """Tesseract OCR 识别"""
        import pytesseract
        from PIL import Image

        # 获取文字和详细信息
        data = pytesseract.image_to_data(
            Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB)),
            lang='chi_sim+eng',
            output_type=pytesseract.Output.DICT
        )

        texts = []
        n_boxes = len(data['text'])

        for i in range(n_boxes):
            text = data['text'][i].strip()
            conf = int(data['conf'][i])

            if text and conf > 0:
                bbox = [
                    [data['left'][i], data['top'][i]],
                    [data['left'][i] + data['width'][i], data['top'][i]],
                    [data['left'][i] + data['width'][i], data['top'][i] + data['height'][i]],
                    [data['left'][i], data['top'][i] + data['height'][i]]
                ]
                texts.append({
                    'text': text,
                    'bbox': bbox,
                    'confidence': conf / 100.0
                })

        return texts


class TextReader:
    """通用文字读取器"""

    def __init__(self, ocr_engine: Optional[OCREngine] = None):
        """
        初始化文字读取器
        :param ocr_engine: OCR引擎实例，为None则自动创建
        """
        self.ocr = ocr_engine or OCREngine()

        # 文字过滤配置
        self.min_text_length = 1
        self.min_confidence = 0.3
        self.max_results = 20

    def read_text(self, image: np.ndarray, mode: str = 'general') -> Dict[str, Any]:
        """
        从图像中读取文字
        :param image: BGR格式图像
        :param mode: 'general' 通用识别 | 'bus' 公交车识别
        :return: {
            'success': bool,
            'texts': list,
            'message': str,
            'raw_results': list
        }
        """
        if image is None:
            return {
                'success': False,
                'texts': [],
                'message': '图像为空',
                'raw_results': []
            }

        if not self.ocr.is_available():
            return {
                'success': False,
                'texts': [],
                'message': 'OCR引擎不可用，请安装 PaddleOCR、EasyOCR 或 Tesseract',
                'raw_results': []
            }

        try:
            # 执行OCR
            raw_results = self.ocr.recognize(image)

            # 后处理
            if mode == 'bus':
                processed = self._process_bus_results(raw_results)
            elif mode == 'restroom':
                processed = self._process_restroom_results(raw_results, image_shape=image.shape[:2])
            else:
                processed = self._process_general_results(raw_results)

            return {
                'success': len(processed['texts']) > 0,
                'texts': processed['texts'],
                'message': processed['message'],
                'raw_results': raw_results
            }

        except Exception as e:
            logger.error(f"[TextReader] 读取失败: {e}")
            return {
                'success': False,
                'texts': [],
                'message': f'读取失败: {str(e)}',
                'raw_results': []
            }

    def _process_general_results(self, raw_results: List[Dict]) -> Dict[str, Any]:
        """处理通用识别结果"""
        # 过滤低置信度和过短文本
        filtered = [
            r for r in raw_results
            if len(r['text']) >= self.min_text_length
            and r['confidence'] >= self.min_confidence
        ]

        # 去重（保留位置和文本都相近的只保留一个）
        unique_texts = self._deduplicate_texts(filtered)

        # 按位置排序（从上到下，从左到右）
        sorted_texts = self._sort_by_position(unique_texts)

        texts = [t['text'] for t in sorted_texts[:self.max_results]]

        # 生成消息
        if texts:
            combined = '、'.join(texts[:5])  # 最多显示5个
            if len(texts) > 5:
                combined += f" 等{len(texts)}项"
            message = f"我读到：{combined}。"
        else:
            message = "没有识别到清晰的文字。"

        return {
            'texts': texts,
            'message': message
        }

    def _process_bus_results(self, raw_results: List[Dict]) -> Dict[str, Any]:
        """处理公交车路线识别结果"""
        # 公交车相关关键词
        bus_keywords = ['路', '线', '开往', '终点', '起点', '站', '环线', '支线', '专线', '快线']

        # 提取包含路线信息的文本
        route_texts = []
        for r in raw_results:
            text = r['text']
            # 检查是否包含数字和路线关键词
            if re.search(r'\d+', text) and any(kw in text for kw in bus_keywords):
                route_texts.append(r)
            # 或者是纯数字（可能是路号）
            elif text.isdigit() and len(text) <= 3:
                route_texts.append({'text': text + '路', 'bbox': r['bbox'], 'confidence': r['confidence']})

        if route_texts:
            # 按置信度排序
            route_texts.sort(key=lambda x: x['confidence'], reverse=True)
            texts = [t['text'] for t in route_texts[:3]]

            # 提取路号
            route_numbers = []
            for text in texts:
                numbers = re.findall(r'\d+', text)
                route_numbers.extend([f"{n}路" for n in numbers])

            if route_numbers:
                # 去重
                route_numbers = list(dict.fromkeys(route_numbers))[:3]
                message = f"这辆车可能是：{'、'.join(route_numbers)}。"
            else:
                message = f"这辆车可能是：{texts[0]}。"
        else:
            # 没找到明确的路线信息，返回所有数字
            all_numbers = []
            for r in raw_results:
                numbers = re.findall(r'\d+', r['text'])
                all_numbers.extend(numbers)

            if all_numbers:
                # 去重并限制数量
                unique_numbers = list(dict.fromkeys(all_numbers))[:3]
                message = f"可能是：{'、'.join(unique_numbers)}路。你可以把镜头对准路线牌。"
                texts = [f"{n}路" for n in unique_numbers]
            else:
                message = "没有识别到清晰的路线号。请确保画面包含公交车头或路线牌。"
                texts = []

        return {
            'texts': texts,
            'message': message
        }

    def _process_restroom_results(self, raw_results: List[Dict], image_shape: Optional[Tuple[int, int]] = None) -> Dict[str, Any]:
        """处理卫生间标识/入口出口方向识别结果"""
        filtered = [
            r for r in (raw_results or [])
            if str(r.get('text', '')).strip() and float(r.get('confidence', 0.0) or 0.0) >= self.min_confidence
        ]
        if not filtered:
            return {
                'texts': [],
                'message': '没有识别到清晰的卫生间标识。'
            }

        restroom_keywords = ['卫生间', '洗手间', '厕所', 'toilet', 'restroom', 'washroom', 'wc']
        entry_keywords = ['入口', 'entry', 'enter', 'in']
        exit_keywords = ['出口', 'exit', 'out']

        found_restroom = False
        gender_tokens: List[str] = []
        cue_candidates: List[Tuple[float, str, str]] = []
        texts: List[str] = []

        frame_h = int(image_shape[0]) if image_shape and len(image_shape) > 0 else 0
        frame_w = int(image_shape[1]) if image_shape and len(image_shape) > 1 else 0

        for r in filtered:
            text = str(r.get('text', '')).strip()
            if not text:
                continue
            texts.append(text)
            conf = float(r.get('confidence', 0.0) or 0.0)
            norm = re.sub(r'\s+', '', text).lower()

            if any(k in norm for k in restroom_keywords):
                found_restroom = True

            if ('女' in text) or any(k in norm for k in ['female', 'women', 'ladies']):
                if '女' not in gender_tokens:
                    gender_tokens.append('女')
            if ('男' in text) or any(k in norm for k in ['male', 'men', 'gentlemen']):
                if '男' not in gender_tokens:
                    gender_tokens.append('男')
            if ('无障碍' in text) or ('accessible' in norm) or ('wheelchair' in norm):
                if '无障碍' not in gender_tokens:
                    gender_tokens.append('无障碍')

            cue_type = ''
            if any(k in norm for k in exit_keywords):
                cue_type = '出口'
            elif any(k in norm for k in entry_keywords):
                cue_type = '入口'

            if cue_type:
                direction = self._infer_direction_hint(text, r.get('bbox'), frame_w, frame_h)
                cue_candidates.append((conf, cue_type, direction))

        if cue_candidates:
            cue_candidates.sort(key=lambda x: x[0], reverse=True)
            best_type, best_dir = cue_candidates[0][1], cue_candidates[0][2]
        else:
            best_type, best_dir = '', ''

        if found_restroom:
            if gender_tokens:
                rest_desc = ''.join(gender_tokens) + '卫生间标识'
            else:
                rest_desc = '卫生间标识'
        elif best_type:
            rest_desc = '通行标识'
        else:
            rest_desc = ''

        if rest_desc and best_type and best_dir:
            message = f"识别到{rest_desc}，{best_type}在{best_dir}。"
        elif rest_desc and best_type:
            message = f"识别到{rest_desc}，请留意{best_type}方向。"
        elif rest_desc:
            message = f"识别到{rest_desc}。"
        elif best_type and best_dir:
            message = f"识别到{best_type}指引，方向在{best_dir}。"
        else:
            message = '没有识别到清晰的卫生间标识。'

        unique_texts = list(dict.fromkeys(texts))[: self.max_results]
        return {
            'texts': unique_texts,
            'message': message
        }

    def _infer_direction_hint(self, text: str, bbox: Any, frame_w: int, frame_h: int) -> str:
        """优先用箭头/方位词，其次用bbox位置推断左右前方。"""
        raw_text = str(text or '')
        if ('←' in raw_text) or ('左' in raw_text):
            return '左侧'
        if ('→' in raw_text) or ('右' in raw_text):
            return '右侧'
        if ('↑' in raw_text) or ('前' in raw_text) or ('直行' in raw_text):
            return '前方'

        if not bbox or frame_w <= 0:
            return '前方'

        try:
            if isinstance(bbox, list) and len(bbox) == 4 and isinstance(bbox[0], (list, tuple)):
                cx = (float(bbox[0][0]) + float(bbox[2][0])) / 2.0
                cy = (float(bbox[0][1]) + float(bbox[2][1])) / 2.0
            elif isinstance(bbox, (list, tuple)) and len(bbox) >= 2:
                cx = float(bbox[0])
                cy = float(bbox[1]) if frame_h > 0 else 0.0
            else:
                return '前方'
            xr = cx / max(1.0, float(frame_w))
            if xr < 0.4:
                return '左侧'
            if xr > 0.6:
                return '右侧'
            if frame_h > 0:
                yr = cy / max(1.0, float(frame_h))
                if yr < 0.35:
                    return '前上方'
            return '前方'
        except Exception:
            return '前方'

    def _deduplicate_texts(self, results: List[Dict]) -> List[Dict]:
        """去重相似的文本"""
        unique = []
        seen = set()

        for r in results:
            text = r['text'].strip()
            # 标准化文本（去除空格、统一大小写）
            normalized = re.sub(r'\s+', '', text.lower())

            if normalized and normalized not in seen:
                seen.add(normalized)
                unique.append(r)

        return unique

    def _sort_by_position(self, results: List[Dict]) -> List[Dict]:
        """按位置排序（从上到下，从左到右）"""
        def get_center_y(r):
            bbox = r['bbox']
            if len(bbox) == 4:
                # [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
                return (bbox[0][1] + bbox[2][1]) / 2
            else:
                return bbox[1] if len(bbox) > 1 else 0

        # 先按Y坐标排序（行）
        sorted_by_y = sorted(results, key=get_center_y)

        # 然后在同一行内按X坐标排序
        final_sorted = []
        i = 0
        while i < len(sorted_by_y):
            current = sorted_by_y[i]
            current_y = get_center_y(current)

            # 收集同一行的元素
            row = [current]
            j = i + 1
            while j < len(sorted_by_y):
                next_y = get_center_y(sorted_by_y[j])
                if abs(next_y - current_y) < 20:  # 同一行的判定阈值
                    row.append(sorted_by_y[j])
                    j += 1
                else:
                    break

            # 按X坐标排序行内元素
            def get_center_x(r):
                bbox = r['bbox']
                if len(bbox) == 4:
                    return (bbox[0][0] + bbox[2][0]) / 2
                else:
                    return bbox[0] if len(bbox) > 0 else 0

            row.sort(key=get_center_x)
            final_sorted.extend(row)
            i = j

        return final_sorted


class BusReader:
    """公交车路线识别器（专用）"""

    def __init__(self):
        """初始化公交车识别器"""
        self.text_reader = TextReader()

        # 公交车检测相关（可选，需要YOLO检测车头区域）
        self.bus_class_keywords = ['bus', 'coach', 'vehicle']

    def read_bus_route(self, image: np.ndarray) -> Dict[str, Any]:
        """
        识别公交车路线
        :param image: BGR格式图像
        :return: {
            'success': bool,
            'route': str,
            'message': str,
            'confidence': float
        }
        """
        if image is None:
            return {
                'success': False,
                'route': '',
                'message': '图像为空',
                'confidence': 0.0
            }

        # 直接使用OCR识别路线
        result = self.text_reader.read_text(image, mode='bus')

        return {
            'success': result['success'],
            'route': result['texts'][0] if result['texts'] else '',
            'message': result['message'],
            'confidence': 0.7 if result['success'] else 0.0
        }


# 全局实例（延迟初始化）
_ocr_instance: Optional[OCREngine] = None
_reader_instance: Optional[TextReader] = None
_bus_reader_instance: Optional[BusReader] = None


def get_ocr_engine() -> OCREngine:
    """获取OCR引擎单例"""
    global _ocr_instance
    if _ocr_instance is None:
        _ocr_instance = OCREngine()
    return _ocr_instance


def get_text_reader() -> TextReader:
    """获取文字读取器单例"""
    global _reader_instance
    if _reader_instance is None:
        _reader_instance = TextReader(get_ocr_engine())
    return _reader_instance


def get_bus_reader() -> BusReader:
    """获取公交车读取器单例"""
    global _bus_reader_instance
    if _bus_reader_instance is None:
        _bus_reader_instance = BusReader()
    return _bus_reader_instance


# 便捷函数
def read_text_from_frame(bgr_image: np.ndarray, mode: str = 'general') -> Dict[str, Any]:
    """
    从帧中读取文字的便捷函数
    :param bgr_image: BGR格式图像
    :param mode: 'general' | 'bus'
    :return: 识别结果字典
    """
    if mode == 'bus':
        return get_bus_reader().read_bus_route(bgr_image)
    else:
        return get_text_reader().read_text(bgr_image, mode=mode)


# 测试代码
if __name__ == '__main__':
    print("=" * 50)
    print("OCR模块测试")
    print("=" * 50)

    # 测试OCR引擎
    ocr = OCREngine()
    if ocr.is_available():
        print(f"OCR引擎类型: {ocr.engine_type}")
    else:
        print("OCR引擎不可用，请安装 PaddleOCR、EasyOCR 或 Tesseract")

    # 创建测试图像
    test_img = np.ones((200, 400, 3), dtype=np.uint8) * 255
    cv2.putText(test_img, "123路", (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 0), 3)

    # 测试公交车读取
    bus_reader = BusReader()
    result = bus_reader.read_bus_route(test_img)
    print(f"公交车识别结果: {result}")
