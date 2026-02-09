# app_main.py
# -*- coding: utf-8 -*-
import os, sys, time, json, asyncio, base64, audioop
# ---- Ultralytics 配置目录（避免在受限环境写 ~/.config）----
_REPO_DIR = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("YOLO_CONFIG_DIR", os.path.join(_REPO_DIR, ".ultralytics"))
try:
    os.makedirs(os.environ["YOLO_CONFIG_DIR"], exist_ok=True)
except Exception:
    pass
from typing import Any, Dict, Optional, Tuple, List, Callable, Set, Deque
from collections import deque
from dataclasses import dataclass
import re
# 在其它 import 之后加：
from qwen_extractor import extract_english_label
from navigation_master import NavigationMaster, OrchestratorResult 
# 新增：导入盲道导航器
from workflow_blindpath import BlindPathNavigator
# 新增：导入过马路导航器
from workflow_crossstreet import CrossStreetNavigator
import torch
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.websockets import WebSocketState
import uvicorn
import cv2
import numpy as np
from ultralytics import YOLO
from obstacle_detector_client import ObstacleDetectorClient

import torch  # 添加这行


import mediapipe as mp
import bridge_io
import threading
import yolomedia  # 确保和 app_main.py 同目录，文件名就是 yolomedia.py
# ---- Windows 事件循环策略 ----
if sys.platform.startswith("win"):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

# ---- .env ----
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# ---- DashScope ASR 基础 ----
from dashscope import audio as dash_audio  # 若未安装，会在原项目里抛错提示

API_KEY = os.getenv("DASHSCOPE_API_KEY")
if not API_KEY:
    print("[WARNING] 未设置 DASHSCOPE_API_KEY，ASR 功能将不可用")
    API_KEY = "placeholder"  # 设置占位符避免后续代码报错

MODEL        = "paraformer-realtime-v2"
SAMPLE_RATE  = 16000
AUDIO_FMT    = "pcm"
CHUNK_MS     = 20
BYTES_CHUNK  = SAMPLE_RATE * CHUNK_MS // 1000 * 2
SILENCE_20MS = bytes(BYTES_CHUNK)

# ---- 引入我们的模块 ----
from audio_stream import (
    register_stream_route,         # 挂 /stream.wav
    broadcast_pcm16_realtime,      # 实时向连接分发 16k PCM
    hard_reset_audio,              # 音频+AI 播放总闸
    BYTES_PER_20MS_16K,
    is_playing_now,
    current_ai_task,
)
# ========== 大模型 AI 对话相关（已禁用）==========
# 当前版本：不使用大模型，注释掉 omni_client 相关代码
# 如需启用，需要��消下方注释并安装 dashscope/openai 包
#
# from omni_client import stream_chat, OmniStreamPiece
# ================================================
from asr_core import (
    ASRCallback,
    set_current_recognition,
    stop_current_recognition,
)
from audio_player import (
    initialize_audio_system,
    play_voice_text,
    play_structured_voice,
    warmup_voice_texts,
    run_startup_audio_selfcheck,
)
from event_logger import get_event_logger

# ---- 新功能模块 ----
# 颜色识别模块
from color_recognition import detect_color_from_frame
# 夜间模式检测模块
from night_mode import get_night_detector, set_night_mode_callback
# OCR/读字模块
from text_reader import read_text_from_frame
# 语音调度器和风险评估
from voice_scheduler import get_voice_scheduler, VoiceScheduler, get_risk_assessor
# 朋友/人脸识别（本地离线优先）
from face_friend_recognition import FaceFriendRecognizer
# 灯光关闭提醒（轻量启发式）
from light_reminder import get_light_detector
# 语义输出模块（Top3 + 去冗余 + 模板生成）
from semantic_output import get_semantic_engine
from structured_voice import NAME_ZH as STRUCTURED_NAME_ZH
# 物品搜索增强模块
from item_search_enhancer import (
    get_item_search_enhancer,
    start_item_search as enhancer_start_search,
    update_item_detection,
    mark_item_found as enhancer_mark_found,
    stop_item_search as enhancer_stop_search
)
# 音乐搜索模块
from music_controller import (
    get_music_searcher,
    get_music_player,
    search_music,
    format_song_list,
    SongInfo
)

# ---- 同步录制器 ----
import sync_recorder
import signal
import atexit

# ---- IMU UDP ----
UDP_IP   = "0.0.0.0"
UDP_PORT = 12345

app = FastAPI()

# ====== 状态与容器 ======
# 静态文件服务（如果 static 目录存在）
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")
else:
    print("[WARNING] static/ 目录不存在，Web UI 功能将不可用")

ui_clients: Dict[int, WebSocket] = {}
current_partial: str = ""
recent_finals: List[str] = []
RECENT_MAX = 50
last_frames: Deque[Tuple[float, bytes]] = deque(maxlen=10)

camera_viewers: Set[WebSocket] = set()
esp32_camera_ws: Optional[WebSocket] = None
imu_ws_clients: Set[WebSocket] = set()
esp32_audio_ws: Optional[WebSocket] = None

# 【新增】盲道导航相关全局变量
blind_path_navigator = None
navigation_active = False
yolo_seg_model = None
obstacle_detector = None

# 【新增】过马路导航相关全局变量
cross_street_navigator = None
cross_street_active = False
orchestrator = None  # 新增

# 【新增】omni对话状态标志（已禁用，不使用大模型）
# omni_conversation_active = False  # 标记omni对话是否正在进行
# omni_previous_nav_state = None  # 保存omni激活前的导航状态，用于恢复

# 【新增】ESP32命令WebSocket连接（用于发送LED控制等指令）
esp32_cmd_ws: Optional[WebSocket] = None
esp32_cmd_lock = asyncio.Lock()

# 【新增】夜间模式检测器
night_detector = None
night_mode_enabled = True  # 是否启用自动夜间检测

# 【新增】语音调度器
voice_scheduler = None

# 【新增】物品搜索增强器
item_search_enhancer = None

# 【新增】朋友/人脸识别器
face_friend_recognizer: Optional[FaceFriendRecognizer] = None

# 【新增】灯光关闭提醒
light_detector = None
light_reminder_enabled = False

# 【新增】户外天黑提醒（夜间户外提醒用户开灯让别人知道是盲人）
night_light_reminder_enabled = os.getenv("AIGLASS_NIGHT_LIGHT_REMINDER", "1") == "1"
night_light_reminder_cooldown = float(os.getenv("AIGLASS_NIGHT_LIGHT_COOLDOWN", "600"))  # 10分钟冷却
last_night_light_remind_time = 0.0

# 【新增】自动场景识别（接收到画面后自动运行检测并主动播报）
auto_scene_detection = os.getenv("AIGLASS_AUTO_SCENE_DETECTION", "1") == "1"
auto_detection_interval = float(os.getenv("AIGLASS_AUTO_DETECTION_INTERVAL", "3.0"))  # 检测间隔（秒）
last_auto_detection_time = 0.0
current_detected_scene = "unknown"  # blindpath / crosswalk / obstacle / traffic_light / unknown

# 【新增】场景探索 / 语义输出
semantic_engine = None
scene_exploration_enabled = False
last_semantic_emit_ts = 0.0
semantic_emit_interval_sec = float(os.getenv("AIGLASS_SEM_PERIOD_SEC", "3.0"))

# 【新增】实时物体播报（输入实时帧后自动播报）
realtime_object_announce_enabled = os.getenv("AIGLASS_REALTIME_OBJECT_ANNOUNCE", "1") == "1"
realtime_object_announce_interval = float(os.getenv("AIGLASS_REALTIME_OBJECT_PERIOD_SEC", "2.5"))
last_realtime_object_announce_ts = 0.0

# 【新增】事件记录器（JSONL，用于回放/评估）
event_logger = None


def _build_realtime_object_announce_text(out: Dict[str, Any]) -> str:
    """从语义输出构建实时物体播报文本（优先简洁、可执行）。"""
    if not isinstance(out, dict):
        return ""

    objs = out.get("objects") or []
    if not objs:
        return ""

    top = objs[0] if isinstance(objs[0], dict) else {}
    direction = top.get("direction") if isinstance(top.get("direction"), dict) else {}
    distance = top.get("distance") if isinstance(top.get("distance"), dict) else {}

    name_zh = str(top.get("name_zh") or top.get("name") or "物体").strip() or "物体"

    clock = direction.get("clock")
    lr_zh = str(direction.get("lr_zh") or "").strip()

    direction_text = ""
    if clock:
        direction_text = f"{clock}点方向"
    elif lr_zh:
        direction_text = lr_zh
    else:
        direction_text = "前方"

    use_steps = os.getenv("AIGLASS_DISTANCE_FORMAT", "steps").lower() == "steps"
    distance_text = ""
    if use_steps:
        steps = distance.get("steps") or top.get("distance_steps")
        if steps is not None:
            try:
                distance_text = f"约{max(1, int(round(float(steps))))}步"
            except Exception:
                distance_text = ""
    else:
        meters = distance.get("meters") or top.get("distance_m")
        if meters is not None:
            try:
                m = float(meters)
                distance_text = f"{m:.0f}米" if m >= 1 else f"{m:.1f}米"
            except Exception:
                distance_text = ""

    urgency = str(top.get("urgency") or "").upper()
    action = str(top.get("action") or top.get("avoidance_action") or "").strip().rstrip("。")

    prefix = ""
    if urgency == "HIGH":
        prefix = "紧急，"
    elif urgency == "MEDIUM":
        prefix = "注意，"

    base = f"{prefix}{direction_text}"
    if distance_text:
        base += distance_text
    base += f"有{name_zh}"
    if action:
        base += f"，{action}"
    return base


def _build_whitelist_voice_phrases() -> List[str]:
    """基于白名单构建详细预设语音语料（含方向/距离/行动建议模板）。"""
    classes: List[str] = []
    try:
        from obstacle_detector_client import DEFAULT_WHITELIST_CLASSES
        classes = list(DEFAULT_WHITELIST_CLASSES)
    except Exception:
        classes = []

    zh_map = dict(STRUCTURED_NAME_ZH or {})
    scene_prefixes = ["街道环境", "人行道上", "室内环境", "路口附近"]
    direction_phrases = ["前方", "左侧", "右侧", "12点方向", "3点方向", "9点方向"]
    distance_phrases = ["约一步", "约两步", "约三步", "1米", "2米", "3米"]
    action_phrases = ["保持直行", "请从侧面绕开", "注意避让", "先停一下"]

    dynamic_set = {
        "person", "bicycle", "car", "motorcycle", "bus", "truck", "scooter",
        "dog", "cat", "animal", "taxi", "train", "police car", "ambulance",
    }
    hazard_set = {
        "crosswalk", "traffic light", "stop sign", "stairs", "stair", "escalator",
        "elevator", "cone", "barrier", "fence", "stone", "box",
    }

    phrases: List[str] = []
    seen: Set[str] = set()

    def add(text: str):
        t = (text or "").strip()
        if not t or t in seen:
            return
        seen.add(t)
        phrases.append(t)

    add("已开启实时物体播报")
    add("已关闭实时物体播报")
    add("实时物体播报已启动")
    add("当前画面未检测到白名单物体")

    for cls in classes:
        key = str(cls or "").strip().lower()
        if not key:
            continue
        name_zh = zh_map.get(key) or key

        add(f"检测到{name_zh}")
        add(f"前方有{name_zh}")
        add(f"{name_zh}在附近")

        for d in direction_phrases:
            add(f"{d}有{name_zh}")
            add(f"{d}检测到{name_zh}")

        for dist in distance_phrases:
            add(f"前方{dist}有{name_zh}")
            add(f"{dist}处有{name_zh}")

        for d in direction_phrases[:3]:
            for dist in distance_phrases[:4]:
                add(f"{d}{dist}有{name_zh}")

        for scene in scene_prefixes:
            add(f"{scene}，前方有{name_zh}")

        if key in dynamic_set:
            add(f"注意，{name_zh}正在靠近")
            add(f"{name_zh}靠近，请注意避让")
            add(f"{name_zh}在移动，注意安全")

        if key in hazard_set:
            add(f"注意{name_zh}，请减速")
            add(f"{name_zh}在前方，请谨慎通行")

        for action in action_phrases:
            add(f"发现{name_zh}，{action}")

    return phrases


def _warmup_object_voice_assets_in_background() -> None:
    """后台预生成白名单物体相关语音，减少实时播报首次延迟。"""
    def _runner():
        try:
            phrases = _build_whitelist_voice_phrases()
            generated = warmup_voice_texts(phrases, max_items=int(os.getenv("AIGLASS_OBJECT_VOICE_PREGEN_MAX", "2000")))
            print(f"[VOICE] 白名单物体预设语音准备完成: total={len(phrases)}, generated={generated}")
        except Exception as e:
            print(f"[VOICE] 白名单物体预设语音准备失败: {e}")

    threading.Thread(target=_runner, daemon=True).start()

