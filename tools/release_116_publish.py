# -*- coding: utf-8 -*-
"""Continue release: download artifacts of the successful run, create Release v1.1.6."""
import io
import json
import os
import subprocess
import zipfile

TOKEN = os.environ["GH_TOKEN"]
REPO = "jintao3652-cell/FMS-UPDATE-MANAGER"
RUN_ID = "35353331048"
VERSION = "1.1.6"
REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(REPO_DIR, "release_v1.1.6")


def api(path, method="GET", payload=None):
    import urllib.request
    req = urllib.request.Request(
        "https://api.github.com" + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={
            "Authorization": "Bearer " + TOKEN,
            "Accept": "application/vnd.github+json",
            "User-Agent": "fms-release",
        },
        method=method,
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
        return json.loads(data) if data else None


def log(m):
    print(m, flush=True)


os.makedirs(OUT_DIR, exist_ok=True)
arts = api("/repos/%s/actions/runs/%s/artifacts" % (REPO, RUN_ID))
for art in arts.get("artifacts", []):
    name = art["name"]
    log("downloading artifact: %s (size=%s, expired=%s)" % (name, art.get("size_in_bytes"), art.get("expired")))
    url = "https://api.github.com/repos/%s/actions/artifacts/%s/zip" % (REPO, art["id"])
    arc = os.path.join(OUT_DIR, name + "__bundle.zip")
    for attempt in range(5):
        p = subprocess.run(
            ["curl", "-sL", "-m", "600", "--retry", "3",
             "-H", "Authorization: Bearer " + TOKEN,
             "-H", "User-Agent: fms-release",
             "-o", arc, url],
            capture_output=True, text=True, timeout=660,
        )
        if p.returncode == 0 and os.path.getsize(arc) > 0:
            break
        log("  retry %d: curl exit=%d" % (attempt + 1, p.returncode))
    with zipfile.ZipFile(arc) as zf:
        zf.extractall(OUT_DIR)
    os.remove(arc)
    log("extracted: %s" % name)

# release notes from CHANGELOG
notes = ""
try:
    with io.open(os.path.join(REPO_DIR, "CHANGELOG.md"), encoding="utf-8") as fh:
        content = fh.read()
    start = content.find("## 1.1.6")
    end = content.find("## 1.1.5")
    notes = content[start:end].strip() if start >= 0 else ""
except Exception as exc:
    log("changelog read failed: %s" % exc)

assets = [
    os.path.join(OUT_DIR, fn)
    for fn in sorted(os.listdir(OUT_DIR))
    if os.path.isfile(os.path.join(OUT_DIR, fn)) and (fn.endswith(".msi") or fn.endswith(".zip"))
]
log("assets: %s" % [os.path.basename(a) for a in assets])
if len(assets) != 2:
    log("ERROR: expected 2 assets (MSI + Portable zip), got %d" % len(assets))
    raise SystemExit(1)

# create release (idempotent: delete existing draft/release with same tag if any)
import urllib.request
existing = api("/repos/%s/releases/tags/v%s" % (REPO, VERSION))
if isinstance(existing, dict) and existing.get("id"):
    log("deleting existing release %s" % existing["id"])
    subprocess.run(
        ["curl", "-s", "-X", "DELETE",
         "-H", "Authorization: Bearer " + TOKEN,
         "-H", "User-Agent: fms-release",
         "https://api.github.com/repos/%s/releases/%s" % (REPO, existing["id"])],
        timeout=60,
    )
    subprocess.run(["git", "push", "origin", ":refs/tags/v" + VERSION],
                   cwd=REPO_DIR, capture_output=True, text=True, timeout=120)

rel = api(
    "/repos/%s/releases" % REPO,
    method="POST",
    payload={
        "tag_name": "v" + VERSION,
        "target_commitish": "main",
        "name": "FMS Update Manager v" + VERSION,
        "body": notes or ("FMS Update Manager v%s" % VERSION),
        "draft": False,
        "prerelease": False,
    },
)
release_id = rel["id"]
log("release created: id=%s tag=%s" % (release_id, rel.get("tag_name")))

for p in assets:
    fn = os.path.basename(p)
    log("uploading %s (%d bytes)..." % (fn, os.path.getsize(p)))
    up = "https://uploads.github.com/repos/%s/releases/%s/assets?name=%s" % (REPO, release_id, fn)
    for attempt in range(5):
        proc = subprocess.run(
            ["curl", "-s", "-m", "1200", "--retry", "3",
             "-H", "Authorization: Bearer " + TOKEN,
             "-H", "Content-Type: application/octet-stream",
             "-H", "User-Agent: fms-release",
             "--data-binary", "@" + p, up],
            capture_output=True, text=True, timeout=1260,
        )
        try:
            res = json.loads(proc.stdout)
        except Exception:
            res = {}
        if proc.returncode == 0 and res.get("state") == "uploaded":
            log("uploaded: %s (state=%s)" % (fn, res.get("state")))
            break
        log("  retry %d: %s" % (attempt + 1, (proc.stdout or proc.stderr)[:200]))

log("DONE. release url: %s" % rel.get("html_url"))
