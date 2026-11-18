"""The invariants in AGENTS.md, checked."""

import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module.split(".")[0])
    return out


def test_the_product_never_imports_the_world_or_the_evaluations():
    for p in (ROOT / "src" / "signals").rglob("*.py"):
        assert not imports(p) & {"world", "evals"}, p


def test_the_world_does_not_read_the_products_settings():
    for p in (ROOT / "world").rglob("*.py"):
        src = p.read_text()
        assert "signals" not in imports(p), p
        for name in ("pipelines.toml", "gates.toml", "designs.toml"):
            assert name not in src, (p, name)


def test_settings_live_in_config_not_in_code():
    """Thresholds are read from config: no bare decimal thresholds in the deciding modules."""
    for rel in ("resolve/match.py", "classify/cascade.py", "events/detect.py", "golden.py", "ingest/runner.py"):
        src = (ROOT / "src" / "signals" / rel).read_text()
        code = "\n".join(line.split("#")[0] for line in src.splitlines() if not line.strip().startswith('"'))
        found = [x for x in re.findall(r"(?<![\w.])0\.\d+", code) if x != "0.0"]
        assert not found, (rel, found)


def test_reports_are_generated_not_edited():
    readme = (ROOT / "README.md").read_text()
    assert "<!-- results:start -->" in readme and "<!-- results:end -->" in readme
    dev = json.loads((ROOT / "reports" / "dev.json").read_text())
    assert dev["world"] == "dev" and "platform" in dev["designs"]


def test_hasura_metadata_exposes_only_the_analytics_schema():
    meta = json.loads((ROOT / "hasura" / "metadata.json").read_text())
    for t in meta["sources"][0]["tables"]:
        assert t["table"]["schema"] == "analytics"