# 【新增】模型加载函数
def load_navigation_models():
    """加载盲道导航所需的模型"""
    global yolo_seg_model, obstacle_detector

    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        default_seg_model_path = os.path.join(base_dir, "model", "yolo-seg.pt")
        seg_model_path = os.getenv("BLIND_PATH_MODEL", default_seg_model_path)
        #print(f"[NAVIGATION] 尝试加载模型: {seg_model_path}")

        if os.path.exists(seg_model_path):
            print(f"[NAVIGATION] 模型文件存在，开始加载...")
            yolo_seg_model = YOLO(seg_model_path)

            # 强制放到 GPU
            if torch.cuda.is_available():
                yolo_seg_model.to("cuda")
                print(f"[NAVIGATION] 盲道分割模型加载成功并放到GPU: {yolo_seg_model.device}")
            else:
                print("[NAVIGATION] CUDA不可用，模型仍在CPU")

            # 测试模型是否能正常运行
            try:
                test_img = np.zeros((640, 640, 3), dtype=np.uint8)
                results = yolo_seg_model.predict(
                    test_img,
                    device="cuda" if torch.cuda.is_available() else "cpu",
                    verbose=False
                )
                print(f"[NAVIGATION] 模型测试成功，支持的类别数: {len(yolo_seg_model.names) if hasattr(yolo_seg_model, 'names') else '未知'}")
                if hasattr(yolo_seg_model, 'names'):
                    print(f"[NAVIGATION] 模型类别: {yolo_seg_model.names}")
            except Exception as e:
                print(f"[NAVIGATION] 模型测试失败: {e}")
        else:
            print(f"[NAVIGATION] 错误：找不到模型文件: {seg_model_path}")
            print(f"[NAVIGATION] 当前工作目录: {os.getcwd()}")
            print(f"[NAVIGATION] 请检查文件路径是否正确")
            
        # 【修改开始】使用 ObstacleDetectorClient 替代直接的 YOLO
        default_obstacle_model_path = os.path.join(base_dir, "model", "yoloe-11l-seg.pt")
        obstacle_model_path = os.getenv("OBSTACLE_MODEL", default_obstacle_model_path)
        print(f"[NAVIGATION] 尝试加载障碍物检测模型: {obstacle_model_path}")
        
        if os.path.exists(obstacle_model_path):
            print(f"[NAVIGATION] 障碍物检测模型文件存在，开始加载...")
            try:
                # 使用 ObstacleDetectorClient 封装的 YOLO-E
                obstacle_detector = ObstacleDetectorClient(model_path=obstacle_model_path)
                print(f"[NAVIGATION] ========== YOLO-E 障碍物检测器加载成功 ==========")
                
                # 检查模型是否成功加载
                if hasattr(obstacle_detector, 'model') and obstacle_detector.model is not None:
                    print(f"[NAVIGATION] YOLO-E 模型已初始化")
                    print(f"[NAVIGATION] 模型设备: {next(obstacle_detector.model.parameters()).device}")
                else:
                    print(f"[NAVIGATION] 警告：YOLO-E 模型初始化异常")
                
                # 检查白名单是否成功加载
                if hasattr(obstacle_detector, 'WHITELIST_CLASSES'):
                    print(f"[NAVIGATION] 白名单类别数: {len(obstacle_detector.WHITELIST_CLASSES)}")
                    print(f"[NAVIGATION] 白名单前10个类别: {', '.join(obstacle_detector.WHITELIST_CLASSES[:10])}")
                else:
                    print(f"[NAVIGATION] 警告：白名单类别未定义")
                
                # 检查文本特征是否成功预计算
                if hasattr(obstacle_detector, 'whitelist_embeddings') and obstacle_detector.whitelist_embeddings is not None:
                    print(f"[NAVIGATION] YOLO-E 文本特征已预计算")
                    print(f"[NAVIGATION] 文本特征张量形状: {obstacle_detector.whitelist_embeddings.shape if hasattr(obstacle_detector.whitelist_embeddings, 'shape') else '未知'}")
                else:
                    print(f"[NAVIGATION] 警告：YOLO-E 文本特征未预计算")
                
                # 测试障碍物检测功能
                print(f"[NAVIGATION] 开始测试 YOLO-E 检测功能...")
                try:
                    test_img = np.zeros((640, 640, 3), dtype=np.uint8)
                    # 在测试图像中画一个白色矩形，模拟一个物体
                    cv2.rectangle(test_img, (200, 200), (400, 400), (255, 255, 255), -1)
                    
                    # 测试检测（不提供 path_mask）
                    test_results = obstacle_detector.detect(test_img)
                    print(f"[NAVIGATION] YOLO-E 检测测试成功!")
                    print(f"[NAVIGATION] 测试检测结果数: {len(test_results)}")
                    
                    if len(test_results) > 0:
                        print(f"[NAVIGATION] 测试检测到的物体:")
                        for i, obj in enumerate(test_results):
                            print(f"  - 物体 {i+1}: {obj.get('name', 'unknown')}, "
                                  f"面积比例: {obj.get('area_ratio', 0):.3f}, "
                                  f"位置: ({obj.get('center_x', 0):.0f}, {obj.get('center_y', 0):.0f})")
                except Exception as e:
                    print(f"[NAVIGATION] YOLO-E 检测测试失败: {e}")
                    import traceback
                    traceback.print_exc()
                
                print(f"[NAVIGATION] ========== YOLO-E 障碍物检测器加载完成 ==========")
                
            except Exception as e:
                print(f"[NAVIGATION] 障碍物检测器加载失败: {e}")
                import traceback
                traceback.print_exc()
                obstacle_detector = None
        else:
            print(f"[NAVIGATION] 警告：找不到障碍物检测模型文件: {obstacle_model_path}")
        
    except Exception as e:
        print(f"[NAVIGATION] 模型加载失败: {e}")
        import traceback
        traceback.print_exc()

# 在程序启动时加载模型
print("[NAVIGATION] 开始加载导航模型...")
load_navigation_models()
print(f"[NAVIGATION] 模型加载完成 - yolo_seg_model: {yolo_seg_model is not None}")

# 【已禁用】启动同步录制 - 已注释以减少数据传输占用
# print("[RECORDER] 启动同步录制系统...")
# sync_recorder.start_recording()
# print("[RECORDER] 录制系统已启动，将自动保存视频和音频")

# 【已禁用】注册退出处理器，确保Ctrl+C时保存录制文件
# def cleanup_on_exit():
#     """程序退出时的清理工作"""
#     print("\n[SYSTEM] 正在关闭录制器...")
#     try:
#         sync_recorder.stop_recording()
#         print("[SYSTEM] 录制文件已保存")
#     except Exception as e:
#         print(f"[SYSTEM] 关闭录制器时出错: {e}")
#
# def signal_handler(sig, frame):
#     """处理Ctrl+C信号"""
#     print("\n[SYSTEM] 收到中断信号，正在安全退出...")
#     cleanup_on_exit()
#     import sys
#     sys.exit(0)
#
# # 注册信号处理器
# signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
# signal.signal(signal.SIGTERM, signal_handler)  # 终止信号
# atexit.register(cleanup_on_exit)  # 正常退出时也调用

# print("[RECORDER] 已注册退出处理器 - Ctrl+C时会自动保存录制文件")



# 【新增】预加载红绿灯检测模型（避免进入WAIT_TRAFFIC_LIGHT状态时卡顿）
try:
    import trafficlight_detection
    print("[TRAFFIC_LIGHT] 开始预加载红绿灯检测模型...")
    if trafficlight_detection.init_model():
        print("[TRAFFIC_LIGHT] 红绿灯检测模型预加载成功")
        # 执行一次测试推理，完全预热模型
        try:
            test_img = np.zeros((640, 640, 3), dtype=np.uint8)
            _ = trafficlight_detection.process_single_frame(test_img)
            print("[TRAFFIC_LIGHT] 模型预热完成")
        except Exception as e:
            print(f"[TRAFFIC_LIGHT] 模型预热失败: {e}")
    else:
        print("[TRAFFIC_LIGHT] 红绿灯检测模型预加载失败")
except Exception as e:
    print(f"[TRAFFIC_LIGHT] 红绿灯模型预加载出错: {e}")

# ============== 关键：系统级"硬重置"总闸 =================
interrupt_lock = asyncio.Lock()

# ============== YOLO媒体线程管理 =================
yolomedia_thread: Optional[threading.Thread] = None
yolomedia_stop_event = threading.Event()
yolomedia_running = False
yolomedia_sending_frames = False  # 新增：标记YOLO是否已经开始发送处理后的帧

# 物品名称到YOLO类别的映射
ITEM_TO_CLASS_MAP = {
    "红牛": "Red_Bull",
    "AD钙奶": "AD_milk",
    "ad钙奶": "AD_milk",
    "钙奶": "AD_milk",
}

async def ui_broadcast_raw(msg: str):
    dead = []
    for k, ws in list(ui_clients.items()):
        try:
            await ws.send_text(msg)
        except Exception:
            dead.append(k)
    for k in dead:
        ui_clients.pop(k, None)


async def ui_broadcast_partial(text: str):
    global current_partial
    current_partial = text
    await ui_broadcast_raw("PARTIAL:" + text)

async def ui_broadcast_final(text: str):
    global current_partial, recent_finals
    current_partial = ""
    recent_finals.append(text)
    if len(recent_finals) > RECENT_MAX:
        recent_finals = recent_finals[-RECENT_MAX:]
    await ui_broadcast_raw("FINAL:" + text)
    print(f"[ASR/AI FINAL] {text}", flush=True)
    # 【已禁用】记录结构化事件（不影响主流程）
    # try:
    #     if event_logger is not None:
    #         m = re.match(r"^\\[(.*?)\\]\\s*", text or "")
    #         tag = m.group(1) if m else None
    #         st = orchestrator.get_state() if orchestrator else None
    #         event_logger.log(
    #             {
    #                 "type": "ui_final",
    #                 "tag": tag,
    #                 "text": text,
    #                 "state": st,
    #                 "imu_yaw_deg": globals().get("latest_yaw_deg"),
    #                 "imu_yaw_rate_dps": globals().get("latest_yaw_rate_dps"),
    #             }
    #         )
    # except Exception:
    #     pass

async def full_system_reset(reason: str = ""):
    """
    回到刚启动后的状态：
    1) 停播 + 取消AI任务 + 切断所有/stream.wav（hard_reset_audio）
    2) 停止 ASR 实时识别流（关键）
    3) 清 UI 状态
    4) 清最近相机帧（避免把旧帧又拼进下一轮）
    5) 告知 ESP32：RESET（可选）
    """
    # 1) 音频&AI
    await hard_reset_audio(reason or "full_system_reset")

    # 2) ASR
    await stop_current_recognition()

    # 3) UI
    global current_partial, recent_finals
    current_partial = ""
    recent_finals = []

    # 4) 相机帧
    try:
        last_frames.clear()
    except Exception:
        pass

    # 5) 通知 ESP32
    try:
        if esp32_audio_ws and (esp32_audio_ws.client_state == WebSocketState.CONNECTED):
            await esp32_audio_ws.send_text("RESET")
    except Exception:
        pass

    print("[SYSTEM] full reset done.", flush=True)

# ========= 启动/停止 YOLO 媒体处理 =========
def start_yolomedia_with_target(target_name: str):
    """启动yolomedia线程，搜索指定物品"""
    global yolomedia_thread, yolomedia_stop_event, yolomedia_running, yolomedia_sending_frames
    
    # 如果已经在运行，先停止
    if yolomedia_running:
        stop_yolomedia()
    
    # 查找对应的YOLO类别
    yolo_class = ITEM_TO_CLASS_MAP.get(target_name, target_name)
    print(f"[YOLOMEDIA] Starting with target: {target_name} -> YOLO class: {yolo_class}", flush=True)
    print(f"[YOLOMEDIA] Available mappings: {ITEM_TO_CLASS_MAP}", flush=True)  # 添加这行调试
    
    yolomedia_stop_event.clear()
    yolomedia_running = True
    yolomedia_sending_frames = False  # 重置发送帧状态
    
    def _run():
        try:
            # 传递目标类别名和停止事件
            yolomedia.main(headless=True, prompt_name=yolo_class, stop_event=yolomedia_stop_event)
        except Exception as e:
            print(f"[YOLOMEDIA] worker stopped: {e}", flush=True)
        finally:
            global yolomedia_running, yolomedia_sending_frames
            yolomedia_running = False
            yolomedia_sending_frames = False
    
    yolomedia_thread = threading.Thread(target=_run, daemon=True)
    yolomedia_thread.start()
    print(f"[YOLOMEDIA] background worker started for: {yolo_class}（正在初始化，暂时显示原始画面）", flush=True)

def stop_yolomedia():
    """停止yolomedia线程"""
    global yolomedia_thread, yolomedia_stop_event, yolomedia_running, yolomedia_sending_frames
    
    if yolomedia_running:
        print("[YOLOMEDIA] Stopping worker...", flush=True)
        yolomedia_stop_event.set()
        
        # 等待线程结束（最多等5秒）
        if yolomedia_thread and yolomedia_thread.is_alive():
            yolomedia_thread.join(timeout=5.0)
        
        yolomedia_running = False
        yolomedia_sending_frames = False
        
        # 【新增】如果orchestrator在找物品模式，结束时不自动恢复（由命令控制）
        # 只清理标志位即可
        print("[YOLOMEDIA] Worker stopped, 等待状态切换.", flush=True)

