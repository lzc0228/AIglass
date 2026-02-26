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


def _action_for(out, name):
    for item in out.get("objects", []):
        if str(item.get("name", "")) == name:
            return str(item.get("avoidance_action", ""))
    return ""


class SemanticParkedVehicleSidePolicyTests(unittest.TestCase):
    def setUp(self):
        self.engine = SemanticOutputEngine()

    def test_parked_vehicle_on_right_blocks_right_side_bypass(self):
        raw = [
            _obj("chair", 0.83, [80, 180, 460, 710]),
            _obj("car", 0.90, [760, 180, 1240, 710]),
        ]
        out = self.engine.describe(raw, frame_w=1280, frame_h=720, schema_version=1)
        action = _action_for(out, "chair")
        self.assertTrue(action, "chair should be present in semantic output")
        self.assertNotIn("从右侧绕开", action)
        self.assertNotIn("向右侧避让", action)
        self.assertTrue(
            ("左侧" in action) or ("先停" in action) or ("减速" in action) or ("观察" in action) or ("直行" in action)
        )

    def test_both_sides_blocked_by_parked_vehicles_avoid_directional_bypass(self):
        raw = [
            _obj("chair", 0.86, [500, 180, 780, 710]),
            _obj("car", 0.92, [20, 180, 420, 710]),
            _obj("truck", 0.90, [860, 170, 1260, 710]),
        ]
        out = self.engine.describe(raw, frame_w=1280, frame_h=720, schema_version=1)
        action = _action_for(out, "chair")
        self.assertTrue(action, "chair should be present in semantic output")
        self.assertNotIn("从左侧绕开", action)
        self.assertNotIn("从右侧绕开", action)
        self.assertNotIn("向左侧避让", action)
        self.assertNotIn("向右侧避让", action)
        self.assertTrue(("先停" in action) or ("减速" in action) or ("观察" in action))


if __name__ == "__main__":
    unittest.main()
