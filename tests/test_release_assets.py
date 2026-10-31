"""Every file the release build uploads must be in the release toolkit's asset inventory, or the
toolkit stages a release without it (0.32.0 shipped without ``vixl-host-api.schema.json``)."""

import fnmatch
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]


def uploaded_patterns(artifact):
    workflow = yaml.safe_load((ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8"))
    for job in workflow["jobs"].values():
        for step in job.get("steps", ()):
            options = step.get("with") or {}
            if str(step.get("uses", "")).startswith("actions/upload-artifact@") and options.get("name") == artifact:
                return [Path(line.strip()).name for line in options["path"].splitlines() if line.strip()]
    raise AssertionError(f"release.yml uploads no {artifact} artifact")


def test_every_python_distribution_upload_is_a_configured_release_asset():
    config = json.loads((ROOT / ".release/config.json").read_text(encoding="utf-8"))
    assets = [name.replace("{version}", "1.2.3") for name in config["apps"]["vixl"]["assets"]]
    dropped = [pattern for pattern in uploaded_patterns("python-distributions")
               if not any(fnmatch.fnmatch(asset, pattern) for asset in assets)]
    assert not dropped, f"uploaded but missing from .release/config.json assets: {dropped}"
    assert "vixl-host-api.schema.json" in assets
