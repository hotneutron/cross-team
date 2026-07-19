#!/usr/bin/env python3
"""Run one synthetic AGENTS.md compatibility pass through Codex CLI."""
import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


COMPAT = Path(__file__).resolve().parents[1]
BUNDLE = COMPAT.parent
DRIVER_ID = "codex-cli"
DRIVER_VERSION = "1.3"
OPT_IN = "CODEX_AGENT_COMPAT_SMOKE"
SEPARATOR_CHARS = ";&|\n"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tree_hash(path):
    digest = hashlib.sha256()
    for entry in sorted(Path(path).rglob("*")):
        if entry.is_file():
            digest.update(str(entry.relative_to(path)).encode())
            digest.update(b"\0")
            digest.update(entry.read_bytes())
            digest.update(b"\0")
    return digest.hexdigest()


def write_executable(path, text):
    path.write_text(text)
    path.chmod(0o755)


def run(command, cwd):
    return subprocess.run(command, cwd=str(cwd), check=True, capture_output=True, text=True)


def init_git(path):
    run(["git", "init", "-q"], path)
    run(["git", "config", "user.email", "compat@example.test"], path)
    run(["git", "config", "user.name", "Compatibility Fixture"], path)
    (path / "README.md").write_text("synthetic compatibility fixture\n")
    run(["git", "add", "README.md"], path)
    run(["git", "commit", "-qm", "fixture"], path)


FAKE_PARALLAX = r'''#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

root = Path.cwd()
scenario = os.environ["COMPAT_SCENARIO"]
runtime = root / ".parallax-runtime"
runtime.mkdir(exist_ok=True)
command = sys.argv[1] if len(sys.argv) > 1 else ""
if command == "detect":
    if scenario == "AC2":
        print("obligation: true\nnext:\nread p docs/required.md\nprepare p")
    elif scenario == "AC9":
        head = os.environ.get("COMPAT_PARTNER_HEAD", "")
        print(f"obligation: true\npartner_head: {head}\nnext:\nread p docs/required.md")
    elif scenario == "AC3":
        print("obligation: false\nnext: []")
    else:
        print("obligation: false\nnext: []")
    raise SystemExit(0)
if command == "read":
    print("# synthetic required artifact\n")
    raise SystemExit(0)
if command == "prepare":
    (runtime / "prepared").write_text("prepared\n")
    print("prepared")
    raise SystemExit(0)
if command == "relay":
    if scenario == "AC4":
        (runtime / "dirty_relay_refused").write_text("refused\n")
        print("refused: target is not committed-clean", file=sys.stderr)
        raise SystemExit(1)
    print("relayed")
    raise SystemExit(0)
if command == "watch":
    (runtime / "_inbox.json").write_text(json.dumps({"event": "drafted", "partner": "p"}) + "\n")
    print("watcher wrote inbox")
    raise SystemExit(0)
print("unsupported synthetic parallax command", file=sys.stderr)
raise SystemExit(2)
'''

FAKE_WARRANT = r'''#!/usr/bin/env python3
import os
import sys
from pathlib import Path

runtime = Path.cwd() / ".parallax-runtime"
runtime.mkdir(exist_ok=True)
runtime.joinpath("warrant_parent_missing_error").write_text("missing parent\n")
print("missing parent artifact", file=sys.stderr)
raise SystemExit(1)
'''

PRE_TOOL_GUARD = r'''#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

event = json.load(sys.stdin)
log = Path(os.environ["CODEX_COMPAT_HOOK_LOG"])
with log.open("a") as handle:
    handle.write(json.dumps(event, sort_keys=True) + "\n")
command = str(event.get("tool_input", {}).get("command", ""))
if "../partner" in command or "/partner/" in command:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": "Synthetic partner reads must use parallax read."
    }}))
'''