# ========= 自定义的 start_ai_with_text，支持识别特殊命令 =========
async def start_ai_with_text_custom(user_text: str):
    """扩展版的AI启动函数，支持识别特殊命令"""
    global navigation_active, blind_path_navigator, cross_street_active, cross_street_navigator, orchestrator, night_detector
    
    # 【修改】在导航模式和红绿灯检测模式下，只有特定词才进入omni对话
    if orchestrator:
        current_state = orchestrator.get_state()
        # 如果在导航模式或红绿灯检测模式（非CHAT模式）
        if current_state not in ["CHAT", "IDLE"]:
            # 检查是否是允许的对话触发词
            allowed_keywords = ["帮我看", "帮我看下", "帮我找", "找一下", "看看", "识别一下"]
            is_allowed_query = any(keyword in user_text for keyword in allowed_keywords)

            # 允许在导航中触发的本地命令（不走 omni）
            local_allow_patterns = [
                r"^(这是|记住|认识|他叫|她叫|名叫|把他记成|把她记成)\\s*",
                r"^(忘记|删除|移除)\\s*",
                r"(这是谁|谁在我面前|识别朋友|识别人脸|朋友列表|有哪些朋友|我认识谁)",
                r"(检查灯|灯关了吗|提醒我关灯|关灯提醒)",
                r"(描述周围|周围有什么|场景探索|环境描述|语义描述)",
            ]
            is_local_allowed = any(re.search(p, user_text) for p in local_allow_patterns)
            
            # 检查是否是导航控制命令
            nav_control_keywords = ["开始过马路", "过马路结束", "开始导航", "盲道导航", "停止导航", "结束导航", 
                                   "检测红绿灯", "看红绿灯", "停止检测", "停止红绿灯"]
            is_nav_control = any(keyword in user_text for keyword in nav_control_keywords)
            
            # 如果既不是允许的查询，也不是导航控制命令，则丢弃
            if not is_allowed_query and not is_nav_control and not is_local_allowed:
                mode_name = "红绿灯检测" if current_state == "TRAFFIC_LIGHT_DETECTION" else "导航"
                print(f"[{mode_name}模式] 丢弃非对话语音: {user_text}")
                return  # 直接丢弃，不进入omni
    
    # 【修改】检查是否是过马路相关命令 - 使用orchestrator控制
    if "开始过马路" in user_text or "帮我过马路" in user_text:
        # 【新增】如果正在找物品，先停止
        if yolomedia_running:
            stop_yolomedia()
            print("[ITEM_SEARCH] 从找物品模式切换到过马路")
        
        if orchestrator:
            orchestrator.start_crossing()
            print(f"[CROSS_STREET] 过马路模式已启动，状态: {orchestrator.get_state()}")
            # 播放启动语音并广播到UI
            play_voice_text("过马路模式已启动。")
            await ui_broadcast_final("[系统] 过马路模式已启动")
        else:
            print("[CROSS_STREET] 警告：导航统领器未初始化！")
            play_voice_text("启动过马路模式失败，请稍后重试。")
            await ui_broadcast_final("[系统] 导航系统未就绪")
        return
    
    if "过马路结束" in user_text or "结束过马路" in user_text:
        if orchestrator:
            orchestrator.stop_navigation()
            print(f"[CROSS_STREET] 导航已停止，状态: {orchestrator.get_state()}")
            # 播放停止语音并广播到UI
            play_voice_text("已停止导航。")
            await ui_broadcast_final("[系统] 过马路模式已停止")
        else:
            await ui_broadcast_final("[系统] 导航系统未运行")
        return
    
    # 【修改】检查是否是红绿灯检测命令 - 实现与盲道导航互斥
    if "检测红绿灯" in user_text or "看红绿灯" in user_text:
        try:
            import trafficlight_detection
            
            # 切换orchestrator到红绿灯检测模式（暂停盲道导航）
            if orchestrator:
                orchestrator.start_traffic_light_detection()
                print(f"[TRAFFIC] 切换到红绿灯检测模式，状态: {orchestrator.get_state()}")
            
            # 【改进】使用主线程模式而不是独立线程，避免掉帧
            success = trafficlight_detection.init_model()  # 只初始化模型，不启动线程
            trafficlight_detection.reset_detection_state()  # 重置状态
            
            if success:
                await ui_broadcast_final("[系统] 红绿灯检测已启动")
            else:
                await ui_broadcast_final("[系统] 红绿灯模型加载失败")
        except Exception as e:
            print(f"[TRAFFIC] 启动红绿灯检测失败: {e}")
            await ui_broadcast_final(f"[系统] 启动失败: {e}")
        return
    
    if "停止检测" in user_text or "停止红绿灯" in user_text:
        try:
            # 恢复到对话模式
            if orchestrator:
                orchestrator.stop_navigation()  # 回到CHAT模式
                print(f"[TRAFFIC] 红绿灯检测停止，恢复到{orchestrator.get_state()}模式")
            
            await ui_broadcast_final("[系统] 红绿灯检测已停止")
        except Exception as e:
            print(f"[TRAFFIC] 停止红绿灯检测失败: {e}")
            await ui_broadcast_final(f"[系统] 停止失败: {e}")
        return
    
    # 【修改】检查是否是导航相关命令 - 使用orchestrator控制
    if "开始导航" in user_text or "盲道导航" in user_text or "帮我导航" in user_text:
        # 【新增】如果正在找物品，先停止
        if yolomedia_running:
            stop_yolomedia()
            print("[ITEM_SEARCH] 从找物品模式切换到盲道导航")
        
        if orchestrator:
            orchestrator.start_blind_path_navigation()
            print(f"[NAVIGATION] 盲道导航已启动，状态: {orchestrator.get_state()}")
            await ui_broadcast_final("[系统] 盲道导航已启动")
        else:
            print("[NAVIGATION] 警告：导航统领器未初始化！")
            await ui_broadcast_final("[系统] 导航系统未就绪")
        return
    
    if "停止导航" in user_text or "结束导航" in user_text:
        if orchestrator:
            orchestrator.stop_navigation()
            print(f"[NAVIGATION] 导航已停止，状态: {orchestrator.get_state()}")
            await ui_broadcast_final("[系统] 盲道导航已停止")
        else:
            await ui_broadcast_final("[系统] 导航系统未运行")
        return

    nav_cmd_keywords = ["开始过马路", "过马路结束", "开始导航", "盲道导航", "停止导航", "结束导航", "立即通过", "现在通过", "继续"]
    if any(k in user_text for k in nav_cmd_keywords):
        if orchestrator:
            orchestrator.on_voice_command(user_text)
            await ui_broadcast_final("[系统] 导航模式已更新")
        else:
            await ui_broadcast_final("[系统] 导航统领器未初始化")
        return    

    # 检查是否是"帮我找/识别一下xxx"的命令
    # 扩展正则表达式，支持更多关键词和多目标（用"和/以及/还有/并且/，/、"分隔）
    find_pattern = r"(?:^\s*帮我)?\s*找一下\s*(.+?)(?:。|！|？|$)"
    match = re.search(find_pattern, user_text)

    if match:
        # 提取中文物品名称（支持多目标）
        items_text = match.group(1).strip()

        # 分割多个物品（支持：和、以及、还有、并且、，、、）
        separators = r'[和以及还有并且，、、]'
        items_cn = re.split(separators, items_text)
        items_cn = [item.strip() for item in items_cn if item.strip()]

        print(f"[COMMAND] Finder request: {items_cn}", flush=True)

        # 为每个物品提取英文类名
        labels_en = []
        for item_cn in items_cn:
            label_en, src = extract_english_label(item_cn)
            labels_en.append(label_en)
            print(f"[COMMAND]   '{item_cn}' -> '{label_en}' (src={src})", flush=True)

        # 【新增】使用物品搜索增强器
        if item_search_enhancer:
            item_search_enhancer.start_search(items_cn, labels_en)
            print(f"[ITEM_SEARCH] 启动增强搜索，目标数量: {len(items_cn)}")

        # 【新增】切换到找物品模式（暂停导航）
        if orchestrator:
            orchestrator.start_item_search()
            print(f"[ITEM_SEARCH] 已切换到找物品模式，状态: {orchestrator.get_state()}")

        # 【关键】把第一个英文类名传给 yolomedia
        start_yolomedia_with_target(labels_en[0] if labels_en else "unknown")

        # 给前端/语音来个确认反馈
        try:
            if len(items_cn) == 1:
                await ui_broadcast_final(f"[找物品] 正在寻找 {items_cn[0]}...")
            else:
                await ui_broadcast_final(f"[找物品] 开始寻找：{'、'.join(items_cn)}，共{len(items_cn)}个目标。")
        except Exception:
            pass

        return

    # 检查是否是"找到了"的命令
    if "找到了" in user_text or "拿到了" in user_text:
        print("[COMMAND] Found command detected", flush=True)
        # 停止yolomedia
        stop_yolomedia()
        
        # 【新增】停止找物品模式，恢复之前的导航状态
        if orchestrator:
            orchestrator.stop_item_search(restore_nav=True)
            current_state = orchestrator.get_state()
            print(f"[ITEM_SEARCH] 找物品结束，当前状态: {current_state}")
            
            # 根据恢复的状态给出反馈
            if current_state in ["BLINDPATH_NAV", "SEEKING_CROSSWALK", "WAIT_TRAFFIC_LIGHT", "CROSSING", "SEEKING_NEXT_BLINDPATH"]:
                await ui_broadcast_final("[找物品] 已找到物品，继续导航。")
            else:
                await ui_broadcast_final("[找物品] 已找到物品。")
        else:
            await ui_broadcast_final("[找物品] 已找到物品。")
        
        return

    # ====== 新增命令：颜色识别 ======
    color_keywords = ["这个是什么���色", "帮我看颜色", "看下颜色", "颜色识别", "这是啥颜色", "是什么颜色"]
    if any(kw in user_text for kw in color_keywords):
        print("[COLOR] 颜色识别命令触发", flush=True)

        # 获取最新帧
        if last_frames:
            try:
                _, jpeg_bytes = last_frames[-1]
                arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
                bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)

                if bgr is not None and bgr.size > 0:
                    # 执行颜色识别
                    result = detect_color_from_frame(bgr)
                    print(f"[COLOR] 识别结果: {result}")

                    # UI播报
                    await ui_broadcast_final(f"[AI] {result['message']}")
                    # 语音播报
                    play_voice_text(result['message'])
                else:
                    await ui_broadcast_final("[AI] 无法获取画面，请检查摄像头。")
            except Exception as e:
                print(f"[COLOR] 颜色识别失败: {e}")
                await ui_broadcast_final(f"[AI] 颜色识别失败: {e}")
        else:
            await ui_broadcast_final("[AI] 暂无画面，请稍后再试。")
        return

    # ====== 新增命令：OCR/读字 ======
    ocr_keywords = ["读一下这上面写的什么", "识别文字", "读字", "读一下", "这是什么字", "写的是什么"]
    if any(kw in user_text for kw in ocr_keywords):
        print("[OCR] 通用读字命令触发", flush=True)

        # 获取最新帧
        if last_frames:
            try:
                _, jpeg_bytes = last_frames[-1]
                arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
                bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)

                if bgr is not None and bgr.size > 0:
                    # 执行OCR
                    result = read_text_from_frame(bgr, mode='general')
                    print(f"[OCR] 识别结果: {result}")

                    # UI播报
                    await ui_broadcast_final(f"[AI] {result['message']}")
                    # 语音播报
                    play_voice_text(result['message'])
                else:
                    await ui_broadcast_final("[AI] 无法获取画面，请检查摄像头。")
            except Exception as e:
                print(f"[OCR] 读字失败: {e}")
                await ui_broadcast_final(f"[AI] 读字失败: {e}")
        else:
            await ui_broadcast_final("[AI] 暂无画面，请稍后再试。")
        return

    # ====== 新增命令：公交车路线识别 ======
    bus_keywords = ["公交车来了是哪一路", "帮我看公交几路", "这是几路车", "公交车是几路", "几路公交"]
    if any(kw in user_text for kw in bus_keywords):
        print("[OCR] 公交车路线识别命令触发", flush=True)

        # 获取最新帧
        if last_frames:
            try:
                _, jpeg_bytes = last_frames[-1]
                arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
                bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)

                if bgr is not None and bgr.size > 0:
                    # 执行公交车OCR
                    result = read_text_from_frame(bgr, mode='bus')
                    print(f"[OCR] 公交识别结果: {result}")

                    # UI播报
                    await ui_broadcast_final(f"[AI] {result['message']}")
                    # 语音播报
                    play_voice_text(result['message'])
                else:
                    await ui_broadcast_final("[AI] 无法获取画面，请检查摄像头。")
            except Exception as e:
                print(f"[OCR] 公交识别失败: {e}")
                await ui_broadcast_final(f"[AI] 公交识别失败: {e}")
        else:
            await ui_broadcast_final("[AI] 暂无画面，请稍后再试。")
        return

    # ====== 新增命令：朋友/人脸识别 ======
    global face_friend_recognizer
    face_recog_keywords = ["这是谁", "谁在我面前", "这人是谁", "识别朋友", "识别人脸", "认一下这个人", "认一下人", "认识他吗", "认识她吗"]
    if any(kw in user_text for kw in face_recog_keywords):
        if face_friend_recognizer is None:
            await ui_broadcast_final("[AI] 人脸识别模块未初始化。")
            return
        if not last_frames:
            await ui_broadcast_final("[AI] 暂无画面，请稍后再试。")
            return
        try:
            _, jpeg_bytes = last_frames[-1]
            arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
            bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            result = face_friend_recognizer.recognize(bgr)
            msg = result.get("message", "识别失败。")
            await ui_broadcast_final(f"[AI] {msg}")
            play_voice_text(msg)
        except Exception as e:
            await ui_broadcast_final(f"[AI] 人脸识别失败: {e}")
        return

    face_list_keywords = ["朋友列表", "有哪些朋友", "我认识谁"]
    if any(kw in user_text for kw in face_list_keywords):
        if face_friend_recognizer is None:
            await ui_broadcast_final("[AI] 人脸识别模块未初始化。")
            return
        people = face_friend_recognizer.list_people()
        if not people:
            msg = "我还没有录入任何朋友。你可以说：这是张三。"
            await ui_broadcast_final(f"[AI] {msg}")
            play_voice_text(msg)
            return
        brief = "、".join([p["name"] for p in people[:10]])
        more = "等" if len(people) > 10 else ""
        msg = f"我认识：{brief}{more}。"
        await ui_broadcast_final(f"[AI] {msg}")
        play_voice_text(msg)
        return

    if user_text.startswith("忘记") or user_text.startswith("删除") or user_text.startswith("移除"):
        if face_friend_recognizer is None:
            await ui_broadcast_final("[AI] 人脸识别模块未初始化。")
            return
        m = re.search(r"^(?:忘记|删除|移除)\\s*([\\u4e00-\\u9fffA-Za-z0-9]{1,16})", user_text.strip())
        name = m.group(1).strip() if m else ""
        result = face_friend_recognizer.forget(name)
        msg = result.get("message", "操作失败。")
        await ui_broadcast_final(f"[AI] {msg}")
        play_voice_text(msg)
        return

    # 录入朋友：优先匹配明确口令，避免与“这是几路车”等冲突
    if re.search(r"^(这是|记住|认识|他叫|她叫|名叫|把他记成|把她记成)\\s*", user_text.strip()) and ("几路" not in user_text) and ("公交" not in user_text):
        if face_friend_recognizer is None:
            await ui_broadcast_final("[AI] 人脸识别模块未初始化。")
            return
        if not last_frames:
            await ui_broadcast_final("[AI] 暂无画面，请稍后再试。")
            return
        info = FaceFriendRecognizer.parse_name_gender_age(user_text)
        name = info.get("name")
        if not name:
            msg = "我没听清名字。你可以说：这是张三，男，30岁。"
            await ui_broadcast_final(f"[AI] {msg}")
            play_voice_text(msg)
            return
        try:
            _, jpeg_bytes = last_frames[-1]
            arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
            bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            result = face_friend_recognizer.enroll(bgr, name=name, gender=info.get("gender"), age=info.get("age"))
            msg = result.get("message", "录入失败。")
            await ui_broadcast_final(f"[AI] {msg}")
            play_voice_text(msg)
        except Exception as e:
            await ui_broadcast_final(f"[AI] 录入失败: {e}")
        return

    # ====== 新增命令：灯光关闭提醒 ======
    global light_detector, light_reminder_enabled

    light_check_keywords = ["灯关了吗", "检查灯", "检查灯有没有关", "灯有没有关", "帮我看看灯关了没"]
    if any(kw in user_text for kw in light_check_keywords):
        if light_detector is None:
            try:
                light_detector = get_light_detector()
            except Exception as e:
                await ui_broadcast_final(f"[AI] 灯光检测模块初始化失败: {e}")
                return
        if not last_frames:
            await ui_broadcast_final("[AI] 暂无画面，请稍后再试。")
            return
        try:
            _, jpeg_bytes = last_frames[-1]
            arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
            bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            result = light_detector.check_once(bgr)
            msg = result.get("message", "检查失败。")
            await ui_broadcast_final(f"[AI] {msg}")
            play_voice_text(msg)
        except Exception as e:
            await ui_broadcast_final(f"[AI] 检查灯光失败: {e}")
        return

    if ("提醒我关灯" in user_text) or ("开启关灯提醒" in user_text) or ("打开关灯提醒" in user_text) or (user_text.strip() == "关灯提醒"):
        if light_detector is None:
            try:
                light_detector = get_light_detector()
            except Exception as e:
                await ui_broadcast_final(f"[AI] 灯光检测模块初始化失败: {e}")
                return
        light_reminder_enabled = True
        msg = "好的，我会帮你留意灯是否忘关。"
        await ui_broadcast_final(f"[AI] {msg}")
        play_voice_text(msg)
        return

    if ("关闭关灯提醒" in user_text) or ("停止关灯提醒" in user_text) or ("关掉关灯提醒" in user_text):
        light_reminder_enabled = False
        msg = "好的，已关闭关灯提醒。"
        await ui_broadcast_final(f"[AI] {msg}")
        play_voice_text(msg)
        return

    # ====== 新增命令：场景探索 / 语义描述 ======
    global semantic_engine, scene_exploration_enabled, last_semantic_emit_ts
    global realtime_object_announce_enabled, last_realtime_object_announce_ts

    if ("开启场景探索" in user_text) or ("打开场景探索" in user_text) or ("持续描述" in user_text):
        if semantic_engine is None:
            try:
                semantic_engine = get_semantic_engine()
            except Exception as e:
                await ui_broadcast_final(f"[AI] 语义输出模块初始化失败: {e}")
                return
        scene_exploration_enabled = True
        last_semantic_emit_ts = 0.0
        msg = "好的，我会在对话模式下持续描述关键物体。"
        await ui_broadcast_final(f"[AI] {msg}")
        play_voice_text(msg)
        return

    if ("关闭场景探索" in user_text) or ("停止场景探索" in user_text):
        scene_exploration_enabled = False
        msg = "好的，已关闭场景探索。"
        await ui_broadcast_final(f"[AI] {msg}")
        play_voice_text(msg)
        return

    # ====== 新增命令：实时物体播报 ======
    if ("开启实时物体播报" in user_text) or ("打开实时物体播报" in user_text) or ("开启物体播报" in user_text):
        if semantic_engine is None:
            try:
                semantic_engine = get_semantic_engine()
            except Exception as e:
                await ui_broadcast_final(f"[AI] 语义输出模块初始化失败: {e}")
                return
        realtime_object_announce_enabled = True
        last_realtime_object_announce_ts = 0.0
        msg = "已开启实时物体播报。"
        await ui_broadcast_final(f"[AI] {msg}")
        play_voice_text(msg)
        return

    if ("关闭实时物体播报" in user_text) or ("停止实时物体播报" in user_text) or ("关闭物体播报" in user_text):
        realtime_object_announce_enabled = False
        msg = "已关闭实时物体播报。"
        await ui_broadcast_final(f"[AI] {msg}")
        play_voice_text(msg)
        return

    if ("重新加载语义权重" in user_text) or ("刷新语义权重" in user_text):
        if semantic_engine is None:
            try:
                semantic_engine = get_semantic_engine()
            except Exception as e:
                await ui_broadcast_final(f"[AI] 语义输出模块初始化失败: {e}")
                return
        try:
            semantic_engine.reload_weights()
            msg = "好的，语义权重已重新加载。"
            await ui_broadcast_final(f"[AI] {msg}")
            play_voice_text(msg)
        except Exception as e:
            await ui_broadcast_final(f"[AI] 重新加载失败: {e}")
        return

    semantic_once_keywords = ["描述周围", "周围有什么", "环境描述", "语义描述", "场景探索"]
    if any(kw in user_text for kw in semantic_once_keywords):
        if semantic_engine is None:
            try:
                semantic_engine = get_semantic_engine()
            except Exception as e:
                await ui_broadcast_final(f"[AI] 语义输出模块初始化失败: {e}")
                return
        if not last_frames:
            await ui_broadcast_final("[AI] 暂无画面，请稍后再试。")
            return
        try:
            _, jpeg_bytes = last_frames[-1]
            arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
            bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if bgr is None or bgr.size == 0:
                await ui_broadcast_final("[AI] 无法获取画面，请检查摄像头。")
                return
            h, w = bgr.shape[:2]
            mean_luma = float(np.mean(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)))
            raw_objs = obstacle_detector.detect(bgr) if obstacle_detector is not None else []
            out = semantic_engine.describe(
                raw_objs,
                frame_w=w,
                frame_h=h,
                mean_luma=mean_luma,
                imu_yaw_deg=latest_yaw_deg,
                imu_yaw_rate_dps=latest_yaw_rate_dps,
            )
            # 【已禁用】记录语义事件
            # try:
            #     if event_logger is not None:
            #         event_logger.log({"type": "semantic_once", "state": orchestrator.get_state() if orchestrator else None, "payload": out})
            # except Exception:
            #     pass
            msg = out.get("text") or "我暂时无法生成描述。"
            await ui_broadcast_final(f"[导航] {msg}")
            if not play_structured_voice(out):
                play_voice_text(msg)
        except Exception as e:
            await ui_broadcast_final(f"[AI] 场景描述失败: {e}")
        return

    # ====== 新增命令：夜间模式手动控制 ======
    if "打开夜间模式" in user_text or "开启夜间模式" in user_text:
        if night_detector:
            night_detector.force_mode(True)
            await ui_broadcast_final("[系统] 已手动开启夜间模式。")
            await send_esp32_command({"type": "NIGHT", "on": True, "mode": "LOW_BEACON"})
        else:
            await ui_broadcast_final("[系统] 夜间模式未初始化。")
        return

    if "关闭夜间模式" in user_text:
        if night_detector:
            night_detector.force_mode(False)
            await ui_broadcast_final("[系统] 已手动关闭夜间模式。")
            await send_esp32_command({"type": "NIGHT", "on": False, "mode": "OFF"})
        else:
            await ui_broadcast_final("[系统] 夜间模式未初始化。")
        return

    # ====== 新增命令：音乐搜索/点歌 ======
    music_keywords = [
        "我想听", "来一首", "播放", "点歌", "放首歌", "我想听歌",
        "来点音乐", "放音乐", "听听歌", "帮我放歌"
    ]
    if any(kw in user_text for kw in music_keywords):
        print("[MUSIC] 音乐搜索命令触发", flush=True)

        # 提取搜索关键词
        import re
        # 尝试多种模式提取歌名
        patterns = [
            r"我想听\s*(.+?)(?:。|！|？|$)",
            r"来一首\s*(.+?)(?:。|！|？|$)",
            r"播放\s*(.+?)(?:。|！|？|$)",
            r"点歌\s*(.+?)(?:。|！|？|$)",
            r"放首歌\s*(.+?)(?:。|！|？|$)",
            r"放音乐\s*(.+?)(?:。|！|？|$)",
            r"来点音乐\s*(.+?)(?:。|！|？|$)",
        ]

        search_keyword = None
        for pattern in patterns:
            match = re.search(pattern, user_text)
            if match:
                search_keyword = match.group(1).strip()
                break

        if not search_keyword:
            # 如果没有匹配到，尝试去掉关键词后的内容
            for kw in music_keywords:
                if kw in user_text:
                    search_keyword = user_text.replace(kw, "").strip()
                    if search_keyword:
                        break

        if search_keyword:
            try:
                await ui_broadcast_partial("[AI] 正在搜索音乐，请稍候...")
                print(f"[MUSIC] 搜索关键词: {search_keyword}")

                # 异步搜索音乐
                songs = await search_music(search_keyword, source="migu", limit=5)

                if songs:
                    # 保存到播放器
                    player = get_music_player()
                    player.set_queue(songs)

                    # 播报搜索结果
                    result_text = format_song_list(songs[:5], max_count=5)
                    await ui_broadcast_final(f"[音乐] {result_text}")

                    # 同时发送播放链接给ESP32（如果有播放功能）
                    first_song = songs[0]
                    await send_esp32_command({
                        "type": "MUSIC",
                        "action": "search_result",
                        "songs": [
                            {
                                "name": s.name,
                                "artists": s.artists,
                                "url": s.url,
                                "index": i
                            }
                            for i, s in enumerate(songs[:5])
                        ]
                    })
                else:
                    await ui_broadcast_final("[音乐] 抱歉，没有找到相关歌曲。请换个关键词试试。")

            except Exception as e:
                print(f"[MUSIC] 搜索失败: {e}")
                await ui_broadcast_final(f"[音乐] 搜索失败: {e}")
        else:
            await ui_broadcast_final("[音乐] 请告诉我你想听什么歌，比如：我想听周杰伦的稻香。")
        return

    # 音乐播放控制
    play_control_keywords = ["下一首", "上一首", "暂停", "继续播放", "停止播放", "重新播放"]
    if any(kw in user_text for kw in play_control_keywords):
        player = get_music_player()

        if "下一首" in user_text:
            song = player.next()
            if song:
                await ui_broadcast_final(f"[音乐] 正在播放：{song.artists}的{song.name}")
                await send_esp32_command({
                    "type": "MUSIC",
                    "action": "play",
                    "url": song.url,
                    "name": song.name,
                    "artists": song.artists
                })
            else:
                await ui_broadcast_final("[音乐] 播放列表为空，请先搜索歌曲。")

        elif "上一首" in user_text:
            song = player.prev()
            if song:
                await ui_broadcast_final(f"[音乐] 正在播放：{song.artists}的{song.name}")
                await send_esp32_command({
                    "type": "MUSIC",
                    "action": "play",
                    "url": song.url,
                    "name": song.name,
                    "artists": song.artists
                })
            else:
                await ui_broadcast_final("[音乐] 播放列表为空，请先搜索歌曲。")

        elif "暂停" in user_text or "停止" in user_text:
            await ui_broadcast_final("[音乐] 已暂停播放")
            await send_esp32_command({"type": "MUSIC", "action": "pause"})

        elif "继续" in user_text:
            await ui_broadcast_final("[音乐] 继续播放")
            await send_esp32_command({"type": "MUSIC", "action": "resume"})

        elif "重新" in user_text:
            song = player.play_index(0)
            if song:
                await ui_broadcast_final(f"[音乐] 重新播放：{song.artists}的{song.name}")
                await send_esp32_command({
                    "type": "MUSIC",
                    "action": "play",
                    "url": song.url,
                    "name": song.name,
                    "artists": song.artists
                })
        return

    # 播放指定编号的歌曲
    play_number_match = re.search(r"播放第(\d+)首|第(\d+)首|来第(\d+)首", user_text)
    if play_number_match:
        player = get_music_player()
        song_num = int(play_number_match.group(1) or play_number_match.group(2) or play_number_match.group(3))
        song = player.play_index(song_num - 1)  # 转换为0-based索引

        if song:
            await ui_broadcast_final(f"[音乐] 正在播放：{song.artists}的{song.name}")
            await send_esp32_command({
                "type": "MUSIC",
                "action": "play",
                "url": song.url,
                "name": song.name,
                "artists": song.artists
            })
        else:
            await ui_broadcast_final(f"[音乐] 第{song_num}首不存在，请先搜索歌曲。")
        return

    # ========== omni对话状态管理（已禁用）==========
    # # 【修改】omni对话开始时，切换到CHAT模式
    # global omni_conversation_active, omni_previous_nav_state
    # omni_conversation_active = True
    #
    # # 保存当前导航状态并切换到CHAT模式
    # if orchestrator:
    #     current_state = orchestrator.get_state()
    #     # 只有在导航模式下才需要保存和切换
    #     if current_state not in ["CHAT", "IDLE"]:
    #         omni_previous_nav_state = current_state
    #         orchestrator.force_state("CHAT")
    #         print(f"[OMNI] 对话开始，从{current_state}切换到CHAT模式")
    #     else:
    #         omni_previous_nav_state = None
    #         print(f"[OMNI] 对话开始（当前已在{current_state}模式）")
    # ============================================
    
    # 如果不是特殊命令，执行原有的AI对话逻辑
    # 但如果yolomedia正在运行，暂时不处理普通对话
    if yolomedia_running:
        print("[AI] YOLO media is running, skipping normal AI response", flush=True)
        return
    
    # 原有的AI对话逻辑
    await start_ai_with_text(user_text)

