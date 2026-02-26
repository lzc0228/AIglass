import unittest

import audio_player


class AudioRoutingPolicyTests(unittest.TestCase):
    def test_bluetooth_mode_prefers_bluetooth_route(self):
        route = audio_player._resolve_output_route_policy(
            output_mode="bluetooth",
            stream_client_count=2,
            loop_ready=True,
            bluetooth_connected=True,
            speaker_fallback_enabled=False,
        )
        self.assertEqual(route, "bluetooth_local_preferred")

    def test_no_speaker_fallback_without_explicit_opt_in(self):
        route = audio_player._resolve_output_route_policy(
            output_mode="local",
            stream_client_count=0,
            loop_ready=False,
            bluetooth_connected=False,
            speaker_fallback_enabled=False,
        )
        self.assertEqual(route, "no_route")

    def test_stream_is_used_when_available_and_not_forced_bluetooth(self):
        route = audio_player._resolve_output_route_policy(
            output_mode="local",
            stream_client_count=1,
            loop_ready=True,
            bluetooth_connected=False,
            speaker_fallback_enabled=False,
        )
        self.assertEqual(route, "stream")


if __name__ == "__main__":
    unittest.main()
