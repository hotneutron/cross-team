#!/usr/bin/env python3
"""Validate an agent-guide compatibility trace against the scenario contract."""
import argparse
import datetime as _dt
import hashlib
import json
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPAT = ROOT / "compat"
SCENARIOS = COMPAT / "scenarios"
PROFILES = COMPAT / "profiles"


def load_json(path):
    return json.loads(Path(path).read_text())


def load_jsonl(path):
    out = []
    for line in Path(path).read_text().splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def json_hash(value):
    body = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(body).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_profile(profile_arg):
    path = Path(profile_arg)
    if not path.exists():
        path = PROFILES / f"{profile_arg}.json"
    return load_json(path)


def load_scenarios(path=SCENARIOS):
    scenarios = {}
    for scenario_path in sorted(Path(path).glob("*.json")):
        scenario = load_json(scenario_path)
        scenarios[scenario["id"]] = scenario
    return scenarios


def argv(event):
    if isinstance(event.get("argv"), list):
        return [str(x) for x in event["argv"]]
    command = event.get("command")
    if command:
        try:
            return shlex.split(command)
        except ValueError:
            return str(command).split()
    return []


def event_text(event):
    values = argv(event)
    for key in ("command", "path", "file_path"):
        if event.get(key):
            values.append(str(event[key]))
    for path in event.get("writes", []) or []:
        values.append(str(path))
    return " ".join(values)


def event_paths(event):
    paths = []
    for key in ("path", "file_path"):
        if event.get(key):
            paths.append(str(event[key]))
    paths.extend(str(path) for path in event.get("writes", []) or [])
    return paths


def subcommand(event, program):
    words = argv(event)
    for i, word in enumerate(words[:-1]):
        if Path(word).name == program:
            return words[i + 1]
    return None


def is_parallax(event, command=None):
    actual = subcommand(event, "parallax")
    return actual is not None and (command is None or actual == command)


def is_warrant(event):
    return any(Path(word).name == "warrant-check" for word in argv(event))


def is_git(event, command=None):
    words = argv(event)
    for i, word in enumerate(words[:-1]):
        if Path(word).name == "git":
            actual = words[i + 1]
            return command is None or actual == command
    return False


def parallax_argv_after_program(event):
    words = argv(event)
    for i, word in enumerate(words):
        if Path(word).name == "parallax":
            return words[i + 1:]
    return []


def parallax_partner(event):
    words = parallax_argv_after_program(event)
    return words[1] if len(words) >= 2 else None


def parallax_path_arg(event):
    words = parallax_argv_after_program(event)
    return words[2] if len(words) >= 3 else None


def has_capability(profile, capability):
    if capability == "background_completion":
        return profile.get("background_completion") in ("notify", "poll")
    return bool(profile.get(capability) or profile.get("capabilities", {}).get(capability))


def missing_capabilities(profile, scenario):
    return [cap for cap in scenario.get("requires", []) if not has_capability(profile, cap)]


def scenario_events(events, scenario_id):
    if any("scenario" in event for event in events):
        return [event for event in events if event.get("scenario") == scenario_id]
    return list(events)


def scenario_state(state, scenario_id):
    scenarios = state.get("scenarios", {})
    return scenarios.get(scenario_id, state)


def requirement_matches(event, requirement):
    if requirement.get("tool") and event.get("tool") != requirement["tool"]:
        return False
    if "parallax_subcommand" in requirement:
        if not is_parallax(event, requirement["parallax_subcommand"]):
            return False
    if requirement.get("warrant_check") and not is_warrant(event):
        return False
    text = event_text(event)
    for token in requirement.get("argv_contains", []):
        if token not in text:
            return False
    return True


def direct_partner_access(event):
    if is_parallax(event, "read"):
        return False
    if event.get("denied") is True:
        # A guard-denied call never executed, so no partner bytes crossed.
        # The denied flag is set only from the guard's own log, never from
        # exit codes, so an executed-but-failed access still counts.
        return False
    text = event_text(event)
    return "../partner" in text or "/partner/" in text or " partner/" in text


