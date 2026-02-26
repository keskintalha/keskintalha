from pathlib import Path

from senior_cpp_agent.config import AgentSettings


def test_models_property(tmp_path: Path):
    settings = AgentSettings(workspace=tmp_path)
    models = settings.models
    assert set(models.keys()) == {"architect", "implementer", "reviewer", "validator"}
