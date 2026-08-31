# pj

pj is a thin wrapper around Pulumi for running the same stacks
against several environments. Instead of repeating the state
backend, stack name, and secrets provider on every command, pj
derives all three from the active AWS profile and the current
project directory, logs in, and hands everything else to Pulumi.

## Install

```
uv tool install git+https://github.com/paunovic/pj
```

## What pj needs

A `[tool.pj]` table in the pyproject.toml at or above the Pulumi project:

```toml
[tool.pj]
organization = "acme"
domain = "acme.io"
```

And an AWS profile, either directly via `AWS_PROFILE` or through
[swaj](https://github.com/f0rk/swaj) (`SWAJ_PROFILE`). The profile
name is the environment name: `swaj --profile=qa exec …` means
environment `qa`.

## How pj runs a command

From the environment and the `[tool.pj]` table pj derives the
state bucket `s3://pulumi-state-<env>.<domain>`, the stack name,
and the region, logs into the bucket, and forwards the remaining
arguments to Pulumi. Commands that take a stack get `--stack <env>`
added automatically, and `up` or `preview` create the stack on
first run, with `awskms` as the secrets provider on real
environments.

Anything pj does not recognize is passed through untouched: `pj
<pulumi args>` behaves like `pulumi <pulumi args>` with the
environment wired up.

## Usage

```
$ cd my-project/infrastructure/pulumi/api
$ swaj --profile=qa exec pj up
```

pj logs into `s3://pulumi-state-qa.acme.io`, selects stack `qa`,
and runs the update. `pj` with no arguments or `--help` prints
Pulumi's usage and works from any directory.

## Development

```
uv sync
uv run pytest
```
