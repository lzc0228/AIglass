import unittest

from semantic_output import SemanticOutputEngine, VERTICAL_STATIC_CLASSES


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


class SemanticVerticalStaticObstacleTests(unittest.TestCase):
    def setUp(self):
        self.engine = SemanticOutputEngine()

    def test_aliases_are_normalized_for_target_classes(self):
        self.assertEqual(self.engine._normalize_object_name("fire hydrant"), "hydrant")
        self.assertEqual(self.engine._normalize_object_name("sign post"), "signpost")
        self.assertEqual(self.engine._normalize_object_name("tree trunk"), "tree")

    def test_vertical_static_whitelist_contains_target_classes(self):
        required = {"pole", "bollard", "hydrant", "signpost", "tree"}
        self.assertTrue(required.issubset(set(VERTICAL_STATIC_CLASSES)))

    def test_street_vertical_obstacles_have_higher_priority_than_generic_furniture(self):
        sign_score = self.engine._compute_score("signpost", conf=0.62, area_ratio=0.02, scene="street")
        hydrant_score = self.engine._compute_score("hydrant", conf=0.62, area_ratio=0.02, scene="street")
        chair_score = self.engine._compute_score("chair", conf=0.9, area_ratio=0.02, scene="street")
        self.assertGreater(sign_score, chair_score)
        self.assertGreater(hydrant_score, chair_score)

    def test_output_keeps_multiple_target_vertical_classes(self):
        raw = [
            _obj("fire hydrant", 0.72, [540, 300, 700, 700]),
            _obj("sign post", 0.70, [240, 180, 320, 700]),
            _obj("tree trunk", 0.68, [900, 160, 980, 700]),
            _obj("chair", 0.92, [400, 260, 560, 700]),
            _obj("table", 0.90, [700, 260, 980, 700]),
        ]
        out = self.engine.describe(raw, frame_w=1280, frame_h=720, schema_version=1)
        names = [o.get("name") for o in (out.get("objects") or [])]
        self.assertGreaterEqual(
            len([n for n in names if n in {"hydrant", "signpost", "tree", "bollard", "pole"}]),
            2,
        )


if __name__ == "__main__":
    unittest.main()
