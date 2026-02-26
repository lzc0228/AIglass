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


class SemanticGlassGuidanceTests(unittest.TestCase):
    def setUp(self):
        self.engine = SemanticOutputEngine()

    def test_door_handle_switch_yields_glass_door_cue(self):
        raw = [
            _obj("door", 0.86, [500, 90, 900, 700]),
            _obj("door handle", 0.79, [820, 360, 900, 460]),
            _obj("light switch", 0.74, [920, 280, 980, 410]),
        ]
        out = self.engine.describe(raw, frame_w=1280, frame_h=720, schema_version=1)
        names = [o.get("name") for o in (out.get("objects") or [])]
        self.assertIn("glass_door", names)
        self.assertIn("点方向", str(out.get("text") or ""))
        self.assertTrue(("玻璃门" in str(out.get("text") or "")) or ("门把手" in str(out.get("text") or "")))

    def test_window_handle_yields_glass_window_cue(self):
        raw = [
            _obj("window", 0.88, [420, 120, 860, 500]),
            _obj("handle", 0.72, [780, 280, 840, 360]),
        ]
        out = self.engine.describe(raw, frame_w=1280, frame_h=720, schema_version=1)
        names = [o.get("name") for o in (out.get("objects") or [])]
        self.assertIn("glass_window", names)
        self.assertIn("点方向", str(out.get("text") or ""))

    def test_glass_door_action_is_guidance_not_generic_avoid(self):
        action, urgency = self.engine._avoidance(
            name="glass_door",
            cx=640,
            w=1280,
            distance_m=2.0,
            risk_score=0.52,
            motion_dir="unknown",
            support_factor=0.3,
            speed_norm=0.0,
            approach_rate=0.0,
        )
        self.assertIn(urgency, ("LOW", "MEDIUM", "HIGH"))
        self.assertNotIn("绕开", action)
        self.assertNotIn("避让", action)
        self.assertTrue(("玻璃" in action) or ("门把手" in action) or ("开关" in action))


if __name__ == "__main__":
    unittest.main()
