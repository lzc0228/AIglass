import time
import unittest

from semantic_output import SemanticOutputEngine


def _obj(name, conf, bbox, frame_w=1280, frame_h=720):
    x1, y1, x2, y2 = bbox
    area_ratio = max(0.0, (x2 - x1) * (y2 - y1)) / float(frame_w * frame_h)
    return {
        "name": name,
        "conf": conf,
        "bbox": [x1, y1, x2, y2],
        "center_x": (x1 + x2) / 2.0,
        "center_y": (y1 + y2) / 2.0,
        "area_ratio": area_ratio,
    }


class SemanticStopGazeFocusModeTests(unittest.TestCase):
    def setUp(self):
        self.engine = SemanticOutputEngine()
        self.engine.focus_gaze_hold_sec = 2.0

    def _sample_forward_scene(self):
        return [
            _obj("door", 0.88, [450, 160, 820, 700]),
            _obj("chair", 0.74, [260, 250, 430, 700]),
            _obj("fence", 0.68, [860, 520, 1240, 700]),
        ]

    def test_focus_mode_triggers_after_stop_and_gaze_hold(self):
        raw = self._sample_forward_scene()
        out1 = self.engine.describe(
            raw,
            frame_w=1280,
            frame_h=720,
            schema_version=1,
            imu_yaw_deg=10.0,
            imu_yaw_rate_dps=0.8,
        )
        self.assertIn("focused_mode", out1)
        self.assertFalse(bool(out1.get("focused_mode")))

        self.engine._focus_anchor_ts = time.time() - 2.3
        self.engine._focus_anchor_yaw = 10.0
        out2 = self.engine.describe(
            raw,
            frame_w=1280,
            frame_h=720,
            schema_version=1,
            imu_yaw_deg=10.4,
            imu_yaw_rate_dps=0.6,
        )
        self.assertTrue(bool(out2.get("focused_mode")))

    def test_turning_state_disables_focus_mode(self):
        raw = self._sample_forward_scene()
        self.engine._focus_anchor_ts = time.time() - 2.6
        self.engine._focus_anchor_yaw = 8.0
        out = self.engine.describe(
            raw,
            frame_w=1280,
            frame_h=720,
            schema_version=1,
            imu_yaw_deg=8.1,
            imu_yaw_rate_dps=35.0,
        )
        self.assertFalse(bool(out.get("focused_mode")))

    def test_focus_mode_uses_richer_forward_text(self):
        raw = self._sample_forward_scene()
        self.engine._focus_anchor_ts = time.time() - 2.4
        self.engine._focus_anchor_yaw = 12.0
        out = self.engine.describe(
            raw,
            frame_w=1280,
            frame_h=720,
            schema_version=1,
            imu_yaw_deg=12.2,
            imu_yaw_rate_dps=0.5,
        )
        self.assertTrue(bool(out.get("focused_mode")))
        text = str(out.get("text") or "")
        self.assertIn("重点观察前方", text)


if __name__ == "__main__":
    unittest.main()
