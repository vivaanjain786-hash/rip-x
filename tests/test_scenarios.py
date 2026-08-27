import json

import pytest

from ripx.analytics.experiment import run_scenario
from ripx.simulation.scenarios import load_scenario


def test_loads_and_runs_a_file_backed_scenario(tmp_path):
    source = tmp_path / "scenario.json"
    source.write_text(json.dumps({"name": "small-ring", "topology": "ring", "routers": 4}))
    scenario = load_scenario(source)
    result = run_scenario(source)
    assert scenario.name == "small-ring"
    assert result["scenario"] == "small-ring"
    assert result["routers"] == 4
    assert result["convergence_rounds"] <= 4


def test_rejects_unknown_topology(tmp_path):
    source = tmp_path / "scenario.json"
    source.write_text(json.dumps({"name": "bad", "topology": "mesh", "routers": 4}))
    with pytest.raises(ValueError, match="baseline topology"):
        load_scenario(source)
