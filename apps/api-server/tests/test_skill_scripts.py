"""The two bundled sandbox scripts, run exactly as the container would run them (TC-M5-03)."""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from app.core.config import REPO_ROOT

SCRIPTS = REPO_ROOT / "packages" / "builtin-skills-rules" / "scripts"


def _run(script: str, *args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
    )


def _json(done: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    loaded = json.loads(done.stdout)
    assert isinstance(loaded, dict)
    return loaded


def test_openapi_validator_accepts_a_3x_spec(tmp_path: Path) -> None:
    (tmp_path / "api.json").write_text(json.dumps({"openapi": "3.1.0", "paths": {}}), encoding="utf-8")
    done = _run("validate_openapi.py", "--file", "api.json", cwd=tmp_path)
    assert done.returncode == 0
    assert _json(done) == {"valid": True, "openapi": "3.1.0"}


def test_openapi_validator_accepts_a_yaml_spec(tmp_path: Path) -> None:
    (tmp_path / "api.yaml").write_text("openapi: 3.0.3\npaths: {}\n", encoding="utf-8")
    done = _run("validate_openapi.py", "--file", "api.yaml", cwd=tmp_path)
    assert done.returncode == 0
    assert _json(done) == {"valid": True, "openapi": "3.0.3"}


@pytest.mark.parametrize(
    ("body", "error"),
    [
        ({"info": {"title": "T"}}, "missing openapi field"),
        ({"openapi": "2.0"}, "openapi version must be 3.x"),
    ],
)
def test_openapi_validator_rejects_a_spec_without_a_3x_version(
    tmp_path: Path,
    body: dict[str, Any],
    error: str,
) -> None:
    (tmp_path / "api.json").write_text(json.dumps(body), encoding="utf-8")
    done = _run("validate_openapi.py", "--file", "api.json", cwd=tmp_path)
    assert done.returncode == 2
    assert _json(done) == {"valid": False, "error": error}


def test_openapi_validator_reports_a_missing_file(tmp_path: Path) -> None:
    done = _run("validate_openapi.py", "--file", "absent.json", cwd=tmp_path)
    assert done.returncode == 2
    assert _json(done) == {"valid": False, "error": "file not found"}


def test_irr_calculator_reports_a_known_irr_and_payback(tmp_path: Path) -> None:
    done = _run("fin_calculator.py", "--cashflows", "-100,110", "--rate", "0.1", cwd=tmp_path)
    assert done.returncode == 0
    report = _json(done)
    assert report["npv"] == 0.0
    assert report["irr"] == pytest.approx(0.1, abs=1e-6)
    assert report["payback_periods"] == 0.9091


def test_irr_calculator_prints_three_scenarios_with_known_npvs(tmp_path: Path) -> None:
    done = _run("fin_calculator.py", "--cashflows", "-1000,300,400,500,200", "--rate", "0.08", cwd=tmp_path)
    assert done.returncode == 0
    report = _json(done)
    assert report["npv"] == 164.64
    npv_by_name = {row["name"]: row["npv"] for row in report["scenarios"]}
    assert npv_by_name == {"保守": -68.29, "基準": 164.64, "樂觀": 397.56}
    table = str(report["scenario_table"]).splitlines()
    assert table[0] == "| 情境 | NPV | IRR | 回收期 |"
    assert any(line.startswith("| 樂觀 | 397.56 |") for line in table)


def test_irr_calculator_needs_at_least_two_periods(tmp_path: Path) -> None:
    done = _run("fin_calculator.py", "--cashflows", "-100", "--rate", "0.1", cwd=tmp_path)
    assert done.returncode == 2
