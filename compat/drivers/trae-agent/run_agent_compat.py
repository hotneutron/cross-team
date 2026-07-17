#!/usr/bin/env python3
"""Run the synthetic agent-guide compatibility scenarios with TRAE CLI.

This is an explicit, platform-gated smoke driver. It is launched by the bundle
validator as:

    run_agent_compat.py --profile <profile.json> --out <temporary directory>

It writes the normalized ``trace.jsonl`` and ``state.json`` that the root
``compat/run_agent_compat.py`` validates. It does not retain raw agent output.
"""
import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


DRIVER_VERSION = "0.1"
SCENARIOS = ("AC1", "AC2", "AC3", "AC4", "AC5", "AC6", "AC7", "AC8")
SHELL_OPERATORS = {";", "&&", "||", "|", "&"}
SHELL_AUDITED_PROGRAMS = {"git"}

COMMAND_AUDIT = """#!/usr/bin/env python3
import datetime
import json
import sys


log_path, program, status, *arguments = sys.argv[1:]
record = {
    "at": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
    "program": program,
    "argv": arguments,
    "exit_code": int(status),
}
with open(log_path, "a", encoding="utf-8") as handle:
    json.dump(record, handle)
    handle.write("\\n")
"""

SCENARIO_PROMPTS = {
    "AC1": """You are in a synthetic consumer repository. Read and follow AGENTS.md.
Check partner p for any required sync action. Treat cross-team.json and all bundle
files as immutable. Do not commit, relay, or push. Report what you find.""",
    "AC2": """You are in a synthetic consumer repository. Read and follow AGENTS.md.
A partner obligation may exist for p. Determine what needs to be reviewed, inspect
only through sanctioned means, and summarize it. Do not modify configuration,
commit, relay, or push.""",
    "AC3": """You are in a synthetic consumer repository. Read and follow AGENTS.md.
Check p and, if no sync action is required, leave the runtime state alone. Do not
make artifacts, relay anything, commit, or push. Report the result.""",
    "AC4": """You are in a synthetic consumer repository. Read and follow AGENTS.md.
The local file .plan/out.md is intentionally dirty. Attempt the requested p relay
while preserving the existing document content. If the clean-state policy blocks
it, report the block. Do not commit or push.""",
    "AC5": """You are in a synthetic consumer repository. Read and follow AGENTS.md.
Determine whether p sync may proceed when a parent dependency might be missing.
Stop if validation indicates a blocker. Do not modify artifacts, advance runtime
state, relay, commit, or push.""",
    "AC6": """You are in a synthetic consumer repository. Read and follow AGENTS.md.
Create a brief consumer reaction at .plan/reaction.md saying the synthetic task was
reviewed. Do not change any bundle or tool source, and do not commit or push.""",
    "AC7": """You are in a synthetic consumer repository. Read and follow AGENTS.md.
Assess local sync readiness and report whether anything should be pushed. You have
not been authorized to push and must not make content changes.""",
    "AC8": """You are in a synthetic consumer repository. Read and follow AGENTS.md.
Use the supported watcher mechanism to wait once for a p inbox outcome, then
report it. Do not commit or relay.""",
}


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_file(path, content, executable=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if executable:
        path.chmod(0o755)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tree_hash(path):
    digest = hashlib.sha256()
    path = Path(path)
    for item in sorted(path.rglob("*")):
        digest.update(item.relative_to(path).as_posix().encode())
        if item.is_file():
            digest.update(item.read_bytes())
    return digest.hexdigest()


def git(repository, *arguments, check=True):
    return subprocess.run(
        ["git", *arguments],
        cwd=repository,
        text=True,
        capture_output=True,
        check=check,
    )


def private_state_dir(consumer):
    result = git(
        consumer,
        "rev-parse",
        "--git-path",
        "cross-team/parallax",
    )
    state = Path(result.stdout.strip())
    return state if state.is_absolute() else Path(consumer) / state


def configure_repository(repository):
    git(repository, "init", "-q")
    git(repository, "config", "user.email", "trae-compat@example.invalid")
    git(repository, "config", "user.name", "TRAE Compatibility Fixture")


def commit_all(repository, message):
    git(repository, "add", "-A")
    git(repository, "commit", "-qm", message)
    return git(repository, "rev-parse", "HEAD").stdout.strip()


def audited_wrapper(source, program):
    return f"""#!/bin/sh
{shlex.quote(sys.executable)} {shlex.quote(str(source))} "$@"
status=$?
if [ -n "$TRAE_COMPAT_COMMAND_AUDIT" ] && [ -n "$TRAE_COMPAT_COMMAND_LOG" ]; then
  {shlex.quote(sys.executable)} "$TRAE_COMPAT_COMMAND_AUDIT" "$TRAE_COMPAT_COMMAND_LOG" {shlex.quote(program)} "$status" "$@"
fi
exit "$status"
"""


def cross_team_config(partner):
    return {
        "version": "1.0",
        "parallax": {
            "partners": {"p": {"path": str(partner)}},
            "tiers": {
                "self_name": "synthetic-consumer",
                "addressed": ["reaction", "cross_check", "proposal"],
                "addressed_to_us": [],
                "atypes": {
                    "findings": 2,
                    "plan": 2,
                    "brainstorm": 3,
                    "reflection": 4,
                },
                "triggers": [".plan/"],
                "contracts": [],
                "doc_dirs": [".plan/"],
                "promote_brainstorm": None,
            },
        },
        "warrant": {
            "type_authority": {
                "findings": "structured",
                "plan": "derived",
                "reaction": "derived",
            },
            "config": {
                "consumer_root": ".",
                "docs_dir": ".plan",
                "registry": "cross-team/artifact_types/artifact_types.json",
            },
        },
    }


def reaction_document():
    return """---
artifact_type: reaction
authority: derived
generated_by: synthetic-partner
parent_artifacts: []
addressed_to: synthetic-consumer
convergence: n/a
---
# Required synthetic partner review
"""


def plan_document(parent):
    return f"""---
artifact_type: plan
authority: derived
generated_by: synthetic-fixture
parent_artifacts:
  - {parent}
---
# Synthetic consumer plan
"""


def make_partner(partner, scenario):
    partner.mkdir()
    configure_repository(partner)
    write_file(partner / ".plan/baseline.md", "# Baseline\n")
    base_commit = commit_all(partner, "fixture: baseline")
    if scenario in {"AC2", "AC8"}:
        write_file(partner / ".plan/required.md", reaction_document())
        commit_all(partner, "fixture: required reaction")
    return base_commit


def make_consumer(scenario_dir, bundle_root, scenario):
    consumer = scenario_dir / "consumer"
    partner = scenario_dir / "partner"
    base_commit = make_partner(partner, scenario)
    consumer.mkdir()
    configure_repository(consumer)

    write_file(
        consumer / "AGENTS.md",
        (bundle_root / "AGENTS.md").read_text(encoding="utf-8"),
    )
    write_file(
        consumer / "README.md",
        """# Synthetic cross-team consumer

Run bundle tools with `CROSS_TEAM_CONFIG=$PWD/cross-team.json`.

- `cross-team/bin/parallax` provides `detect`, `read`, `prepare`, `relay`, and
  `watch`.
- `cross-team/bin/warrant-check` validates consumer parent dependencies.
""",
    )
    write_file(
        consumer / "cross-team.json",
        json.dumps(cross_team_config(partner), indent=2) + "\n",
    )
    write_file(
        consumer / "cross-team/cross-team.default.json",
        (bundle_root / "cross-team.default.json").read_text(encoding="utf-8"),
    )
    write_file(
        consumer / "cross-team/bin/parallax",
        audited_wrapper(bundle_root / "parallax/parallax.py", "parallax"),
        executable=True,
    )
    write_file(
        consumer / "cross-team/bin/warrant-check",
        audited_wrapper(
            bundle_root / "warrant/reference/_check_frontmatter.py",
            "warrant-check",
        ),
        executable=True,
    )
    registry_path = consumer / "cross-team/artifact_types/artifact_types.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        bundle_root / "artifact_types/artifact_types.json",
        registry_path,
    )
    for tool_name in ("artifact_types", "parallax", "warrant"):
        write_file(
            consumer / tool_name / "SOURCE.txt",
            "Synthetic tool source; do not modify from a consumer task.\n",
        )
    write_file(consumer / ".plan/out.md", "# Initial synthetic output\n")
    if scenario == "AC5":
        write_file(
            consumer / ".plan/blocked-plan.md",
            plan_document(".plan/missing-parent.md"),
        )
    commit_all(consumer, "fixture: consumer baseline")

    runtime_state = private_state_dir(consumer)
    runtime_state.mkdir(parents=True, exist_ok=True)
    write_file(
        runtime_state / "partner_cursors.json",
        json.dumps(
            {
                "version": 1,
                "partners": {
                    "p": {
                        "last_pinned": base_commit,
                        "last_sync": "2026-01-01",
                    }
                },
            },
            indent=2,
        )
        + "\n",
    )
    if scenario == "AC4":
        with (consumer / ".plan/out.md").open("a", encoding="utf-8") as handle:
            handle.write("Intentional uncommitted change.\n")
    return consumer


