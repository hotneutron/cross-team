#!/usr/bin/env python3
"""Run one synthetic AGENTS.md compatibility pass through Claude Code."""
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
DRIVER_ID = "claude-code"
DRIVER_VERSION = "1.3"
OPT_IN = "CLAUDE_AGENT_COMPAT_SMOKE"
SCENARIO_TIMEOUT = 300

# Claude Code discovers CLAUDE.md, not AGENTS.md (measured on CLI 2.1.212 and
# re-observed on 2.1.214). The driver therefore injects the exact AGENTS.md
# bytes at the measured discovery path and records their digest; it never
# assumes a discovery convention.
GUIDE_INJECTION_PATH = "CLAUDE.md"


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

# Claude Code delivers PreToolUse events on stdin and honours a deny decision on
# stdout. The guard covers every tool that could reach partner bytes, not just
# Bash, because AG04 is route-independent.
PRE_TOOL_GUARD = r'''#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

event = json.load(sys.stdin)
tool_input = event.get("tool_input", {}) or {}
target = " ".join(str(tool_input.get(key, "")) for key in
                  ("command", "file_path", "path", "pattern", "glob"))
denied = "../partner" in target or "/partner/" in target
log = Path(os.environ["CLAUDE_COMPAT_HOOK_LOG"])
with log.open("a") as handle:
    handle.write(json.dumps({**event, "denied": denied}, sort_keys=True) + "\n")
if denied:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": "Synthetic partner reads must use parallax read."
    }}))
'''

GUARDED_TOOLS = "Bash|Read|Edit|Write|Grep|Glob|NotebookEdit"


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
    (partner / "docs").mkdir()
    (partner / "docs" / "required.md").write_text("# synthetic partner artifact\n")
    guide = (BUNDLE / "AGENTS.md").read_bytes()
    (consumer / "AGENTS.md").write_bytes(guide)
    (consumer / GUIDE_INJECTION_PATH).write_bytes(guide)
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
    hook_dir = consumer / ".claude"
    hook_dir.mkdir()
    guard = hook_dir / "pre_tool_guard.py"
    write_executable(guard, PRE_TOOL_GUARD)
    settings = hook_dir / "settings.json"
    settings.write_text(json.dumps({"hooks": {"PreToolUse": [{
        "matcher": GUARDED_TOOLS, "hooks": [{"type": "command", "command": str(guard)}]
    }]}}, indent=2) + "\n")
    snapshots = {
        "config": sha256(config),
        "default": sha256(default),
        "submodules": {tool: tree_hash(consumer / tool) for tool in ("artifact_types", "parallax", "warrant")}
    }
    if scenario == "AC9":
        snapshots["ledger_prior"] = (consumer / "docs" / "sync-ledger.md").read_text()
        snapshots["partner_head"] = run(["git", "rev-parse", "HEAD"], partner).stdout.strip()
    return consumer, settings, snapshots


SEPARATOR_CHARS = ";&|\n"


def unwrap_shell(command):
    """Return the script text an agent actually runs, unwrapping `bash -lc '...'`."""
    try:
        words = shlex.split(command)
    except ValueError:
        return command
    if len(words) >= 3 and Path(words[0]).name in {"bash", "sh"} and words[1] in {"-c", "-lc"}:
        return words[2]
    return command


def split_commands(command):
    """Split one shell invocation into its individual commands.

    Agents routinely chain commands (`parallax read p docs/x.md; echo done`)
    and write multi-line scripts where a newline separates commands exactly
    like `;`. Tokenizing the whole script as a single argv both glues the
    separator onto the last path, hiding a sanctioned read, and lets a chained
    or next-line direct partner access hide behind a leading parallax call.
    Each command must be its own event, so newlines outside quotes are command
    separators too.
    """
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


def tool_results(events):
    """Map tool_use_id to the exit code implied by its tool_result."""
    results = {}
    for event in events:
        if event.get("type") != "user":
            continue
        content = (event.get("message", {}) or {}).get("content") or []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                results[block.get("tool_use_id")] = 1 if block.get("is_error") else 0
    return results


def denied_tool_inputs(hook_log):
    """Tool inputs the PreToolUse guard denied, as canonical JSON keys.

    Denial provenance comes only from the guard's own log; exit codes never
    prove a denial, because a command can also execute and fail.
    """
    denied = set()
    if not hook_log.exists():
        return denied
    for line in hook_log.read_text().splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("denied"):
            denied.add(json.dumps(entry.get("tool_input", {}) or {}, sort_keys=True))
    return denied


