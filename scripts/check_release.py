"""Check release metadata without importing the database-backed application."""

import argparse
import ast
import json
import re
import tomllib
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", help="Expected annotated release tag, for example v0.1.0")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    version = project["version"]
    if not re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", version):
        parser.error("Use a MAJOR.MINOR.PATCH application version")
    if args.tag and args.tag != "v" + version:
        parser.error(f"Tag must be v{version}, received {args.tag}")
    versions = {}
    for filename in ("package.json", "web/package.json"):
        versions[filename] = json.loads((root / filename).read_text(encoding="utf-8"))["version"]
    for filename in ("package-lock.json", "web/package-lock.json"):
        data = json.loads((root / filename).read_text(encoding="utf-8"))
        versions[filename] = data["version"]
        versions[filename + " root"] = data["packages"][""]["version"]
    lock = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
    versions["uv.lock"] = next(p["version"] for p in lock["package"] if p["name"] == "oxybridge")
    tree = ast.parse((root / "oxybridge/api.py").read_text(encoding="utf-8"))
    runtime = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "FastAPI":
            runtime.extend(ast.literal_eval(k.value) for k in node.keywords if k.arg == "version")
        if isinstance(node, ast.Dict):
            runtime.extend(
                ast.literal_eval(value)
                for key, value in zip(node.keys, node.values, strict=True)
                if isinstance(key, ast.Constant)
                and key.value == "version"
                and isinstance(value, ast.Constant)
                and isinstance(value.value, str)
            )
    if len(runtime) != 3:
        parser.error("Expected the API, system-info, and liveness version declarations")
    versions.update({f"runtime version {i + 1}": value for i, value in enumerate(runtime)})
    mismatch = [name for name, value in versions.items() if value != version]
    if mismatch:
        parser.error("Version mismatch in " + ", ".join(mismatch))
    if f"badge/version-{version}-" not in (root / "README.md").read_text(encoding="utf-8"):
        parser.error("Update the README version badge")
    if f"## [{version}] - " not in (root / "CHANGELOG.md").read_text(encoding="utf-8"):
        parser.error("Add the dated release to CHANGELOG.md")
    print(f"Release metadata matches v{version}: {len(versions)} declarations, badge, and changelog")


if __name__ == "__main__":
    main()
