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


class SemanticLowFenceDetectionTests(unittest.TestCase):
    def setUp(self):
        self.engine = SemanticOutputEngine()

    def test_low_fence_aliases_are_normalized_to_fence(self):
        self.assertEqual(self.engine._normalize_object_name("low fence"), "fence")
        self.assertEqual(self.engine._normalize_object_name("short fence"), "fence")
        self.assertEqual(self.engine._normalize_object_name("guard rail"), "fence")

    def test_low_fence_priority_is_higher_than_generic_furniture_on_sidewalk(self):
        fence_score = self.engine._compute_score("low fence", conf=0.62, area_ratio=0.012, scene="sidewalk")
        chair_score = self.engine._compute_score("chair", conf=0.90, area_ratio=0.012, scene="sidewalk")
        self.assertGreater(fence_score, chair_score)

    def test_output_keeps_low_fence_with_competing_objects(self):
        raw = [
            _obj("low fence", 0.60, [120, 520, 1040, 700]),
            _obj("chair", 0.93, [120, 220, 420, 700]),
            _obj("table", 0.91, [460, 220, 960, 700]),
            _obj("car", 0.88, [980, 180, 1260, 700]),
        ]
        out = self.engine.describe(raw, frame_w=1280, frame_h=720, schema_version=1)
        names = [o.get("name") for o in (out.get("objects") or [])]
        self.assertIn("fence", names)
        text = str(out.get("text") or "")
        self.assertTrue(("围栏" in text) or ("栏杆" in text))


if __name__ == "__main__":
    unittest.main()