# ========= AI 播放启动（已禁用大模型，改为本地语音）==========
async def start_ai_with_text(user_text: str):
    """
    当前版本：不使用大模型，改为本地语音播报
    如需启用大模型，请取消注释原始实现
    """
    # 简单播报用户说的话（通过本地 TTS 或预录音频）
    await ui_broadcast_final(f"[系统] {user_text}")

    # 尝试使用本地语音播报
    try:
        from audio_player import play_voice_text
        play_voice_text(user_text)
    except Exception as e:
        print(f"[AI] 本地语音播报失败: {e}")

    # ========== 原始大模型实现（已禁用）==========
    # async def _runner():
    #     txt_buf: List[str] = []
    #     rate_state = None
    #
    #     # 组装（图像+文本）
    #     content_list = []
    #     if last_frames:
    #         try:
    #             _, jpeg_bytes = last_frames[-1]
    #             img_b64 = base64.b64encode(jpeg_bytes).decode("ascii")
    #             content_list.append({
    #                 "type": "image_url",
    #                 "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}
    #             })
    #         except Exception:
    #             pass
    #     content_list.append({"type": "text", "text": user_text})
    #
    #     try:
    #         async for piece in stream_chat(content_list, voice="Cherry", audio_format="wav"):
    #             # 文本增量（仅 UI）
    #             if piece.text_delta:
    #                 txt_buf.append(piece.text_delta)
    #                 try:
    #                     await ui_broadcast_partial("[AI] " + "".join(txt_buf))
    #                 except Exception:
    #                     pass
    #
    #             # 音频分片：Omni 返回 24k (PCM16) 的 wav audio.data（Base64）；下行需要 8k PCM16
    #             if piece.audio_b64:
    #                 try:
    #                     pcm24 = base64.b64decode(piece.audio_b64)
    #                 except Exception:
    #                     pcm24 = b""
    #                 if pcm24:
    #                     # 24k → 8k (使用ratecv保证音调和速度不变)
    #                     pcm8k, rate_state = audioop.ratecv(pcm24, 2, 1, 24000, 8000, rate_state)
    #                     pcm8k = audioop.mul(pcm8k, 2, 0.60)
    #                     if pcm8k:
    #                         await broadcast_pcm16_realtime(pcm8k)
    #
    #     except asyncio.CancelledError:
    #         # 被新一轮打断
    #         raise
    #     except Exception as e:
    #         try:
    #             await ui_broadcast_final(f"[AI] 发生错误：{e}")
    #         except Exception:
    #             pass
    #     finally:
    #         # 【修改】标记omni对话结束，恢复之前的导航模式
    #         global omni_conversation_active, omni_previous_nav_state
    #         omni_conversation_active = False
    #
    #         # 恢复之前的导航状态
    #         if orchestrator and omni_previous_nav_state:
    #             orchestrator.force_state(omni_previous_nav_state)
    #             print(f"[OMNI] 对话结束，恢复到{omni_previous_nav_state}模式")
    #             omni_previous_nav_state = None
    #         else:
    #             print(f"[OMNI] 对话结束（无需恢复导航状态）")
    #
    #         # 自然结束时，给当前连接一个 "完结" 信号
    #         from audio_stream import stream_clients  # 局部导入，避免环依赖
    #         for sc in list(stream_clients):
    #             if not sc.abort_event.is_set():
    #                 try: sc.q.put_nowait(b"\x00"*BYTES_PER_20MS_16K)  # 一帧静音
    #                 except Exception: pass
    #                 try: sc.q.put_nowait(None)
    #                 except Exception: pass
    #
    #         final_text = ("".join(txt_buf)).strip() or "（空响应）"
    #         try:
    #             await ui_broadcast_final("[AI] " + final_text)
    #         except Exception:
    #             pass
    #
    # # 真正启动前先硬重置，保证**绝无**旧音频残留
    # await hard_reset_audio("start_ai_with_text")
    # loop = asyncio.get_running_loop()
    # from audio_stream import current_ai_task as _task_holder  # 读写模块内全局
    # from audio_stream import __dict__ as _as_dict
    # # 设置模块内的 current_ai_task
    # task = loop.create_task(_runner())
    # _as_dict["current_ai_task"] = task
    # ============================================

