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


class SemanticElevatorHallucinationTests(unittest.TestCase):
    def setUp(self):
        self.engine = SemanticOutputEngine()

    def test_non_elevator_scene_suppresses_weak_elevator_candidate(self):
        raw = [
            _obj("elevator", 0.42, [500, 180, 820, 700]),
            _obj("chair", 0.90, [130, 250, 390, 700]),
            _obj("table", 0.82, [860, 260, 1160, 700]),
        ]
        out = self.engine.describe(raw, frame_w=1280, frame_h=720, schema_version=1)
        names = [str(item.get("name", "")) for item in out.get("objects", [])]
        text = str(out.get("text", ""))
        self.assertNotIn("elevator", names)
        self.assertNotIn("电梯", text)

    def test_elevator_cue_kept_when_support_evidence_is_sufficient(self):
        raw = [
            _obj("elevator", 0.88, [420, 80, 980, 710]),
            _obj("floor button", 0.86, [940, 210, 1110, 560]),
            _obj("door", 0.76, [360, 120, 1020, 710]),
        ]
        out = self.engine.describe(raw, frame_w=1280, frame_h=720, schema_version=1)
        names = [str(item.get("name", "")) for item in out.get("objects", [])]
        self.assertIn("elevator", names)


if __name__ == "__main__":
    unittest.main()
