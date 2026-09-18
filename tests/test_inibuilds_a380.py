import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import catalog  # noqa: E402
import state  # noqa: E402


def _a380_addon(platform: str = "Steam") -> "state.Addon":
    return state.to_addon(
        {
            "name": "iniBuilds A380",
            "description": "iniBuilds A380",
            "simulator": "MSFS 2024",
            "platform": platform,
            "target_path": "",
            "package_name": "inibuilds-aircraft-a380",
            "navdata_subpath": r"work\NavigationData",
        }
    )


class InibuildsA380Tests(unittest.TestCase):
    def test_default_addons_include_a380(self):
        items = [
            d
            for d in state.default_addons()
            if d.get("package_name") == "inibuilds-aircraft-a380"
        ]
        keys = {(d["simulator"], d["platform"]) for d in items}
        self.assertEqual(keys, {("MSFS 2024", "Steam"), ("MSFS 2024", "Xbox/MS Store")})
        for d in items:
            self.assertEqual(d["navdata_subpath"], r"work\NavigationData")

    def test_fixed_relative_path(self):
        self.assertEqual(
            catalog.fixed_relative_path(_a380_addon()),
            os.path.join("inibuilds-aircraft-a380", "work", "NavigationData"),
        )

    def test_cycle_name_matches_dfd_v2(self):
        # iniBuilds 机型共用 Navigraph "iniBuilds DFD v2" 数据包名。
        self.assertTrue(
            catalog.cycle_name_matches_addon(_a380_addon(), "iniBuilds DFD v2")
        )
        self.assertTrue(
            catalog.cycle_name_matches_addon(_a380_addon(), "iniBuilds A380")
        )

    def test_resolve_target_dir_in_wasm2024(self):
        with tempfile.TemporaryDirectory(prefix="fms_a380_") as tmp:
            wasm_root = Path(tmp) / "WASM" / "MSFS2024"
            nav = wasm_root / "inibuilds-aircraft-a380" / "work" / "NavigationData"
            nav.mkdir(parents=True)
            (nav / "cycle.json").write_text(
                json.dumps({"cycle": "2609", "revision": "1", "name": "iniBuilds DFD v2", "format": "dfdv2"}),
                encoding="utf-8",
            )
            (nav / "db.s3db").write_bytes(b"x")

            fake_state = {
                "community_paths": {},
                "community_2024_paths": {},
                "wasm_scan_paths": {"MSFS 2024|Steam": [str(wasm_root)]},
            }
            target = catalog.resolve_target_dir(_a380_addon(), fake_state)
            self.assertIsNotNone(target)
            self.assertEqual(Path(target), nav)

            status, cycle, _, target_str = catalog.addon_status(_a380_addon(), "2609", fake_state)
            self.assertEqual(status, "UP TO DATE")
            self.assertEqual(cycle, "2609")
            self.assertEqual(Path(target_str), nav)

    def test_not_installed_when_missing(self):
        from unittest import mock

        with tempfile.TemporaryDirectory(prefix="fms_a380_empty_") as tmp:
            fake_state = {
                "community_paths": {},
                "community_2024_paths": {},
                "wasm_scan_paths": {"MSFS 2024|Steam": [tmp]},
            }
            with mock.patch.object(
                catalog, "default_wasm_scan_bases", return_value=[tmp]
            ):
                target = catalog.resolve_target_dir(_a380_addon(), fake_state)
                self.assertIsNone(target)
                status, _, _, _ = catalog.addon_status(_a380_addon(), "2609", fake_state)
                self.assertEqual(status, "NOT INSTALLED")


if __name__ == "__main__":
    unittest.main()
