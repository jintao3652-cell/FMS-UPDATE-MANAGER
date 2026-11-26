import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import catalog  # noqa: E402
import openlist  # noqa: E402
import state  # noqa: E402
import targets  # noqa: E402


def _bluebird_addon(simulator: str = "MSFS 2024", platform: str = "Steam") -> "state.Addon":
    return state.to_addon(
        {
            "name": "Bluebird B757-200",
            "description": "Bluebird Simulations Boeing 757-200",
            "simulator": simulator,
            "platform": platform,
            "target_path": "",
            "package_name": "bluebirdsim-aircraft-757-200",
            "navdata_subpath": r"work\NavigationData",
        }
    )


def _write_cycle(nav_dir: Path, cycle: str = "2611") -> None:
    nav_dir.mkdir(parents=True, exist_ok=True)
    (nav_dir / "cycle.json").write_text(
        json.dumps(
            {
                "cycle": cycle,
                "revision": "n4",
                "name": "Bluebird 757/767",
                "format": "dfdv2",
            }
        ),
        encoding="utf-8",
    )
    (nav_dir / "db.s3db").write_bytes(b"x")


class Bluebird757Tests(unittest.TestCase):
    def test_default_addons_include_bluebird_for_both_simulators(self):
        items = [
            d for d in state.default_addons() if d.get("package_name") == "bluebirdsim-aircraft-757-200"
        ]
        keys = {(d["simulator"], d["platform"]) for d in items}
        self.assertEqual(
            keys,
            {
                ("MSFS 2020", "Steam"),
                ("MSFS 2020", "Xbox/MS Store"),
                ("MSFS 2024", "Steam"),
                ("MSFS 2024", "Xbox/MS Store"),
            },
        )
        for d in items:
            self.assertEqual(d["name"], "Bluebird B757-200")
            self.assertEqual(d["navdata_subpath"], r"work\NavigationData")

    def test_fixed_relative_path(self):
        self.assertEqual(
            catalog.fixed_relative_path(_bluebird_addon()),
            os.path.join("bluebirdsim-aircraft-757-200", "work", "NavigationData"),
        )

    def test_cycle_and_folder_signatures(self):
        addon = _bluebird_addon()
        self.assertTrue(targets.cycle_name_matches_addon(addon, "Bluebird 757/767"))
        self.assertTrue(targets.cycle_name_matches_addon(addon, "Bluebird B757-200"))
        self.assertFalse(targets.cycle_name_matches_addon(addon, "iniBuilds DFD v2"))
        self.assertTrue(targets.cycle_name_is_generic_for_addon(addon, "Bluebird"))
        self.assertFalse(targets.cycle_name_is_generic_for_addon(addon, "Bluebird 757/767"))
        self.assertTrue(
            targets.folder_name_matches_addon_signature(
                addon, Path("bluebirdsim-aircraft-757-200")
            )
        )
        self.assertFalse(
            targets.folder_name_matches_addon_signature(addon, Path("pmdg-aircraft-738"))
        )

    def test_resolve_target_dir_in_wasm2024(self):
        with tempfile.TemporaryDirectory(prefix="fms_bluebird_2024_") as tmp:
            wasm_root = Path(tmp) / "WASM" / "MSFS2024"
            nav = wasm_root / "bluebirdsim-aircraft-757-200" / "work" / "NavigationData"
            _write_cycle(nav)

            fake_state = {
                "community_paths": {},
                "community_2024_paths": {},
                "wasm_scan_paths": {"MSFS 2024|Steam": [str(wasm_root)]},
            }
            target = catalog.resolve_target_dir(_bluebird_addon(), fake_state)
            self.assertIsNotNone(target)
            self.assertEqual(Path(target), nav)

            status, cycle, _, target_str = catalog.addon_status(
                _bluebird_addon(), "2611", fake_state
            )
            self.assertEqual(status, "UP TO DATE")
            self.assertEqual(cycle, "2611")
            self.assertEqual(Path(target_str), nav)

    def test_resolve_target_dir_in_msfs2020_packages(self):
        with tempfile.TemporaryDirectory(prefix="fms_bluebird_2020_") as tmp:
            packages_root = Path(tmp) / "packages"
            nav = packages_root / "bluebirdsim-aircraft-757-200" / "work" / "NavigationData"
            _write_cycle(nav)

            fake_state = {
                "community_paths": {},
                "community_2024_paths": {},
                "wasm_scan_paths": {"MSFS 2020|Xbox/MS Store": [str(packages_root)]},
            }
            addon = _bluebird_addon("MSFS 2020", "Xbox/MS Store")
            target = catalog.resolve_target_dir(addon, fake_state)
            self.assertIsNotNone(target)
            self.assertEqual(Path(target), nav)

            status, cycle, _, _ = catalog.addon_status(addon, "2611", fake_state)
            self.assertEqual(status, "UP TO DATE")
            self.assertEqual(cycle, "2611")

    def test_not_installed_when_missing(self):
        from unittest import mock

        with tempfile.TemporaryDirectory(prefix="fms_bluebird_empty_") as tmp:
            fake_state = {
                "community_paths": {},
                "community_2024_paths": {},
                "wasm_scan_paths": {"MSFS 2024|Steam": [tmp]},
            }
            with mock.patch.object(
                catalog, "default_wasm_scan_bases", return_value=[tmp]
            ):
                target = catalog.resolve_target_dir(_bluebird_addon(), fake_state)
                self.assertIsNone(target)
                status, _, _, _ = catalog.addon_status(
                    _bluebird_addon(), "2611", fake_state
                )
                self.assertEqual(status, "NOT INSTALLED")

    def test_openlist_archive_selection(self):
        items = [
            {"name": "PMDG_WASM_NavData_2611.zip", "is_dir": False},
            {"name": "Bluebird_B757-200_NavData_2611.zip", "is_dir": False},
            {"name": "iniBuilds_DFD_v2_2611.zip", "is_dir": False},
        ]
        picked = openlist.select_openlist_archive_for_addon(
            _bluebird_addon(), "2611", items
        )
        self.assertIsNotNone(picked)
        self.assertEqual(picked["name"], "Bluebird_B757-200_NavData_2611.zip")

        shared = [
            {"name": "Bluebird_757-767_DFDv2_2611.zip", "is_dir": False},
            {"name": "PMDG_WASM_NavData_2611.zip", "is_dir": False},
        ]
        picked_shared = openlist.select_openlist_archive_for_addon(
            _bluebird_addon(), "2611", shared
        )
        self.assertIsNotNone(picked_shared)
        self.assertEqual(picked_shared["name"], "Bluebird_757-767_DFDv2_2611.zip")

        # Regression: the server also hosts an unrelated QualityWings 757
        # package. A bare "757" hint used to select it for Bluebird installs.
        unrelated = [
            {"name": "qualitywings-b757-bae146-avrorj-2612-r1.zip", "is_dir": False},
            {"name": "msfs2020-2612-r1.7z", "is_dir": False},
        ]
        self.assertIsNone(
            openlist.select_openlist_archive_for_addon(
                _bluebird_addon(), "2612", unrelated
            )
        )


if __name__ == "__main__":
    unittest.main()
