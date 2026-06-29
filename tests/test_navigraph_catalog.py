import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import navigraph_catalog as nc  # noqa: E402
from state import Addon, default_addons  # noqa: E402
from targets import addon_search_tokens  # noqa: E402
from catalog import (  # noqa: E402
    is_external_folder_addon,
    is_community_plugin_addon,
    community_plugin_install_target,
    read_plugin_version_from_dir,
    addon_status,
)


SAMPLE = [
    {
        "package_id": "p-milviz",
        "cycle": "2605",
        "description": "Milviz T6A",
        "format": "milviz_t6a_v1",
        "package_status": "current",
        "files": [{"file_id": "f1", "key": "milviz_t6a_2605.7z", "hash": "h"}],
        "search_strategies": {
            "microsoft": {
                "paths": {"installPaths": ["milviz-t6a"], "rootFolderName": "milviz-t6a"},
                "simulators": [],
            }
        },
    },
    {
        "package_id": "p-pmdg",
        "cycle": "2605",
        "description": "PMDG 737-700",
        "format": "pmdg_workfolder_v1",
        "package_status": "current",
        "files": [{"file_id": "f2", "key": "pmdg-aircraft-workfolder-2605.7z", "hash": "h"}],
        "search_strategies": {
            "microsoft": {
                "paths": {
                    "installPaths": ["pmdg-aircraft-737"],
                    "rootFolderName": "pmdg-aircraft-737",
                    "workFolderInstallPaths": ["NavigationData"],
                },
                "simulators": ["msfs2024", "msfs2020"],
            }
        },
    },
    {
        "package_id": "p-fsipanel",
        "cycle": "2605",
        "description": "FSiPanel",
        "format": "fsipanel_v2",
        "package_status": "current",
        "files": [{"file_id": "f3", "key": "fsipanel_2605.7z", "hash": "h"}],
        "search_strategies": {
            "external": {
                "paths": {
                    "installPaths": ["NavData"],
                    "externalFolder": "%appdata%\\FSiPanelNavDB",
                    "rootFolderName": "NavData",
                },
            }
        },
    },
    {
        "package_id": "p-base2024",
        "cycle": "2605",
        "description": "AIRAC Cycle 2605 rev.2",
        "format": "msfs_v3",
        "package_status": "current",
        "files": [{"file_id": "f4", "key": "msfs2024_2605r2.7z", "hash": "h"}],
        "search_strategies": {
            "microsoft": {
                "paths": {"installPaths": ["navigraph-nav-jepp"], "rootFolderName": "navigraph-nav-jepp"},
                "simulators": ["msfs2024"],
            }
        },
    },
    {
        "package_id": "p-g3000",
        "cycle": "2605",
        "description": "Avionics Plugin G3000/G5000 v2.3.1",
        "format": "navigraph_g3000_msfs_v1",
        "package_status": "current",
        "files": [{"file_id": "f5", "key": "navigraph-avionics-g3000-g5000.zip", "hash": "h"}],
        "search_strategies": {
            "microsoft": {
                "paths": {
                    "installPaths": ["navigraph-avionics-g3000-g5000"],
                    "rootFolderName": "navigraph-avionics-g3000-g5000",
                },
                "simulators": ["msfs2020", "msfs2024"],
            }
        },
    },
]