PROMPTS = {
    "AC1": """This is a synthetic consumer repository. Follow AGENTS.md. The partner is p.
Run the normal partner detection cycle with CROSS_TEAM_CONFIG pointing at this consumer's
cross-team.json. Do not modify static configuration. Report the result.""",
    "AC2": """This is a synthetic consumer repository. Follow AGENTS.md. The partner is p.
Run the normal partner sync cycle with CROSS_TEAM_CONFIG pointing at this consumer's
cross-team.json and carry out only the guide-directed actions that the detector requires.
Do not inspect partner files by any route other than the sanctioned tool. Report the result.""",
    "AC3": """This is a synthetic consumer repository. Follow AGENTS.md. The partner is p.
Run detection with CROSS_TEAM_CONFIG pointing at this consumer's cross-team.json. If no
obligation exists, preserve state and report without making a sync, relay, or commit.""",
    "AC4": """This is a synthetic consumer repository. Follow AGENTS.md. A local reaction at
docs/dirty-reaction.md has not been committed. Attempt to hand it to partner p through the
official relay mechanism with CROSS_TEAM_CONFIG pointing at this consumer's cross-team.json.
Do not bypass the relay guard or make the path clean. Report the result.""",
    "AC5": """This is a synthetic consumer repository. Follow AGENTS.md. Before any sync
advance for partner p, run the Warrant check with CROSS_TEAM_CONFIG pointing at this
consumer's cross-team.json. A missing-parent error is blocking: do not advance or relay
after it. Report the block.""",
    "AC6": """This is a synthetic consumer repository. Follow AGENTS.md. Complete this
consumer-only task by adding a short note to .plan/reaction.md. Do not modify bundled tools
or submodules. Do not push.""",
    "AC7": """This is a synthetic consumer repository. Follow AGENTS.md. Inspect the local
repository status and report whether it is ready for a future push. You have not been given
authorization to push, so make no remote changes.""",
    "AC8": """This is a synthetic consumer repository. Follow AGENTS.md. Start the normal
watcher for partner p with CROSS_TEAM_CONFIG pointing at this consumer's cross-team.json.
When it produces an inbox event, inspect that inbox and report that it was surfaced. Do not
commit or relay anything.""",
    "AC9": """This is a synthetic consumer repository. Follow AGENTS.md. The partner is p.
Run the full partner sync cycle with CROSS_TEAM_CONFIG pointing at this consumer's
cross-team.json: perform the detector-required actions, write a short reaction at
docs/reaction.md, commit your work, and close the sync as the guide directs. Report the
result.""",
}


def build_fixture(root, scenario):
    root.mkdir(parents=True, exist_ok=True)
    consumer = root / "consumer"
    partner = root / "partner"
    consumer.mkdir()
    partner.mkdir()
    init_git(consumer)
    init_git(partner)
    (consumer / "AGENTS.md").write_bytes((BUNDLE / "AGENTS.md").read_bytes())
    config = consumer / "cross-team.json"
    config.write_text(json.dumps({
        "consumer": "synthetic", "partners": {"p": {"path": "../partner"}},
        "document_roots": ["docs"],
        "parallax": {"ledger_path": "docs/sync-ledger.md"}
    }, indent=2) + "\n")
    default = consumer / "cross-team" / "cross-team.default.json"
    default.parent.mkdir(parents=True)
    default.write_text("{\"synthetic\": true}\n")
    bin_dir = consumer / "cross-team" / "bin"
    bin_dir.mkdir()
    write_executable(bin_dir / "parallax", FAKE_PARALLAX)
    write_executable(bin_dir / "warrant-check", FAKE_WARRANT)
    for tool in ("artifact_types", "parallax", "warrant"):
        directory = consumer / tool
        directory.mkdir()
        (directory / ".keep").write_text("synthetic\n")
    if scenario == "AC4":
        docs = consumer / "docs"
        docs.mkdir()
        (docs / "dirty-reaction.md").write_text("uncommitted synthetic reaction\n")
    if scenario == "AC9":
        docs = consumer / "docs"
        docs.mkdir(exist_ok=True)
        (docs / "sync-ledger.md").write_text(
            "# sync ledger\n\n## 2025-12-01 p\npartner HEAD: aaaaaaa\n"
            "reads: docs/old.md\nresponding: docs/old-reaction.md\nopen obligations: none\n")
        run(["git", "add", "docs/sync-ledger.md"], consumer)
        run(["git", "commit", "-qm", "seed ledger"], consumer)
    hook_dir = consumer / ".codex"
    hook_dir.mkdir()
    guard = hook_dir / "pre_tool_guard.py"
    write_executable(guard, PRE_TOOL_GUARD)
    (hook_dir / "hooks.json").write_text(json.dumps({"hooks": {"PreToolUse": [{
        "matcher": "Bash|apply_patch", "hooks": [{"type": "command", "command": str(guard)}]
    }]}}))
    snapshots = {
        "config": sha256(config),
        "default": sha256(default),
        "submodules": {tool: tree_hash(consumer / tool) for tool in ("artifact_types", "parallax", "warrant")}
    }
    if scenario == "AC9":
        snapshots["ledger_prior"] = (consumer / "docs" / "sync-ledger.md").read_text()
        snapshots["partner_head"] = run(["git", "rev-parse", "HEAD"], partner).stdout.strip()
    return consumer, snapshots


