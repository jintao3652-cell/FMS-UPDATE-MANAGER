# -*- coding: utf-8 -*-
"""Poll CI build for v1.1.6, download artifacts, create GitHub Release."""
import io
import json
import os
import sys
import time
import zipfile
from urllib.request import Request, urlopen

TOKEN = os.environ["GH_TOKEN"]
REPO = "jintao3652-cell/FMS-UPDATE-MANAGER"
HEAD_SHA_PREFIX = "ea7af65"
VERSION = "1.1.6"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "release_v1.1.6")


def api(path, method="GET", payload=None, raw=False):
    req = Request(
        "https://api.github.com" + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={
            "Authorization": "Bearer " + TOKEN,
            "Accept": "application/vnd.github+json",
            "User-Agent": "fms-release",
        },
        method=method,
    )
    with urlopen(req, timeout=60) as r:
        data = r.read()
        return r.status, (data if raw else (json.loads(data) if data else None))


def log(msg):
    print(msg, flush=True)


# 1) find our run
run_id = None
for attempt in range(30):
    st, runs = api(
        "/repos/%s/actions/workflows/build.yml/runs?per_page=10" % REPO
    )
    for run in runs.get("workflow_runs", []):
        if (
            run.get("event") == "workflow_dispatch"
            and run.get("head_sha", "").startswith(HEAD_SHA_PREFIX)
            and run.get("name") == "Build MSI and ZIP"
        ):
            run_id = run["id"]
            break
    if run_id:
        break
    time.sleep(10)

if not run_id:
    log("ERROR: workflow_dispatch run not found")
    sys.exit(1)
log("found run id: %s" % run_id)

# 2) poll until completed
conclusion = None
for attempt in range(120):  # up to 60 min
    st, run = api("/repos/%s/actions/runs/%s" % (REPO, run_id))
    if run.get("status") == "completed":
        conclusion = run.get("conclusion")
        break
    if attempt % 6 == 0:
        log("still running: %s (attempt %d)" % (run.get("status"), attempt))
    time.sleep(30)

log("run conclusion: %s" % conclusion)
if conclusion != "success":
    sys.exit(2)

# 3) download artifacts
os.makedirs(OUT_DIR, exist_ok=True)
st, arts = api("/repos/%s/actions/runs/%s/artifacts" % (REPO, run_id))
for art in arts.get("artifacts", []):
    name = art["name"]
    st, blob = api(
        "/repos/%s/actions/artifacts/%s/zip" % (REPO, art["id"]), raw=True
    )
    arc = os.path.join(OUT_DIR, name + "__bundle.zip")
    with open(arc, "wb") as fh:
        fh.write(blob)
    with zipfile.ZipFile(arc) as zf:
        zf.extractall(OUT_DIR)
    os.remove(arc)
    log("artifact downloaded+extracted: %s" % name)

# 4) release notes from CHANGELOG
notes = ""
try:
    with io.open(
        os.path.join(os.path.dirname(OUT_DIR), "CHANGELOG.md"),
        encoding="utf-8",
    ) as fh:
        content = fh.read()
    start = content.find("## 1.1.6")
    end = content.find("## 1.1.5")
    notes = content[start:end].strip() if start >= 0 else ""
except Exception as exc:
    log("changelog read failed: %s" % exc)

# 5) create release
assets = []
for fn in sorted(os.listdir(OUT_DIR)):
    p = os.path.join(OUT_DIR, fn)
    if os.path.isfile(p):
        assets.append(p)
log("assets to upload: %s" % [os.path.basename(a) for a in assets])

st, rel = api(
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
    size = os.path.getsize(p)
    log("uploading %s (%d bytes)..." % (fn, size))
    req = Request(
        "https://uploads.github.com/repos/%s/releases/%s/assets?name=%s"
        % (REPO, release_id, fn),
        data=open(p, "rb").read(),
        headers={
            "Authorization": "Bearer " + TOKEN,
            "Content-Type": "application/octet-stream",
            "User-Agent": "fms-release",
        },
        method="POST",
    )
    with urlopen(req, timeout=600) as r:
        res = json.loads(r.read())
    log("uploaded: %s (state=%s)" % (fn, res.get("state")))

log("DONE. release url: %s" % rel.get("html_url"))