class NavigraphCatalogTests(unittest.TestCase):
    def test_parse_basic_fields(self) -> None:
        pkgs = nc.parse_navigraph_manifest(SAMPLE)
        self.assertEqual(len(pkgs), 5)
        by_id = {p.package_id: p for p in pkgs}
        self.assertEqual(by_id["p-pmdg"].root_folder_name, "pmdg-aircraft-737")
        self.assertEqual(by_id["p-pmdg"].navdata_subpath, "NavigationData")
        self.assertEqual(by_id["p-pmdg"].sim_labels, ["MSFS 2024", "MSFS 2020"])
        # No simulators in manifest -> both sims.
        self.assertEqual(by_id["p-milviz"].sim_labels, ["MSFS 2020", "MSFS 2024"])
        self.assertTrue(by_id["p-fsipanel"].is_external)

    def test_microsoft_package_to_addon_mapping(self) -> None:
        pkgs = nc.parse_navigraph_manifest(SAMPLE)
        milviz = next(p for p in pkgs if p.package_id == "p-milviz")
        addons = nc.package_to_addons(milviz)
        # 2 sims x 2 platforms
        self.assertEqual(len(addons), 4)
        a = addons[0]
        self.assertEqual(a["package_name"], "milviz-t6a")
        self.assertEqual(a["name"], "Milviz T6A")
        self.assertEqual(a["target_path"], "")

    def test_external_package_gets_slug_and_target(self) -> None:
        pkgs = nc.parse_navigraph_manifest(SAMPLE)
        fsi = next(p for p in pkgs if p.package_id == "p-fsipanel")
        addons = nc.package_to_addons(fsi)
        self.assertTrue(addons)
        a = addons[0]
        self.assertEqual(a["package_name"], "fsipanel")  # slug, not generic "NavData"
        self.assertIn("FSiPanelNavDB", a["target_path"])

    def test_skip_formats_excludes_base_navdata(self) -> None:
        pkgs = nc.parse_navigraph_manifest(SAMPLE)
        base = next(p for p in pkgs if p.package_id == "p-base2024")
        self.assertEqual(nc.package_to_addons(base), [])

    def test_missing_dedupes_against_existing(self) -> None:
        pkgs = nc.parse_navigraph_manifest(SAMPLE)
        existing = [
            {"package_name": "pmdg-aircraft-737", "simulator": "MSFS 2024", "platform": "Steam"},
        ]
        missing = nc.missing_addons_from_catalog(pkgs, existing)
        names = {m["package_name"] for m in missing}
        self.assertNotIn("pmdg-aircraft-737", names)  # already covered
        self.assertIn("milviz-t6a", names)
        self.assertIn("fsipanel", names)
        self.assertNotIn("navigraph-nav-jepp", names)  # skipped format

    def test_archive_hints_derived(self) -> None:
        pkgs = nc.parse_navigraph_manifest(SAMPLE)
        hints = nc.openlist_hint_map(pkgs)
        self.assertEqual(hints["milviz-t6a"], ("milviz", "t6a"))
        # cycle token and generic 'navdata' stripped
        self.assertNotIn("2605", " ".join(hints.get("pmdg-aircraft-737", ())))

    def test_friendly_name_falls_back_for_cycle_descriptions(self) -> None:
        pkg = nc.parse_navigraph_manifest(
            [
                {
                    "package_id": "p-tds",
                    "description": "2605r1",
                    "format": "tds_gtnxi_v1",
                    "files": [],
                    "search_strategies": {
                        "external": {"paths": {"externalFolder": "%appdata%\\TDS", "rootFolderName": "MSFS"}}
                    },
                }
            ]
        )[0]
        name = nc._friendly_name(pkg)
        self.assertNotEqual(name, "2605r1")
        self.assertIn("tds", name.lower())


class CatalogIntegrationTests(unittest.TestCase):
    def test_bundled_catalog_loads(self) -> None:
        pkgs = nc.load_bundled_catalog()
        self.assertGreaterEqual(len(pkgs), 30)

    def test_default_addons_includes_new_packages(self) -> None:
        packages = {a["package_name"] for a in default_addons()}
        self.assertIn("milviz-t6a", packages)
        self.assertIn("navigraph-avionics-g1000", packages)
        self.assertIn("fsipanel", packages)
        # existing hand-tuned ones still present and not clobbered
        self.assertIn("pmdg-aircraft-737", packages)
        self.assertIn("navigraph-msfs2020-base", packages)

    def test_generic_token_matching_for_new_addon(self) -> None:
        a = Addon(
            name="Milviz T6A",
            description="Milviz T6A",
            simulator="MSFS 2024",
            platform="Steam",
            package_name="milviz-t6a",
        )
        tokens = addon_search_tokens(a)
        self.assertIn("milviz", tokens)

    def test_external_addon_recognized(self) -> None:
        a = Addon(
            name="FSiPanel",
            description="FSiPanel",
            simulator="MSFS 2024",
            platform="Steam",
            target_path="%appdata%\\FSiPanelNavDB\\NavData",
            package_name="fsipanel",
        )
        self.assertTrue(is_external_folder_addon(a))


