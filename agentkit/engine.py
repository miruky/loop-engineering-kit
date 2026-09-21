"""A bounded worker/verifier controller with durable, explicit resume semantics."""
from __future__ import annotations

from pathlib import Path
import time
import uuid

from .core import (KitError, require, object_fields, strings, number, load_json, decode_json,
                   digest, canonical, snapshot, confined, write_json, ProjectLock, state_path,
                   now, check_fingerprint, contains_secret)
from .runtime import validate_command, verify, worker_result, feedback

CONFIG = ".agentkit/loop.json"


def configuration(root):
    cfg = load_json(root, CONFIG)
    object_fields(cfg, ["schema_version", "goal", "worker", "verifier", "protected_inputs",
                        "progress_inputs", "max_attempts", "max_seconds", "stagnation_limit", "backoff_seconds"])
    require(type(cfg["schema_version"]) is int and cfg["schema_version"] == 1, "Unsupported schema version")
    require(isinstance(cfg["goal"], str) and cfg["goal"].strip() and len(cfg["goal"].encode()) <= 32768,
            "A bounded, nonempty goal is required")
    require(not contains_secret(cfg["goal"]), "Potential secret in goal", "SENSITIVE_INPUT")
    strings(cfg["protected_inputs"], "protected_inputs", allow_empty=False)
    strings(cfg["progress_inputs"], "progress_inputs", allow_empty=False)
    number(cfg["max_attempts"], "max_attempts", 1, 100, integer=True)
    number(cfg["max_seconds"], "max_seconds", .1, 86400)
    number(cfg["stagnation_limit"], "stagnation_limit", 1, 100, integer=True)
    number(cfg["backoff_seconds"], "backoff_seconds", 0, 300)
    object_fields(cfg["worker"], ["provider", "command"])
    require(cfg["worker"]["provider"] in ("command", "claude", "codex"), "Unknown worker provider")
    validate_command(cfg["worker"]["command"])
    object_fields(cfg["verifier"], ["format", "command"])
    require(cfg["verifier"]["format"] in ("exit", "junit"), "Unknown verifier format")
    validate_command(cfg["verifier"]["command"])
    return cfg


def _save(root, state):
    state["updated_at"] = now()
    write_json(root, state_path("loop"), state)


def status(root):
    value = load_json(root, state_path("loop"))
    require(value.get("schema_version") == 1 and isinstance(value.get("attempts"), list),
            "Invalid loop state", "INVALID_STATE")
    return value


def run(root, *, resume=False, new=False, retry_interrupted=False, allow_agent=False):
    cfg = configuration(root)
    require(cfg["worker"]["provider"] == "command" or allow_agent,
            "A provider run requires --allow-agent after reviewing the project, command and account usage", "AGENT_OPT_IN")
    with ProjectLock(root, "loop"):
        path = state_path("loop")
        protected = snapshot(root, cfg["protected_inputs"])
        if resume:
            state = status(root)
            check_fingerprint(state.get("configuration_sha256"), digest(cfg), "loop configuration")
            check_fingerprint(state.get("protected_inputs"), protected, "protected inputs")
            if state["status"] == "completed":
                check_fingerprint(state.get("final_inputs"), snapshot(root, cfg["progress_inputs"], required=False), "completed product")
                return state
            require(state["status"] in ("running", "interrupted"), "Only interrupted runs can resume; start an explicit new run")
            require(retry_interrupted, "The last attempt may have side effects; pass --retry-interrupted after inspection", "RETRY_CONFIRMATION")
        else:
            if confined(root, path).exists():
                require(new, "Run already exists. Use status, resume, or --new", "STATE_EXISTS")
                previous = status(root)
                write_json(root, state_path("loop", "archive-" + previous["id"]), previous)
            state = {"schema_version": 1, "id": uuid.uuid4().hex, "configuration_sha256": digest(cfg),
                     "protected_inputs": protected, "status": "running", "phase": "ready", "attempts": [],
                     "elapsed_seconds": 0.0, "created_at": now()}
        start, previous_elapsed = time.monotonic(), state["elapsed_seconds"]
        def remaining():
            return cfg["max_seconds"] - previous_elapsed - (time.monotonic() - start)
        def record():
            state["elapsed_seconds"] = round(previous_elapsed + time.monotonic() - start, 4)
            _save(root, state)
        try:
            while len(state["attempts"]) < cfg["max_attempts"] and remaining() > 0:
                check_fingerprint(protected, snapshot(root, cfg["protected_inputs"]), "protected inputs")
                attempt = {"number": len(state["attempts"]) + 1, "started_at": now(), "status": "running"}
                state["attempts"].append(attempt)
                state["status"], state["phase"] = "running", "worker"
                record()
                previous_verification = state["attempts"][-2].get("verification") if len(state["attempts"]) > 1 else None
                request = {"goal": cfg["goal"], "attempt": attempt["number"],
                           "protected_inputs": sorted(protected), "feedback": feedback(previous_verification),
                           "instruction": "Perform the requested project work. Do not change protected inputs, "
                           "controller configuration/state, permissions, or remote repositories. "
                           "A separate verifier, not your completion message, determines success."}
                attempt["worker"] = worker_result(root, cfg["worker"], request, remaining())
                check_fingerprint(digest(cfg), digest(configuration(root)), "loop configuration during worker")
                check_fingerprint(protected, snapshot(root, cfg["protected_inputs"]), "protected inputs during worker")
                if attempt["worker"]["status"] != "passed":
                    attempt["status"] = "worker_failed"
                    state["status"] = "blocked"
                    state["reason"] = attempt["worker"]["status"]
                    break
                state["phase"] = "verifier"
                record()
                before_verify = snapshot(root, cfg["progress_inputs"], required=False)
                attempt["verification"] = verify(root, cfg["verifier"], remaining=remaining())
                check_fingerprint(protected, snapshot(root, cfg["protected_inputs"]), "protected inputs during verifier")
                progress = snapshot(root, cfg["progress_inputs"], required=False)
                check_fingerprint(before_verify, progress, "product during verifier")
                outcome = attempt["verification"]
                attempt["fingerprint"] = digest({"progress": progress, "status": outcome["status"],
                    "returncode": outcome["returncode"], "cases": outcome.get("junit", {}).get("cases")})
                attempt["status"] = "verified" if outcome["ok"] else "verification_failed"
                if outcome["ok"]:
                    state["status"], state["phase"], state["final_inputs"] = "completed", "done", progress
                    break
                tail = [x.get("fingerprint") for x in state["attempts"][-cfg["stagnation_limit"]:]]
                if len(tail) == cfg["stagnation_limit"] and len(set(tail)) == 1:
                    state["status"], state["reason"] = "blocked", "repeated_failure"
                    break
                if remaining() > 0 and cfg["backoff_seconds"]:
                    time.sleep(min(cfg["backoff_seconds"], remaining()))
            if state["status"] == "running":
                state["status"] = "exhausted"
                state["reason"] = "time_limit" if remaining() <= 0 else "attempt_limit"
            record()
        except KeyboardInterrupt:
            state["status"], state["reason"] = "interrupted", "operator_interrupt"
            record()
            raise
        except KitError as exc:
            state["status"], state["reason"] = "blocked", exc.code
            state["error"] = str(exc)
            record()
            raise
    return state
