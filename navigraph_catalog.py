"""Navigraph NAVI HUB (FMS Data API) package-manifest parser.

The Navigraph hub exposes its installable navdata packages as a JSON manifest
(see ``navigraph_catalog_2605.json``). Each entry describes one package: where it
installs (``rootFolderName`` / ``workFolderInstallPaths`` for in-sim Community
packages, ``externalFolder`` for external-folder packages), which simulators it
targets, and the archive file name.

This module turns that manifest into:
  * ``NavigraphPackage`` records (a normalized, signed-url-free view), and
  * ``Addon``-shaped dicts that plug straight into ``state.default_addons()``.

Download links (``signed_url``) are intentionally NOT consumed here: they are
short-lived Navigraph CDN links. Downloads keep flowing through the existing
OpenList / backup-power servers; this module only supplies catalog metadata.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Maps Navigraph simulator ids to the project's MSFS_VERSIONS labels.
_SIM_LABELS = {
    "msfs2020": "MSFS 2020",
    "msfs2024": "MSFS 2024",
}

# Default platform variants generated for each simulator (matches state.py).
_DEFAULT_PLATFORMS = ("Steam", "Xbox/MS Store")

# Bundled offline catalog shipped next to this module.
BUNDLED_CATALOG_NAME = "navigraph_catalog_2605.json"

# Packages whose data is already covered by hand-tuned entries in
# ``state.DEFAULT_ADDON_FAMILIES`` / the base-navdata handling. Generating
# generic catalog addons for these would create duplicates with worse matching,
# so they are skipped. Keyed by Navigraph ``format``.
SKIP_FORMATS = frozenset(
    {
        "msfs_v2",  # AIRAC base navdata MSFS2020 -> navigraph-msfs2020-base
        "msfs_v3",  # AIRAC base navdata MSFS2024 -> navigraph-msfs2024-base
        "fenix_nnc_v1",  # -> fnx-aircraft-320 (special Fenix handling)
        "flightsimlabs_a321_v1",  # -> fslabs-aircraft-a321 (special FSLabs handling)
    }
)

# Install-mode tag carried on generated addons; see state.Addon.install_mode.
INSTALL_MODE_COMMUNITY_PLUGIN = "community_plugin"

# Navigraph official packages that are whole-folder MSFS packages dropped into
# Community (manifest.json/layout.json, no cycle.json, no work subfolder). These
# can be installed fresh after login. Matched by format prefix so future minor
# version bumps (``_v1`` -> ``_v2``) keep working.
_PLUGIN_FORMAT_PREFIXES = (
    "navigraph_academy_",
    "navigraph_charts_",
    "navigraph_chartsapp_",
    "navigraph_simbriefapp_",
    "navigraph_simbrief_dispatch_",
    "navigraph_g1000_",
    "navigraph_g3000_",
    "navigraph_g3x_",
)


@dataclass
class NavigraphPackage:
    package_id: str
    cycle: str
    description: str
    format: str
    package_status: str
    strategy: str  # "microsoft" | "external" | ""
    root_folder_name: str
    install_paths: list[str] = field(default_factory=list)
    work_folder_install_paths: list[str] = field(default_factory=list)
    external_folder: str = ""
    simulators: list[str] = field(default_factory=list)
    file_keys: list[str] = field(default_factory=list)

    @property
    def is_external(self) -> bool:
        return self.strategy == "external"

    @property
    def is_community_plugin(self) -> bool:
        """Whole-folder Community package installable fresh after login.

        These are Navigraph official plugins/apps: a single top-level folder
        (``rootFolderName``) with manifest.json/layout.json and no cycle.json.
        """
        if self.strategy != "microsoft" or self.work_folder_install_paths:
            return False
        fmt = (self.format or "").lower()
        return any(fmt.startswith(prefix) for prefix in _PLUGIN_FORMAT_PREFIXES)

    @property
    def navdata_subpath(self) -> str:
        """Sub-path inside the package folder that holds the cycle data."""
        if self.work_folder_install_paths:
            return os.path.normpath(self.work_folder_install_paths[0])
        return ""

    @property
    def sim_labels(self) -> list[str]:
        """Project-facing simulator labels; empty manifest sims => both."""
        labels = [_SIM_LABELS[s] for s in self.simulators if s in _SIM_LABELS]
        return labels or ["MSFS 2020", "MSFS 2024"]


def _strategy_view(search_strategies: dict) -> tuple[str, dict]:
    """Pick the first known strategy and return ``(name, strategy_dict)``."""
    if not isinstance(search_strategies, dict):
        return "", {}
    for name in ("microsoft", "external"):
        block = search_strategies.get(name)
        if isinstance(block, dict):
            return name, block
    # Fall back to whatever single strategy is present.
    for name, block in search_strategies.items():
        if isinstance(block, dict):
            return str(name), block
    return "", {}


def _package_from_dict(item: dict) -> NavigraphPackage | None:
    if not isinstance(item, dict):
        return None
    strategy, block = _strategy_view(item.get("search_strategies", {}))
    paths = block.get("paths", {}) if isinstance(block, dict) else {}
    install_paths = [str(p) for p in paths.get("installPaths", []) or [] if str(p).strip()]
    work_paths = [str(p) for p in paths.get("workFolderInstallPaths", []) or [] if str(p).strip()]
    files = item.get("files", []) or []
    file_keys = [str(f.get("key", "")).strip() for f in files if isinstance(f, dict) and f.get("key")]
    return NavigraphPackage(
        package_id=str(item.get("package_id", "")).strip(),
        cycle=str(item.get("cycle", "")).strip(),
        description=str(item.get("description", "")).strip(),
        format=str(item.get("format", "")).strip(),
        package_status=str(item.get("package_status", "")).strip(),
        strategy=strategy,
        root_folder_name=str(paths.get("rootFolderName", "")).strip(),
        install_paths=install_paths,
        work_folder_install_paths=work_paths,
        external_folder=str(paths.get("externalFolder", "")).strip(),
        simulators=[str(s).strip() for s in (block.get("simulators", []) or [])],
        file_keys=file_keys,
    )


def parse_navigraph_manifest(source: str | Path | list | dict) -> list[NavigraphPackage]:
    """Parse a Navigraph manifest from a path, JSON string, or already-loaded data."""
    if isinstance(source, (list, dict)):
        data = source
    else:
        text = Path(source).read_text(encoding="utf-8", errors="ignore") if _looks_like_path(source) else str(source)
        data = json.loads(text)
    if isinstance(data, dict):
        data = data.get("packages", data.get("data", [data]))
    packages: list[NavigraphPackage] = []
    for item in data or []:
        pkg = _package_from_dict(item)
        if pkg is not None:
            packages.append(pkg)
    return packages


def _looks_like_path(source: str | Path) -> bool:
    if isinstance(source, Path):
        return True
    text = str(source).strip()
    if not text or text[0] in "[{":
        return False
    return len(text) < 4096 and (os.path.sep in text or text.lower().endswith(".json"))


def load_bundled_catalog() -> list[NavigraphPackage]:
    """Load the offline catalog shipped alongside this module (empty on failure)."""
    path = Path(__file__).resolve().parent / BUNDLED_CATALOG_NAME
    try:
        return parse_navigraph_manifest(path)
    except Exception:
        return []


def _friendly_name(pkg: NavigraphPackage) -> str:
    """A concise display name derived from the package description."""
    desc = pkg.description.strip()
    # Drop trailing version / cycle noise like "v2.3.1" or "rev.2".
    desc = re.sub(r"\s+(v?\d+(\.\d+)+|rev\.?\s*\d+|r\d+)\s*$", "", desc, flags=re.IGNORECASE).strip()
    # A description that is just a cycle string (e.g. "2605r1") is useless as a
    # name; fall back to a title-cased slug of the format.
    if not desc or re.fullmatch(r"[0-9]{3,4}(r\d+)?", pkg.description.strip(), flags=re.IGNORECASE):
        base = re.sub(r"_v\d+$", "", pkg.format or "")
        words = [w for w in re.split(r"[^a-z0-9]+", base.lower()) if w]
        desc = " ".join(w.upper() if len(w) <= 4 else w.capitalize() for w in words)
    return desc or pkg.root_folder_name or pkg.package_id


def _external_slug(pkg: NavigraphPackage) -> str:
    """Stable, unique package_name for an external package.

    External packages install outside Community and their ``rootFolderName`` is
    a generic value like ``NavData``/``AS`` that would collide across packages.
    Derive the slug from ``format`` instead (e.g. ``fsipanel_v2`` -> ``fsipanel``).
    """
    base = re.sub(r"_v\d+$", "", pkg.format or "")
    slug = re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")
    return slug or re.sub(r"[^a-z0-9]+", "-", pkg.description.lower()).strip("-")


def _target_folder(pkg: NavigraphPackage) -> str:
    """The concrete install folder used for conflict detection."""
    if pkg.is_external and pkg.external_folder:
        target = pkg.external_folder
        if pkg.root_folder_name and pkg.root_folder_name.lower() not in target.lower():
            target = os.path.join(target, pkg.root_folder_name)
        return os.path.normpath(target).lower()
    return pkg.root_folder_name.strip().lower()


def package_to_addons(pkg: NavigraphPackage) -> list[dict]:
    """Turn one Navigraph package into ``Addon``-shaped dicts (sim x platform)."""
    if pkg.format in SKIP_FORMATS:
        return []
    if not pkg.root_folder_name and not pkg.external_folder:
        return []
    name = _friendly_name(pkg)
    navdata_subpath = pkg.navdata_subpath
    target_path = ""
    if pkg.is_external and pkg.external_folder:
        # External packages live outside Community; pre-resolve their target and
        # give them a unique slug so matching/dedupe does not collide on "NavData".
        package_name = _external_slug(pkg)
        target = pkg.external_folder
        if pkg.root_folder_name and pkg.root_folder_name.lower() not in target.lower():
            target = os.path.join(target, pkg.root_folder_name)
        target_path = target
    else:
        package_name = pkg.root_folder_name

    install_mode = INSTALL_MODE_COMMUNITY_PLUGIN if pkg.is_community_plugin else ""

    addons: list[dict] = []
    for sim in pkg.sim_labels:
        for platform in _DEFAULT_PLATFORMS:
            addons.append(
                {
                    "name": name,
                    "description": pkg.description or name,
                    "simulator": sim,
                    "platform": platform,
                    "target_path": target_path,
                    "package_name": package_name,
                    "navdata_subpath": navdata_subpath,
                    "install_mode": install_mode,
                }
            )
    return addons


def packages_to_addons(packages: list[NavigraphPackage]) -> list[dict]:
    addons: list[dict] = []
    for pkg in packages:
        addons.extend(package_to_addons(pkg))
    return addons


def _addon_signature(addon: dict) -> tuple[str, str, str]:
    """Identity used to dedupe against existing addons: package + sim + platform."""
    return (
        str(addon.get("package_name", "")).strip().lower(),
        str(addon.get("simulator", "")).strip(),
        str(addon.get("platform", "")).strip(),
    )


def missing_addons_from_catalog(
    packages: list[NavigraphPackage],
    existing_addons: list[dict],
) -> list[dict]:
    """Catalog addons whose (package, sim, platform) is not already covered."""
    have = {_addon_signature(a) for a in existing_addons}
    # Also treat the existing package_name set as covered, so a manually-tuned
    # entry (e.g. pmdg-aircraft-737) is never duplicated by the generic catalog.
    have_packages = {sig[0] for sig in have if sig[0]}
    result: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for addon in packages_to_addons(packages):
        sig = _addon_signature(addon)
        if sig in have or sig[0] in have_packages or sig in seen:
            continue
        seen.add(sig)
        result.append(addon)
    return result


def compare_with_supported(
    packages: list[NavigraphPackage],
    existing_addons: list[dict],
) -> dict[str, Any]:
    """Report which catalog packages are already supported vs. missing."""
    have_packages = {str(a.get("package_name", "")).strip().lower() for a in existing_addons}
    supported: list[str] = []
    missing: list[str] = []
    for pkg in packages:
        label = f"{_friendly_name(pkg)} [{pkg.root_folder_name or pkg.external_folder}]"
        key = pkg.root_folder_name.strip().lower()
        if pkg.format in SKIP_FORMATS or (key and key in have_packages):
            supported.append(label)
        else:
            missing.append(label)
    return {
        "total": len(packages),
        "supported_count": len(supported),
        "missing_count": len(missing),
        "supported": sorted(supported),
        "missing": sorted(missing),
    }


def detect_conflicts(packages: list[NavigraphPackage]) -> list[dict[str, Any]]:
    """Find concrete install folders claimed by more than one package (per sim)."""
    by_target: dict[tuple[str, str], list[str]] = {}
    for pkg in packages:
        folder = _target_folder(pkg)
        if not folder:
            continue
        for sim in pkg.sim_labels:
            by_target.setdefault((folder, sim), []).append(_friendly_name(pkg))
    conflicts: list[dict[str, Any]] = []
    for (folder, sim), names in sorted(by_target.items()):
        unique = sorted(set(names))
        if len(unique) > 1:
            conflicts.append({"folder": folder, "simulator": sim, "packages": unique})
    return conflicts


# Generic, low-signal tokens stripped from auto-derived download hints — they
# would match almost any archive and only add noise to OpenList scoring.
_HINT_STOPWORDS = frozenset(
    {
        "navdata", "navigationdata", "navigation", "data", "workfolder", "work",
        "aircraft", "msfs", "msfs2020", "msfs2024", "2020", "2024", "the", "and",
        "for", "zip", "7z", "pro", "professional",
    }
)


def archive_hints_for_package(pkg: NavigraphPackage) -> tuple[str, ...]:
    """Derive OpenList archive-name hints from a package's archive file keys."""
    tokens: list[str] = []
    for key in pkg.file_keys:
        stem = re.split(r"[.]", os.path.basename(key))[0]
        for part in re.split(r"[^a-z0-9]+", stem.lower()):
            if not part or part in _HINT_STOPWORDS:
                continue
            # Drop pure cycle/version tokens like "2605" or "2605r2".
            if re.fullmatch(r"\d{3,4}(r\d+)?", part):
                continue
            if part not in tokens:
                tokens.append(part)
    return tuple(tokens)


def openlist_hint_map(packages: list[NavigraphPackage]) -> dict[str, tuple[str, ...]]:
    """Map ``package_name`` -> archive hints for every catalog package.

    Used to enrich ``openlist.OPENLIST_ARCHIVE_NAME_HINTS`` so newly-added
    packages get a reasonable auto-download match without per-package hardcoding.
    """
    result: dict[str, tuple[str, ...]] = {}
    for pkg in packages:
        addons = package_to_addons(pkg)
        if not addons:
            continue
        package_name = addons[0]["package_name"].strip().lower()
        if not package_name:
            continue
        hints = archive_hints_for_package(pkg)
        if hints:
            result[package_name] = hints
    return result