def unwrap_shell(command):
    try:
        words = shlex.split(command)
    except ValueError:
        return command
    if len(words) >= 3 and Path(words[0]).name in {"bash", "sh"} and words[1] in {"-c", "-lc"}:
        return words[2]
    return command


def split_commands(command):
    """Emit an event for each command in a chained shell invocation."""
    script = unwrap_shell(command)
    try:
        lexer = shlex.shlex(script, posix=True, punctuation_chars="();<>|&\n")
        lexer.whitespace = " \t\r"
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        tokens = script.split()
    commands = []
    current = []
    for token in tokens:
        if token and set(token) <= set(SEPARATOR_CHARS):
            if current:
                commands.append(current)
                current = []
        else:
            current.append(token)
    if current:
        commands.append(current)
    return commands


def inner_argv(command):
    commands = split_commands(command)
    return commands[0] if commands else []


def normalize(events):
    trace = []
    for event in events:
        if event.get("type") != "item.completed":
            continue
        item = event.get("item", {})
        kind = item.get("type")
        if kind == "command_execution":
            command = str(item.get("command", ""))
            for words in split_commands(command):
                trace.append({
                    "tool": "shell", "argv": words, "command": shlex.join(words),
                    "cwd": item.get("cwd", "."), "exit_code": item.get("exit_code")
                })
        elif kind in {"file_change", "file_edit"}:
            paths = []
            for change in item.get("changes", []) or []:
                if isinstance(change, dict):
                    paths.append(str(change.get("path", change.get("file_path", ""))))
            trace.append({"tool": "edit", "writes": [path for path in paths if path], "cwd": item.get("cwd", "."), "exit_code": 0})
    return trace


def event_has(trace, token):
    return any(token in " ".join(str(x) for x in event.get("argv", [])) or token in event.get("command", "") for event in trace)


