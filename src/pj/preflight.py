import os
from collections.abc import Callable

import botocore.session

from pj.environment import Environment


class PreflightError(Exception):
    """raised when the credentials do not resolve for the target environment."""


def _caller_identity() -> str:
    client = botocore.session.get_session().create_client("sts")
    return client.get_caller_identity()["Account"]


def verify_credentials(
    environment: Environment,
    caller_identity: Callable[[], str] | None = None,
) -> None:
    if caller_identity is None:
        caller_identity = _caller_identity

    has_static_keys: bool = bool(os.environ.get("AWS_ACCESS_KEY_ID"))

    if has_static_keys and not environment.uses_swaj:
        raise PreflightError(
            "raw AWS_ACCESS_KEY_ID in the environment without swaj; "
            "run commands under swaj: swaj --profile=<env> exec pj ...",
        )

    try:
        caller_identity()
    except Exception:
        raise PreflightError(
            "aws credentials did not resolve (sts get-caller-identity "
            "failed); re-authenticate via swaj and re-run",
        ) from None