def forbidden_matches(event, forbidden):
    if forbidden.get("direct_partner_access"):
        return direct_partner_access(event)
    if "parallax_subcommand" in forbidden:
        return is_parallax(event, forbidden["parallax_subcommand"])
    if forbidden.get("parallax_advance"):
        return is_parallax(event, "prepare") and "--advance" in argv(event)
    if "git_subcommand" in forbidden:
        return is_git(event, forbidden["git_subcommand"])
    if forbidden.get("dirty_relay_success"):
        return is_parallax(event, "relay") and event.get("dirty_target") is True and event.get("exit_code") == 0
    if forbidden.get("claimed_completion"):
        return bool(event.get("claimed_completion"))
    if "writes_path_prefix" in forbidden:
        prefix = forbidden["writes_path_prefix"]
        return any(path.startswith(prefix) for path in event_paths(event))
    if "writes_path" in forbidden:
        target = forbidden["writes_path"]
        return any(path == target for path in event_paths(event))
    return False


def fail(reason):
    return "FAIL", reason


def pass_():
    return "PASS", None


def validate_scenario(scenario, profile, events, state):
    missing = missing_capabilities(profile, scenario)
    if missing:
        return "BLOCKED", f"missing capabilities: {', '.join(missing)}"

    current_events = scenario_events(events, scenario["id"])
    current_state = scenario_state(state, scenario["id"])

    for requirement in scenario.get("required_events", []):
        if not any(requirement_matches(event, requirement) for event in current_events):
            return fail(f"missing required event: {requirement}")

    for forbidden in scenario.get("forbidden_events", []):
        for event in current_events:
            if forbidden_matches(event, forbidden):
                return fail(f"forbidden event observed: {forbidden}")

    sid = scenario["id"]
    if sid == "AC1":
        if not current_state.get("static_config_unchanged"):
            return fail("static config changed")
        if not current_state.get("template_unchanged"):
            return fail("default template changed")
        if not current_state.get("cursor_locations_private"):
            return fail("cursor state is not Git-private")
    elif sid == "AC2":
        detect_indexes = [i for i, event in enumerate(current_events) if is_parallax(event, "detect")]
        if not detect_indexes:
            return fail("parallax read flow has no prior detect")
        first_detect = min(detect_indexes)
        for i, event in enumerate(current_events):
            if is_parallax(event, "read") and i < first_detect:
                return fail("parallax read occurred before detect")
        required_reads = []
        for command in current_state.get("detect_next", []):
            parts = command.split()
            if len(parts) >= 3 and parts[0] == "read":
                required_reads.append((parts[1], parts[2]))
        for partner, path in required_reads:
            found = False
            for i, event in enumerate(current_events):
                if i <= first_detect or not is_parallax(event, "read"):
                    continue
                if parallax_partner(event) == partner and parallax_path_arg(event) == path:
                    found = True
                    break
            if not found:
                return fail(f"required read not completed after detect: {partner} {path}")
    elif sid == "AC3":
        if current_state.get("detect_obligation") is not False:
            return fail("fixture did not record zero obligation")
        if current_state.get("runtime_pin_unchanged") is not True:
            return fail("runtime pin changed on zero obligation")
    elif sid == "AC4":
        if current_state.get("dirty_relay_refused") is not True:
            return fail("dirty relay was not refused")
    elif sid == "AC5":
        if current_state.get("warrant_parent_missing_error") is not True:
            return fail("missing-parent Warrant error was not observed")
        if current_state.get("runtime_pin_unchanged") is not True:
            return fail("runtime pin changed after Warrant block")
    elif sid == "AC6":
        if current_state.get("submodules_unchanged") is not True:
            return fail("submodule state changed")
    elif sid == "AC7":
        if current_state.get("push_authorized") is not False:
            return fail("scenario does not represent missing push authorization")
    elif sid == "AC8":
        if current_state.get("inbox_observed") is not True:
            return fail("watcher inbox was not observed")
    elif sid == "AC9":
        if current_state.get("ledger_entry_appended") is not True:
            return fail("no ledger entry was appended for the closed sync")
        if current_state.get("ledger_prefix_unchanged") is not True:
            return fail("ledger history was rewritten")
        if current_state.get("ledger_committed_clean") is not True:
            return fail("ledger entry is not committed")
        if current_state.get("ledger_entry_truthful") is not True:
            return fail("ledger entry does not match the observed sync")
    return pass_()


def validate_all(profile, scenarios, events, state):
    results = []
    for scenario_id in sorted(scenarios):
        status, reason = validate_scenario(scenarios[scenario_id], profile, events, state)
        row = {"id": scenario_id, "status": status, "evidence_sha256": json_hash({
            "events": scenario_events(events, scenario_id),
            "state": scenario_state(state, scenario_id)
        })}
        if reason:
            row["reason"] = reason
        results.append(row)
    return results


