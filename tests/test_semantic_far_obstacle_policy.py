import unittest

from semantic_output import SemanticOutputEngine


class SemanticFarObstaclePolicyTests(unittest.TestCase):
    def setUp(self):
        self.engine = SemanticOutputEngine()

    def test_far_static_obstacle_uses_reminder_not_directional_avoid(self):
        action, urgency = self.engine._avoidance(
            name="chair",
            cx=1000,
            w=1280,
            distance_m=4.8,
            risk_score=0.22,
            motion_dir="unknown",
            support_factor=0.1,
            speed_norm=0.0,
            approach_rate=0.0,
        )
        self.assertIn(urgency, ("LOW", "MEDIUM", "HIGH"))
        self.assertNotIn("绕开", action)
        self.assertNotIn("避让", action)
        self.assertTrue(("留意" in action) or ("观察" in action) or ("提醒" in action) or ("注意" in action))

    def test_near_static_obstacle_still_allows_avoidance_instruction(self):
        action, _urgency = self.engine._avoidance(
            name="chair",
            cx=1000,
            w=1280,
            distance_m=1.3,
            risk_score=0.48,
            motion_dir="unknown",
            support_factor=0.2,
            speed_norm=0.0,
            approach_rate=0.0,
        )
        self.assertTrue(("绕开" in action) or ("避让" in action) or ("停" in action))

    def test_far_dynamic_obstacle_not_forced_into_static_reminder_policy(self):
        action, _urgency = self.engine._avoidance(
            name="person",
            cx=1000,
            w=1280,
            distance_m=4.8,
            risk_score=0.32,
            motion_dir="approaching_left",
            support_factor=0.1,
            speed_norm=0.3,
            approach_rate=0.02,
        )
        self.assertFalse(("留意" in action) and ("提醒" in action))


if __name__ == "__main__":
    unittest.main()
