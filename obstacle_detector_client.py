# app/cloud/obstacle_detector_client.py (新文件)
import logging
import os
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("YOLO_CONFIG_DIR", os.path.join(_BASE_DIR, ".ultralytics"))
try:
    os.makedirs(os.environ["YOLO_CONFIG_DIR"], exist_ok=True)
except Exception:
    pass
import cv2
import numpy as np
import torch
from threading import Semaphore
from contextlib import contextmanager
from ultralytics import YOLO
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# --- GPU/CPU & AMP 配置 (从 blindpath 工作流迁移而来，保持一致) ---
DEVICE = os.getenv("AIGLASS_DEVICE", "cuda:0")
if DEVICE.startswith("cuda") and not torch.cuda.is_available():
    logger.warning(f"AIGLASS_DEVICE={DEVICE} 但未检测到 CUDA，将回退到 CPU")
    DEVICE = "cpu"
IS_CUDA = DEVICE.startswith("cuda")

AMP_POLICY = os.getenv("AIGLASS_AMP", "bf16").lower()
if AMP_POLICY not in ("bf16", "fp16", "off"):
    AMP_POLICY = "bf16"
AMP_DTYPE = torch.bfloat16 if AMP_POLICY == "bf16" else (torch.float16 if AMP_POLICY == "fp16" else None)

# --- GPU 并发限流 (从 blindpath 工作流迁移而来，保持一致) ---
GPU_SLOTS = int(os.getenv("AIGLASS_GPU_SLOTS", "2"))
_gpu_slots = Semaphore(GPU_SLOTS)

try:
    torch.backends.cudnn.benchmark = True
except Exception:
    pass


@contextmanager
def gpu_infer_slot():
    """统一管理 GPU 并发限流 + inference_mode + AMP autocast"""
    with _gpu_slots:
        if IS_CUDA and AMP_POLICY != "off":
            # 新式接口：torch.amp.autocast(device_type='cuda', dtype=...)
            with torch.inference_mode(), torch.amp.autocast(device_type='cuda', dtype=AMP_DTYPE):
                yield
        else:
            with torch.inference_mode():
                yield


