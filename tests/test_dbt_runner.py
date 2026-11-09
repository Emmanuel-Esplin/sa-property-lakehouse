"""CodeBuild runs dbt from a small zip and a short install list. These keep both complete."""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent

# What infra/envs/dev/main.tf packs into dbt.zip besides transform/.
PACKED_MODULES = {"ingestion.common.bronze"}


def imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def pins(path: Path) -> dict[str, str]:
    lines = (line.split("#")[0].strip() for line in path.read_text().splitlines())
    return dict(line.split("==") for line in lines if "==" in line)


def test_runner_imports_only_what_is_packed():
    project = {m for m in imports(ROOT / "transform" / "run.py") if m.split(".")[0] == "ingestion"}
    assert project == PACKED_MODULES


def test_packed_modules_need_only_the_standard_library():
    for module in PACKED_MODULES:
        path = ROOT / (module.replace(".", "/") + ".py")
        third_party = {m for m in imports(path) if m.split(".")[0] not in sys.stdlib_module_names}
        assert not third_party, f"{module} imports {third_party}, which CodeBuild doesn't install"


def test_codebuild_installs_the_locked_dbt_versions():
    locked = pins(ROOT / "requirements.lock")
    for package, version in pins(ROOT / "transform" / "requirements-athena.txt").items():
        assert locked[package] == version, f"{package} is {locked[package]} in requirements.lock"