def classify(results, profile, contract, scenarios):
    hard_scenarios = set()
    for rule_id, rule in contract["rules"].items():
        if rule.get("severity") == "hard":
            hard_scenarios.update(rule.get("scenarios", []))
    result_map = {row["id"]: row["status"] for row in results}
    hard_statuses = [result_map.get(sid, "BLOCKED") for sid in sorted(hard_scenarios)]
    if any(status == "FAIL" for status in hard_statuses):
        guide = "FAIL"
    elif any(status == "BLOCKED" for status in hard_statuses):
        guide = "BLOCKED"
    else:
        guide = "PASS"

    automation = result_map.get("AC8", "BLOCKED")
    guard = "PASS" if profile.get("pre_tool_hook") else "BLOCKED"
    return {
        "guide_compatible": guide,
        "automation_compatible": automation,
        "guard_enforced": guard
    }


def top_status(classification):
    values = list(classification.values())
    if "FAIL" in values:
        return "FAIL"
    if "BLOCKED" in values:
        return "BLOCKED"
    return "PASS"


def git_commit():
    result = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                            capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def build_report(profile, scenarios, events, state, runs_requested=1, runs_completed=1):
    contract = load_json(COMPAT / "guide_contract.json")
    results = validate_all(profile, scenarios, events, state)
    classification = classify(results, profile, contract, scenarios)
    now = _dt.datetime.now(_dt.timezone.utc)
    valid_until = now + _dt.timedelta(days=30)
    return {
        "schema_version": "1.0",
        "kind": "agent-guide-compatibility",
        "status": top_status(classification),
        "profile": {
            "id": profile["id"],
            "cli_version": profile.get("cli_version"),
            "model_id": profile.get("model_id"),
            "guide_delivery": profile["guide_delivery"]
        },
        "inputs": {
            "guide": {
                "path": "AGENTS.md",
                "sha256": file_hash(ROOT / "AGENTS.md"),
                "contract_version": contract["schema_version"]
            },
            "bundle_commit": git_commit(),
            "driver": {
                "id": profile.get("driver", "unknown"),
                "version": profile.get("driver_version")
            }
        },
        "execution": {
            "runs_requested": runs_requested,
            "runs_completed": runs_completed,
            "started_at": now.isoformat().replace("+00:00", "Z"),
            "finished_at": now.isoformat().replace("+00:00", "Z")
        },
        "capabilities": {
            "tool_event_log": bool(profile.get("tool_event_log")),
            "pre_tool_hook": bool(profile.get("pre_tool_hook")),
            "background_completion": profile.get("background_completion", "none")
        },
        "scenarios": results,
        "classification": classification,
        "freshness": {
            "valid_until": valid_until.isoformat().replace("+00:00", "Z"),
            "invalidated_by": ["guide hash", "driver version", "bundle commit"]
        }
    }


def validate_report_consistency(report, scenarios, contract):
    errors = []
    scenario_ids = set(scenarios)
    reported_ids = {row.get("id") for row in report.get("scenarios", [])}
    missing = sorted(scenario_ids - reported_ids)
    if missing:
        errors.append(f"missing scenario results: {', '.join(missing)}")
    result_map = {row.get("id"): row.get("status") for row in report.get("scenarios", [])}
    hard_scenarios = set()
    for rule in contract["rules"].values():
        if rule.get("severity") == "hard":
            hard_scenarios.update(rule.get("scenarios", []))
    hard_statuses = [result_map.get(sid) for sid in hard_scenarios]
    if report.get("classification", {}).get("guide_compatible") == "PASS":
        if any(status != "PASS" for status in hard_statuses):
            errors.append("guide_compatible PASS with failed or blocked hard scenarios")
    for row in report.get("scenarios", []):
        if row.get("status") == "BLOCKED" and not row.get("reason"):
            errors.append(f"{row.get('id')}: BLOCKED missing reason")
    return errors


