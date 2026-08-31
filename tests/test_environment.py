import pytest
from pj.environment import (
    Environment,
    PJConfigError,
    find_pj_table,
    read_profile_option,
    resolve_environment,
)


def test_swaj_environment(tmp_path):
    aws_config = tmp_path / "config"
    aws_config.write_text("[profile qa]\nregion = us-east-1\n")

    environment = resolve_environment(
        environ={"SWAJ_PROFILE": "qa"},
        aws_config_path=aws_config,
    )

    assert environment.name == "qa"
    assert environment.uses_swaj is True
    assert environment.region == "us-east-1"
    assert environment.organization == "squad"
    assert environment.domain == "squad.com"
    assert environment.state_bucket == "pulumi-state-qa.squad.com"
    assert environment.name_prefix == "qa-"
    assert environment.uses_local_state is False


def test_aws_profile_environment():
    environment = resolve_environment(environ={"AWS_PROFILE": "qa"})

    assert environment.name == "qa"
    assert environment.uses_swaj is False
    assert environment.uses_local_state is False


def test_swaj_profile_ignores_environment_key(tmp_path):
    aws_config = tmp_path / "config"
    aws_config.write_text(
        "[profile marko]\n"
        "region = eu-central-1\n"
        "environment = qa\n",
    )

    environment = resolve_environment(
        environ={"SWAJ_PROFILE": "marko"},
        aws_config_path=aws_config,
    )

    assert environment.name == "marko"
    assert environment.uses_swaj is True
    assert environment.region == "eu-central-1"
    assert environment.state_bucket == "pulumi-state-marko.squad.com"
    assert environment.name_prefix == "marko-"


def test_aws_profile_ignores_environment_key(tmp_path):
    aws_config = tmp_path / "config"
    aws_config.write_text(
        "[profile marko]\n"
        "region = eu-central-1\n"
        "environment = qa\n",
    )

    environment = resolve_environment(
        environ={"AWS_PROFILE": "marko"},
        aws_config_path=aws_config,
    )

    assert environment.name == "marko"
    assert environment.uses_swaj is False
    assert environment.region == "eu-central-1"
    assert environment.state_bucket == "pulumi-state-marko.squad.com"


def test_profile_without_environment_key_uses_profile_name(tmp_path):
    aws_config = tmp_path / "config"
    aws_config.write_text("[profile marko]\nregion = eu-central-1\n")

    environment = resolve_environment(
        environ={"AWS_PROFILE": "marko"},
        aws_config_path=aws_config,
    )

    assert environment.name == "marko"
    assert environment.region == "eu-central-1"


def test_local_environment():
    environment = resolve_environment(environ={})

    assert environment.name == "localhost"
    assert environment.uses_local_state is True
    assert environment.state_bucket == "pulumi-state-localhost.squad.com"


def test_prod_has_empty_prefix():
    environment = resolve_environment(
        environ={"SWAJ_PROFILE": "prod"},
    )

    assert environment.name_prefix == ""


def test_custom_domain_flows_into_names():
    environment = Environment(
        name="qa",
        organization="squad",
        domain="acme.io",
    )

    assert environment.state_bucket == "pulumi-state-qa.acme.io"


def test_read_profile_option_missing_file(tmp_path):
    assert read_profile_option("qa", "region", tmp_path / "config") is None


def test_read_profile_option_reads_arbitrary_keys(tmp_path):
    aws_config = tmp_path / "config"
    aws_config.write_text(
        "[profile qa]\n"
        "region = us-east-1\n"
        "swaj_role_arn = arn:aws:iam::123456789012:role/ops\n",
    )

    assert (
        read_profile_option("qa", "swaj_role_arn", aws_config)
        == "arn:aws:iam::123456789012:role/ops"
    )
    assert read_profile_option("qa", "region", aws_config) == "us-east-1"
    assert read_profile_option("qa", "missing", aws_config) is None


def test_find_pj_table_walks_up_to_the_nearest_table(tmp_path):
    nested = tmp_path / "services" / "kms"
    nested.mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pj]\n"
        'organization = "squad"\n'
        'domain = "squad.com"\n',
    )

    assert find_pj_table(nested) == {
        "organization": "squad",
        "domain": "squad.com",
    }


def test_find_pj_table_skips_pyproject_without_the_table(tmp_path):
    nested = tmp_path / "python" / "pj"
    nested.mkdir(parents=True)
    (nested / "pyproject.toml").write_text('[project]\nname = "pj"\n')
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pj]\n"
        'organization = "squad"\n'
        'domain = "squad.com"\n',
    )

    assert find_pj_table(nested) == {
        "organization": "squad",
        "domain": "squad.com",
    }


def test_find_pj_table_errors_when_no_pyproject_has_the_table(tmp_path):
    with pytest.raises(PJConfigError, match=r"\[tool\.pj\]"):
        find_pj_table(tmp_path)


def test_resolve_environment_rejects_incomplete_table(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text('[tool.pj]\norganization = "squad"\n')

    with pytest.raises(PJConfigError, match="domain"):
        resolve_environment(environ={})
