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


class SemanticIndoorPottedPlantTests(unittest.TestCase):
    def setUp(self):
        self.engine = SemanticOutputEngine()

    def test_indoor_plant_alias_is_normalized_to_potted_plant(self):
        raw = [
            _obj("plant", 0.9, [520, 220, 760, 700]),
            _obj("chair", 0.8, [260, 260, 430, 700]),
            _obj("table", 0.75, [820, 280, 1100, 700]),
        ]
        out = self.engine.describe(raw, frame_w=1280, frame_h=720, schema_version=1)
        names = [o.get("name") for o in (out.get("objects") or [])]
        text = str(out.get("text") or "")
        self.assertIn("potted plant", names)
        self.assertIn("盆栽", text)

    def test_near_potted_plant_uses_specific_obstacle_guidance(self):
        raw = [
            _obj("potted plant", 0.88, [520, 220, 860, 700]),
            _obj("chair", 0.74, [220, 300, 420, 700]),
        ]
        out = self.engine.describe(raw, frame_w=1280, frame_h=720, schema_version=1)
        plant_obj = next(o for o in (out.get("objects") or []) if o.get("name") == "potted plant")
        action = str(plant_obj.get("avoidance_action") or "")
        self.assertIn("盆栽", action)
        self.assertNotIn("稍微向右侧避让", action)

    def test_indoor_potted_plant_is_kept_with_competing_furniture(self):
        raw = [
            _obj("potted plant", 0.45, [520, 320, 700, 700]),
            _obj("chair", 0.93, [180, 220, 430, 700]),
            _obj("table", 0.92, [760, 240, 1180, 700]),
            _obj("monitor", 0.9, [500, 120, 760, 320]),
        ]
        out = self.engine.describe(raw, frame_w=1280, frame_h=720, schema_version=1)
        names = [o.get("name") for o in (out.get("objects") or [])]
        self.assertIn("potted plant", names)


if __name__ == "__main__":
    unittest.main()
