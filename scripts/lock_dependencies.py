"""Pin the installed, tested dependency closure for portable deployments."""

import tomllib
from importlib.metadata import requires, version
from pathlib import Path

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


def closure(roots):
    pinned, queue, seen = {}, list(roots), set()
    environment = {
        **default_environment(),
        "sys_platform": "linux",
        "platform_system": "Linux",
        "os_name": "posix",
    }
    while queue:
        requirement = Requirement(queue.pop())
        name = canonicalize_name(requirement.name)
        signature = (name, tuple(sorted(requirement.extras)))
        if signature in seen:
            continue
        seen.add(signature)
        pinned[name] = version(name)
        for dependency in requires(name) or []:
            child = Requirement(dependency)
            if not child.marker or any(
                child.marker.evaluate({**environment, "extra": extra})
                for extra in {"", *requirement.extras}
            ):
                queue.append(dependency)
    return pinned


if __name__ == "__main__":
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]
    runtime = closure(project["dependencies"])
    development = closure(project["optional-dependencies"]["dev"])
    for filename, dependencies in [
        ("requirements.txt", runtime),
        ("requirements-dev.txt", {k: v for k, v in development.items() if k not in runtime}),
    ]:
        header = "# Generated from the tested environment by scripts/lock_dependencies.py.\n"
        if filename.endswith("-dev.txt"):
            header += "-r requirements.txt\n"
        Path(filename).write_text(
            header + "\n".join(f"{k}=={v}" for k, v in sorted(dependencies.items())) + "\n",
            encoding="utf-8",
        )
    assert "celery" not in runtime and "redis" not in runtime
    print(f"Pinned {len(runtime)} runtime packages and {len(development)} development packages.")
