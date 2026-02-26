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


class SemanticStairStabilityTests(unittest.TestCase):
    def setUp(self):
        self.engine = SemanticOutputEngine()
        self.engine.stair_memory_sec = 5.0
        self.engine.stair_support_min_conf = 0.3

    def test_step_label_is_normalized_to_stairs(self):
        raw = [_obj("step", 0.88, [480, 280, 820, 700])]
        out = self.engine.describe(raw, frame_w=1280, frame_h=720, schema_version=1)
        names = [o.get("name") for o in (out.get("objects") or [])]
        self.assertIn("stairs", names)

    def test_stair_guidance_is_stable_with_handrail_support(self):
        raw1 = [
            _obj("stairs", 0.9, [450, 240, 860, 710]),
            _obj("handrail", 0.75, [860, 200, 980, 700]),
        ]
        out1 = self.engine.describe(raw1, frame_w=1280, frame_h=720, schema_version=1)
        self.assertTrue(any(o.get("name") == "stairs" for o in (out1.get("objects") or [])))

        raw2 = [_obj("handrail", 0.82, [850, 180, 980, 700])]
        out2 = self.engine.describe(raw2, frame_w=1280, frame_h=720, schema_version=1)
        text2 = str(out2.get("text") or "")
        self.assertTrue(
            any(o.get("name") == "stairs" for o in (out2.get("objects") or []))
            or ("楼梯" in text2)
            or ("台阶" in text2)
        )

    def test_no_stair_reinject_without_support_cue(self):
        raw1 = [_obj("stairs", 0.9, [450, 240, 860, 710])]
        self.engine.describe(raw1, frame_w=1280, frame_h=720, schema_version=1)

        raw2 = [_obj("chair", 0.86, [560, 360, 760, 700])]
        out2 = self.engine.describe(raw2, frame_w=1280, frame_h=720, schema_version=1)
        names = [o.get("name") for o in (out2.get("objects") or [])]
        self.assertNotIn("stairs", names)


if __name__ == "__main__":
    unittest.main()
