import re
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


class SemanticDistanceFormatTests(unittest.TestCase):
    def setUp(self):
        self.engine = SemanticOutputEngine()

    def test_default_text_prefers_steps_without_double_prefix(self):
        raw = [
            _obj("chair", 0.88, [520, 260, 780, 700]),
        ]
        out = self.engine.describe(raw, frame_w=1280, frame_h=720, schema_version=1)
        text = str(out.get("text") or "")
        self.assertIn("步", text)
        self.assertNotIn("约约", text)
        self.assertIsNone(re.search(r"\d+\.\d", text))

    def test_meter_mode_uses_integer_meters_only(self):
        raw = [
            _obj("chair", 0.88, [580, 430, 700, 700]),
        ]
        sem = self.engine.build_semantic_objects(raw, frame_w=1280, frame_h=720)
        text = self.engine.render_text(sem, use_steps=False)
        self.assertIn("米", text)
        self.assertIsNone(re.search(r"\d+\.\d", text))


if __name__ == "__main__":
    unittest.main()