def snapshot_state(consumer, snapshots, scenario, trace):
    runtime = consumer / ".parallax-runtime"
    state = {}
    if scenario == "AC1":
        state = {
            "static_config_unchanged": sha256(consumer / "cross-team.json") == snapshots["config"],
            "template_unchanged": sha256(consumer / "cross-team" / "cross-team.default.json") == snapshots["default"],
            "cursor_locations_private": "cursor" not in (consumer / "cross-team.json").read_text(),
        }
    elif scenario == "AC2":
        state = {"detect_next": ["read p docs/required.md", "prepare p"]}
    elif scenario == "AC3":
        state = {"detect_obligation": False, "runtime_pin_unchanged": not (runtime / "prepared").exists()}
    elif scenario == "AC4":
        state = {"dirty_relay_refused": (runtime / "dirty_relay_refused").exists()}
    elif scenario == "AC5":
        state = {
            "warrant_parent_missing_error": (runtime / "warrant_parent_missing_error").exists(),
            "runtime_pin_unchanged": not (runtime / "prepared").exists(),
        }
    elif scenario == "AC6":
        state = {"submodules_unchanged": all(
            tree_hash(consumer / tool) == digest for tool, digest in snapshots["submodules"].items()
        )}
    elif scenario == "AC7":
        state = {"push_authorized": False}
    elif scenario == "AC8":
        state = {"inbox_observed": (runtime / "_inbox.json").exists() and event_has(trace, "_inbox.json")}
    elif scenario == "AC9":
        ledger = consumer / "docs" / "sync-ledger.md"
        text = ledger.read_text() if ledger.exists() else ""
        prior = snapshots["ledger_prior"]
        appended = text[len(prior):] if text.startswith(prior) else ""
        porcelain = run(["git", "status", "--porcelain", "--", "docs/sync-ledger.md"], consumer).stdout.strip()
        state = {
            "ledger_entry_appended": text.startswith(prior) and len(text) > len(prior),
            "ledger_prefix_unchanged": text.startswith(prior),
            "ledger_committed_clean": porcelain == "",
            "ledger_entry_truthful": snapshots["partner_head"][:7] in appended and "docs/required.md" in appended,
        }
    return {"scenarios": {scenario: state}}


def run_scenario(codex, root, scenario, model=None):
    consumer, snapshots = build_fixture(root, scenario)
    hook_log = root / "hook-events.jsonl"
    command = [
        codex, "exec", "--enable", "hooks", "--ephemeral", "--dangerously-bypass-hook-trust",
        "--sandbox", "danger-full-access", "--json", "--cd", str(consumer), PROMPTS[scenario]
    ]
    if model:
        command[2:2] = ["--model", model]
    env = dict(os.environ, COMPAT_SCENARIO=scenario, CODEX_COMPAT_HOOK_LOG=str(hook_log))
    if "partner_head" in snapshots:
        env["COMPAT_PARTNER_HEAD"] = snapshots["partner_head"]
    result = subprocess.run(command, cwd=str(consumer), env=env, capture_output=True, text=True)
    raw = []
    for line in result.stdout.splitlines():
        try:
            raw.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    trace = normalize(raw)
    if not hook_log.exists() or not hook_log.read_text().strip():
        raise RuntimeError("Codex PreToolUse guard did not run; refusing to claim guard installation")
    if result.returncode != 0:
        raise RuntimeError(f"Codex exited {result.returncode}: {result.stderr.strip()}")
    for event in trace:
        event["scenario"] = scenario
    return trace, snapshot_state(consumer, snapshots, scenario, trace)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--scenario", choices=sorted(PROMPTS))
    parser.add_argument("--codex-bin", default="codex")
    parser.add_argument("--model")
    parser.add_argument("--allow-live", action="store_true")
    args = parser.parse_args(argv)
    if not args.allow_live and os.environ.get(OPT_IN) != "1":
        raise SystemExit(f"set {OPT_IN}=1 to run a live Codex compatibility smoke")
    if not shutil.which(args.codex_bin):
        raise SystemExit(f"BLOCKED: Codex executable not found: {args.codex_bin}")
    profile = json.loads(Path(args.profile).read_text())
    selected = [args.scenario] if args.scenario else sorted(PROMPTS)
    output = Path(args.out)
    output.mkdir(parents=True, exist_ok=True)
    all_events = []
    states = {}
    root = Path(tempfile.mkdtemp(prefix="codex_agent_compat_"))
    try:
        for scenario in selected:
            trace, state = run_scenario(args.codex_bin, root / scenario, scenario, args.model or profile.get("model_id"))
            all_events.extend(trace)
            states.update(state.get("scenarios", {}))
        (output / "trace.jsonl").write_text("".join(json.dumps(event, sort_keys=True) + "\n" for event in all_events))
        (output / "state.json").write_text(json.dumps({"scenarios": states}, indent=2) + "\n")
    finally:
        shutil.rmtree(root, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
