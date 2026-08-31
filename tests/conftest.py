import pytest


@pytest.fixture(autouse=True)
def pj_workspace(monkeypatch, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "pyproject.toml").write_text(
        "[tool.pj]\n"
        'organization = "squad"\n'
        'domain = "squad.com"\n',
    )
    monkeypatch.chdir(workspace)
