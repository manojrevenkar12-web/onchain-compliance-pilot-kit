"""The kit sees only what a solutions architect and the customer's systems would see."""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "ocp"


def _imports(path: Path) -> set[str]:
    out = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module:
            out.add("." * node.level + node.module)
        elif isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
    return out


def test_kit_and_service_never_import_the_world() -> None:
    for pkg in ("kit", "service"):
        for f in (SRC / pkg).rglob("*.py"):
            bad = [m for m in _imports(f) if any(x in m for x in ("world", "sim", "lab"))]
            assert not bad, f"{f}: {bad}"


def test_world_never_reads_kit_settings() -> None:
    for f in (SRC / "world").rglob("*.py"):
        text = f.read_text(encoding="utf-8")
        assert "kit.yml" not in text and "config.kit" not in text and "designs" not in text, f
        assert not [m for m in _imports(f) if "kit" in m or "sim" in m or "lab" in m], f