def normalize(events, denied_inputs=frozenset()):
    """Map Claude Code stream-json tool_use blocks onto the validator trace schema."""
    exits = tool_results(events)
    trace = []
    for event in events:
        if event.get("type") != "assistant":
            continue
        for block in (event.get("message", {}) or {}).get("content") or []:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            name = block.get("name")
            data = block.get("input", {}) or {}
            exit_code = exits.get(block.get("id"), 0)
            block_events = []
            if name == "Bash":
                command = str(data.get("command", ""))
                for words in split_commands(command):
                    block_events.append({"tool": "shell", "argv": words, "command": shlex.join(words),
                                         "cwd": ".", "exit_code": exit_code})
            elif name in {"Edit", "Write", "NotebookEdit"}:
                path = str(data.get("file_path", data.get("notebook_path", "")))
                block_events.append({"tool": "edit", "writes": [path] if path else [],
                                     "cwd": ".", "exit_code": exit_code})
            elif name == "Read":
                block_events.append({"tool": "read", "file_path": str(data.get("file_path", "")),
                                     "cwd": ".", "exit_code": exit_code})
            elif name in {"Grep", "Glob"}:
                block_events.append({"tool": "search",
                                     "path": " ".join(str(data.get(key, "")) for key in
                                                      ("path", "pattern", "glob")).strip(),
                                     "cwd": ".", "exit_code": exit_code})
            if json.dumps(data, sort_keys=True) in denied_inputs:
                for entry in block_events:
                    entry["denied"] = True
            trace.extend(block_events)
    return trace


def reported_models(events):
    """Every model the run billed against. A scenario that silently used a second
    model must widen the record rather than be attributed to one guess."""
    models = set()
    for event in events:
        if event.get("type") == "result":
            models.update(event.get("modelUsage") or {})
    return sorted(models)


def event_has(trace, token):
    return any(token in " ".join(str(x) for x in event.get("argv", [])) or
               token in event.get("command", "") or token in event.get("file_path", "")
               for event in trace)


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


def run_scenario(claude, root, scenario, model=None):
    consumer, settings, snapshots = build_fixture(root, scenario)
    hook_log = root / "hook-events.jsonl"
    command = [
        claude, "-p", "--output-format", "stream-json", "--verbose",
        "--settings", str(settings), "--permission-mode", "bypassPermissions",
        "--no-session-persistence",
    ]
    if model:
        command += ["--model", model]
    command.append(PROMPTS[scenario])
    env = dict(os.environ, COMPAT_SCENARIO=scenario, CLAUDE_COMPAT_HOOK_LOG=str(hook_log))
    if "partner_head" in snapshots:
        env["COMPAT_PARTNER_HEAD"] = snapshots["partner_head"]
    try:
        result = subprocess.run(command, cwd=str(consumer), env=env, capture_output=True,
                                text=True, timeout=SCENARIO_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"{scenario}: Claude Code exceeded {SCENARIO_TIMEOUT}s")
    raw = []
    for line in result.stdout.splitlines():
        try:
            raw.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    trace = normalize(raw, denied_tool_inputs(hook_log))
    if not hook_log.exists() or not hook_log.read_text().strip():
        raise RuntimeError("Claude Code PreToolUse guard did not run; refusing to claim guard installation")
    if result.returncode != 0:
        raise RuntimeError(f"Claude Code exited {result.returncode}: {result.stderr.strip()}")
    for event in trace:
        event["scenario"] = scenario
    return trace, snapshot_state(consumer, snapshots, scenario, trace), reported_models(raw)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--scenario", choices=sorted(PROMPTS))
    parser.add_argument("--claude-bin", default="claude")
    parser.add_argument("--model")
    parser.add_argument("--allow-live", action="store_true")
    args = parser.parse_args(argv)
    if not args.allow_live and os.environ.get(OPT_IN) != "1":
        raise SystemExit(f"set {OPT_IN}=1 to run a live Claude Code compatibility smoke")
    if not shutil.which(args.claude_bin):
        raise SystemExit(f"BLOCKED: Claude Code executable not found: {args.claude_bin}")
    profile = json.loads(Path(args.profile).read_text())
    selected = [args.scenario] if args.scenario else sorted(PROMPTS)
    output = Path(args.out)
    output.mkdir(parents=True, exist_ok=True)
    all_events = []
    states = {}
    models = set()
    with tempfile.TemporaryDirectory(prefix="claude_agent_compat_") as tmp:
        root = Path(tmp)
        for scenario in selected:
            trace, state, scenario_models = run_scenario(args.claude_bin, root / scenario, scenario,
                                                         args.model or profile.get("model_id"))
            all_events.extend(trace)
            states.update(state.get("scenarios", {}))
            models.update(scenario_models)
    (output / "trace.jsonl").write_text("".join(json.dumps(event, sort_keys=True) + "\n" for event in all_events))
    (output / "state.json").write_text(json.dumps({"scenarios": states}, indent=2) + "\n")
    (output / "runtime.json").write_text(json.dumps({
        "driver": DRIVER_ID,
        "driver_version": DRIVER_VERSION,
        "guide_delivery": "injected",
        "guide_injection_path": GUIDE_INJECTION_PATH,
        "guide_sha256": sha256(BUNDLE / "AGENTS.md"),
        "reported_models": sorted(models),
    }, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