# ---------- 页面 / 健康 ----------
@app.get("/", response_class=HTMLResponse)
def root():
    with open(os.path.join("templates", "index.html"), "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.get("/api/health", response_class=PlainTextResponse)
def health():
    return "OK"

# 注册 /stream.wav
register_stream_route(app)

# ---------- WebSocket：WebUI 文本（ASR/AI 状态推送） ----------
@app.websocket("/ws_ui")
async def ws_ui(ws: WebSocket):
    await ws.accept()
    ui_clients[id(ws)] = ws
    try:
        init = {"partial": current_partial, "finals": recent_finals[-10:]}
        await ws.send_text("INIT:" + json.dumps(init, ensure_ascii=False))
        while True:
            await asyncio.sleep(60)
    except WebSocketDisconnect:
        pass
    finally:
        ui_clients.pop(id(ws), None)

# ---------- WebSocket：ESP32 音频入口（ASR 上行） ----------
@app.websocket("/ws_audio")
async def ws_audio(ws: WebSocket):
    global esp32_audio_ws
    esp32_audio_ws = ws
    await ws.accept()
    print("\n[AUDIO] client connected")
    recognition = None
    streaming = False
    last_ts = time.monotonic()
    keepalive_task: Optional[asyncio.Task] = None

    async def stop_rec(send_notice: Optional[str] = None):
        nonlocal recognition, streaming, keepalive_task
        if keepalive_task and not keepalive_task.done():
            keepalive_task.cancel()
            try: await keepalive_task
            except Exception: pass
        keepalive_task = None
        if recognition:
            try: recognition.stop()
            except Exception: pass
            recognition = None
        await set_current_recognition(None)
        streaming = False
        if send_notice:
            try: await ws.send_text(send_notice)
            except Exception: pass

    async def on_sdk_error(_msg: str):
        await stop_rec(send_notice="RESTART")

    async def keepalive_loop():
        nonlocal last_ts, recognition, streaming
        try:
            while streaming and recognition is not None:
                idle = time.monotonic() - last_ts
                if idle > 0.35:
                    try:
                        for _ in range(30):  # ~600ms 静音
                            recognition.send_audio_frame(SILENCE_20MS)
                        last_ts = time.monotonic()
                    except Exception:
                        await on_sdk_error("keepalive send failed")
                        return
                await asyncio.sleep(0.10)
        except asyncio.CancelledError:
            return

    # START 节流变量（必须在 while 循环外声明，避免每次消息重置）
    last_start_time = 0
    START_COOLDOWN = 1.0  # 1秒冷却时间

    try:
        while True:
            if WebSocketState and ws.client_state != WebSocketState.CONNECTED:
                break
            try:
                msg = await ws.receive()
            except WebSocketDisconnect:
                break
            except RuntimeError as e:
                if "Cannot call \"receive\"" in str(e):
                    break
                raise

            if "text" in msg and msg["text"] is not None:
                raw = (msg["text"] or "").strip()
                cmd = raw.upper()

                if cmd == "START":
                    current_time = time.monotonic()
                    if current_time - last_start_time < START_COOLDOWN:
                        print(f"[AUDIO] 忽略重复START指令（冷却中）")
                        await ws.send_text("ERR:TOO_FAST")
                        continue
                    last_start_time = current_time

                    print("[AUDIO] START received")
                    await stop_rec()
                    loop = asyncio.get_running_loop()
                    def post(coro):
                        asyncio.run_coroutine_threadsafe(coro, loop)

                    # 组装 ASR 回调（把依赖都注入）
                    cb = ASRCallback(
                        on_sdk_error=lambda s: post(on_sdk_error(s)),
                        post=post,
                        ui_broadcast_partial=ui_broadcast_partial,
                        ui_broadcast_final=ui_broadcast_final,
                        is_playing_now_fn=is_playing_now,
                        start_ai_with_text_fn=start_ai_with_text_custom,  # 使用自定义版本
                        full_system_reset_fn=full_system_reset,
                        interrupt_lock=interrupt_lock,
                    )

                    recognition = dash_audio.asr.Recognition(
                        api_key=API_KEY, model=MODEL, format=AUDIO_FMT,
                        sample_rate=SAMPLE_RATE, callback=cb
                    )
                    recognition.start()
                    await set_current_recognition(recognition)
                    streaming = True
                    last_ts = time.monotonic()
                    keepalive_task = asyncio.create_task(keepalive_loop())
                    await ui_broadcast_partial("（已开始接收音频…）")
                    await ws.send_text("OK:STARTED")

                elif cmd == "STOP":
                    if recognition:
                        for _ in range(15):  # ~300ms 静音
                            try: recognition.send_audio_frame(SILENCE_20MS)
                            except Exception: break
                    await stop_rec(send_notice="OK:STOPPED")

                elif raw.startswith("PROMPT:"):
                    # 设备端主动发起一轮：同样使用“先硬重置后播放”的强语义
                    text = raw[len("PROMPT:"):].strip()
                    if text:
                        async with interrupt_lock:
                            await start_ai_with_text_custom(text) # 使用自定义的启动函数
                        await ws.send_text("OK:PROMPT_ACCEPTED")
                    else:
                        await ws.send_text("ERR:EMPTY_PROMPT")

            elif "bytes" in msg and msg["bytes"] is not None:
                if streaming and recognition:
                    try:
                        recognition.send_audio_frame(msg["bytes"])
                        last_ts = time.monotonic()
                    except Exception:
                        await on_sdk_error("send_audio_frame failed")

    except Exception as e:
        print(f"\n[WS ERROR] {e}")
    finally:
        await stop_rec()
        try:
            if WebSocketState is None or ws.client_state == WebSocketState.CONNECTED:
                await ws.close(code=1000)
        except Exception:
            pass
        if esp32_audio_ws is ws:
            esp32_audio_ws = None
        print("[WS] connection closed")

# ---------- WebSocket：ESP32 相机入口（JPEG 二进制） ----------
@app.websocket("/ws/camera")
async def ws_camera_esp(ws: WebSocket):
    global esp32_camera_ws, blind_path_navigator, cross_street_navigator, cross_street_active, navigation_active, orchestrator
    global last_semantic_emit_ts, scene_exploration_enabled
    global last_realtime_object_announce_ts, realtime_object_announce_enabled
    global last_night_light_remind_time, last_auto_detection_time, current_detected_scene
    if esp32_camera_ws is not None:
        await ws.close(code=1013)
        return
    esp32_camera_ws = ws
    await ws.accept()
    print("[CAMERA] ESP32 connected")
    
    # 【新增】初始化盲道导航器
    if blind_path_navigator is None and yolo_seg_model is not None:
        blind_path_navigator = BlindPathNavigator(yolo_seg_model, obstacle_detector)
        print("[NAVIGATION] 盲道导航器已初始化")
    else:
        if blind_path_navigator is not None:
            print("[NAVIGATION] 导航器已存在，无需重新初始化")
        elif yolo_seg_model is None:
            print("[NAVIGATION] 警告：YOLO模型未加载，无法初始化导航器")
    
    # 【新增】初始化过马路导航器
    if cross_street_navigator is None:
        if yolo_seg_model:
            cross_street_navigator = CrossStreetNavigator(
                seg_model=yolo_seg_model,
                coco_model=None,  # 不使用交通灯检测
                obs_model=None    # 暂时也不用障碍物检测，让它更快
            )
            print("[CROSS_STREET] 过马路导航器已初始化（简化版 - 仅斑马线检测）")
        else:
            print("[CROSS_STREET] 错误：缺少分割模型，无法初始化过马路导航器")
            
            if not yolo_seg_model:
                print("[CROSS_STREET] - 缺少分割模型 (yolo_seg_model)")
            if not obstacle_detector:
                print("[CROSS_STREET] - 缺少障碍物检测器 (obstacle_detector)")
    
    if orchestrator is None and blind_path_navigator is not None and cross_street_navigator is not None:
        orchestrator = NavigationMaster(blind_path_navigator, cross_street_navigator)
        print("[NAV MASTER] 统领状态机已初始化（托管模式）")

    # 【新增】初始化语音调度器
    global voice_scheduler
    if voice_scheduler is None:
        voice_scheduler = get_voice_scheduler()
        voice_scheduler.set_play_callback(play_voice_text)
        print("[VOICE_SCHED] 语音调度器已初始化")

    # 【新增】初始化物品搜索增强器
    global item_search_enhancer
    if item_search_enhancer is None:
        item_search_enhancer = get_item_search_enhancer()

        # 设置引导回调（使用 play_voice_text）
        item_search_enhancer.set_guidance_callback(play_voice_text)

        # 设置找到目标回调（UI播报）
        async def on_target_found(target):
            """找到目标时的回调"""
            try:
                await ui_broadcast_final(f"[找物品] 找到{target.name_cn}了！")
            except Exception:
                pass

        # 设置目标完成回调
        async def on_target_complete(target):
            """目标完成时的回调"""
            try:
                await ui_broadcast_final(f"[找物品] {target.name_cn}已完成。")
            except Exception:
                pass

        # 注意：由于回调是异步的，这里需要特殊处理
        # 暂时使用同步回调，在回调中通过 asyncio 处理
        import asyncio
        loop = asyncio.get_running_loop()

        def sync_on_target_found(target):
            asyncio.create_task(on_target_found(target))

        def sync_on_target_complete(target):
            asyncio.create_task(on_target_complete(target))

        item_search_enhancer.set_target_found_callback(sync_on_target_found)
        item_search_enhancer.set_target_complete_callback(sync_on_target_complete)

        print("[ITEM_SEARCH] 物品搜索增强器已初始化")

    # 【新增】初始化夜间模式检测器并设置回调
    global night_detector
    if night_detector is None and night_mode_enabled:
        night_detector = get_night_detector()

        async def on_night_mode_change(is_night: bool):
            """夜间模式切换回调"""
            mode = "夜间" if is_night else "日间"
            print(f"[NIGHT_MODE] 切换到{mode}模式")

            # UI播报
            await ui_broadcast_final(f"[导航] 已进入{'夜间' if is_night else '日间'}模式。")

            # 发送ESP32指令
            await send_esp32_command({
                "type": "NIGHT",
                "on": is_night,
                "mode": "LOW_BEACON" if is_night else "OFF"
            })

        set_night_mode_callback(on_night_mode_change)
        print("[NIGHT_MODE] 夜间检测器已初始化")

    frame_counter = 0  # 添加帧计数器
    
    try:
        while True:
            msg = await ws.receive()
            if "bytes" in msg and msg["bytes"] is not None:
                data = msg["bytes"]
                frame_counter += 1

                # 【已禁用】录制原始帧 - 已注释以减少数据传输占用
                # try:
                #     sync_recorder.record_frame(data)
                # except Exception as e:
                #     if frame_counter % 100 == 0:  # 避免日志刷屏
                #         print(f"[RECORDER] 录制帧失败: {e}")

                try:
                    last_frames.append((time.time(), data))
                except Exception:
                    pass
                
                # 推送到bridge_io（供yolomedia使用）
                bridge_io.push_raw_jpeg(data)
                
                # 【调试】检查导航条件
                if frame_counter % 30 == 0:  # 每30帧输出一次
                    state_dbg = orchestrator.get_state() if orchestrator else "N/A"
                    print(f"[NAVIGATION DEBUG] 帧:{frame_counter}, state={state_dbg}, yolomedia_running={yolomedia_running}")
                
                # 统一解码（添加更严格的异常处理）
                try:
                    arr = np.frombuffer(data, dtype=np.uint8)
                    bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                    # 验证解码结果
                    if bgr is None or bgr.size == 0:
                        if frame_counter % 30 == 0:
                            print(f"[JPEG] 解码失败：数据长度={len(data)}")
                        bgr = None
                except Exception as e:
                    if frame_counter % 30 == 0:
                        print(f"[JPEG] 解码异常: {e}")
                    bgr = None

                # 【新增】夜间模式检测（每帧检查，但内部按间隔采样）
                if night_detector is not None and bgr is not None:
                    try:
                        night_result = night_detector.process_frame(bgr)
                        if night_result.get('changed', False):
                            # 夜间模式切换回调已在初始化时设置
                            pass

                        # 【新增】户外天黑提醒：夜间模式下检测是否户外，提醒用户开灯让别人知道是盲人
                        if night_light_reminder_enabled and night_result.get('is_night', False):
                            current_time = time.time()
                            if (current_time - last_night_light_remind_time) > night_light_reminder_cooldown:
                                is_outdoor = _check_if_outdoor(bgr)
                                if is_outdoor:
                                    msg = "天色已晚，建议打开指示灯，让别人注意到您。"
                                    play_voice_text(msg)
                                    await ui_broadcast_final(f"[导航] {msg}")
                                    last_night_light_remind_time = current_time
                                    print(f"[NIGHT_LIGHT] 已提醒用户开灯 (冷却时间: {night_light_reminder_cooldown}秒)")
                    except Exception as e:
                        if frame_counter % 100 == 0:
                            print(f"[NIGHT_MODE] 检测失败: {e}")

                # 【新增】灯光关闭提醒（开启后才检测；尽量不打断导航）
                if light_detector is not None and light_reminder_enabled and bgr is not None:
                    try:
                        st = orchestrator.get_state() if orchestrator else "CHAT"
                        if st in ("CHAT", "IDLE"):
                            lr = light_detector.process_frame(bgr)
                            if lr.get("should_remind", False) and lr.get("is_on", False):
                                msg = "我检测到灯可能还开着，记得关灯。"
                                play_voice_text(msg)
                                await ui_broadcast_final(f"[AI] {msg}")
                    except Exception as e:
                        if frame_counter % 200 == 0:
                            print(f"[LIGHT] 检测失败: {e}")

                # 【新增】场景探索：周期性输出 Top-3 关键物体的可执行提示（仅在非导航模式）
                if semantic_engine is not None and scene_exploration_enabled and bgr is not None:
                    try:
                        st = orchestrator.get_state() if orchestrator else "CHAT"
                        now_ts = time.time()
                        if st in ("CHAT", "IDLE") and (now_ts - last_semantic_emit_ts) >= semantic_emit_interval_sec:
                            h, w = bgr.shape[:2]
                            mean_luma = float(np.mean(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY))) if bgr is not None else None
                            raw_objs = obstacle_detector.detect(bgr) if obstacle_detector is not None else []
                            out = semantic_engine.describe(
                                raw_objs,
                                frame_w=w,
                                frame_h=h,
                                mean_luma=mean_luma,
                                imu_yaw_deg=latest_yaw_deg,
                                imu_yaw_rate_dps=latest_yaw_rate_dps,
                            )
                            # 【已禁用】记录语义自动事件
                            # try:
                            #     if event_logger is not None:
                            #         event_logger.log({"type": "semantic_auto", "state": st, "payload": out})
                            # except Exception:
                            #     pass
                            if out.get("should_speak", False):
                                if not play_structured_voice(out):
                                    if out.get("text"):
                                        play_voice_text(out["text"])
                                if out.get("text"):
                                    await ui_broadcast_final(f"[导航] {out['text']}")
                            last_semantic_emit_ts = now_ts
                    except Exception as e:
                        if frame_counter % 200 == 0:
                            print(f"[SEMANTIC] 输出失败: {e}")

                # 【新增】实时物体播报：输入实时帧后直接播报白名单物体（默认开启）
                if semantic_engine is not None and realtime_object_announce_enabled and bgr is not None:
                    try:
                        now_ts = time.time()
                        if (now_ts - last_realtime_object_announce_ts) >= realtime_object_announce_interval:
                            h, w = bgr.shape[:2]
                            mean_luma = float(np.mean(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)))
                            raw_objs = obstacle_detector.detect(bgr) if obstacle_detector is not None else []
                            out = semantic_engine.describe(
                                raw_objs,
                                frame_w=w,
                                frame_h=h,
                                mean_luma=mean_luma,
                                imu_yaw_deg=latest_yaw_deg,
                                imu_yaw_rate_dps=latest_yaw_rate_dps,
                            )
                            msg = _build_realtime_object_announce_text(out)
                            if msg and out.get("should_speak", False):
                                play_voice_text(msg)
                                await ui_broadcast_final(f"[导航] {msg}")
                                last_realtime_object_announce_ts = now_ts
                    except Exception as e:
                        if frame_counter % 200 == 0:
                            print(f"[REALTIME_OBJECT] 播报失败: {e}")

                # 【新增】自动场景识别：接收到画面后自动运行检测并主动播报
                if auto_scene_detection and bgr is not None:
                    current_time = time.time()
                    if (current_time - last_auto_detection_time) >= auto_detection_interval:
                        last_auto_detection_time = current_time

                        try:
                            scene, confidence = _detect_scene(bgr)
                            # 场景切换或高置信度时播报
                            if scene != current_detected_scene and confidence > 0.6:
                                current_detected_scene = scene
                                msg = _get_scene_announcement(scene)
                                if msg:
                                    play_voice_text(msg)
                                    await ui_broadcast_final(f"[导航] {msg}")
                                    print(f"[AUTO_SCENE] 检测到场景: {scene}, 播报: {msg}")
                        except Exception as e:
                            if frame_counter % 200 == 0:
                                print(f"[AUTO_SCENE] 检测失败: {e}")

                # 【托管】优先交给统领状态机（寻物未占用画面时）
                # 【修改】找物品模式时不执行导航处理，让yolomedia接管画面
                if orchestrator and not yolomedia_running and bgr is not None:
                    current_state = orchestrator.get_state()
                    
                    # 【新增】找物品模式：不处理画面，等待yolomedia发送处理后的帧
                    if current_state == "ITEM_SEARCH":
                        # 找物品模式下，如果yolomedia还没开始发送帧，先显示原始画面
                        if not yolomedia_sending_frames and camera_viewers:
                            ok, enc = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                            if ok:
                                jpeg_data = enc.tobytes()
                                dead = []
                                for viewer_ws in list(camera_viewers):
                                    try:
                                        await viewer_ws.send_bytes(jpeg_data)
                                    except Exception:
                                        dead.append(viewer_ws)
                                for d in dead:
                                    camera_viewers.discard(d)
                        continue  # 跳过后续的导航处理
                    
                    out_img = bgr
                    try:
                        # 【新增】检查是否在红绿灯检测模式
                        if current_state == "TRAFFIC_LIGHT_DETECTION":
                            # 红绿灯检测模式：在主线程中直接处理，避免掉帧
                            import trafficlight_detection
                            result = trafficlight_detection.process_single_frame(bgr, ui_broadcast_callback=ui_broadcast_final)
                            out_img = result['vis_image'] if result['vis_image'] is not None else bgr
                        else:
                            # 其他模式：正常的导航处理
                            res = orchestrator.process_frame(bgr)

                            # 语音引导（内部已节流）
                            # 注：omni对话时已切换到CHAT模式，不会生成导航语音
                            if res.guidance_text:
                                try:
                                    # 先播放语音，再广播到UI
                                    play_voice_text(res.guidance_text)
                                    await ui_broadcast_final(f"[导航] {res.guidance_text}")
                                except Exception:
                                    pass

                            # 输出图像
                            out_img = res.annotated_image if res.annotated_image is not None else bgr
                    except Exception as e:
                        if frame_counter % 100 == 0:
                            print(f"[NAV MASTER] 处理帧时出错: {e}")

                    # 广播图像
                    if camera_viewers and out_img is not None:
                        ok, enc = cv2.imencode(".jpg", out_img, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                        if ok:
                            jpeg_data = enc.tobytes()
                            dead = []
                            for viewer_ws in list(camera_viewers):
                                try:
                                    await viewer_ws.send_bytes(jpeg_data)
                                except Exception:
                                    dead.append(viewer_ws)
                            for d in dead:
                                camera_viewers.discard(d)
                    # 已托管，进入下一帧
                    continue

                # 【回退】寻物占用或者未解码成功，按原始画面回传
                if not yolomedia_sending_frames and camera_viewers:
                    try:
                        if bgr is None:
                            arr = np.frombuffer(data, dtype=np.uint8)
                            bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                        if bgr is not None:
                            ok, enc = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                            if ok:
                                jpeg_data = enc.tobytes()
                                dead = []
                                for viewer_ws in list(camera_viewers):
                                    try:
                                        await viewer_ws.send_bytes(jpeg_data)
                                    except Exception:
                                        dead.append(viewer_ws)
                                for ws in dead:
                                    camera_viewers.discard(ws)
                    except Exception as e:
                        print(f"[CAMERA] Broadcast error: {e}")

            elif "type" in msg and msg["type"] in ("websocket.close", "websocket.disconnect"):
                break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[CAMERA ERROR] {e}")
    finally:
        try:
            if WebSocketState is None or ws.client_state == WebSocketState.CONNECTED:
                await ws.close(code=1000)
        except Exception:
            pass
        esp32_camera_ws = None
        print("[CAMERA] ESP32 disconnected")
        
        # 【新增】清理导航状态
        if blind_path_navigator:
            blind_path_navigator.reset()
        if cross_street_navigator:
            cross_street_navigator.reset()
        if orchestrator:
            orchestrator.reset()
            print("[NAV MASTER] 统领器已重置")

# ---------- WebSocket：浏览器订阅相机帧 ----------
@app.websocket("/ws/viewer")
async def ws_viewer(ws: WebSocket):
    await ws.accept()
    camera_viewers.add(ws)
    print(f"[VIEWER] Browser connected. Total viewers: {len(camera_viewers)}", flush=True)
    try:
        while True:
            # 保持连接活跃
            await asyncio.sleep(60)
    except WebSocketDisconnect:
        print("[VIEWER] Browser disconnected", flush=True)
    finally:
        try: 
            camera_viewers.remove(ws)
        except Exception: 
            pass
        print(f"[VIEWER] Removed. Total viewers: {len(camera_viewers)}", flush=True)

# ---------- WebSocket：浏览器订阅 IMU ----------
@app.websocket("/ws")
async def ws_imu(ws: WebSocket):
    await ws.accept()
    imu_ws_clients.add(ws)
    try:
        while True:
            await asyncio.sleep(60)
    except WebSocketDisconnect:
        pass
    finally:
        imu_ws_clients.discard(ws)

async def imu_broadcast(msg: str):
    if not imu_ws_clients: return
    dead = []
    for ws in list(imu_ws_clients):
        try:
            await ws.send_text(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        imu_ws_clients.discard(ws)

# ---------- ESP32命令WebSocket（用于LED控制等） ----------
async def send_esp32_command(command: Dict[str, Any]):
    """
    发送命令给ESP32
    :param command: 命令字典，如 {"type": "LED", "mode": "BLINK"}
    """
    global esp32_cmd_ws
    if esp32_cmd_ws is None:
        print(f"[ESP32_CMD] 无ESP32命令连接，命令未发送: {command}")
        return False

    try:
        async with esp32_cmd_lock:
            await esp32_cmd_ws.send_json(command)
        print(f"[ESP32_CMD] 命令已发送: {command}")
        return True
    except Exception as e:
        print(f"[ESP32_CMD] 发送命令失败: {e}")
        return False

@app.websocket("/ws/cmd")
async def ws_esp32_command(ws: WebSocket):
    """ESP32命令WebSocket - ESP32连接此端口接收控制命令"""
    global esp32_cmd_ws
    await ws.accept()
    esp32_cmd_ws = ws
    print("[ESP32_CMD] ESP32命令连接已建立")

    try:
        while True:
            # 接收ESP32的ACK响应
            msg = await ws.receive()
            if "text" in msg:
                try:
                    data = json.loads(msg["text"])
                    print(f"[ESP32_CMD] 收到ESP32响应: {data}")
                except:
                    print(f"[ESP32_CMD] 收到ESP32消息: {msg['text']}")
    except WebSocketDisconnect:
        print("[ESP32_CMD] ESP32命令连接断开")
    finally:
        esp32_cmd_ws = None

# ---------- 服务端 IMU 估计（原样保留） ----------
from math import atan2, hypot, pi
GRAV_BETA   = 0.98
STILL_W     = 0.4
YAW_DB      = 0.08
YAW_LEAK    = 0.2
ANG_EMA     = 0.15
AUTO_REZERO = True
USE_PROJ    = True
FREEZE_STILL= True
G     = 9.807
A_TOL = 0.08 * G
gLP = {"x":0.0, "y":0.0, "z":0.0}
gOff= {"x":0.0, "y":0.0, "z":0.0}
BIAS_ALPHA = 0.002
yaw  = 0.0
Rf = Pf = Yf = 0.0
ref = {"roll":0.0, "pitch":0.0, "yaw":0.0}
holdStart = 0.0
isStill   = False
last_ts_imu = 0.0
last_wall = 0.0
imu_store: List[Dict[str, Any]] = []

# 【新增】为语义输出/闭环稳定提供的 IMU 快照
latest_yaw_deg: float = 0.0
latest_yaw_rate_dps: float = 0.0
latest_yaw_ts: float = 0.0
_prev_yaw_for_rate: Optional[float] = None
_prev_yaw_ts_for_rate: float = 0.0

def _wrap180(a: float) -> float:
    a = a % 360.0
    if a >= 180.0: a -= 360.0
    if a < -180.0: a += 360.0
    return a

def _check_if_outdoor(bgr_image: np.ndarray) -> bool:
    """
    简单判断是否在户外环境。
    基于亮度分布特征：户外天空通常比地面亮。
    """
    if bgr_image is None or bgr_image.size == 0:
        return False

    try:
        gray = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape

        # 上半部分（天空）和下半部分（地面）亮度对比
        top_half = gray[:h//2, :]
        bottom_half = gray[h//2:, :]
        top_mean = float(np.mean(top_half))
        bottom_mean = float(np.mean(bottom_half))
        overall_mean = float(np.mean(gray))

        # 户外特征：
        # 1. 天空比地面亮（top_mean > bottom_mean * 1.2）
        # 2. 整体亮度不太暗（>30，表示有环境光）
        # 3. 天空亮度显著高于整体
        is_outdoor = (
            (top_mean > bottom_mean * 1.2) and
            (top_mean > 30) and
            (top_mean > overall_mean * 1.1)
        )

        return is_outdoor
    except Exception as e:
        print(f"[NIGHT_LIGHT] 户外判断失败: {e}")
        return False

def _detect_scene(bgr_image: np.ndarray) -> Tuple[str, float]:
    """
    检测当前场景，返回 (scene_type, confidence)

    支持的场景类型：
    - 导航场景：blindpath / crosswalk / obstacle / traffic_light_*
    - 建筑场景：hospital / supermarket / mall / restaurant / bank / office
    - 室内场景：elevator / stairs / corridor / restroom
    - 自然场景：park / square
    - 特殊场景：construction / parking
    """
    if bgr_image is None or bgr_image.size == 0:
        return "unknown", 0.0

    candidates: List[Tuple[str, float]] = []

    # 1) 盲道 / 斑马线：优先复用 BlindPathNavigator 的分割输出
    try:
        if blind_path_navigator is not None and hasattr(blind_path_navigator, "_detect_path_and_crosswalk"):
            if getattr(blind_path_navigator, "yolo_model", None) is not None:
                blind_mask, crosswalk_mask = blind_path_navigator._detect_path_and_crosswalk(bgr_image)

                if blind_mask is not None and blind_mask.size > 0:
                    blind_ratio = float(np.mean(blind_mask > 0))
                    if blind_ratio >= 0.006:
                        conf = min(0.95, 0.55 + blind_ratio * 12.0)
                        candidates.append(("blindpath", conf))

                if crosswalk_mask is not None and crosswalk_mask.size > 0:
                    cross_ratio = float(np.mean(crosswalk_mask > 0))
                    if cross_ratio >= 0.01:
                        conf = min(0.95, 0.60 + cross_ratio * 10.0)
                        candidates.append(("crosswalk", conf))
    except Exception:
        pass

    # 2) 红绿灯：复用 navigation_master 的 TrafficLightDetector
    try:
        from navigation_master import TrafficLightDetector
        tld = TrafficLightDetector()
        color, _meta = tld.detect(bgr_image)
        if color in ("red", "green", "yellow"):
            candidates.append((f"traffic_light_{color}", 0.85))
    except Exception:
        pass

    # 3) 【新增】使用 semantic_engine 进行更广泛的场��识别
    try:
        global semantic_engine, obstacle_detector
        if semantic_engine is not None and obstacle_detector is not None:
            detections = obstacle_detector.detect(bgr_image)
            if detections:
                h, w = bgr_image.shape[:2]
                mean_luma = float(np.mean(cv2.cvtColor(bgr_image, cv2.COLOR_BGR2GRAY)))

                # 提取物体名称用于场景推断
                names = [d.get("name", "") for d in detections]
                scene = semantic_engine.infer_scene(names, mean_luma=mean_luma)

                if scene != "unknown":
                    # 根据匹配到的关键词数量计算置信度
                    scene_conf = 0.7
                    candidates.append((scene, scene_conf))
    except Exception as e:
        if False:  # 调试时可启用
            print(f"[SCENE_DETECT] semantic场景检测失败: {e}")

    # 4) 障碍物：使用 obstacle_detector
    try:
        if obstacle_detector is not None:
            detections = obstacle_detector.detect(bgr_image)
            if detections:
                # 检查是否有危险等级的障碍物
                has_hazard = False
                for d in detections:
                    name = str(d.get("name", "")).lower()
                    area = float(d.get("area", 0) or 0)
                    if name in ["car", "bus", "truck"] and area > 10000:
                        has_hazard = True
                        break

                if has_hazard:
                    candidates.append(("hazard", 0.85))

                largest = max(detections, key=lambda d: d.get("area", 0) or 0)
                area = float(largest.get("area", 0) or 0)
                if area > 10000:
                    conf = 0.70
                    area_ratio = largest.get("area_ratio", None)
                    try:
                        if area_ratio is not None:
                            conf = min(0.95, 0.60 + float(area_ratio) * 2.0)
                    except Exception:
                        pass
                    candidates.append(("obstacle", conf))
    except Exception:
        pass

    if not candidates:
        return "unknown", 0.0

    # 5) 选取置信度最高的场景；危险场景优先
    pri = {
        "hazard": 5,  # 最高优先级
        "obstacle": 4,
        "traffic_light_red": 4,
        "traffic_light_yellow": 3,
        "traffic_light_green": 3,
        "crosswalk": 2,
        "blindpath": 1,
        # 新增场景优先级
        "construction": 4,
        "elevator": 3,
        "stairs": 3,
        "hospital": 2,
        "supermarket": 2,
        "mall": 2,
        "subway": 3,
        "park": 1,
        "bus_stop": 2,
        "restaurant": 2,
        "bank": 2,
        "office": 1,
        "school": 1,
        "corridor": 1,
        "restroom": 1,
        "square": 1,
        "parking": 2,
        "underpass": 2,
        "bridge": 2,
        "unknown": 0,
    }
    candidates.sort(key=lambda x: (x[1], pri.get(x[0], 0)), reverse=True)
    return candidates[0]

def _get_scene_announcement(scene: str) -> Optional[str]:
    """
    根据场景返回播报文本（使用结构化格式）

    格式：[场景前缀] + [简要描述]
    """
    # 危险场景（高优先级）
    hazard_announcements = {
        "hazard": "注意，前方有危险物体，先停下",
    }

    # 导航场景
    navigation_announcements = {
        "blindpath": "前方检测到盲道",
        "crosswalk": "发现斑马线",
        "traffic_light_red": "前方是红灯，请等待",
        "traffic_light_green": "前方是绿灯，可以通行",
        "traffic_light_yellow": "前方是黄灯，请注意",
        "obstacle": "前方有障碍物，注意安全",
    }

    # 建筑场景（新增）
    building_announcements = {
        "hospital": "医院环境，请注意周围",
        "supermarket": "超市通道，货架较多",
        "mall": "商场环境，小心扶梯",
        "restaurant": "餐厅环境",
        "bank": "银行环境",
        "office": "办公楼环境",
        "school": "学校环境",
        "subway": "地铁站，注意闸机",
        "bus_stop": "公交车站，注意站台边缘",
    }

    # 室内场景（新增）
    indoor_announcements = {
        "elevator": "电梯区域",
        "stairs": "楼梯区域，注意脚下",
        "corridor": "走廊",
        "restroom": "卫生间",
    }

    # 自然场景（新增）
    nature_announcements = {
        "park": "公园环境",
        "square": "广场环境",
    }

    # 特殊场景（新增）
    special_announcements = {
        "construction": "施工区域，请注意安全",
        "parking": "停车场，注意车辆",
        "underpass": "地下通道，注意照明",
        "bridge": "天桥区域，注意台阶",
    }

    # 合并所有场景播报
    announcements = {}
    announcements.update(hazard_announcements)
    announcements.update(navigation_announcements)
    announcements.update(building_announcements)
    announcements.update(indoor_announcements)
    announcements.update(nature_announcements)
    announcements.update(special_announcements)
    announcements["unknown"] = None  # 未知场景不播报

    return announcements.get(scene)

def process_imu_and_maybe_store(d: Dict[str, Any]):
    global gLP, gOff, yaw, Rf, Pf, Yf, ref, holdStart, isStill, last_ts_imu, last_wall
    global latest_yaw_deg, latest_yaw_rate_dps, latest_yaw_ts, _prev_yaw_for_rate, _prev_yaw_ts_for_rate

    t_ms = float(d.get("ts", 0.0))
    now_wall = time.monotonic()
    if t_ms <= 0.0:
        t_ms = (now_wall * 1000.0)
    if last_ts_imu <= 0.0 or t_ms <= last_ts_imu or (t_ms - last_ts_imu) > 3000.0:
        dt = 0.02
    else:
        dt = (t_ms - last_ts_imu) / 1000.0
    last_ts_imu = t_ms

    ax = float(((d.get("accel") or {}).get("x", 0.0)))
    ay = float(((d.get("accel") or {}).get("y", 0.0)))
    az = float(((d.get("accel") or {}).get("z", 0.0)))
    wx = float(((d.get("gyro")  or {}).get("x", 0.0)))
    wy = float(((d.get("gyro")  or {}).get("y", 0.0)))
    wz = float(((d.get("gyro")  or {}).get("z", 0.0)))

    gLP["x"] = GRAV_BETA * gLP["x"] + (1.0 - GRAV_BETA) * ax
    gLP["y"] = GRAV_BETA * gLP["y"] + (1.0 - GRAV_BETA) * ay
    gLP["z"] = GRAV_BETA * gLP["z"] + (1.0 - GRAV_BETA) * az
    gmag = hypot(gLP["x"], gLP["y"], gLP["z"]) or 1.0
    gHat = {"x": gLP["x"]/gmag, "y": gLP["y"]/gmag, "z": gLP["z"]/gmag}

    roll  = (atan2(az, ay)   * 180.0 / pi)
    pitch = (atan2(-ax, ay)  * 180.0 / pi)

    aNorm = hypot(ax, ay, az); wNorm = hypot(wx, wy, wz)
    nearFlat = (abs(roll) < 2.0 and abs(pitch) < 2.0)
    stillCond = (abs(aNorm - G) < A_TOL) and (wNorm < STILL_W)

    if stillCond:
        if holdStart <= 0.0: holdStart = t_ms
        if not isStill and (t_ms - holdStart) > 350.0: isStill = True
        gOff["x"] = (1.0 - BIAS_ALPHA)*gOff["x"] + BIAS_ALPHA*wx
        gOff["y"] = (1.0 - BIAS_ALPHA)*gOff["y"] + BIAS_ALPHA*wy
        gOff["z"] = (1.0 - BIAS_ALPHA)*gOff["z"] + BIAS_ALPHA*wz
    else:
        holdStart = 0.0; isStill = False

    if USE_PROJ:
        yawdot = ((wx - gOff["x"])*gHat["x"] + (wy - gOff["y"])*gHat["y"] + (wz - gOff["z"])*gHat["z"])
    else:
        yawdot = (wy - gOff["y"])

    if abs(yawdot) < YAW_DB: yawdot = 0.0
    if FREEZE_STILL and stillCond: yawdot = 0.0

    yaw = _wrap180(yaw + yawdot * dt)

    if (YAW_LEAK > 0.0) and nearFlat and stillCond and abs(yaw) > 0.0:
        step = YAW_LEAK * dt * (-1.0 if yaw > 0 else (1.0 if yaw < 0 else 0.0))
        if abs(yaw) <= abs(step): yaw = 0.0
        else: yaw += step

    global Rf, Pf, Yf, ref, last_wall
    Rf = ANG_EMA * roll  + (1.0 - ANG_EMA) * Rf
    Pf = ANG_EMA * pitch + (1.0 - ANG_EMA) * Pf
    Yf = ANG_EMA * yaw   + (1.0 - ANG_EMA) * Yf

    if AUTO_REZERO and nearFlat and (wNorm < STILL_W):
        if holdStart <= 0.0: holdStart = t_ms
        if not isStill and (t_ms - holdStart) > 350.0:
            ref.update({"roll": Rf, "pitch": Pf, "yaw": Yf})
            isStill = True

    R = _wrap180(Rf - ref["roll"])
    P = _wrap180(Pf - ref["pitch"])
    Y = _wrap180(Yf - ref["yaw"])

    # 更新给“语义输出/稳定性”用的快照（单位：deg / deg/s）
    now_ts_sec = t_ms / 1000.0
    latest_yaw_deg = float(Y)
    latest_yaw_ts = float(now_ts_sec)
    if _prev_yaw_for_rate is not None and now_ts_sec > _prev_yaw_ts_for_rate:
        dt_rate = now_ts_sec - _prev_yaw_ts_for_rate
        dy = _wrap180(float(Y) - float(_prev_yaw_for_rate))
        latest_yaw_rate_dps = float(dy / max(1e-6, dt_rate))
    _prev_yaw_for_rate = float(Y)
    _prev_yaw_ts_for_rate = float(now_ts_sec)

    now_wall = time.monotonic()
    if last_wall <= 0.0 or (now_wall - last_wall) >= 0.100:
        last_wall = now_wall
        item = {
            "ts": t_ms/1000.0,
            "angles": {"roll": R, "pitch": P, "yaw": Y},
            "accel":  {"x": ax, "y": ay, "z": az},
            "gyro":   {"x": wx, "y": wy, "z": wz},
        }
        imu_store.append(item)

# ---------- UDP 接收 IMU 并转发 ----------
class UDPProto(asyncio.DatagramProtocol):
    def connection_made(self, transport):
        print(f"[UDP] listening on {UDP_IP}:{UDP_PORT}")
    def datagram_received(self, data, addr):
        try:
            s = data.decode('utf-8', errors='ignore').strip()
            d = json.loads(s)
            if 'ts' not in d and 'timestamp_ms' in d:
                d['ts'] = d.pop('timestamp_ms')
            process_imu_and_maybe_store(d)
            asyncio.create_task(imu_broadcast(json.dumps(d)))
        except Exception:
            pass



# === 新增：注册给 bridge_io 的发送回调（把 JPEG 广播给 /ws/viewer） ===
@app.on_event("startup")
async def on_startup_register_bridge_sender():
    # 保存主线程的事件循环
    main_loop = asyncio.get_event_loop()
    
    def _sender(jpeg_bytes: bytes):
        # 注意：这个函数可能在非协程线程里被调用，需要切回主事件循环
        try:
            # 检查事件循环状态，避免在关闭时发送
            if main_loop.is_closed():
                return
            
            # 标记YOLO已经开始发送处理后的帧
            global yolomedia_sending_frames
            if not yolomedia_sending_frames:
                yolomedia_sending_frames = True
                print("[YOLOMEDIA] 开始发送处理后的帧，切换到YOLO画面", flush=True)
            
            async def _broadcast():
                if not camera_viewers:
                    return
                dead = []
                for ws in list(camera_viewers):
                    try:
                        await ws.send_bytes(jpeg_bytes)
                    except Exception as e:
                        dead.append(ws)
                for ws in dead:
                    try:
                        camera_viewers.remove(ws)
                    except Exception:
                        pass
            
            # 使用保存的主线程事件循环
            future = asyncio.run_coroutine_threadsafe(_broadcast(), main_loop)
            # 不等待结果，避免阻塞生产线程
        except Exception as e:
            # 只在非预期错误时打印日志
            if "Event loop is closed" not in str(e):
                print(f"[DEBUG] _sender error: {e}", flush=True)

    bridge_io.set_sender(_sender)

@app.on_event("startup")
async def on_startup_init_audio():
    """启动时初始化音频系统"""
    # 记录 FastAPI 主事件循环，供音频工作线程正确调度 /stream.wav 广播
    try:
        import audio_stream as _as
        _as.set_server_loop(asyncio.get_running_loop())
    except Exception:
        pass

    # 在后台线程中初始化，避免阻塞启动
    def _init():
        try:
            initialize_audio_system()
            print(f"[AUDIO] 音频系统初始化完成")
        except Exception as e:
            print(f"[AUDIO] 初始化失败: {e}")

    threading.Thread(target=_init, daemon=True).start()

    # 等待音频系统初始化，然后执行启动自检与测试语音
    await asyncio.sleep(2)  # 等待初始化完成

    try:
        selfcheck = run_startup_audio_selfcheck(
            play_probe=os.getenv("AIGLASS_STARTUP_AUDIO_SELFTEST_PLAY", "1") == "1",
            probe_text=os.getenv("AIGLASS_STARTUP_AUDIO_SELFTEST_TEXT", "音频链路自检完成"),
        )
        print(f"[AUDIO] 启动自检详情: {selfcheck}")
    except Exception as e:
        print(f"[AUDIO] 启动自检失败: {e}")

    # 后台预热：为白名单物体准备预设语音（尽可能覆盖）
    _warmup_object_voice_assets_in_background()

    try:
        play_voice_text("系统已启动")
        print("[AUDIO] 已播放测试语音: 系统已启动")
    except Exception as e:
        print(f"[AUDIO] 测试语音播放失败: {e}")

# 【已禁用】启动时初始化事件记录器（JSONL）- 已注释以减少数据传输占用
# @app.on_event("startup")
# async def on_startup_init_event_logger():
#     """启动时初始化事件记录器（JSONL）"""
#     global event_logger
#     try:
#         event_logger = get_event_logger()
#         if getattr(event_logger, "enabled", False):
#             print(f"[EVENT] 事件记录已开启: {getattr(event_logger, 'path', '')}")
#         else:
#             print("[EVENT] 事件记录未开启")
#     except Exception as e:
#         event_logger = None
#         print(f"[EVENT] 初始化失败: {e}")

@app.on_event("startup")
async def on_startup_init_face_friend():
    """启动时初始化本地人脸/朋友识别模块"""
    global face_friend_recognizer
    try:
        face_friend_recognizer = FaceFriendRecognizer()
        print("[FACE] 人脸/朋友识别器已初始化")
    except Exception as e:
        face_friend_recognizer = None
        print(f"[FACE] 人脸/朋友识别器初始化失败: {e}")

@app.on_event("startup")
async def on_startup_init_light_reminder():
    """启动时初始化灯光关闭提醒模块（默认不启用提醒）"""
    global light_detector
    try:
        light_detector = get_light_detector()
        print("[LIGHT] 灯光检测器已初始化")
    except Exception as e:
        light_detector = None
        print(f"[LIGHT] 灯光检测器初始化失败: {e}")

@app.on_event("startup")
async def on_startup_init_semantic_engine():
    """启动时初始化语义输出模块（用于场景探索/结构化输出）"""
    global semantic_engine
    try:
        semantic_engine = get_semantic_engine()
        print("[SEMANTIC] 语义输出模块已初始化")
    except Exception as e:
        semantic_engine = None
        print(f"[SEMANTIC] 语义输出模块初始化失败: {e}")

@app.on_event("startup")
async def on_startup():
    loop = asyncio.get_running_loop()
    await loop.create_datagram_endpoint(lambda: UDPProto(), local_addr=(UDP_IP, UDP_PORT))

@app.on_event("shutdown")
async def on_shutdown():
    """应用关闭时的清理工作"""
    print("[SHUTDOWN] 开始清理资源...")
    
    # 停止YOLO媒体处理
    stop_yolomedia()
    
    # 停止音频和AI任务
    await hard_reset_audio("shutdown")

    # 【已禁用】关闭事件记录器（可选）
    # try:
    #     if event_logger is not None:
    #         event_logger.close()
    # except Exception:
    #     pass

    print("[SHUTDOWN] 资源清理完成")

# app_main.py —— 在文件里已有的 @app.on_event("startup") 之后，再加一个新的 startup 钩子


# --- 导出接口（可选） ---
def get_last_frames():
    return last_frames

def get_camera_ws():
    return esp32_camera_ws

if __name__ == "__main__":
    uvicorn.run(
        app, host="0.0.0.0", port=8081,
        log_level="warning", access_log=False,
        loop="asyncio", workers=1, reload=False
    )
