# -*- coding: utf-8 -*-
"""
轻量 JSONL 事件记录器（用于评估/回放/调试复现）

- 以 JSON Lines 形式追加写入：一行一个事件
- 写入采用后台线程 + 队列，避免阻塞主线程/事件循环

默认开关：
- AIGLASS_EVENT_LOG=1 启用（默认 1）
- AIGLASS_EVENT_LOG_PATH 可指定输出路径（默认 recordings/events_<timestamp>.jsonl）
"""

from __future__ import annotations

import json
import os
import queue
import threading
import time
from datetime import datetime
from typing import Any, Dict, Optional


class JsonlEventLogger:
    def __init__(self, path: str, enabled: bool = True, max_queue: int = 2000):
        self.path = path
        self.enabled = bool(enabled)
        self.q: "queue.Queue[str]" = queue.Queue(maxsize=max_queue)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

        if not self.enabled:
            return

        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        self._thread = threading.Thread(target=self._worker, name="event_logger", daemon=True)
        self._thread.start()

    def _worker(self):
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                while not self._stop.is_set():
                    try:
                        line = self.q.get(timeout=0.5)
                    except queue.Empty:
                        continue
                    if line is None:  # type: ignore[comparison-overlap]
                        break
                    f.write(line + "\n")
                    f.flush()
        except Exception:
            # 记录器失败不应影响主流程
            pass

    def log(self, event: Dict[str, Any]):
        if not self.enabled:
            return
        if not isinstance(event, dict):
            return
        if "ts" not in event:
            event["ts"] = time.time()
        try:
            line = json.dumps(event, ensure_ascii=False)
        except Exception:
            return
        try:
            self.q.put_nowait(line)
        except queue.Full:
            # 队列满时丢弃，保证实时性
            return

    def close(self):
        if not self.enabled:
            return
        try:
            self._stop.set()
            try:
                self.q.put_nowait(None)  # type: ignore[arg-type]
            except Exception:
                pass
        except Exception:
            pass


_logger: Optional[JsonlEventLogger] = None


def get_event_logger() -> JsonlEventLogger:
    global _logger
    if _logger is not None:
        return _logger

    enabled = os.getenv("AIGLASS_EVENT_LOG", "1").strip() not in ("0", "false", "False", "no", "NO")
    path = os.getenv("AIGLASS_EVENT_LOG_PATH", "").strip()
    if not path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(_repo_root(), "recordings", f"events_{ts}.jsonl")

    _logger = JsonlEventLogger(path=path, enabled=enabled)
    return _logger


def _repo_root() -> str:
    return os.path.dirname(os.path.abspath(__file__))

