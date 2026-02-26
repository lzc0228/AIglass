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


class SemanticTurnstilePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.engine = SemanticOutputEngine()
        self.engine.turnstile_memory_sec = 5.0
        self.engine.turnstile_support_min_conf = 0.3

    def test_turnstile_context_kept_after_gate_transition(self):
        raw1 = [
            _obj("turnstile", 0.9, [460, 180, 860, 700]),
            _obj("ticket machine", 0.78, [860, 200, 1100, 700]),
        ]
        out1 = self.engine.describe(raw1, frame_w=1280, frame_h=720, schema_version=1)
        self.assertTrue(any(o.get("name") == "turnstile" for o in (out1.get("objects") or [])))

        raw2 = [
            _obj("ticket machine", 0.84, [840, 180, 1100, 700]),
            _obj("barrier", 0.76, [460, 220, 760, 700]),
        ]
        out2 = self.engine.describe(raw2, frame_w=1280, frame_h=720, schema_version=1)
        names2 = [o.get("name") for o in (out2.get("objects") or [])]
        text2 = str(out2.get("text") or "")
        self.assertTrue(("turnstile" in names2) or ("闸机" in text2))

    def test_no_turnstile_reinject_without_support(self):
        raw1 = [_obj("turnstile", 0.9, [460, 180, 860, 700])]
        self.engine.describe(raw1, frame_w=1280, frame_h=720, schema_version=1)

        raw2 = [_obj("chair", 0.88, [560, 240, 760, 700])]
        out2 = self.engine.describe(raw2, frame_w=1280, frame_h=720, schema_version=1)
        names2 = [o.get("name") for o in (out2.get("objects") or [])]
        self.assertNotIn("turnstile", names2)

    def test_turnstile_action_is_channel_guidance_not_generic_avoid(self):
        action, urgency = self.engine._avoidance(
            name="turnstile",
            cx=640,
            w=1280,
            distance_m=1.8,
            risk_score=0.52,
            motion_dir="unknown",
            support_factor=0.2,
            speed_norm=0.0,
            approach_rate=0.0,
        )
        self.assertIn(urgency, ("LOW", "MEDIUM", "HIGH"))
        self.assertNotIn("稍微向右侧避让", action)
        self.assertIn("闸机", action)


if __name__ == "__main__":
    unittest.main()