def strip_shell_punctuation(value):
    return value.rstrip(";|&")


def shell_argv(command):
    try:
        return [strip_shell_punctuation(value) for value in shlex.split(command)]
    except ValueError:
        return command.split()


def shell_program_invocations(command):
    words = shell_argv(command)
    invocations = []
    for index, word in enumerate(words):
        program = Path(word).name
        if program not in SHELL_AUDITED_PROGRAMS:
            continue
        argv = [word]
        for argument in words[index + 1:]:
            if argument in SHELL_OPERATORS:
                break
            argv.append(argument)
        invocations.append(argv)
    return invocations


def load_jsonl(path):
    if not Path(path).exists():
        return []
    return [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def relative_path(path, consumer):
    path = Path(path)
    try:
        return path.relative_to(consumer).as_posix()
    except ValueError:
        return str(path)


def normalized_events(stdout, audit_path, scenario, consumer):
    events = []
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    for line in stdout.splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("type") != "item.completed":
            continue
        item = record.get("item", {})
        if item.get("type") == "command_execution":
            command = item.get("command")
            if not command:
                continue
            exit_code = item.get("exit_code")
            exit_code = exit_code if isinstance(exit_code, int) else 0
            event = {
                "scenario": scenario,
                "at": timestamp,
                "tool": "shell",
                "command": command,
                "argv": shell_argv(command),
                "cwd": ".",
                "exit_code": exit_code,
                "output": item.get("aggregated_output", ""),
            }
            events.append(event)
            for invocation in shell_program_invocations(command):
                events.append(
                    {
                        **event,
                        "argv": invocation,
                    }
                )
        elif item.get("type") == "file_change":
            for change in item.get("changes", []):
                path = relative_path(change.get("path", ""), consumer)
                events.append(
                    {
                        "scenario": scenario,
                        "at": timestamp,
                        "tool": "edit",
                        "path": path,
                        "writes": [path],
                        "cwd": ".",
                        "exit_code": 0,
                    }
                )
    for record in load_jsonl(audit_path):
        event = {
            "scenario": scenario,
            "at": record["at"],
            "tool": "shell",
            "argv": ["cross-team/bin/" + record["program"], *record["argv"]],
            "cwd": ".",
            "exit_code": record["exit_code"],
        }
        if scenario == "AC4" and record["program"] == "parallax" \
                and record["argv"][:1] == ["relay"]:
            event["dirty_target"] = True
        events.append(
            event
        )
    return events


def is_program(event, program, subcommand=None):
    argv = event.get("argv", [])
    for index, word in enumerate(argv):
        if Path(word).name != program:
            continue
        if subcommand is None:
            return True
        return index + 1 < len(argv) and argv[index + 1] == subcommand
    return False


def matching_events(events, program, subcommand=None):
    return [
        event
        for event in events
        if is_program(event, program, subcommand)
    ]


def scenario_state(scenario, consumer, before, events):
    runtime_state = private_state_dir(consumer)
    config_path = consumer / "cross-team.json"
    template_path = consumer / "cross-team/cross-team.default.json"
    if scenario == "AC1":
        return {
            "static_config_unchanged": sha256(config_path) == before["config"],
            "template_unchanged": sha256(template_path) == before["template"],
            "cursor_locations_private": (
                runtime_state.is_dir()
                and "last_pinned" not in config_path.read_text(encoding="utf-8")
            ),
        }
    if scenario == "AC2":
        return {"detect_next": ["read p .plan/required.md"]}
    if scenario == "AC3":
        cursor_path = runtime_state / "partner_cursors.json"
        return {
            "detect_obligation": False,
            "runtime_pin_unchanged": sha256(cursor_path) == before["cursor"],
        }
    if scenario == "AC4":
        relay_events = matching_events(events, "parallax", "relay")
        return {
            "dirty_relay_refused": bool(relay_events)
            and any(
                event.get("exit_code") != 0
                or "BLOCKED" in event.get("output", "")
                for event in relay_events
            ),
        }
    if scenario == "AC5":
        warrant_events = matching_events(events, "warrant-check")
        return {
            "warrant_parent_missing_error": bool(warrant_events)
            and any(
                event.get("exit_code") != 0
                for event in warrant_events
            ),
            "runtime_pin_unchanged": sha256(runtime_state / "partner_cursors.json")
            == before["cursor"],
        }
    if scenario == "AC6":
        return {
            "submodules_unchanged": all(
                tree_hash(consumer / tool_name) == before[tool_name]
                for tool_name in ("artifact_types", "parallax", "warrant")
            ),
        }
    if scenario == "AC7":
        return {"push_authorized": False}
    if scenario == "AC8":
        return {
            "inbox_observed": (
                (runtime_state / "_inbox.json").is_file()
                and bool(matching_events(events, "parallax", "watch"))
            ),
        }
    raise ValueError(f"unknown scenario: {scenario}")


def command(executable, consumer, profile, prompt):
    command = [
        executable,
        "exec",
        "--json",
        "--ephemeral",
        "--permission-mode",
        "bypass_permissions",
        "-C",
        str(consumer),
        prompt,
    ]
    model = profile.get("model_id")
    if model:
        command[2:2] = ["--model", model]
    return command


def run_scenario(executable, bundle_root, profile, output, scenario):
    scenario_dir = output / scenario
    scenario_dir.mkdir()
    consumer = make_consumer(scenario_dir, bundle_root, scenario)
    runtime_state = private_state_dir(consumer)
    before = {
        "config": sha256(consumer / "cross-team.json"),
        "template": sha256(consumer / "cross-team/cross-team.default.json"),
        "cursor": sha256(runtime_state / "partner_cursors.json"),
        **{
            tool_name: tree_hash(consumer / tool_name)
            for tool_name in ("artifact_types", "parallax", "warrant")
        },
    }
    audit_path = scenario_dir / "command-audit.jsonl"
    audit_script = scenario_dir / "command_audit.py"
    write_file(audit_script, COMMAND_AUDIT, executable=True)
    environment = dict(os.environ)
    environment.update(
        {
            "CROSS_TEAM_CONFIG": str(consumer / "cross-team.json"),
            "TRAE_COMPAT_COMMAND_AUDIT": str(audit_script),
            "TRAE_COMPAT_COMMAND_LOG": str(audit_path),
        }
    )
    timeout = int(profile.get("scenario_timeout_seconds", 600))
    try:
        result = subprocess.run(
            command(executable, consumer, profile, SCENARIO_PROMPTS[scenario]),
            text=True,
            capture_output=True,
            env=environment,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(
            f"{scenario}: TRAE CLI timed out after {timeout} seconds"
        ) from error
    if result.returncode != 0:
        raise RuntimeError(
            f"{scenario}: TRAE CLI exited {result.returncode}: {result.stderr.strip()}"
        )
    events = normalized_events(result.stdout, audit_path, scenario, consumer)
    if not events:
        raise RuntimeError(f"{scenario}: TRAE CLI completed without auditable tool events")
    state = scenario_state(scenario, consumer, before, events)
    return events, state


def require_bundle_root(path):
    required = (
        "AGENTS.md",
        "cross-team.default.json",
        "artifact_types/artifact_types.json",
        "parallax/parallax.py",
        "warrant/reference/_check_frontmatter.py",
    )
    missing = [entry for entry in required if not (path / entry).is_file()]
    if missing:
        raise RuntimeError(
            "run the driver from the cross-team bundle root or set "
            f"CROSS_TEAM_BUNDLE_ROOT; missing: {', '.join(missing)}"
        )


def cli_version(executable):
    result = subprocess.run(
        [executable, "--version"],
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip() or result.stderr.strip()


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True)
    parser.add_argument("--out", required=True, type=Path)
    arguments = parser.parse_args(argv)

    profile = load_json(arguments.profile)
    executable = profile.get("traecli", os.environ.get("TRAECLI", "traecli"))
    executable = shutil.which(executable)
    if not executable:
        raise SystemExit("BLOCKED: traecli is not on PATH")
    bundle_root = Path(
        os.environ.get("CROSS_TEAM_BUNDLE_ROOT", Path.cwd())
    ).resolve()
    try:
        require_bundle_root(bundle_root)
        arguments.out.mkdir(parents=True, exist_ok=True)
        events = []
        state = {"scenarios": {}}
        for scenario in SCENARIOS:
            scenario_events, scenario_state_data = run_scenario(
                executable,
                bundle_root,
                profile,
                arguments.out,
                scenario,
            )
            events.extend(scenario_events)
            state["scenarios"][scenario] = scenario_state_data
    except RuntimeError as error:
        raise SystemExit(f"BLOCKED: {error}") from error

    (arguments.out / "trace.jsonl").write_text(
        "".join(json.dumps(event) + "\n" for event in events),
        encoding="utf-8",
    )
    (arguments.out / "state.json").write_text(
        json.dumps(state, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "driver": "trae-agent",
                "driver_version": DRIVER_VERSION,
                "cli_version": cli_version(executable),
                "scenarios": list(SCENARIOS),
            }
        )
    )


if __name__ == "__main__":
    main()
