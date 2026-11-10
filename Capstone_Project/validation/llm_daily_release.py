"""Durable daily classifier state and evidence, separate from the public-data ZIP."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from . import llm_classifier as C
from .llm_daily import RUNTIME

TAG = "bedrock-candidates"
ASSET = "classifier_state.json"
REPOSITORY = "BigJayJayHuang/DTCC-External-Risk-Intelligence"


def gh(*args, missing_ok=False):
    result = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=180)
    if result.returncode:
        if missing_ok and "(HTTP 404)" in result.stderr:
            return None
        raise RuntimeError("GitHub classifier-state operation failed; no model call should be retried until state is recovered")
    return result.stdout


def release(repository):
    value = gh("api", f"repos/{repository}/releases/tags/{TAG}", missing_ok=True)
    return json.loads(value) if value is not None else None


def restore(repository, state_file):
    record = release(repository)
    if record is None:
        tag = gh("api", f"repos/{repository}/git/ref/tags/{TAG}", missing_ok=True)
        if tag is not None:
            raise ValueError("Classifier release missing but its tag remains; recover state instead of resetting it")
        if state_file.exists():
            raise ValueError("Unexpected local state on initial release restore")
        return {"status": "initial_bootstrap", "paid_calls": 0}
    if ASSET not in {a["name"] for a in record["assets"]}:
        raise ValueError("Classifier state asset missing; recover before invoking")
    state_file.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        gh("release", "download", TAG, "--repo", repository, "--pattern", ASSET, "--dir", tmp)
        shutil.copyfile(Path(tmp) / ASSET, state_file)
    return {"status": "state_restored", "paid_calls": 0}


def checkpoint(repository, state_file):
    if not state_file.is_file():
        raise ValueError("Prepared state required before publishing a checkpoint")
    if release(repository) is None:
        gh("release", "create", TAG, "--repo", repository, "--target", os.environ.get("GITHUB_SHA", "main"),
           "--title", "Bedrock review candidates and run evidence", "--prerelease", "--notes",
           "Unreviewed model classifications of public feed text. Inspect run summaries and raw outputs; the event register is unchanged.")
    # gh's explicit upload label controls the stable asset name, not the local name.
    with tempfile.TemporaryDirectory() as tmp:
        upload = Path(tmp) / ASSET
        shutil.copyfile(state_file, upload)
        gh("release", "upload", TAG, "--repo", repository, "--clobber", str(upload))
    return {"status": "state_checkpointed", "paid_calls": 0}


def publish(repository, state_file, run_dir):
    if not (run_dir / "plan.json").exists():
        raise ValueError("Run plan missing; refusing to publish unrelated files")
    archive = run_dir.parent / (run_dir.name + ".zip")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for path in sorted(run_dir.rglob("*")):
            if path.is_symlink():
                raise ValueError("Symlinks are not classifier evidence")
            if path.is_file():
                entry = zipfile.ZipInfo((Path(run_dir.name) / path.relative_to(run_dir)).as_posix(), (1980, 1, 1, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                entry.external_attr = 0o644 << 16
                output.writestr(entry, path.read_bytes())
    # An immutable evidence archive must arrive before releasing its budget hold.
    digest = C.sha(archive.read_bytes())
    record = release(repository)
    prior = next((a for a in record["assets"] if a["name"] == archive.name), None) if record else None
    if prior is not None:
        if prior.get("digest") != "sha256:" + digest:
            raise ValueError("Existing evidence archive differs; refusing to overwrite it")
    else:
        gh("release", "upload", TAG, "--repo", repository, str(archive))
    checkpoint(repository, state_file)
    return {"status": "evidence_and_state_published", "archive": archive.name,
            "sha256": digest, "paid_calls": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["restore", "checkpoint", "publish"])
    parser.add_argument("--state-file", type=Path, default=RUNTIME / "state.json")
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--repo", default=REPOSITORY)
    args = parser.parse_args()
    try:
        if args.repo != REPOSITORY:
            raise ValueError("Use the approved project repository")
        if args.command == "publish":
            if args.run_dir is None:
                raise ValueError("--run-dir is required")
            result = publish(args.repo, args.state_file, args.run_dir)
        else:
            result = globals()[args.command](args.repo, args.state_file)
        print(json.dumps(result), flush=True)
    except Exception as exc:
        print(json.dumps({"status": "error", "reason": str(exc) if isinstance(exc, (ValueError, RuntimeError)) else type(exc).__name__}), flush=True)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
