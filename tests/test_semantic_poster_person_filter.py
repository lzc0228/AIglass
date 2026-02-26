import unittest

from semantic_output import SemanticOutputEngine


class SemanticPosterPersonFilterTests(unittest.TestCase):
    def setUp(self):
        self.engine = SemanticOutputEngine()

    def test_static_poster_like_person_is_not_forced_to_avoid(self):
        action, urgency = self.engine._avoidance(
            name="person",
            cx=640,
            w=1280,
            distance_m=3.0,
            risk_score=0.20,
            motion_dir="unknown",
            support_factor=0.88,
            speed_norm=0.01,
            approach_rate=0.0,
        )
        self.assertEqual(urgency, "LOW")
        self.assertNotIn("避让", action)
        self.assertNotIn("绕开", action)
        self.assertNotIn("停", action)

    def test_approaching_person_keeps_avoidance_instruction(self):
        action, urgency = self.engine._avoidance(
            name="person",
            cx=300,
            w=1280,
            distance_m=1.6,
            risk_score=0.76,
            motion_dir="approaching_left",
            support_factor=0.20,
            speed_norm=0.35,
            approach_rate=0.05,
        )
        self.assertIn(urgency, ("HIGH", "MEDIUM"))
        self.assertTrue(("避让" in action) or ("绕开" in action) or ("绕行" in action) or ("停" in action))

    def test_near_person_still_requires_safety_action_even_if_static(self):
        action, urgency = self.engine._avoidance(
            name="person",
            cx=640,
            w=1280,
            distance_m=1.0,
            risk_score=0.30,
            motion_dir="unknown",
            support_factor=0.90,
            speed_norm=0.01,
            approach_rate=0.0,
        )
        self.assertIn(urgency, ("HIGH", "MEDIUM"))
        self.assertTrue(("避让" in action) or ("绕开" in action) or ("绕行" in action) or ("停" in action))


if __name__ == "__main__":
    unittest.main()
