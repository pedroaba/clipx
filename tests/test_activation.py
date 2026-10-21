import os
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from clipx.platforms.linux.activation import activation_token_for_launch, x11_startup_token


class ActivationTests(unittest.TestCase):
    def test_native_activation_token_is_preserved_without_creating_another(self):
        with patch.dict(os.environ, {"XDG_ACTIVATION_TOKEN": "native-token"}):
            with patch("clipx.platforms.linux.activation.x11_startup_token") as fallback:
                self.assertEqual(activation_token_for_launch(), "native-token")
        fallback.assert_not_called()

    def test_gnome_custom_shortcut_gets_a_startup_notification_when_needed(self):
        environment = {"XDG_ACTIVATION_TOKEN": "", "DESKTOP_STARTUP_ID": "",
                       "WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ":0", "QT_QPA_PLATFORM": "wayland;xcb"}
        with patch.dict(os.environ, environment):
            with patch("clipx.platforms.linux.activation.x11_startup_token", return_value="startup-token") as create:
                self.assertEqual(activation_token_for_launch(), "startup-token")
                create.assert_called_once()

    def test_offscreen_tests_and_x11_only_sessions_do_not_create_wayland_tokens(self):
        for platform, wayland in (("offscreen", "wayland-0"), ("xcb", "")):
            with patch.dict(os.environ, {"QT_QPA_PLATFORM": platform, "WAYLAND_DISPLAY": wayland,
                                         "XDG_ACTIVATION_TOKEN": "", "DESKTOP_STARTUP_ID": ""}):
                with patch("clipx.platforms.linux.activation.x11_startup_token") as create:
                    self.assertEqual(activation_token_for_launch(), "")
                    create.assert_not_called()

    @unittest.skipUnless(__import__("importlib.util").util.find_spec("Xlib"), "requires Linux python-xlib")
    def test_startup_notification_uses_server_time_and_an_unmapped_requestor(self):
        from Xlib import X

        connection = Mock()
        root = connection.screen.return_value.root
        source = root.create_window.return_value
        source.id = 123
        connection.get_default_screen.return_value = 0
        atoms = {"CLIPX_ACTIVATION_TIME": 10, "_NET_STARTUP_INFO_BEGIN": 11, "_NET_STARTUP_INFO": 12}
        connection.intern_atom.side_effect = atoms.__getitem__
        connection.pending_events.return_value = True
        connection.next_event.return_value = SimpleNamespace(type=X.PropertyNotify, atom=10, time=4567)
        with patch("Xlib.display.Display", return_value=connection):
            token = x11_startup_token()
        self.assertTrue(token.endswith("_TIME4567"))
        events = [call.args[0] for call in root.send_event.call_args_list]
        self.assertEqual(events[0].client_type, 11)
        self.assertTrue(all(event.client_type == 12 for event in events[1:]))
        data = b"".join(bytes(event.data[1]) for event in events).rstrip(b"\0")
        self.assertIn(token.encode(), data)
        self.assertIn(b"TIMESTAMP=4567", data)
        self.assertTrue(all(len(event.data[1]) == 20 for event in events))
        source.map.assert_not_called()
        source.destroy.assert_called_once()
        connection.close.assert_called_once()

    def test_unavailable_startup_notification_does_not_stop_opening_the_app(self):
        with patch.dict(os.environ, {"XDG_ACTIVATION_TOKEN": "", "DESKTOP_STARTUP_ID": "",
                                     "WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ":0", "QT_QPA_PLATFORM": "wayland"}):
            with patch("clipx.platforms.linux.activation.x11_startup_token", side_effect=RuntimeError("unavailable")):
                self.assertEqual(activation_token_for_launch(), "")


if __name__ == "__main__":
    unittest.main()
