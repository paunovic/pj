import pytest
from pj.environment import resolve_environment
from pj.preflight import PreflightError, verify_credentials


class FakeCaller:
    def __init__(self, account_id: str | None) -> None:
        self.account_id = account_id

    def __call__(self) -> str:
        if self.account_id is None:
            raise RuntimeError("NoCredentialProviders")
        return self.account_id


def test_refuses_raw_static_keys_without_swaj(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAEXAMPLE")

    environment = resolve_environment(environ={"AWS_PROFILE": "qa"})

    with pytest.raises(PreflightError, match="swaj"):
        verify_credentials(environment, caller_identity=FakeCaller("123456789012"))


def test_accepts_materialized_keys_under_swaj(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "ASIAEXAMPLE")

    environment = resolve_environment(environ={"SWAJ_PROFILE": "qa"})

    verify_credentials(environment, caller_identity=FakeCaller("123456789012"))


def test_expired_credentials_error_names_swaj(monkeypatch):
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)

    environment = resolve_environment(environ={"SWAJ_PROFILE": "qa"})

    with pytest.raises(PreflightError, match="swaj"):
        verify_credentials(environment, caller_identity=FakeCaller(None))
