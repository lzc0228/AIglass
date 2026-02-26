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


class StationOCRModeTests(unittest.TestCase):
    def test_subway_station_sign_text_is_recognized(self):
        reader = TextReader(
            _DummyOCR(
                [
                    {"text": "地铁2号线 人民广场站", "bbox": _box(420, 120, 900, 260), "confidence": 0.94},
                ]
            )
        )
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        out = reader.read_text(frame, mode="station")
        self.assertTrue(out.get("success"))
        msg = str(out.get("message") or "")
        self.assertIn("地铁站", msg)
        self.assertTrue(("2号线" in msg) or ("人民广场站" in msg))

    def test_bus_station_direction_is_generated(self):
        reader = TextReader(
            _DummyOCR(
                [
                    {"text": "公交站→", "bbox": _box(900, 120, 1160, 230), "confidence": 0.9},
                ]
            )
        )
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        out = reader.read_text(frame, mode="station")
        self.assertTrue(out.get("success"))
        msg = str(out.get("message") or "")
        self.assertIn("公交站", msg)
        self.assertIn("右", msg)

    def test_station_exit_direction_is_generated(self):
        reader = TextReader(
            _DummyOCR(
                [
                    {"text": "METRO", "bbox": _box(460, 120, 700, 240), "confidence": 0.88},
                    {"text": "Exit A ←", "bbox": _box(100, 120, 360, 220), "confidence": 0.92},
                ]
            )
        )
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        out = reader.read_text(frame, mode="station")
        self.assertTrue(out.get("success"))
        msg = str(out.get("message") or "")
        self.assertIn("地铁站", msg)
        self.assertIn("出口", msg)
        self.assertIn("左", msg)


if __name__ == "__main__":
    unittest.main()
