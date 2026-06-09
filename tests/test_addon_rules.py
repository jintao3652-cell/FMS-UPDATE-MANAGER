import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from archive import read_cycle_from_payload  # noqa: E402
from openlist import select_openlist_archive_for_addon  # noqa: E402
from state import Addon  # noqa: E402
from targets import (  # noqa: E402
    cycle_name_matches_addon,
    folder_name_matches_addon_signature,
    is_ifly_737max8_addon,
    is_pmdg_737_addon,
    path_matches_addon_signature,
)


class AddonRuleTests(unittest.TestCase):
    def test_737_families_stay_separate(self) -> None:
        pmdg = Addon(
            name="PMDG 737-800",
            description="",
            simulator="MSFS 2024",
            platform="Steam",
            package_name="pmdg-aircraft-738",
        )
        ifly = Addon(
            name="iFly 737 MAX8",
            description="",
            simulator="MSFS 2024",
            platform="Steam",
            package_name="ifly-aircraft-737max8",
        )

        self.assertTrue(is_pmdg_737_addon(pmdg))
        self.assertFalse(is_ifly_737max8_addon(pmdg))
        self.assertTrue(is_ifly_737max8_addon(ifly))
        self.assertFalse(is_pmdg_737_addon(ifly))

        pmdg_path = Path(r"C:\MSFS\Community\pmdg-aircraft-738\Work")
        ifly_path = Path(r"C:\MSFS\Community\ifly-aircraft-737max8\work\navdata\Permanent")
        self.assertTrue(folder_name_matches_addon_signature(pmdg, pmdg_path))
        self.assertTrue(folder_name_matches_addon_signature(ifly, ifly_path))
        self.assertFalse(folder_name_matches_addon_signature(pmdg, ifly_path))
        self.assertFalse(folder_name_matches_addon_signature(ifly, pmdg_path))

    def test_cycle_json_needs_matching_folder_and_name(self) -> None:
        pmdg = Addon(
            name="PMDG 737-700",
            description="",
            simulator="MSFS 2024",
            platform="Steam",
            package_name="pmdg-aircraft-737",
        )
        ifly = Addon(
            name="iFly 737 MAX8",
            description="",
            simulator="MSFS 2024",
            platform="Steam",
            package_name="ifly-aircraft-737max8",
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pmdg_dir = root / "pmdg-aircraft-737" / "Work"
            pmdg_dir.mkdir(parents=True, exist_ok=True)
            cycle_json = pmdg_dir / "cycle.json"
            cycle_json.write_text(json.dumps({"name": "PMDG 737 NavData"}), encoding="utf-8")

            self.assertTrue(path_matches_addon_signature(pmdg, pmdg_dir, cycle_json))
            self.assertFalse(path_matches_addon_signature(ifly, pmdg_dir, cycle_json))

    def test_cycle_payload_reader(self) -> None:
        self.assertEqual(read_cycle_from_payload({"cycle_id": "2401"}), "2401")
        self.assertEqual(read_cycle_from_payload({"name": "AIRAC 2410"}), "2410")
        self.assertEqual(read_cycle_from_payload(["x", "AIRAC 2501"]), "2501")

    def test_msfs2024_inibuilds_a340_only_matches_a340_300(self) -> None:
        addon = Addon(
            name="iniBuilds A340-300",
            description="",
            simulator="MSFS 2024",
            platform="Steam",
            package_name="inibuilds-aircraft-a340",
        )

        self.assertTrue(cycle_name_matches_addon(addon, "iniBuilds A340 NavData"))
        self.assertTrue(cycle_name_matches_addon(addon, "iniBuilds A340-300 NavData"))
        self.assertTrue(cycle_name_matches_addon(addon, "iniBuilds A343 NavData"))
        self.assertFalse(cycle_name_matches_addon(addon, "iniBuilds A340-600 NavData"))
        self.assertFalse(cycle_name_matches_addon(addon, "iniBuilds A346 NavData"))

        self.assertTrue(folder_name_matches_addon_signature(addon, Path(r"C:\MSFS\Community\inibuilds-aircraft-a340")))
        self.assertFalse(folder_name_matches_addon_signature(addon, Path(r"C:\MSFS\Community\inibuilds-aircraft-a340-600")))
        self.assertFalse(folder_name_matches_addon_signature(addon, Path(r"C:\MSFS\Community\inibuilds-aircraft-a346")))

    def test_msfs2024_inibuilds_a340_openlist_rejects_a346(self) -> None:
        addon = Addon(
            name="iniBuilds A340-300",
            description="",
            simulator="MSFS 2024",
            platform="Steam",
            package_name="inibuilds-aircraft-a340",
        )

        items = [
            {"name": "iniBuilds_A340-600_NavData_2501.zip", "is_dir": False},
            {"name": "iniBuilds_A346_NavData_2501.zip", "is_dir": False},
            {"name": "iniBuilds_A340-300_NavData_2501.zip", "is_dir": False},
        ]
        chosen = select_openlist_archive_for_addon(addon, "2501", items)
        self.assertIsNotNone(chosen)
        self.assertEqual(chosen["name"], "iniBuilds_A340-300_NavData_2501.zip")


if __name__ == "__main__":
    unittest.main()
