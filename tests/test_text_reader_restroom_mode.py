import unittest

import numpy as np

from text_reader import TextReader


class _DummyOCR:
    def __init__(self, results):
        self._results = list(results or [])

    def is_available(self):
        return True

    def recognize(self, _image):
        return list(self._results)


def _box(x1, y1, x2, y2):
    return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]


class RestroomOCRModeTests(unittest.TestCase):
    def test_restroom_sign_text_is_recognized(self):
        reader = TextReader(
            _DummyOCR(
                [
                    {"text": "女卫生间", "bbox": _box(520, 120, 760, 260), "confidence": 0.93},
                ]
            )
        )
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        out = reader.read_text(frame, mode="restroom")
        self.assertTrue(out.get("success"))
        msg = str(out.get("message") or "")
        self.assertIn("卫生间", msg)
        self.assertIn("女", msg)

    def test_restroom_entry_direction_uses_arrow_or_position(self):
        reader = TextReader(
            _DummyOCR(
                [
                    {"text": "卫生间入口→", "bbox": _box(860, 120, 1120, 230), "confidence": 0.9},
                ]
            )
        )
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        out = reader.read_text(frame, mode="restroom")
        self.assertTrue(out.get("success"))
        msg = str(out.get("message") or "")
        self.assertIn("入口", msg)
        self.assertIn("右", msg)

    def test_restroom_exit_direction_is_generated(self):
        reader = TextReader(
            _DummyOCR(
                [
                    {"text": "WC", "bbox": _box(500, 140, 680, 260), "confidence": 0.88},
                    {"text": "EXIT", "bbox": _box(80, 120, 260, 220), "confidence": 0.91},
                ]
            )
        )
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        out = reader.read_text(frame, mode="restroom")
        self.assertTrue(out.get("success"))
        msg = str(out.get("message") or "")
        self.assertIn("出口", msg)
        self.assertIn("左", msg)


if __name__ == "__main__":
    unittest.main()