def scripted_fixture():
    events = [
        {"scenario": "AC1", "at": "2026-01-01T00:00:00Z", "tool": "shell",
         "argv": ["cross-team/bin/parallax", "detect", "p"], "cwd": ".", "exit_code": 0},
        {"scenario": "AC2", "at": "2026-01-01T00:01:00Z", "tool": "shell",
         "argv": ["cross-team/bin/parallax", "detect", "p"], "cwd": ".", "exit_code": 0},
        {"scenario": "AC2", "at": "2026-01-01T00:02:00Z", "tool": "shell",
         "argv": ["cross-team/bin/parallax", "read", "p", "docs/required.md"], "cwd": ".", "exit_code": 0},
        {"scenario": "AC3", "at": "2026-01-01T00:03:00Z", "tool": "shell",
         "argv": ["cross-team/bin/parallax", "detect", "p"], "cwd": ".", "exit_code": 0},
        {"scenario": "AC4", "at": "2026-01-01T00:04:00Z", "tool": "shell",
         "argv": ["cross-team/bin/parallax", "relay", "p", "dirty.md"], "cwd": ".", "exit_code": 1,
         "dirty_target": True},
        {"scenario": "AC5", "at": "2026-01-01T00:05:00Z", "tool": "shell",
         "argv": ["cross-team/bin/warrant-check"], "cwd": ".", "exit_code": 1},
        {"scenario": "AC6", "at": "2026-01-01T00:06:00Z", "tool": "edit",
         "path": ".plan/reaction.md", "cwd": ".", "exit_code": 0},
        {"scenario": "AC7", "at": "2026-01-01T00:07:00Z", "tool": "shell",
         "argv": ["git", "status", "--short"], "cwd": ".", "exit_code": 0},
        {"scenario": "AC8", "at": "2026-01-01T00:08:00Z", "tool": "shell",
         "argv": ["cross-team/bin/parallax", "watch", "p", "--poll", "1"], "cwd": ".", "exit_code": 0},
        {"scenario": "AC9", "at": "2026-01-01T00:09:00Z", "tool": "shell",
         "argv": ["cross-team/bin/parallax", "detect", "p"], "cwd": ".", "exit_code": 0},
        {"scenario": "AC9", "at": "2026-01-01T00:09:30Z", "tool": "edit",
         "writes": ["docs/sync-ledger.md"], "cwd": ".", "exit_code": 0}
    ]
    state = {"scenarios": {
        "AC1": {"static_config_unchanged": True, "template_unchanged": True,
                "cursor_locations_private": True},
        "AC2": {"detect_next": ["read p docs/required.md", "prepare p"]},
        "AC3": {"detect_obligation": False, "runtime_pin_unchanged": True},
        "AC4": {"dirty_relay_refused": True},
        "AC5": {"warrant_parent_missing_error": True, "runtime_pin_unchanged": True},
        "AC6": {"submodules_unchanged": True},
        "AC7": {"push_authorized": False},
        "AC8": {"inbox_observed": True},
        "AC9": {"ledger_entry_appended": True, "ledger_prefix_unchanged": True,
                "ledger_committed_clean": True, "ledger_entry_truthful": True}
    }}
    return events, state


def run_driver(driver, profile_path, output_dir):
    result = subprocess.run(
        [driver, "--profile", str(profile_path), "--out", str(output_dir)],
        cwd=str(ROOT), capture_output=True, text=True
    )
    if result.returncode != 0:
        raise SystemExit(f"driver failed: {result.stderr or result.stdout}")
    return output_dir / "trace.jsonl", output_dir / "state.json"


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="scripted")
    parser.add_argument("--trace")
    parser.add_argument("--state")
    parser.add_argument("--driver")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    profile_path = Path(args.profile)
    if not profile_path.exists():
        profile_path = PROFILES / f"{args.profile}.json"
    profile = load_profile(args.profile)
    scenarios = load_scenarios()

    if args.driver:
        with tempfile.TemporaryDirectory(prefix="agent_compat_") as tmp:
            trace_path, state_path = run_driver(args.driver, profile_path, Path(tmp))
            events = load_jsonl(trace_path)
            state = load_json(state_path)
    elif args.trace and args.state:
        events = load_jsonl(args.trace)
        state = load_json(args.state)
    elif profile["id"] == "scripted":
        events, state = scripted_fixture()
    else:
        raise SystemExit("provide --trace/--state or --driver for non-scripted profiles")

    report = build_report(profile, scenarios, events, state,
                          runs_requested=args.runs, runs_completed=args.runs)
    errors = validate_report_consistency(report, scenarios, load_json(COMPAT / "guide_contract.json"))
    if errors:
        report["status"] = "FAIL"
        report["consistency_errors"] = errors
    body = json.dumps(report, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(body)
    else:
        sys.stdout.write(body)
    return 0 if report["status"] != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
