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


class SemanticStairHandrailGuidanceTests(unittest.TestCase):
    def setUp(self):
        self.engine = SemanticOutputEngine()

    def test_handrail_action_uses_directional_guidance_in_stair_context(self):
        raw = [
            _obj("stairs", 0.9, [520, 220, 860, 700]),
            _obj("handrail", 0.82, [260, 180, 360, 700]),
        ]
        out = self.engine.describe(raw, frame_w=1280, frame_h=720, schema_version=1)
        names = [o.get("name") for o in (out.get("objects") or [])]
        self.assertIn("handrail", names)

        handrail_obj = next(o for o in (out.get("objects") or []) if o.get("name") == "handrail")
        action = str(handrail_obj.get("avoidance_action") or "")
        self.assertIn("扶手", action)
        self.assertNotIn("绕开", action)
        self.assertNotIn("避让", action)
        self.assertTrue(("左" in action) or ("右" in action) or ("前方" in action))

    def test_stair_context_keeps_handrail_in_output_priority(self):
        raw = [
            _obj("stairs", 0.9, [520, 220, 860, 700]),
            _obj("handrail", 0.82, [260, 180, 360, 700]),
            _obj("person", 0.95, [620, 260, 760, 690]),
            _obj("car", 0.93, [880, 260, 1240, 700]),
            _obj("bicycle", 0.9, [380, 260, 560, 700]),
        ]
        out = self.engine.describe(raw, frame_w=1280, frame_h=720, schema_version=1)
        names = [o.get("name") for o in (out.get("objects") or [])]
        text = str(out.get("text") or "")

        self.assertIn("stairs", names)
        self.assertIn("handrail", names)
        self.assertIn("扶手", text)


if __name__ == "__main__":
    unittest.main()
