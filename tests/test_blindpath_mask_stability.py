import unittest

import numpy as np

from workflow_blindpath import BlindPathNavigator


def _make_mask(h=720, w=1280, left=520, right=760, top=220):
    mask = np.zeros((h, w), dtype=np.uint8)
    mask[top:h, left:right] = 255
    return mask


class BlindPathMaskStabilityTests(unittest.TestCase):
    def setUp(self):
        self.nav = BlindPathNavigator(yolo_model=None, obstacle_detector=None)
        self.nav.BLINDPATH_MIN_AREA_RATIO = 0.01
        self.nav.BLINDPATH_MISS_HOLD_FRAMES = 2

    def test_short_miss_uses_previous_blind_path_mask(self):
        valid = _make_mask()
        out1 = self.nav._stabilize_blind_path_presence(valid)
        self.assertIsNotNone(out1)

        out2 = self.nav._stabilize_blind_path_presence(None)
        out3 = self.nav._stabilize_blind_path_presence(None)
        self.assertIsNotNone(out2)
        self.assertIsNotNone(out3)

        out4 = self.nav._stabilize_blind_path_presence(None)
        self.assertIsNone(out4)

    def test_small_noise_mask_is_treated_as_miss(self):
        valid = _make_mask()
        self.nav._stabilize_blind_path_presence(valid)

        tiny = np.zeros((720, 1280), dtype=np.uint8)
        tiny[10:20, 10:20] = 255  # 面积极小，低于min area ratio
        out = self.nav._stabilize_blind_path_presence(tiny)
        self.assertIsNotNone(out)
        self.assertGreater(int(np.sum(out > 0)), int(np.sum(tiny > 0)))

    def test_new_valid_mask_resets_miss_streak(self):
        valid1 = _make_mask(left=480, right=720)
        self.nav._stabilize_blind_path_presence(valid1)
        self.nav._stabilize_blind_path_presence(None)
        self.assertEqual(self.nav.blindpath_miss_streak, 1)

        valid2 = _make_mask(left=560, right=820)
        out = self.nav._stabilize_blind_path_presence(valid2)
        self.assertIsNotNone(out)
        self.assertEqual(self.nav.blindpath_miss_streak, 0)
        self.assertGreater(np.sum(out[:, 560:820] > 0), np.sum(out[:, 480:560] > 0))


if __name__ == "__main__":
    unittest.main()