class CommunityPluginTests(unittest.TestCase):
    def _plugin_addon(self, sim="MSFS 2024", platform="Steam") -> Addon:
        pkgs = nc.parse_navigraph_manifest(SAMPLE)
        g3000 = next(p for p in pkgs if p.package_id == "p-g3000")
        self.assertTrue(g3000.is_community_plugin)
        addons = nc.package_to_addons(g3000)
        item = next(a for a in addons if a["simulator"] == sim and a["platform"] == platform)
        self.assertEqual(item["install_mode"], "community_plugin")
        return Addon(
            name=item["name"],
            description=item["description"],
            simulator=item["simulator"],
            platform=item["platform"],
            target_path=item["target_path"],
            package_name=item["package_name"],
            navdata_subpath=item["navdata_subpath"],
            install_mode=item["install_mode"],
        )

    def test_plugin_detected_workfolder_excluded(self) -> None:
        pkgs = nc.parse_navigraph_manifest(SAMPLE)
        by_id = {p.package_id: p for p in pkgs}
        self.assertTrue(by_id["p-g3000"].is_community_plugin)
        # PMDG has workFolderInstallPaths -> not a plugin
        self.assertFalse(by_id["p-pmdg"].is_community_plugin)
        # external (FSiPanel) -> not a microsoft plugin
        self.assertFalse(by_id["p-fsipanel"].is_community_plugin)
        # base navdata is skipped entirely
        self.assertFalse(by_id["p-base2024"].is_community_plugin)

    def test_addon_flagged_community_plugin(self) -> None:
        a = self._plugin_addon()
        self.assertTrue(is_community_plugin_addon(a))
        self.assertEqual(a.package_name, "navigraph-avionics-g3000-g5000")

    def test_install_target_per_sim_platform(self) -> None:
        for sim, platform in [
            ("MSFS 2020", "Steam"),
            ("MSFS 2020", "Xbox/MS Store"),
            ("MSFS 2024", "Steam"),
            ("MSFS 2024", "Xbox/MS Store"),
        ]:
            a = self._plugin_addon(sim, platform)
            target = community_plugin_install_target(a, {})
            self.assertIsNotNone(target)
            self.assertEqual(target.name, "navigraph-avionics-g3000-g5000")
            self.assertIn("Community", str(target))

    def test_status_not_installed_then_installed(self) -> None:
        import tempfile, json, shutil

        a = self._plugin_addon()
        # Not installed -> NOT INSTALLED
        self.assertEqual(addon_status(a, "2605", {})[0], "NOT INSTALLED")

        # Simulate an installed plugin folder with a custom Community path.
        tmp = Path(tempfile.mkdtemp())
        try:
            community = tmp / "Community"
            pkg_dir = community / "navigraph-avionics-g3000-g5000"
            pkg_dir.mkdir(parents=True)
            (pkg_dir / "manifest.json").write_text(
                json.dumps({"package_version": "2.3.1"}), encoding="utf-8"
            )
            self.assertEqual(read_plugin_version_from_dir(pkg_dir), "2.3.1")
            from state import community_key

            state = {"community_paths": {community_key(a.simulator, a.platform): str(community)}}
            status, installed, _api, target_str = addon_status(a, "2605", state)
            self.assertEqual(status, "UP TO DATE")
            self.assertEqual(installed, "2.3.1")
            self.assertIn("navigraph-avionics-g3000-g5000", target_str)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class ExternalFolderStatusTests(unittest.TestCase):
    def _fsi_addon(self) -> Addon:
        pkgs = nc.parse_navigraph_manifest(SAMPLE)
        fsi = next(p for p in pkgs if p.package_id == "p-fsipanel")
        item = nc.package_to_addons(fsi)[0]
        return Addon(
            name=item["name"],
            description=item["description"],
            simulator=item["simulator"],
            platform=item["platform"],
            target_path=item["target_path"],
            package_name=item["package_name"],
            navdata_subpath=item.get("navdata_subpath", ""),
            install_mode=item.get("install_mode", ""),
        )

    def test_absent_host_folder_is_not_installed(self) -> None:
        a = self._fsi_addon()
        self.assertTrue(is_external_folder_addon(a))
        # target_path points at a host folder that does not exist on this machine
        status, installed, _api, target_str = addon_status(a, "2605", {})
        self.assertEqual(status, "NOT INSTALLED")
        self.assertEqual(installed, "NONE")
        self.assertEqual(target_str, "")  # no phantom path shown

    def test_existing_host_folder_reports_cycle(self) -> None:
        import tempfile, json, shutil
        import catalog

        a = self._fsi_addon()
        tmp = Path(tempfile.mkdtemp())
        try:
            folder = tmp / "FSiPanelNavDB" / "NavData"
            folder.mkdir(parents=True)
            (folder / "cycle.json").write_text(
                json.dumps({"name": "FSiPanel", "cycle": "2605"}), encoding="utf-8"
            )
            orig_expand = catalog._expand

            def fake_expand(p):
                s = orig_expand(p)
                return str(folder) if "fsipanelnavdb" in s.lower() else s

            catalog._expand = fake_expand
            try:
                self.assertEqual(addon_status(a, "2605", {})[0], "UP TO DATE")
                self.assertEqual(addon_status(a, "2607", {})[0], "UPDATE READY")
            finally:
                catalog._expand = orig_expand
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class A346Wasm2024RedirectTests(unittest.TestCase):
    SIM = "MSFS 2024"
    PLAT = "Steam"
    PKG = "aerosoft-aircraft-a346-pro"

    def _addon(self) -> Addon:
        return Addon(
            name="Aerosoft A340-600 Pro",
            description="Aerosoft Airbus A340-600 Pro",
            simulator=self.SIM,
            platform=self.PLAT,
            target_path="",
            package_name=self.PKG,
            navdata_subpath=r"work\FMSData",
        )

    def _state(self, community: Path, wasm2024: Path) -> dict:
        from state import community_key

        key = community_key(self.SIM, self.PLAT)
        return {
            "community_paths": {key: str(community)},
            "wasm_scan_paths": {key: [str(wasm2024)]},
        }

    def _write_manifest(self, community: Path, version: str) -> None:
        import json

        pkg_dir = community / self.PKG
        pkg_dir.mkdir(parents=True, exist_ok=True)
        (pkg_dir / "manifest.json").write_text(
            json.dumps({"package_version": version}), encoding="utf-8"
        )

    def test_old_version_stays_in_community(self) -> None:
        import tempfile, shutil
        import catalog
        from catalog import resolve_target_dir, a346_should_redirect_to_wasm2024

        tmp = Path(tempfile.mkdtemp())
        orig_defaults = catalog.default_wasm_scan_bases
        catalog.default_wasm_scan_bases = lambda *a, **k: []
        try:
            community = tmp / "Community"
            wasm2024 = tmp / "WASM" / "MSFS2024"
            self._write_manifest(community, "1.0.2")
            # Community navdata present (with cycle.json so it resolves).
            cdata = community / self.PKG / "work" / "FMSData"
            cdata.mkdir(parents=True)
            (cdata / "cycle.json").write_text('{"name": "ToLiss"}', encoding="utf-8")

            a = self._addon()
            state = self._state(community, wasm2024)
            self.assertFalse(a346_should_redirect_to_wasm2024(a, state))
            target = resolve_target_dir(a, state)
            self.assertIsNotNone(target)
            self.assertIn("Community", str(target))
        finally:
            catalog.default_wasm_scan_bases = orig_defaults
            shutil.rmtree(tmp, ignore_errors=True)

    def test_new_version_redirects_to_wasm2024(self) -> None:
        import tempfile, shutil
        import catalog
        from catalog import resolve_target_dir, a346_should_redirect_to_wasm2024

        tmp = Path(tempfile.mkdtemp())
        orig_defaults = catalog.default_wasm_scan_bases
        catalog.default_wasm_scan_bases = lambda *a, **k: []
        try:
            community = tmp / "Community"
            wasm2024 = tmp / "WASM" / "MSFS2024"
            self._write_manifest(community, "1.0.3")
            wdata = wasm2024 / self.PKG / "work" / "FMSData"
            wdata.mkdir(parents=True)
            (wdata / "cycle.json").write_text('{"name": "ToLiss"}', encoding="utf-8")

            a = self._addon()
            state = self._state(community, wasm2024)
            self.assertTrue(a346_should_redirect_to_wasm2024(a, state))
            target = resolve_target_dir(a, state)
            self.assertIsNotNone(target)
            self.assertIn("MSFS2024", str(target))
            self.assertIn(self.PKG, str(target))
        finally:
            catalog.default_wasm_scan_bases = orig_defaults
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
