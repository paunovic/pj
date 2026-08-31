import configparser
import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


class PJConfigError(Exception):
    """raised when no pyproject.toml with a [tool.pj] table is in scope."""


@dataclass(frozen=True)
class Environment:
    name: str
    organization: str
    domain: str
    region: str | None = None
    uses_swaj: bool = False

    @property
    def name_prefix(self) -> str:
        if self.name == "prod":
            return ""
        return f"{self.name}-"

    @property
    def state_bucket(self) -> str:
        return f"pulumi-state-{self.name}.{self.domain}"

    @property
    def uses_local_state(self) -> bool:
        return not self.uses_swaj and self.name == "localhost"

    @property
    def secrets_provider(self) -> str:
        # the kms key lives in the account's default region; the aws
        # config region wins, us-east-1 matches the stack config default
        return f"awskms://alias/pulumi-secrets?region={self.region or 'us-east-1'}"


def find_pj_table(start: Path | None = None) -> dict:
    # organization and domain live in [tool.pj] of the nearest
    # pyproject.toml at or above start; pyproject.toml files without
    # the table are skipped so sub-packages do not shadow the root
    directory: Path = start if start is not None else Path.cwd()
    for candidate in [directory, *directory.parents]:
        pyproject = candidate / "pyproject.toml"
        if not pyproject.is_file():
            continue
        with open(pyproject, "rb") as fp:
            document = tomllib.load(fp)
        tool_table = document.get("tool")
        if isinstance(tool_table, dict) and isinstance(tool_table.get("pj"), dict):
            return tool_table["pj"]

    raise PJConfigError(
        f"no pyproject.toml with a [tool.pj] table found at or above "
        f"{directory}; pj reads organization and domain from that table",
    )


def read_profile_option(
    profile: str,
    option: str,
    aws_config_path: Path | None = None,
) -> str | None:
    path: Path = aws_config_path or Path.home() / ".aws" / "config"
    if not path.is_file():
        return None

    parser = configparser.ConfigParser()
    parser.read(path)

    for section in (f"profile {profile}", profile):
        if parser.has_option(section, option):
            return parser.get(section, option)

    return None


def resolve_environment(
    environ: Mapping[str, str] | None = None,
    aws_config_path: Path | None = None,
) -> Environment:
    # the profile name IS the environment name; the aws config is
    # consulted only for the region
    environ = environ if environ is not None else os.environ
    pj_table = find_pj_table()

    organization = pj_table.get("organization")
    domain = pj_table.get("domain")
    if not isinstance(organization, str) or not isinstance(domain, str):
        raise PJConfigError(
            "[tool.pj] needs string values for organization and domain; "
            f"got organization={organization!r}, domain={domain!r}",
        )

    swaj_profile: str | None = environ.get("SWAJ_PROFILE")
    if swaj_profile:
        return Environment(
            name=swaj_profile,
            organization=organization,
            domain=domain,
            region=read_profile_option(swaj_profile, "region", aws_config_path),
            uses_swaj=True,
        )

    aws_profile: str | None = environ.get("AWS_PROFILE")
    if aws_profile:
        return Environment(
            name=aws_profile,
            organization=organization,
            domain=domain,
            region=read_profile_option(aws_profile, "region", aws_config_path),
        )

    return Environment(
        name="localhost",
        organization=organization,
        domain=domain,
    )
