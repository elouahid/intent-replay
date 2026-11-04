"""Install two hash-bound saved comparisons. Never interpret or execute them."""
import hashlib
import json
import re
from pathlib import Path

from intent_replay.meta_client import PROJECT_ROOT


BUNDLE_ROOT = PROJECT_ROOT / "demo"
DEFAULT_STORAGE = PROJECT_ROOT / ".local" / "recorded-demo"


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def read_bundle(bundle_root=None):
    root = Path(bundle_root or BUNDLE_ROOT)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("bundle_version") != "recorded-execution-demo-v1" or [e.get("key") for e in manifest.get("examples", [])] != ["withdrawal", "control"]:
        raise ValueError("Recorded demo manifest is missing its two canonical comparisons.")
    result = []
    for entry in manifest["examples"]:
        if entry.get("filename") != entry["key"] + ".json" or not re.fullmatch(r"[a-f0-9]{32}", entry.get("pair_id", "")):
            raise ValueError("Recorded demo filename or identity is invalid.")
        path = root / entry["filename"]
        if path.is_symlink():
            raise ValueError("Recorded demo source links are not supported.")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != entry.get("sha256"):
            raise ValueError("Recorded demo source hash differs; no saved report was imported.")
        report = json.loads(raw)
        provenance = report.get("provenance", {})
        if (report.get("schema_version") != 6 or report.get("report_type") != "agent_comparison"
            or report.get("pair_id") != entry["pair_id"] or report.get("run_id") != entry["pair_id"]
            or provenance.get("original_pair_id") != entry.get("original_pair_id")
            or provenance.get("original_pair_sha256") != entry.get("original_pair_sha256")
            or provenance.get("original_capture_sha256") != _digest(report.get("capture"))
            or provenance.get("saved_branch_sha256") != [_digest(b) for b in report.get("reports", [])]
            or len(report.get("reports", [])) != 2):
            raise ValueError("Recorded demo source/capture/branch association is invalid.")
        result.append((entry, raw))
    trial = root / "language-trial.json"
    if trial.is_symlink() or hashlib.sha256(trial.read_bytes()).hexdigest() != manifest.get("language_trial_sha256"):
        raise ValueError("Recorded language-trial summary hash differs.")
    return result


def install_demo(directory=None, *, bundle_root=None):
    """Idempotent byte copies with validation/preflight before writing any report.

    Conflicts and links fail closed. Existing reports are never overwritten, and
    no configuration, model client or database is opened.
    """
    records = read_bundle(bundle_root)
    directory = Path(directory or DEFAULT_STORAGE)
    if directory.is_symlink():
        raise ValueError("Recorded demo storage cannot be a symbolic link.")
    directory.mkdir(parents=True, exist_ok=True)
    planned = []
    for entry, raw in records:
        target = directory / (entry["pair_id"] + ".json")
        if target.is_symlink() or (target.exists() and (not target.is_file() or target.read_bytes() != raw)):
            raise ValueError("A recorded demo report conflicts with an existing file; nothing was overwritten. Choose another --demo-dir.")
        planned.append((entry, raw, target))
    for entry, raw, target in planned:
        if not target.exists():
            try:
                with target.open("xb") as stream:
                    stream.write(raw)
            except FileExistsError:
                if target.is_symlink() or target.read_bytes() != raw:
                    raise ValueError("A conflicting report appeared during import; it was not overwritten.") from None
    return [{"key": entry["key"], "label": entry["label"], "run_id": entry["pair_id"], "sha256": entry["sha256"]}
            for entry, _, _ in planned]


def configure_demo(app, directory=None):
    root = Path(directory or DEFAULT_STORAGE)
    examples = install_demo(root)
    app.state.agent_storage_root = root
    app.state.recorded_demo_examples = examples
    app.state.recorded_demo_enabled = True
    return examples
