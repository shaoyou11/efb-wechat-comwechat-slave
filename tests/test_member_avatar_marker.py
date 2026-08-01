import importlib.util
import tempfile
import time
import unittest
from io import BytesIO
from pathlib import Path

from PIL import Image

MODULE_PATH = Path(__file__).parents[1] / "efb_wechat_comwechat_slave" / "member_avatar_marker.py"
SPEC = importlib.util.spec_from_file_location("member_avatar_marker", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
MemberAvatarMarkerStore = MODULE.MemberAvatarMarkerStore
fallback_marker = MODULE.fallback_marker
marker_from_avatar = MODULE.marker_from_avatar


def solid_image(color):
    output = BytesIO()
    Image.new("RGB", (32, 32), color).save(output, format="PNG")
    output.seek(0)
    return output


class MemberAvatarMarkerTest(unittest.TestCase):
    def test_dominant_avatar_colors(self):
        self.assertEqual(marker_from_avatar(solid_image((25, 110, 220))), "🔵")
        self.assertEqual(marker_from_avatar(solid_image((35, 170, 75))), "🟢")

    def test_fallback_is_stable(self):
        self.assertEqual(fallback_marker("wxid_example"), fallback_marker("wxid_example"))

    def test_store_returns_immediately_then_persists_avatar_result(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "member-avatar-markers.json"
            store = MemberAvatarMarkerStore(path)
            first = store.marker_for("wxid_blue", lambda _wxid: solid_image((25, 110, 220)))
            self.assertIn(first, {"🔴", "🟠", "🟡", "🟢", "🔵", "🟣", "🟤"})
            for _ in range(50):
                avatar_count, _ = store.counts()
                if avatar_count == 1:
                    break
                time.sleep(0.02)
            self.assertEqual(store.marker_for("wxid_blue", lambda _wxid: None), "🔵")

            restored = MemberAvatarMarkerStore(path)
            self.assertEqual(restored.marker_for("wxid_blue", lambda _wxid: None), "🔵")

    def test_disable_hides_marker_and_persists(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "member-avatar-markers.json"
            store = MemberAvatarMarkerStore(path)
            store.set_enabled(False)
            self.assertIsNone(store.marker_for("wxid_example", lambda _wxid: None))
            self.assertFalse(MemberAvatarMarkerStore(path).enabled)


if __name__ == "__main__":
    unittest.main()
