# -*- coding: utf-8 -*-
"""
本地人脸/朋友识别（离线优先）

实现目标：
- 支持“录入朋友（记住/这是XXX）”与“识别朋友（这是谁）”闭环
- 数据落盘：context/faces/db.json + context/faces/images/*.png + context/faces/lbph.yml
- 依赖：OpenCV（含 cv2.face.LBPHFaceRecognizer_create）
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np


def _repo_root() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def _now_ts() -> float:
    return time.time()


def _safe_write_json(path: str, data: Dict[str, Any]):
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


@dataclass
class PersonProfile:
    label: int
    name: str
    gender: Optional[str] = None  # "男" / "女" / None
    age: Optional[int] = None
    created_at: float = 0.0
    updated_at: float = 0.0
    samples: List[str] = None

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "PersonProfile":
        return PersonProfile(
            label=int(d.get("label", 0)),
            name=str(d.get("name", "")),
            gender=d.get("gender"),
            age=(int(d["age"]) if d.get("age") is not None else None),
            created_at=float(d.get("created_at", 0.0) or 0.0),
            updated_at=float(d.get("updated_at", 0.0) or 0.0),
            samples=list(d.get("samples") or []),
        )


class FaceFriendRecognizer:
    """
    - Haar Cascade 做人脸检测
    - LBPH 做本地识别（对光照/分辨率有一定鲁棒性）
    """

    def __init__(self, db_dir: Optional[str] = None):
        self.db_dir = db_dir or os.getenv(
            "AIGLASS_FACE_DB_DIR", os.path.join(_repo_root(), "context", "faces")
        )
        self.images_dir = os.path.join(self.db_dir, "images")
        self.db_path = os.path.join(self.db_dir, "db.json")
        self.model_path = os.path.join(self.db_dir, "lbph.yml")
        os.makedirs(self.images_dir, exist_ok=True)

        cascade_path = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
        self.detector = cv2.CascadeClassifier(cascade_path)
        if self.detector.empty():
            raise RuntimeError(f"无法加载人脸检测器: {cascade_path}")

        if not hasattr(cv2, "face") or not hasattr(cv2.face, "LBPHFaceRecognizer_create"):
            raise RuntimeError("当前 OpenCV 不包含 cv2.face.LBPHFaceRecognizer_create（需要 opencv-contrib）")

        self.recognizer = cv2.face.LBPHFaceRecognizer_create()
        self.people_by_label: Dict[int, PersonProfile] = {}
        self.label_by_name: Dict[str, int] = {}
        self.next_label = 1

        self.is_trained = False
        self._load_db()
        self._rebuild_model_from_db()

        # 识别阈值：LBPH 距离越小越相似；阈值越大越“宽松”
        self.match_threshold = float(os.getenv("AIGLASS_FACE_MATCH_THRESHOLD", "65"))

    # ---------- DB ----------
    def _load_db(self):
        if not os.path.exists(self.db_path):
            self._persist_db()
            return
        try:
            with open(self.db_path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
        except Exception:
            data = {}

        people = data.get("people") or []
        for item in people:
            p = PersonProfile.from_dict(item)
            if p.label <= 0 or not p.name:
                continue
            p.samples = list(p.samples or [])
            self.people_by_label[p.label] = p
            self.label_by_name[p.name] = p.label
            self.next_label = max(self.next_label, p.label + 1)

    def _persist_db(self):
        data = {
            "version": 1,
            "updated_at": _now_ts(),
            "people": [asdict(p) for p in sorted(self.people_by_label.values(), key=lambda x: x.label)],
        }
        _safe_write_json(self.db_path, data)

    # ---------- Face detect / preprocess ----------
    def _detect_faces(self, bgr: np.ndarray) -> List[Tuple[int, int, int, int]]:
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        faces = self.detector.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(80, 80),
            flags=cv2.CASCADE_SCALE_IMAGE,
        )
        return [(int(x), int(y), int(w), int(h)) for (x, y, w, h) in (faces or [])]

    @staticmethod
    def _expand_box(x: int, y: int, w: int, h: int, W: int, H: int, pad: float = 0.15) -> Tuple[int, int, int, int]:
        px = int(w * pad)
        py = int(h * pad)
        x1 = max(0, x - px)
        y1 = max(0, y - py)
        x2 = min(W - 1, x + w + px)
        y2 = min(H - 1, y + h + py)
        return x1, y1, x2, y2

    @staticmethod
    def _prep_face(gray_face: np.ndarray, size: int = 160) -> np.ndarray:
        face = cv2.resize(gray_face, (size, size), interpolation=cv2.INTER_LINEAR)
        face = cv2.equalizeHist(face)
        return face

    def _extract_primary_face(self, bgr: np.ndarray) -> Tuple[Optional[np.ndarray], Dict[str, Any]]:
        H, W = bgr.shape[:2]
        faces = self._detect_faces(bgr)
        if not faces:
            return None, {"reason": "no_face"}
        # 取面积最大的脸
        x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
        x1, y1, x2, y2 = self._expand_box(x, y, w, h, W, H)
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        crop = gray[y1:y2, x1:x2]
        if crop.size == 0:
            return None, {"reason": "bad_crop"}
        face = self._prep_face(crop)
        return face, {"bbox": [x1, y1, x2, y2], "faces": len(faces)}

    # ---------- Train / update ----------
    def _rebuild_model_from_db(self):
        images: List[np.ndarray] = []
        labels: List[int] = []
        for label, person in self.people_by_label.items():
            for rel_path in list(person.samples or []):
                img_path = rel_path
                if not os.path.isabs(img_path):
                    img_path = os.path.join(self.db_dir, rel_path)
                if not os.path.exists(img_path):
                    continue
                img = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
                if img is None or img.size == 0:
                    continue
                img = self._prep_face(img)
                images.append(img)
                labels.append(int(label))

        if not images:
            self.is_trained = False
            return

        self.recognizer.train(images, np.array(labels, dtype=np.int32))
        self.is_trained = True
        try:
            self.recognizer.write(self.model_path)
        except Exception:
            pass

    # ---------- Public APIs ----------
    @staticmethod
    def parse_name_gender_age(text: str) -> Dict[str, Any]:
        """
        从中文口令里尽可能解析 name / gender / age。
        例：
        - "这是张三，男，30岁"
        - "记住她叫小美 25岁"
        """
        t = (text or "").strip()
        # name
        name = None
        m = re.search(r"(?:这是|叫|名叫|他叫|她叫|记住|认识|把他记成|把她记成)\s*([\\u4e00-\\u9fffA-Za-z0-9]{1,16})", t)
        if m:
            name = m.group(1).strip()

        # gender
        gender = None
        if re.search(r"(男性|男生|男人|\\b男\\b|男)", t):
            gender = "男"
        if re.search(r"(女性|女生|女人|\\b女\\b|女)", t):
            gender = "女" if gender is None else gender

        # age
        age = None
        m2 = re.search(r"(\\d{1,3})\\s*岁", t)
        if m2:
            try:
                age = int(m2.group(1))
            except Exception:
                age = None

        return {"name": name, "gender": gender, "age": age}

    def list_people(self) -> List[Dict[str, Any]]:
        out = []
        for p in sorted(self.people_by_label.values(), key=lambda x: x.label):
            out.append(
                {
                    "name": p.name,
                    "gender": p.gender,
                    "age": p.age,
                    "samples": len(p.samples or []),
                }
            )
        return out

    def enroll(self, bgr: np.ndarray, name: str, gender: Optional[str] = None, age: Optional[int] = None) -> Dict[str, Any]:
        if bgr is None or bgr.size == 0:
            return {"ok": False, "message": "没有画面，无法录入。"}
        name = (name or "").strip()
        if not name:
            return {"ok": False, "message": "请告诉我要记住的名字，比如：这是张三。"}

        face, meta = self._extract_primary_face(bgr)
        if face is None:
            return {"ok": False, "message": "没有检测到清晰的人脸，请把人脸对准镜头再试。", "meta": meta}

        label = self.label_by_name.get(name)
        now = _now_ts()
        if label is None:
            label = self.next_label
            self.next_label += 1
            profile = PersonProfile(
                label=label,
                name=name,
                gender=gender,
                age=age,
                created_at=now,
                updated_at=now,
                samples=[],
            )
            self.people_by_label[label] = profile
            self.label_by_name[name] = label
        else:
            profile = self.people_by_label.get(label)
            if profile is None:
                profile = PersonProfile(label=label, name=name, samples=[])
                self.people_by_label[label] = profile
            profile.updated_at = now
            if gender:
                profile.gender = gender
            if age is not None:
                profile.age = age

        # 保存样本
        fname = f"{name}_{label}_{int(now)}.png"
        rel_path = os.path.join("images", fname)
        abs_path = os.path.join(self.db_dir, rel_path)
        try:
            cv2.imwrite(abs_path, face)
        except Exception as e:
            return {"ok": False, "message": f"保存人脸样本失败: {e}"}

        profile.samples = list(profile.samples or [])
        profile.samples.append(rel_path)
        self._persist_db()

        # 训练/更新模型（简单起见：每次录入后重建）
        self._rebuild_model_from_db()
        if not self.is_trained:
            return {"ok": False, "message": "录入完成，但训练失败（样本不足或损坏）。"}

        g = f"，{profile.gender}" if profile.gender else ""
        a = f"，{profile.age}岁" if profile.age is not None else ""
        return {"ok": True, "message": f"已记住：{profile.name}{g}{a}。", "meta": meta}

    def forget(self, name: str) -> Dict[str, Any]:
        name = (name or "").strip()
        if not name:
            return {"ok": False, "message": "请告诉我要删除的名字，比如：忘记张三。"}
        label = self.label_by_name.get(name)
        if label is None:
            return {"ok": False, "message": f"我还没记住 {name}。"}
        profile = self.people_by_label.pop(label, None)
        self.label_by_name.pop(name, None)
        # 不强制删除图片文件（避免误删）；只从 db 中移除即可
        self._persist_db()
        self._rebuild_model_from_db()
        if profile:
            return {"ok": True, "message": f"已忘记：{profile.name}。"}
        return {"ok": True, "message": f"已忘记：{name}。"}

    def recognize(self, bgr: np.ndarray) -> Dict[str, Any]:
        if bgr is None or bgr.size == 0:
            return {"ok": False, "message": "没有画面，无法识别。"}
        if not self.is_trained:
            return {"ok": False, "message": "我还没有录入任何朋友。你可以说：这是张三。"}

        face, meta = self._extract_primary_face(bgr)
        if face is None:
            return {"ok": False, "message": "没有检测到清晰的人脸，请把人脸对准镜头再试。", "meta": meta}

        try:
            label, dist = self.recognizer.predict(face)
        except Exception as e:
            return {"ok": False, "message": f"识别失败: {e}"}

        dist = float(dist)
        if dist > self.match_threshold:
            return {
                "ok": True,
                "message": "我看到有人，但还不认识。你可以说：这是某某。",
                "meta": {**meta, "distance": dist},
            }

        profile = self.people_by_label.get(int(label))
        if not profile:
            return {"ok": True, "message": "我可能认识这个人，但档案缺失。你可以重新录入。", "meta": meta}

        # 置信度（粗略映射）
        conf = max(0.0, min(1.0, (self.match_threshold - dist) / max(1e-6, self.match_threshold)))
        g = f"，{profile.gender}" if profile.gender else ""
        a = f"，{profile.age}岁" if profile.age is not None else ""
        return {
            "ok": True,
            "message": f"我觉得是 {profile.name}{g}{a}。",
            "meta": {**meta, "distance": dist, "confidence": conf},
        }

