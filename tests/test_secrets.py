from pj.app import PJ
from pj.environment import resolve_environment


def test_secrets_provider_url_derives_from_region(tmp_path):
    aws_config = tmp_path / "config"
    aws_config.write_text("[profile qa]\nregion = us-east-1\n")

    environment = resolve_environment(
        environ={"SWAJ_PROFILE": "qa"},
        aws_config_path=aws_config,
    )

    assert environment.secrets_provider == (
        "awskms://alias/pulumi-secrets?region=us-east-1"
    )


def test_secrets_provider_defaults_region(tmp_path):
    environment = resolve_environment(
        environ={"SWAJ_PROFILE": "qa"},
        aws_config_path=tmp_path / "config",
    )

    assert environment.secrets_provider == (
        "awskms://alias/pulumi-secrets?region=us-east-1"
    )


def test_mutating_commands_get_secrets_provider(tmp_path):
    pj = PJ()
    environment = resolve_environment(
        environ={"SWAJ_PROFILE": "qa"},
        aws_config_path=tmp_path / "config",
    )

    args = pj.with_secrets_provider(["up"], environment)

    assert args == [
        "up",
        "--secrets-provider",
        "awskms://alias/pulumi-secrets?region=us-east-1",
    ]


def test_local_commands_stay_untouched():
    pj = PJ()
    environment = resolve_environment(environ={})

    args = pj.with_secrets_provider(["up"], environment)

    assert args == ["up"]


def test_other_commands_pass_through():
    pj = PJ()
    environment = resolve_environment(environ={"SWAJ_PROFILE": "qa"})

    assert pj.with_secrets_provider(["stack", "ls"], environment) == ["stack", "ls"]


def test_local_run_sets_empty_passphrase():
    pj = PJ()
    environment = resolve_environment(environ={})

    pulumi_env = pj.pulumi_environment(environment)

    assert pulumi_env["PULUMI_CONFIG_PASSPHRASE"] == ""


def test_real_env_does_not_set_passphrase(monkeypatch):
    monkeypatch.setenv("PULUMI_CONFIG_PASSPHRASE", "leaked")

    pj = PJ()
    environment = resolve_environment(environ={"SWAJ_PROFILE": "qa"})

    pulumi_env = pj.pulumi_environment(environment)

    assert "PULUMI_CONFIG_PASSPHRASE" not in pulumi_env


def test_preview_does_not_get_secrets_provider(tmp_path):
    pj = PJ()
    environment = resolve_environment(
        environ={"SWAJ_PROFILE": "qa"},
        aws_config_path=tmp_path / "config",
    )

    assert pj.with_secrets_provider(["preview"], environment) == ["preview"]


def test_stack_init_stays_untouched_on_local():
    pj = PJ()
    environment = resolve_environment(environ={})

    args = pj.with_secrets_provider(["stack", "init", "dev"], environment)

    assert args == ["stack", "init", "dev"]


def test_stack_init_appends_secrets_provider_on_real_envs(tmp_path):
    pj = PJ()
    environment = resolve_environment(
        environ={"SWAJ_PROFILE": "qa"},
        aws_config_path=tmp_path / "config",
    )

    args = pj.with_secrets_provider(["stack", "init", "qa"], environment)

    assert args == [
        "stack",
        "init",
        "qa",
        "--secrets-provider",
        "awskms://alias/pulumi-secrets?region=us-east-1",
    ]