class ObstacleDetectorClient:
    def __init__(self, model_path: str = 'models/yoloe-11l-seg.pt'):
        self.model = None
        self.whitelist_embeddings = None
        self.WHITELIST_CLASSES = [
            # === 动态类别（交通） ===
            'person',
            'bicycle', 'car', 'motorcycle', 'bus', 'truck',
            'scooter', 'stroller', 'wheelchair',

            # === 动物 ===
            'dog', 'cat', 'animal',

            # === 交通工具扩展 ===
            'taxi', 'train', 'police car', 'ambulance',

            # === 交通设施（新增） ===
            'traffic light',    # 红绿灯
            'crosswalk',        # 斑马线
            'stop sign',        # 停止标志
            'parking meter',    # 停车计时器
            'fire hydrant',     # 消防栓

            # === 静态障碍物 ===
            'pole', 'post', 'column', 'pillar', 'stanchion', 'bollard',
            'utility pole', 'telegraph pole', 'light pole', 'street pole',
            'signpost', 'support post', 'vertical post',

            # === 公共设施 ===
            'bench', 'chair', 'potted plant', 'hydrant',
            'cone', 'barrier', 'fence', 'stone', 'box',

            # === 室内导航（新增）===
            'door',             # 门
            'stairs',           # 楼梯
            'stair',            # 楼梯（单数）
            'escalator',        # 扶梯
            'elevator',         # 电梯
            'handrail',         # 扶手
            'railing',          # 栏杆

            # === 家居/办公室（新增）===
            'table',            # 桌子
            'sofa',             # 沙发
            'couch',            # 长沙发
            'bed',              # 床
            'desk',             # 书桌
            'tv',               # 电视
            'monitor',          # 显示器
            'laptop',           # 笔记本电脑
            'computer',         # 电脑

            # === 个人物品（新增）===
            'backpack',         # 背包
            'handbag',          # 手提包
            'suitcase',         # 行李箱
            'umbrella',         # 雨伞
            'cell phone',       # 手机
            'cup',              # 杯子
            'bottle',           # 瓶子
        ]
        try:
            logger.info("正在加载 YOLOE 障碍物模型...")
            self.model = YOLO(model_path)
            self.model.to(DEVICE)
            self.model.fuse()
            logger.info(f"YOLOE 障碍物模型加载成功，使用设备: {DEVICE}")

            logger.info("正在为 YOLOE 预计算白名单文本特征...")
            if IS_CUDA and AMP_DTYPE is not None:
                with torch.inference_mode(), torch.amp.autocast(device_type='cuda', dtype=AMP_DTYPE):
                    self.whitelist_embeddings = self.model.get_text_pe(self.WHITELIST_CLASSES)
            else:
                self.whitelist_embeddings = self.model.get_text_pe(self.WHITELIST_CLASSES)
            logger.info("YOLOE 特征预计算完成。")
        except Exception as e:
            logger.error(f"YOLOE 模型加载或特征计算失败: {e}", exc_info=True)
            raise
    def tensor_to_numpy_mask(mask_tensor):
        """安全地将各种类型的张量转换为 numpy 掩码"""
        # 处理不同的数据类型
        if mask_tensor.dtype in (torch.bfloat16, torch.float16):
            mask_tensor = mask_tensor.float()
        
        # 转换为 numpy
        mask = mask_tensor.cpu().numpy()
        
        # 确保是二值掩码
        if mask.max() <= 1.0:
            mask = (mask > 0.5).astype(np.uint8) * 255
        else:
            mask = mask.astype(np.uint8)
        
        return mask 
    def detect(self, image: np.ndarray, path_mask: np.ndarray = None) -> List[Dict[str, Any]]:
        """
        利用白名单作为提示词寻找障碍物。
        如果提供了 path_mask，则执行与路径相关的空间过滤。
        如果 path_mask 为 None，则进行全局检测。
        """
        if self.model is None:
            return []

        H, W = image.shape[:2]
        try:
            self.model.set_classes(self.WHITELIST_CLASSES, self.whitelist_embeddings)
        except Exception as e:
            logger.error(f"设置 YOLOE 提示词失败: {e}")
            return []

        conf_thr = float(os.getenv("AIGLASS_OBS_CONF", "0.25"))
        with gpu_infer_slot():
            results = self.model.predict(image, verbose=False, conf=conf_thr)

        if not (results and results[0].masks):
            return []

        # --- 过滤与后处理 (逻辑与 blindpath 工作流保持一致) ---
        final_obstacles = []
        num_masks = len(results[0].masks.data)
        num_boxes = len(results[0].boxes.cls) if getattr(results[0].boxes, "cls", None) is not None else 0

        for i, mask_tensor in enumerate(results[0].masks.data):
            if i >= num_boxes: continue

            # 【修复】处理 BFloat16 类型的掩码
            # 先转换为 float32，避免 numpy 不支持 BFloat16 的问题
            if mask_tensor.dtype == torch.bfloat16:
                mask_tensor = mask_tensor.float()
            
            # 转换为 numpy 数组
            mask = mask_tensor.cpu().numpy()
            
            # 处理概率掩码（值在0-1之间）或二值掩码
            if mask.max() <= 1.0:
                # 概率掩码，需要二值化
                mask = (mask > 0.5).astype(np.uint8) * 255
            else:
                # 已经是二值掩码
                mask = mask.astype(np.uint8)
            
            mask = cv2.resize(mask, (W, H), interpolation=cv2.INTER_NEAREST)
            area = np.sum(mask > 0)

            # 尺寸过滤：太大的物体（如整片地面）通常是误识别
            if (area / (H * W)) > 0.7: continue

            # 空间过滤：如果提供了 path_mask，则只保留路径上的障碍物
            if path_mask is not None:
                intersection_area = np.sum(cv2.bitwise_and(mask, path_mask) > 0)
                # 必须与路径有足够的重叠
                if intersection_area < 100 or (intersection_area / area) < 0.01:
                    continue

            cls_id = int(results[0].boxes.cls[i])
            conf = None
            try:
                if getattr(results[0].boxes, "conf", None) is not None:
                    conf = float(results[0].boxes.conf[i])
            except Exception:
                conf = None
            bbox = None
            try:
                if getattr(results[0].boxes, "xyxy", None) is not None:
                    x1, y1, x2, y2 = results[0].boxes.xyxy[i].tolist()
                    bbox = [float(x1), float(y1), float(x2), float(y2)]
            except Exception:
                bbox = None
            class_names_map = results[0].names
            class_name = "Unknown"
            if isinstance(class_names_map, dict):
                # 如果是字典，使用 .get() 方法
                class_name = class_names_map.get(cls_id, "Unknown")
            elif isinstance(class_names_map, list) and 0 <= cls_id < len(class_names_map):
                # 如果是列表，通过索引安全地获取
                class_name = class_names_map[cls_id]

            # 计算距离指标
            y_coords, x_coords = np.where(mask > 0)
            if len(y_coords) == 0: continue

            final_obstacles.append({
                'name': class_name.strip(),
                'conf': conf,
                'bbox': bbox,
                'mask': mask,
                'area': area,
                'area_ratio': area / (H * W),
                'center_x': np.mean(x_coords),
                'center_y': np.mean(y_coords),
                'bottom_y_ratio': np.max(y_coords) / H
            })

        return final_obstacles
