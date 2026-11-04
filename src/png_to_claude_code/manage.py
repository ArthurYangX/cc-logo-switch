"""Build separately; install and restore with checksummed backups."""

from pathlib import Path
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
import platform
import shutil
import subprocess
import tempfile
import uuid
from . import engine


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_to(source, image, output, width=28):
    source = Path(source).expanduser().resolve(strict=True)
    output = Path(output).expanduser().absolute()
    if output.exists() or output.is_symlink():
        raise ValueError("Output already exists; choose a new filename")
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise ValueError(
            "Building/installing currently requires macOS Apple Silicon; preview works on other platforms"
        )
    for tool in ("node", "codesign"):
        if not shutil.which(tool):
            raise ValueError(f"Required tool is missing: {tool}")
    data = source.read_bytes()
    expected = hashlib.sha256(data).hexdigest()
    stub, pixels = engine.art(image, width)
    blob = engine.build(data, stub)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation also protects a concurrently created output.
    with output.open("xb") as stream:
        stream.write(blob)
    try:
        output.chmod(0o755)
        engine.sign(output, source)
        result = subprocess.run(
            [str(output), "--version"],
            capture_output=True,
            text=True,
            check=True,
            timeout=20,
        )
        if result.stdout.strip() != "2.1.318 (Claude Code)":
            raise ValueError("Built executable failed the version check")
        if sha256(source) != expected:
            raise ValueError(
                "Source changed during build; run again against the current version"
            )
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    return {
        "source_sha256": expected,
        "output_sha256": sha256(output),
        "width": pixels.width,
        "rows": pixels.height // 2,
        "version": "2.1.318",
        "output": str(output),
    }


def _save(path, data):
    path = Path(path)
    fd, name = tempfile.mkstemp(prefix=".state-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(data, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


@contextmanager
def _lock(state):
    state.parent.mkdir(parents=True, exist_ok=True)
    with state.with_suffix(".lock").open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def activate(candidate, target, state, expected_source):
    """Activate a candidate already validated by build_to()."""
    candidate = Path(candidate).expanduser().resolve(strict=True)
    target = Path(target).expanduser().resolve(strict=True)
    state = Path(state).expanduser().absolute()
    if candidate == target:
        raise ValueError("Candidate must be separate from the installed executable")
    if sha256(target) != expected_source:
        raise ValueError("Installed executable changed; refusing to overwrite it")
    with _lock(state):
        if state.exists() and json.loads(state.read_text()).get("status") != "restored":
            raise ValueError(
                "An installation record already exists; restore it first or use a separate --state path"
            )
        if sha256(target) != expected_source:
            raise ValueError("Installed executable changed; refusing to overwrite it")
        backup = target.with_name(
            target.name + ".before-png-to-claude-" + uuid.uuid4().hex[:12]
        )
        shutil.copy2(target, backup)
        if sha256(backup) != expected_source:
            raise ValueError("Backup changed during copy; no executable replaced")
        fd, temp = tempfile.mkstemp(prefix=".pixel-header-", dir=target.parent)
        os.close(fd)
        try:
            shutil.copy2(candidate, temp)
            installed = sha256(candidate)
            if sha256(temp) != installed:
                raise ValueError("Candidate changed during staging")
            record = {
                "schema": 1,
                "target": str(target),
                "backup": str(backup),
                "source_sha256": expected_source,
                "installed_sha256": installed,
                "status": "prepared",
            }
            _save(state, record)
            if sha256(target) != expected_source:
                raise ValueError("Installed executable changed; no executable replaced")
            os.replace(temp, target)
            record["status"] = "installed"
            _save(state, record)
            return record
        finally:
            if os.path.exists(temp):
                os.unlink(temp)


def restore(state):
    state = Path(state).expanduser().absolute()
    with _lock(state):
        record = json.loads(state.read_text())
        if record.get("schema") != 1:
            raise ValueError("Unknown installation record format")
        target = Path(record["target"])
        backup = Path(record["backup"])
        current = sha256(target)
        if record["status"] == "restored":
            raise ValueError("This installation has already been restored")
        if current not in (record["installed_sha256"], record["source_sha256"]):
            raise ValueError(
                "Claude was updated or modified after installation; refusing to overwrite the newer file"
            )
        if sha256(backup) != record["source_sha256"]:
            raise ValueError("Backup checksum failed; no files changed")
        if current == record["source_sha256"]:
            record["status"] = "restored"
            _save(state, record)
            return record
        fd, temp = tempfile.mkstemp(prefix=".pixel-restore-", dir=target.parent)
        os.close(fd)
        try:
            shutil.copy2(backup, temp)
            if sha256(temp) != record["source_sha256"]:
                raise ValueError("Backup changed during staging")
            if sha256(target) != current:
                raise ValueError("Installed executable changed during restore")
            os.replace(temp, target)
            record["status"] = "restored"
            _save(state, record)
            return record
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
