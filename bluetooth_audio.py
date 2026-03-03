# bluetooth_audio.py
"""
蓝牙音频管理模块

支持 Jetson Nano 通过蓝牙将音频传输到骨传导耳机
使用 PulseAudio 进行音频路由
"""
import os
import subprocess
import logging
import time
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class BluetoothDevice:
    """蓝牙设备信息"""
    mac_addr: str
    name: str
    connected: bool = False


class BluetoothAudioManager:
    """
    蓝牙音频管理器

    功能：
    - 扫描附近蓝牙设备
    - 连接/断开蓝牙设备
    - 通过 PulseAudio 路由音频到蓝牙设备
    - 检查连���状态
    """

    def __init__(self):
        self.device_addr: Optional[str] = None
        self.device_name: Optional[str] = None
        self.connected = False
        self._last_check_time = 0.0
        self._check_interval = float(os.getenv("AIGLASS_BLUETOOTH_CHECK_INTERVAL", "5"))
        self._pulse_client = None

        # 从环境变量读取配置
        self.enabled = os.getenv("AIGLASS_BLUETOOTH_ENABLED", "0") == "1"
        self.auto_connect = os.getenv("AIGLASS_BLUETOOTH_AUTO_CONNECT", "0") == "1"
        self.target_device_name = os.getenv("AIGLASS_BLUETOOTH_DEVICE_NAME", "")
        self.target_device_addr = os.getenv("AIGLASS_BLUETOOTH_DEVICE_ADDR", "")

        if self.enabled:
            logger.info("[BT] 蓝牙音频已启用")
            self._init_pulseaudio()

    def _init_pulseaudio(self):
        """初始化 PulseAudio"""
        try:
            # 检查 PulseAudio 是否运行
            result = subprocess.run(
                ["pactl", "info"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                logger.info("[BT] PulseAudio 已运行")
            else:
                logger.warning("[BT] PulseAudio 未运行，尝试启动...")
                subprocess.run(["pulseaudio", "--start"], check=False)
        except FileNotFoundError:
            logger.error("[BT] 未找到 pactl 命令，请安装 pulseaudio")
        except Exception as e:
            logger.error(f"[BT] 初始化 PulseAudio 失败: {e}")

    def scan_devices(self) -> List[BluetoothDevice]:
        """
        扫描附近蓝牙设备

        返回: 设备列表
        """
        devices = []

        if not self.enabled:
            logger.warning("[BT] 蓝牙音频未启用")
            return devices

        try:
            # 使用 bluetoothctl 扫描设备
            result = subprocess.run(
                ["bluetoothctl", "devices"],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                for line in result.stdout.split("\n"):
                    if "Device" in line:
                        parts = line.split(maxsplit=2)
                        if len(parts) >= 3:
                            mac_addr = parts[1]
                            name = parts[2].strip("()")
                            devices.append(BluetoothDevice(mac_addr=mac_addr, name=name))

                logger.info(f"[BT] 扫描到 {len(devices)} 个设备")
        except FileNotFoundError:
            logger.error("[BT] 未找到 bluetoothctl 命令，请安装 bluez")
        except subprocess.TimeoutExpired:
            logger.error("[BT] 扫描超时")
        except Exception as e:
            logger.error(f"[BT] 扫描失败: {e}")

        return devices

    def connect(self, device_addr: Optional[str] = None, device_name: Optional[str] = None) -> bool:
        """
        连接蓝牙设备

        Args:
            device_addr: 设备 MAC 地址（可选，默认使用配置）
            device_name: 设备名称（用于日志）

        Returns:
            bool: 连接是否成功
        """
        if not self.enabled:
            logger.warning("[BT] 蓝牙音频未启用")
            return False

        addr = device_addr or self.target_device_addr
        if not addr:
            logger.error("[BT] 未指定蓝牙设备地址")
            return False

        try:
            # 使用 bluetoothctl 连接设备
            result = subprocess.run(
                ["bluetoothctl", "connect", addr],
                capture_output=True,
                text=True,
                timeout=15
            )

            if result.returncode == 0 and "successful" in result.stdout.lower():
                self.device_addr = addr
                self.device_name = device_name or addr
                self.connected = True
                logger.info(f"[BT] 成功连接到 {device_name or addr}")

                # 设置为音频输出设备
                self._set_audio_sink(addr)
                return True
            else:
                logger.error(f"[BT] 连接失败: {result.stdout}")
                return False

        except subprocess.TimeoutExpired:
            logger.error(f"[BT] 连接超时: {addr}")
            return False
        except Exception as e:
            logger.error(f"[BT] 连接异常: {e}")
            return False

    def disconnect(self) -> bool:
        """断开蓝牙连接"""
        if not self.connected or not self.device_addr:
            return True

        try:
            result = subprocess.run(
                ["bluetoothctl", "disconnect", self.device_addr],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0:
                self.connected = False
                logger.info(f"[BT] 已断开 {self.device_name or self.device_addr}")
                return True
            return False

        except Exception as e:
            logger.error(f"[BT] 断开连接失败: {e}")
            return False

    def _set_audio_sink(self, device_addr: str):
        """设置音频输出到蓝牙设备"""
        try:
            # 获取蓝牙音频 sink 名称
            result = subprocess.run(
                ["pactl", "list", "sinks", "short"],
                capture_output=True,
                text=True,
                timeout=5
            )

            bluez_sink = None
            for line in result.stdout.split("\n"):
                if "bluez" in line.lower() and device_addr.replace(":", "_").lower() in line.lower():
                    # pactl list sinks short 输出通常为：
                    # <index>\t<sink_name>\t<driver>\t<spec>\t<state>...
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        bluez_sink = parts[1]
                    elif parts:
                        bluez_sink = parts[0]
                    break

            if bluez_sink:
                # 设置默认 sink
                subprocess.run(
                    ["pactl", "set-default-sink", bluez_sink],
                    capture_output=True,
                    timeout=5
                )
                logger.info(f"[BT] 音频输出已设置到 {bluez_sink}")
            else:
                logger.warning(f"[BT] 未找到对应音频 sink: {device_addr}")

        except Exception as e:
            logger.error(f"[BT] 设置音频 sink 失败: {e}")

    def is_connected(self) -> bool:
        """检查蓝牙连接状态（使用缓存值）"""
        return self.connected

    def check_connection(self) -> bool:
        """
        主动检测蓝牙连接状态（通过 PulseAudio）

        Returns:
            bool: 是否有蓝牙音频设备连接
        """
        try:
            now = time.time()
            if now - self._last_check_time < self._check_interval:
                return self.connected
            self._last_check_time = now

            # 使用 pactl 检查是否有蓝牙音频 sink 在运行
            result = subprocess.run(
                ["pactl", "list", "sinks", "short"],
                capture_output=True,
                text=True,
                timeout=5
            )

            prev = self.connected
            detected = False

            # 1) 检查是否有 bluez 设备且状态为 RUNNING
            for line in result.stdout.split("\n"):
                if "bluez" in line.lower() and "RUNNING" in line:
                    self.connected = True
                    detected = True
                    break

            # 2) 有 bluez 设备但不是 RUNNING（可能已连接但未播放）
            if not detected:
                for line in result.stdout.split("\n"):
                    if "bluez" in line.lower():
                        self.connected = False
                        detected = True
                        break

            if not detected:
                self.connected = False

            # 只在状态变化时输出提示，避免刷屏
            if self.connected != prev:
                if self.connected:
                    print("[BT] 检测到蓝牙音频 sink（RUNNING），将切换到蓝牙输出")
                else:
                    print("[BT] 未检测到 RUNNING 蓝牙音频 sink，将切换到本地输出")

            return self.connected

        except FileNotFoundError:
            # pactl 不可用，回退到基本检查
            return self.connected
        except Exception as e:
            logger.error(f"[BT] 检测连接状态失败: {e}")
            return self.connected

    def auto_connect_device(self) -> bool:
        """自动连接到配置的设备"""
        if not self.auto_connect:
            return False

        # 如果有配置的设备地址，直接连接
        if self.target_device_addr:
            return self.connect(self.target_device_addr, self.target_device_name)

        # 否则扫描并按名称匹配
        if self.target_device_name:
            devices = self.scan_devices()
            for device in devices:
                if self.target_device_name.lower() in device.name.lower():
                    return self.connect(device.mac_addr, device.name)

        return False

    def get_connected_device(self) -> Optional[BluetoothDevice]:
        """获取当前连接的设备信息"""
        if not self.connected:
            return None

        return BluetoothDevice(
            mac_addr=self.device_addr or "",
            name=self.device_name or "Unknown",
            connected=True
        )


# 全局单例
_bluetooth_manager: Optional[BluetoothAudioManager] = None


def get_bluetooth_manager() -> BluetoothAudioManager:
    """获取蓝牙音频管理器单例"""
    global _bluetooth_manager
    if _bluetooth_manager is None:
        _bluetooth_manager = BluetoothAudioManager()
    return _bluetooth_manager
