import unittest

from semantic_output import ROADSIDE_OBSTACLE_CLASSES, SemanticOutputEngine


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


class SemanticRoadsideObstacleTests(unittest.TestCase):
    def setUp(self):
        self.engine = SemanticOutputEngine()

    def test_aliases_are_normalized_for_roadside_targets(self):
        self.assertEqual(self.engine._normalize_object_name("trash can"), "trash bin")
        self.assertEqual(self.engine._normalize_object_name("garbage bin"), "trash bin")
        self.assertEqual(self.engine._normalize_object_name("e-bike"), "scooter")
        self.assertEqual(self.engine._normalize_object_name("electric bike"), "scooter")

    def test_roadside_target_whitelist_contains_required_classes(self):
        required = {"trash bin", "bicycle", "scooter", "motorcycle"}
        self.assertTrue(required.issubset(set(ROADSIDE_OBSTACLE_CLASSES)))

    def test_roadside_targets_have_higher_priority_than_generic_furniture(self):
        trash_score = self.engine._compute_score("trash bin", conf=0.66, area_ratio=0.02, scene="street")
        motorcycle_score = self.engine._compute_score("motorcycle", conf=0.62, area_ratio=0.02, scene="street")
        chair_score = self.engine._compute_score("chair", conf=0.90, area_ratio=0.02, scene="street")
        self.assertGreater(trash_score, chair_score)
        self.assertGreater(motorcycle_score, chair_score)

    def test_output_keeps_multiple_roadside_targets_with_competition(self):
        raw = [
            _obj("trash can", 0.62, [80, 210, 280, 700]),
            _obj("bicycle", 0.59, [320, 200, 560, 700]),
            _obj("e-bike", 0.58, [620, 190, 880, 700]),
            _obj("motorcycle", 0.57, [920, 190, 1240, 700]),
            _obj("chair", 0.93, [180, 240, 460, 700]),
            _obj("table", 0.91, [560, 240, 980, 700]),
        ]
        out = self.engine.describe(raw, frame_w=1280, frame_h=720, schema_version=1)
        names = [o.get("name") for o in (out.get("objects") or [])]
        targets = {"trash bin", "bicycle", "scooter", "motorcycle"}
        self.assertGreaterEqual(len([n for n in names if n in targets]), 2)


if __name__ == "__main__":
    unittest.main()
