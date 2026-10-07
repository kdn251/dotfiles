#!/usr/bin/env python3
"""Install shared agent files and portable Pi preferences without copying secrets."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent


def read_object(path):
    if not path.exists():
        return {}
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(data, stream, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def configure(home, install_packages=True):
    home = Path(home).resolve()
    config = read_object(ROOT / "pi-config.json")
    agent = home / ".pi/agent"
    resources = ROOT / "agents"
    plan = []
    sources = set()
    # Never scan the whole agent directory: ignored runtime files may be present
    # in a checkout used with Stow. Only explicitly managed resources are inputs.
    for relative in config["resources"]:
        source = resources / relative
        if not source.exists() or not source.resolve().is_relative_to(resources.resolve()):
            raise ValueError(f"Missing or external managed resource: {source}")
        sources.update(source.rglob("*") if source.is_dir() and not source.is_symlink() else [source])
    # Preflight every link before changing anything. Never overwrite a different
    # local skill, extension, or prompt just because it has the same name.
    for source in sorted(sources):
        if not source.is_symlink() and not source.is_file():
            continue
        if not source.exists() or not source.resolve().is_relative_to(resources.resolve()):
            raise ValueError(f"Broken or external resource symlink: {source}")
        target = home / source.relative_to(resources)
        desired = home / source.resolve().relative_to(resources.resolve()) if source.is_symlink() else source
        if target.resolve() == desired.resolve():
            continue
        exists = target.exists() or target.is_symlink()
        identical = exists and source.is_file() and target.is_file() and source.read_bytes() == target.read_bytes()
        if exists and not identical:
            raise ValueError(f"Conflicting local file, reconcile it before retrying: {target}")
        plan.append((source, target, desired, exists))

    settings_path = agent / "settings.json"
    npm_path = agent / "npm/package.json"
    settings = read_object(settings_path)
    npm = read_object(npm_path)
    # Merge only managed preferences. Preserve model, credentials references,
    # other packages, resource filters, and unknown future settings.
    settings.update(config["settings"])
    npm.setdefault("name", "pi-extensions")
    npm.setdefault("private", True)
    npm.setdefault("dependencies", {})
    overrides = npm.setdefault("overrides", {})
    for package, values in config["npmOverrides"].items():
        existing = overrides.get(package, {})
        if not isinstance(existing, dict):
            raise ValueError(f"Conflicting npm override for {package}; reconcile it first")
        overrides[package] = {**existing, **values}

    if install_packages:
        for command in ("pi", "npm", "node"):
            if not shutil.which(command):
                raise ValueError(f"Install {command} first, then rerun setup-pi.py")
        version = subprocess.check_output(["pi", "--version"], text=True).strip()
        if version != config["testedPiVersion"]:
            print(f"Note: tested with Pi {config['testedPiVersion']}; installed Pi is {version}.")

    backup = None

    def backup_file(path):
        nonlocal backup
        if not (path.exists() or path.is_symlink()):
            return
        if backup is None:
            backup = Path(tempfile.mkdtemp(prefix=".pi-config-backup-", dir=home))
        destination = backup / path.relative_to(home)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        destination.chmod(0o600)

    for source, target, desired, exists in plan:
        target.parent.mkdir(parents=True, exist_ok=True)
        if exists:
            backup_file(target)
            target.unlink()
        # Resolve the physical parent: existing home directories can themselves
        # be symlinks to storage at a completely different depth.
        target.symlink_to(os.path.relpath(desired.resolve(), target.parent.resolve()))

    if read_object(settings_path) != settings:
        backup_file(settings_path)
        atomic_json(settings_path, settings)
    if read_object(npm_path) != npm:
        backup_file(npm_path)
        atomic_json(npm_path, npm)
    calm = agent / "calm.json"
    if not calm.exists():
        atomic_json(calm, {"enabled": True})

    if install_packages:
        env = {**os.environ, "HOME": str(home), "PI_CODING_AGENT_DIR": str(agent)}
        for package in config["packages"]:
            subprocess.run(["pi", "install", package], env=env, check=True)
        # Keep the security override in the managed npm tree and avoid lifecycle
        # scripts/duplicate host peer packages. Pi supplies its extension peers.
        subprocess.run(["npm", "install", "--ignore-scripts", "--legacy-peer-deps"], cwd=agent / "npm", env=env, check=True)
        subprocess.run(["npm", "audit", "--omit=dev"], cwd=agent / "npm", env=env, check=True)

    print(f"Linked {len(plan)} resources; Pi preferences applied in {agent}.")
    if backup:
        print(f"Previous local config backed up in {backup}.")
    print("Run /reload in Pi. On a new machine, sign in using /login.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-packages", action="store_true", help="Link files and apply preferences without installing npm packages")
    args = parser.parse_args()
    if os.environ.get("PI_CODING_AGENT_DIR") and Path(os.environ["PI_CODING_AGENT_DIR"]).expanduser().resolve() != Path.home() / ".pi/agent":
        parser.error("This dotfiles layout targets ~/.pi/agent; unset custom PI_CODING_AGENT_DIR first.")
    try:
        configure(Path.home(), not args.skip_packages)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Setup stopped: {error}\n")


if __name__ == "__main__":
    main()
