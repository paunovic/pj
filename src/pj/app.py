import json
import os
import subprocess
import sys

from pj import preflight
from pj.environment import Environment, PJConfigError, resolve_environment


class PJ:

    def run(self, args: list[str] | None = None) -> int:

        args = args if args is not None else sys.argv[1:]

        # help must work in any directory; config resolution only
        # gates real pulumi commands
        if not args or args[0] in {"--help", "-h"}:
            return self._dispatch_help()

        try:
            environment: Environment = resolve_environment()
        except PJConfigError as e:
            sys.stderr.write(f"error: {e}\n")
            sys.stderr.flush()
            return 1

        # state-mutating commands against real environments need working
        # credentials before any state-backend login
        preflight_return_code = self._preflight(args, environment)
        if preflight_return_code is not None:
            return preflight_return_code

        # login is the only state placement: the environment's bucket
        # with pulumi's default .pulumi/... key layout
        if environment.uses_local_state:
            login_args: list[str] = ["login", "--local"]
        else:
            login_args = [
                "login",
                "--cloud-url",
                f"s3://{environment.state_bucket}",
            ]

        login_exit_status = self.run_pulumi(args=login_args, environment=environment)
        if login_exit_status != 0:
            sys.stderr.write(f"error: pj failed to login to s3 backend, exit code {login_exit_status}\n")
            sys.stderr.flush()
            return login_exit_status

        ensure_return_code = self._ensure_stack(args, environment)
        if ensure_return_code is not None:
            return ensure_return_code

        return self.run_pulumi(
            args=self.with_stack(
                self.with_secrets_provider(args, environment),
                environment,
            ),
            environment=environment,
        )

    def _dispatch_help(self) -> int:
        # passthrough keeps pulumi's usage authoritative instead of
        # pj duplicating it; works without a [tool.pj] table
        is_interactive: bool = sys.stdout.isatty()

        result = subprocess.run(
            ["pulumi", "--help"],
            check=False,
            capture_output=not is_interactive,
            text=not is_interactive,
        )

        if is_interactive:
            return result.returncode

        self._replay_output(result)
        return result.returncode

    def with_secrets_provider(
        self,
        args: list[str],
        environment: Environment,
    ) -> list[str]:
        # pulumi accepts the flag on up and stack init; everything
        # else uses the provider recorded at init
        is_up: bool = bool(args) and args[0] == "up"
        is_stack_init: bool = args[:2] == ["stack", "init"]

        if (is_up or is_stack_init) and not environment.uses_local_state:
            return [*args, "--secrets-provider", environment.secrets_provider]
        return args

    def with_stack(
        self,
        args: list[str],
        environment: Environment,
    ) -> list[str]:
        # env = swaj profile = stack name: passing the derived stack
        # keeps pulumi from prompting for one on a fresh workspace
        stack_aware_subcommands = {
            "up", "preview", "refresh", "destroy", "import",
            "watch", "config", "stack",
        }
        if not args or args[0] not in stack_aware_subcommands:
            return args

        for arg in args:
            if arg in {"-s", "-S", "--stack"} or arg.startswith("--stack="):
                return args

        # these name their stack positionally; pulumi rejects a
        # --stack flag next to the positional ("only one of --stack
        # or argument stack name may be specified")
        if args[0] == "stack" and len(args) > 1 and args[1] in {
            "init", "select", "rm", "rename",
        }:
            return args

        return [*args, "--stack", environment.name]

    def _ensure_stack(self, args: list[str], environment: Environment) -> int | None:
        # up and preview are the first-run entry points, so a missing
        # stack gets inited; destroy/refresh/watch keep failing on one
        # — there is nothing to destroy, refresh or watch yet
        if not args or args[0] not in {"up", "preview"}:
            return None

        # an explicit stack flag means the user owns stack choice
        for arg in args:
            if arg in {"-s", "-S", "--stack"} or arg.startswith("--stack="):
                return None

        stacks = self._list_stacks(environment)
        if stacks is None or environment.name in stacks:
            return None

        init_args = self.with_secrets_provider(
            ["stack", "init", environment.name],
            environment,
        )
        init_result = subprocess.run(
            ["pulumi", *init_args],
            env=self.pulumi_environment(environment),
            check=False,
            capture_output=True,
            text=True,
        )

        # a concurrent init winning the race reads as success
        is_race: bool = "already exists" in init_result.stderr
        if init_result.returncode != 0 and not is_race:
            sys.stderr.write(
                f"error: pj failed to init stack {environment.name}, "
                f"exit code {init_result.returncode}\n",
            )
            sys.stderr.flush()
            self._replay_output(init_result)
            return init_result.returncode

        self._replay_output(init_result)
        return None

    def _list_stacks(self, environment: Environment) -> list[str] | None:
        ls_result = subprocess.run(
            ["pulumi", "stack", "ls", "--json"],
            env=self.pulumi_environment(environment),
            check=False,
            capture_output=True,
            text=True,
        )
        if ls_result.returncode != 0:
            return None

        # the payload may be preceded by login banners or warnings;
        # json starts at the first bracket line and may span lines
        lines: list[str] = ls_result.stdout.splitlines()
        for index, line in enumerate(lines):
            if not line.lstrip().startswith(("[", "{")):
                continue
            try:
                return [entry["name"] for entry in json.loads(
                    "\n".join(lines[index:]),
                )]
            except (json.JSONDecodeError, KeyError, TypeError):
                return None
        return None

    def pulumi_environment(self, environment: Environment) -> dict:
        pulumi_env: dict = os.environ.copy()

        # local state keeps passphrase-encrypted secrets prompt-free;
        # real environments use awskms and never see a passphrase
        if environment.uses_local_state:
            pulumi_env["PULUMI_CONFIG_PASSPHRASE"] = ""
        else:
            pulumi_env.pop("PULUMI_CONFIG_PASSPHRASE", None)

        return pulumi_env

    def _preflight(self, args: list[str], environment: Environment) -> int | None:
        if not args or args[0] not in {"up", "destroy", "refresh"}:
            return None

        if environment.uses_local_state:
            return None

        try:
            preflight.verify_credentials(environment)
        except preflight.PreflightError as e:
            sys.stderr.write(f"preflight error: {e}\n")
            sys.stderr.flush()
            return 1

        return None

    def run_pulumi(self, args: list[str], environment: Environment) -> int:
        # interactive terminals keep pulumi's native output; captured
        # non-interactive output can be inspected for remediation
        is_interactive: bool = sys.stdout.isatty()

        result = subprocess.run(
            ["pulumi", *args],
            env=self.pulumi_environment(environment),
            check=False,
            capture_output=not is_interactive,
            text=not is_interactive,
        )

        if is_interactive:
            return result.returncode

        if (
            result.returncode != 0
            and "error: no stack selected; please use `pulumi stack select` "
            "or `pulumi stack init` to choose one" in result.stderr
        ):
            remediated_return_code = self._remediate_no_stack(args, environment)
            if remediated_return_code is not None:
                return remediated_return_code

        self._replay_output(result)

        # pulumi reports a missing state bucket as a bare NoSuchBucket
        # blob error; name the derived bucket and the bootstrap path
        # instead of leaving the reader to decode it
        if result.returncode != 0 and "NoSuchBucket" in (
            (result.stdout or "") + (result.stderr or "")
        ):
            sys.stderr.write(
                f"pj: state bucket s3://{environment.state_bucket} does not "
                "exist — run setup_aws_environment from the code repo once "
                "to bootstrap the org\n",
            )
            sys.stderr.flush()

        return result.returncode

    def _remediate_no_stack(
        self,
        args: list[str],
        environment: Environment,
    ) -> int | None:
        # auto-select when exactly one stack exists, auto-init when
        # none do; anything more ambiguous is left to the user
        stacks = self._list_stacks(environment)
        if stacks is None:
            return None

        if not stacks:
            return self._init_stack_and_retry(args, environment)

        if len(stacks) > 1:
            names = ", ".join(stacks)
            sys.stderr.write(
                f"pj: no stack selected and multiple stacks exist: {names}; "
                "run `pulumi stack select <name>` and re-run\n",
            )
            sys.stderr.flush()
            return None

        select_result = subprocess.run(
            ["pulumi", "stack", "select", stacks[0]],
            env=self.pulumi_environment(environment),
            check=False,
            capture_output=True,
            text=True,
        )
        if select_result.returncode != 0:
            self._replay_output(select_result)
            return None

        retry_result = subprocess.run(
            ["pulumi", *args],
            env=self.pulumi_environment(environment),
            check=False,
            capture_output=True,
            text=True,
        )
        self._replay_output(retry_result)
        return retry_result.returncode

    def _init_stack_and_retry(
        self,
        args: list[str],
        environment: Environment,
    ) -> int | None:
        # zero stacks: init the environment's stack and retry once
        init_args = self.with_secrets_provider(
            ["stack", "init", environment.name],
            environment,
        )
        init_result = subprocess.run(
            ["pulumi", *init_args],
            env=self.pulumi_environment(environment),
            check=False,
            capture_output=True,
            text=True,
        )
        if init_result.returncode != 0:
            self._replay_output(init_result)
            return None

        retry_result = subprocess.run(
            ["pulumi", *args],
            env=self.pulumi_environment(environment),
            check=False,
            capture_output=True,
            text=True,
        )
        self._replay_output(retry_result)
        return retry_result.returncode

    def _replay_output(self, result: subprocess.CompletedProcess) -> None:
        sys.stdout.write(result.stdout)
        sys.stdout.flush()
        sys.stderr.write(result.stderr)
        sys.stderr.flush()
