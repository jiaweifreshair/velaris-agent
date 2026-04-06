"""CLI smoke tests."""

import json

from typer.testing import CliRunner

from openharness.cli import app


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Velaris" in result.output


def test_cli_lifegoal_demo():
    runner = CliRunner()
    result = runner.invoke(app, ["demo", "lifegoal"])
    assert result.exit_code == 0
    assert "人生目标决策结果" in result.output
    assert "偏好召回" in result.output


def test_cli_lifegoal_demo_json():
    runner = CliRunner()
    result = runner.invoke(app, ["demo", "lifegoal", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert "人生目标决策结果" in payload
    assert payload["人生目标决策结果"]["recommended"]["id"] == "offer-b"


def test_cli_lifegoal_demo_save_to(tmp_path):
    runner = CliRunner()
    output_path = tmp_path / "lifegoal-demo.json"
    result = runner.invoke(app, ["demo", "lifegoal", "--save-to", str(output_path)])
    assert result.exit_code == 0
    assert output_path.exists()
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert "保存结果" in payload
    assert "Demo 结果已保存到:" in result.output
