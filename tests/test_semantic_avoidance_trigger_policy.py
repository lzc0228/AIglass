import unittest

from semantic_output import SemanticOutputEngine


class SemanticAvoidanceTriggerPolicyTests(unittest.TestCase):
    def setUp(self):
        self.engine = SemanticOutputEngine()

    def test_side_static_obstacle_uses_reminder_instead_of_avoidance(self):
        action, urgency = self.engine._avoidance(
            name="chair",
            cx=1080,
            w=1280,
            distance_m=1.2,
            risk_score=0.58,
            motion_dir="unknown",
            support_factor=0.15,
            speed_norm=0.0,
            approach_rate=0.0,
        )
        self.assertIn(urgency, ("LOW", "MEDIUM", "HIGH"))
        self.assertNotIn("绕开", action)
        self.assertNotIn("避让", action)
        self.assertNotIn("靠左", action)
        self.assertNotIn("靠右", action)
        self.assertTrue(("直行" in action) or ("留意" in action) or ("观察" in action) or ("注意" in action))

    def test_straight_ahead_obstacle_keeps_avoidance_instruction(self):
        action, _urgency = self.engine._avoidance(
            name="chair",
            cx=640,
            w=1280,
            distance_m=1.2,
            risk_score=0.58,
            motion_dir="unknown",
            support_factor=0.15,
            speed_norm=0.0,
            approach_rate=0.0,
        )
        self.assertTrue(("绕开" in action) or ("避让" in action) or ("停" in action))

    def test_urgent_approaching_object_keeps_avoidance_even_off_center(self):
        action, urgency = self.engine._avoidance(
            name="person",
            cx=1080,
            w=1280,
            distance_m=1.8,
            risk_score=0.66,
            motion_dir="approaching_left",
            support_factor=0.10,
            speed_norm=0.35,
            approach_rate=0.03,
        )
        self.assertIn(urgency, ("MEDIUM", "HIGH"))
        self.assertTrue(("绕开" in action) or ("避让" in action) or ("停" in action))


if __name__ == "__main__":
    unittest.main()
