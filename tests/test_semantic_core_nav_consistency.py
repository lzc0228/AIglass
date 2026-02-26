import unittest

from semantic_output import CORE_NAV_CLASSES, SemanticOutputEngine


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


class SemanticCoreNavConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.engine = SemanticOutputEngine()

    def test_core_nav_whitelist_contains_required_entities(self):
        required = {"traffic light", "crosswalk", "blindpath", "person", "stairs", "turnstile"}
        self.assertTrue(required.issubset(set(CORE_NAV_CLASSES)))

    def test_blindpath_aliases_are_normalized(self):
        self.assertEqual(self.engine._normalize_object_name("blind path"), "blindpath")
        self.assertEqual(self.engine._normalize_object_name("blind_path"), "blindpath")
        self.assertEqual(self.engine._normalize_object_name("tactile paving"), "blindpath")

    def test_core_nav_entities_have_higher_priority_than_furniture(self):
        crosswalk_score = self.engine._compute_score("crosswalk", conf=0.55, area_ratio=0.015, scene="street")
        blindpath_score = self.engine._compute_score("blind path", conf=0.55, area_ratio=0.015, scene="street")
        chair_score = self.engine._compute_score("chair", conf=0.90, area_ratio=0.015, scene="street")
        self.assertGreater(crosswalk_score, chair_score)
        self.assertGreater(blindpath_score, chair_score)

    def test_crosswalk_hint_is_stable_on_brief_miss(self):
        raw1 = [
            _obj("crosswalk", 0.90, [320, 420, 980, 710]),
            _obj("traffic light", 0.82, [560, 90, 720, 260]),
        ]
        out1 = self.engine.describe(raw1, frame_w=1280, frame_h=720, schema_version=1)
        self.assertTrue(any(o.get("name") == "crosswalk" for o in (out1.get("objects") or [])))

        raw2 = [
            _obj("car", 0.88, [220, 260, 640, 710]),
            _obj("bus", 0.86, [700, 260, 1260, 710]),
        ]
        out2 = self.engine.describe(raw2, frame_w=1280, frame_h=720, schema_version=1)
        names2 = [o.get("name") for o in (out2.get("objects") or [])]
        text2 = str(out2.get("text") or "")
        self.assertTrue(("crosswalk" in names2) or ("斑马线" in text2))


if __name__ == "__main__":
    unittest.main()
