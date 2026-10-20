#!/usr/bin/env python3
"""Reproducible runner for the RQ5 LLM-assisted repair experiment.

The runner deliberately separates four stages:
1. validate-manifest: check task fields and obvious prompt-leakage markers;
2. generate: render the frozen prompt and call only configured model APIs;
3. validate: apply generated Unified Diffs in isolated git worktrees and run
   pre-registered commands; and
4. summarize: aggregate task-level outcomes without claiming repair success.

No API key, GitHub token, PR URL, developer patch, or repaired source file is
stored by this script. The only network request made by ``generate`` is the
configured LLM inference API call. No tools, browser, retrieval, MCP server, or
function-calling specification is included in that request.

Example:
    python rq5_llm_experiment.py validate-manifest --tasks tasks.jsonl
    python rq5_llm_experiment.py generate --tasks tasks.jsonl --models models.json \
        --run-dir runs/2026-09-07 --dry-run
    python rq5_llm_experiment.py generate --tasks tasks.jsonl --models models.json \
        --run-dir runs/2026-09-07
    python rq5_llm_experiment.py validate --tasks tasks.jsonl \
        --run-dir runs/2026-09-07
    python rq5_llm_experiment.py summarize --run-dir runs/2026-09-07
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable


SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = SCRIPT_DIR.parents[1]
DEFAULT_TEMPLATE = WORKSPACE_ROOT / "prompts" / "repair_prompt.txt"
UTC = dt.timezone.utc

# These checks do not replace manual sanitization. They only catch common cases
# where a reference patch URL or a raw diff accidentally reaches the model.
LEAKAGE_PATTERNS = {
    "pull_or_commit_url": re.compile(
        r"https?://github\.com/[^\s/]+/[^\s/]+/(?:pull|commit)/[^\s?#]+", re.I
    ),
    "raw_patch_url": re.compile(r"patch-diff\.githubusercontent\.com|\.diff(?:\s|$)", re.I),
    "embedded_unified_diff": re.compile(r"(?m)^diff --git |^@@ -\d"),
}
DIFF_BLOCK = re.compile(r"```diff\s*\n(.*?)\n```", re.IGNORECASE | re.DOTALL)
FORBIDDEN_REQUEST_KEYS = {
    "tools", "tool_choice", "functions", "function_call", "browser", "web_search",
    "retrieval", "mcp",
}


class ManifestError(ValueError):
    """Raised when a task or model manifest violates the experiment protocol."""


@dataclass(frozen=True)
class ModelSpec:
    """An OpenAI-compatible, no-tools chat-completions endpoint."""

    label: str
    model: str
    base_url: str
    api_key_env: str
    temperature: float = 0.0
    max_tokens: int = 4096
    candidates_per_task: int = 1
    seed: int | None = None
    timeout_seconds: int = 120
    extra_body: dict[str, Any] = field(default_factory=dict)

    @property
    def endpoint(self) -> str:
        return self.base_url.rstrip("/") + "/chat/completions"


@dataclass
class Task:
    """A single Issue-level candidate-patch task."""

    task_id: str
    group: str
    framework: str
    issue_title: str
    issue_body: str
    issue_sanitized: bool
    source_revision: str
    repo_path: str
    files: list[dict[str, Any]]
    validation: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


def utc_now() -> str:
    return dt.datetime.now(tz=UTC).isoformat(timespec="seconds")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._") or "unnamed"


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as error:
                raise ManifestError(f"{path}:{line_number}: invalid JSON: {error.msg}") from error


def ensure_relative_repo_path(path_value: str, task_id: str) -> None:
    candidate = Path(path_value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ManifestError(
            f"Task {task_id}: source file path must be repository-relative: {path_value!r}"
        )


def leakage_hits(text: str) -> list[str]:
    return [name for name, pattern in LEAKAGE_PATTERNS.items() if pattern.search(text)]


def load_tasks(tasks_path: Path) -> list[Task]:
    manifest_dir = tasks_path.resolve().parent
    tasks: list[Task] = []
    seen_ids: set[str] = set()
    required = {
        "task_id",
        "group",
        "framework",
        "issue_title",
        "issue_body",
        "issue_sanitized",
        "source_revision",
        "repo_path",
        "files",
    }

    for raw in read_jsonl(tasks_path):
        missing = sorted(required - raw.keys())
        if missing:
            raise ManifestError(f"Task record lacks required fields: {', '.join(missing)}")
        task = Task(
            task_id=str(raw["task_id"]),
            group=str(raw["group"]),
            framework=str(raw["framework"]),
            issue_title=str(raw["issue_title"]),
            issue_body=str(raw["issue_body"]),
            issue_sanitized=bool(raw["issue_sanitized"]),
            source_revision=str(raw["source_revision"]),
            repo_path=str(raw["repo_path"]),
            files=list(raw["files"]),
            validation=dict(raw.get("validation", {})),
            metadata=dict(raw.get("metadata", {})),
        )
        if task.task_id in seen_ids:
            raise ManifestError(f"Duplicate task_id: {task.task_id}")
        seen_ids.add(task.task_id)
        validate_task_schema(task, manifest_dir)
        tasks.append(task)

    if not tasks:
        raise ManifestError(f"No task records found in {tasks_path}")
    return tasks


def validate_task_schema(task: Task, manifest_dir: Path) -> None:
    if task.group not in {"small", "medium"}:
        raise ManifestError(f"Task {task.task_id}: group must be 'small' or 'medium'")
    if not task.issue_sanitized:
        raise ManifestError(
            f"Task {task.task_id}: set issue_sanitized=true only after issue-text cleaning"
        )
    if not task.issue_title.strip() or not task.issue_body.strip():
        raise ManifestError(f"Task {task.task_id}: issue title and body must be non-empty")
    hits = leakage_hits(task.issue_title + "\n" + task.issue_body)
    if hits:
        raise ManifestError(
            f"Task {task.task_id}: possible repair leakage in issue text ({', '.join(hits)})"
        )
    if not task.files:
        raise ManifestError(f"Task {task.task_id}: at least one source file is required")
    for item in task.files:
        if not isinstance(item, dict) or "path" not in item or "content_file" not in item:
            raise ManifestError(
                f"Task {task.task_id}: each files entry needs 'path' and 'content_file'"
            )
        ensure_relative_repo_path(str(item["path"]), task.task_id)
        content_path = (manifest_dir / str(item["content_file"])).resolve()
        if not content_path.is_file():
            raise ManifestError(
                f"Task {task.task_id}: missing content_file {item['content_file']!r}"
            )


def load_models(models_path: Path) -> list[ModelSpec]:
    try:
        document = json.loads(models_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ManifestError(f"Invalid model JSON: {error.msg}") from error
    records = document.get("models") if isinstance(document, dict) else None
    if not isinstance(records, list) or not records:
        raise ManifestError("Model config must contain a non-empty 'models' list")

    specs: list[ModelSpec] = []
    labels: set[str] = set()
    for raw in records:
        try:
            spec = ModelSpec(**raw)
        except TypeError as error:
            raise ManifestError(f"Invalid model record: {error}") from error
        if spec.label in labels:
            raise ManifestError(f"Duplicate model label: {spec.label}")
        labels.add(spec.label)
        if not spec.base_url.startswith(("https://", "http://localhost:", "http://127.0.0.1:")):
            raise ManifestError(f"Model {spec.label}: base_url must use HTTPS or a loopback HTTP endpoint")
        if spec.candidates_per_task != 1:
            raise ManifestError(f"Model {spec.label}: candidates_per_task must equal one for this Top-1 protocol")
        prohibited = sorted(set(spec.extra_body) & FORBIDDEN_REQUEST_KEYS)
        if prohibited:
            raise ManifestError(
                f"Model {spec.label}: extra_body cannot contain tool, browser, or retrieval fields "
                f"({', '.join(prohibited)})"
            )
        specs.append(spec)
    return specs


def extract_template(template_path: Path) -> str:
    template = template_path.read_text(encoding="utf-8").strip()
    expected = ["{issue_title}", "{issue_body}", "{files_context}"]
    absent = [item for item in expected if item not in template]
    if absent:
        raise ManifestError(f"Prompt template lacks placeholders: {', '.join(absent)}")
    return template


def build_files_context(task: Task, manifest_dir: Path) -> str:
    blocks: list[str] = []
    for item in task.files:
        relative_path = str(item["path"]).replace("\\", "/")
        content_path = (manifest_dir / str(item["content_file"])).resolve()
        content = content_path.read_text(encoding="utf-8")
        blocks.append(f"### {relative_path}\n```\n{content.rstrip()}\n```")
    return "\n\n".join(blocks)


def render_prompt(template: str, task: Task, manifest_dir: Path) -> str:
    replacements = {
        "{issue_title}": task.issue_title.strip(),
        "{issue_body}": task.issue_body.strip(),
        "{files_context}": build_files_context(task, manifest_dir),
    }
    rendered = template
    for token, value in replacements.items():
        rendered = rendered.replace(token, value)
    return rendered


def response_contains_tool_activity(payload: dict[str, Any]) -> bool:
    """Detect tool-related fields without accepting a tool call as a valid run."""
    message = (
        payload.get("choices", [{}])[0].get("message", {})
        if isinstance(payload.get("choices"), list) and payload.get("choices")
        else {}
    )
    return bool(message.get("tool_calls") or message.get("function_call"))


def request_candidate(spec: ModelSpec, prompt: str) -> dict[str, Any]:
    api_key = os.environ.get(spec.api_key_env)
    if not api_key:
        raise RuntimeError(
            f"Missing API key: set environment variable {spec.api_key_env} for {spec.label}"
        )
    body: dict[str, Any] = {
        "model": spec.model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": spec.temperature,
        "max_tokens": spec.max_tokens,
        "top_p": 1.0,
    }
    if spec.seed is not None:
        body["seed"] = spec.seed
    body.update(spec.extra_body)

    # Intentionally no "tools", "tool_choice", browsing, retrieval, MCP, or
    # function-calling fields. The provider endpoint is the sole network target.
    request = urllib.request.Request(
        spec.endpoint,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "RQ5-RL-Repair-Experiment/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=spec.timeout_seconds) as response:
            decoded = response.read().decode("utf-8")
            return json.loads(decoded)
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{spec.label} HTTP {error.code}: {detail}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"{spec.label} network error: {error.reason}") from error


def parse_candidate(payload: dict[str, Any]) -> tuple[str, str | None, bool]:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return "", None, response_contains_tool_activity(payload)
    message = choices[0].get("message", {})
    content = message.get("content", "")
    if content is None:
        content = ""
    if not isinstance(content, str):
        content = json.dumps(content, ensure_ascii=False)
    diff_match = DIFF_BLOCK.search(content)
    diff = diff_match.group(1).strip() if diff_match else None
    return content, diff, response_contains_tool_activity(payload)


def allowed_diff_paths(diff: str, task: Task) -> tuple[bool, list[str]]:
    allowed = {str(item["path"]).replace("\\", "/") for item in task.files}
    changed: set[str] = set()
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            changed.add(line[len("+++ b/") :].strip())
        elif line.startswith("--- a/"):
            changed.add(line[len("--- a/") :].strip())
        elif line.startswith("+++ /dev/null") or line.startswith("--- /dev/null"):
            return False, sorted(changed)
    return bool(changed) and changed.issubset(allowed), sorted(changed)


def task_candidate_path(run_dir: Path, spec: ModelSpec, task: Task, index: int) -> Path:
    return (
        run_dir
        / "candidates"
        / safe_name(spec.label)
        / safe_name(task.task_id)
        / f"candidate_{index:02d}.json"
    )


def generation_record(
    *,
    task: Task,
    spec: ModelSpec,
    candidate_index: int,
    prompt: str,
    template_hash: str,
    status: str,
    response: dict[str, Any] | None,
    error: str | None,
) -> dict[str, Any]:
    content, diff, tool_activity = parse_candidate(response or {})
    diff_allowed = False
    changed_paths: list[str] = []
    if diff:
        diff_allowed, changed_paths = allowed_diff_paths(diff, task)
    return {
        "created_at": utc_now(),
        "task_id": task.task_id,
        "group": task.group,
        "framework": task.framework,
        "model_label": spec.label,
        "model_id": spec.model,
        "candidate_index": candidate_index,
        "status": status,
        "error": error,
        "prompt_template_sha256": template_hash,
        "prompt_sha256": sha256_text(prompt),
        "input_sha256": sha256_text(task.issue_title + "\n" + task.issue_body),
        "tool_activity_detected": tool_activity,
        "response_text": content,
        "parsed_diff": diff,
        "parsed_diff_sha256": sha256_text(diff) if diff else None,
        "diff_changes_only_allowed_files": diff_allowed,
        "changed_paths": changed_paths,
        "raw_response": response,
    }


def command_generate(args: argparse.Namespace) -> int:
    tasks_path = Path(args.tasks).resolve()
    models_path = Path(args.models).resolve()
    template_path = Path(args.template).resolve() if args.template else DEFAULT_TEMPLATE
    run_dir = Path(args.run_dir).resolve()
    tasks = load_tasks(tasks_path)
    specs = load_models(models_path)
    template = extract_template(template_path)
    template_hash = sha256_text(template)
    manifest_dir = tasks_path.parent
    if args.max_tasks:
        tasks = tasks[: args.max_tasks]

    metadata = {
        "created_at": utc_now(),
        "command": "generate",
        "dry_run": args.dry_run,
        "prompt_template": str(template_path),
        "prompt_template_sha256": template_hash,
        "tasks_manifest": str(tasks_path),
        "models_manifest": str(models_path),
        "models": [asdict(spec) for spec in specs],
        "network_policy": "Only configured LLM inference endpoints; no tools/retrieval/browser/MCP.",
    }
    write_json(run_dir / "run_metadata.json", metadata)
    summary_path = run_dir / "generation_summary.jsonl"

    total = len(tasks) * sum(spec.candidates_per_task for spec in specs)
    print(f"Prepared {len(tasks)} tasks, {len(specs)} models, {total} candidate requests.")
    for task in tasks:
        prompt = render_prompt(template, task, manifest_dir)
        for spec in specs:
            for index in range(1, spec.candidates_per_task + 1):
                output_path = task_candidate_path(run_dir, spec, task, index)
                if args.resume and output_path.exists():
                    print(f"[resume] {spec.label} / {task.task_id} / {index}")
                    continue
                response: dict[str, Any] | None = None
                error: str | None = None
                status = "dry_run" if args.dry_run else "completed"
                if not args.dry_run:
                    try:
                        response = request_candidate(spec, prompt)
                    except RuntimeError as caught:
                        status = "request_error"
                        error = str(caught)
                record = generation_record(
                    task=task,
                    spec=spec,
                    candidate_index=index,
                    prompt=prompt,
                    template_hash=template_hash,
                    status=status,
                    response=response,
                    error=error,
                )
                write_json(output_path, record)
                append_jsonl(summary_path, {key: value for key, value in record.items() if key != "raw_response"})
                print(f"[{record['status']}] {spec.label} / {task.task_id} / {index}")
                if args.sleep_seconds and not args.dry_run:
                    time.sleep(args.sleep_seconds)
    return 0


def run_user_command(command: str, cwd: Path, timeout_seconds: int) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        shell=True,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        encoding="utf-8",
        errors="replace",
    )
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def run_git(arguments: list[str], cwd: Path, timeout_seconds: int = 120) -> dict[str, Any]:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        encoding="utf-8",
        errors="replace",
    )
    return {
        "command": ["git", *arguments],
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def validation_commands(task: Task) -> tuple[str | None, list[str], str | None, list[str], int]:
    config = task.validation
    pre_fix = config.get("pre_fix_command")
    build = config.get("build_commands", [])
    targeted = config.get("targeted_test_command")
    regression = config.get("regression_commands", [])
    timeout = int(config.get("timeout_seconds", 600))
    if build and not isinstance(build, list):
        raise ManifestError(f"Task {task.task_id}: build_commands must be a list")
    if regression and not isinstance(regression, list):
        raise ManifestError(f"Task {task.task_id}: regression_commands must be a list")
    return (
        str(pre_fix) if pre_fix else None,
        [str(item) for item in build],
        str(targeted) if targeted else None,
        [str(item) for item in regression],
        timeout,
    )


def validate_one_candidate(
    *,
    task: Task,
    candidate: dict[str, Any],
    run_dir: Path,
    cleanup: bool,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "validated_at": utc_now(),
        "task_id": task.task_id,
        "model_label": candidate.get("model_label"),
        "candidate_index": candidate.get("candidate_index"),
        "group": task.group,
        "framework": task.framework,
        "generation_status": candidate.get("status"),
        "validation_status": "not_started",
        "applicable": False,
        "build_import_pass": False,
        "pre_fix_failure_observed": False,
        "targeted_test_pass": False,
        "regression_pass": False,
        "executable_validation_pass": False,
        "manual_semantic_review": "pending",
        "logs": {},
    }
    diff = candidate.get("parsed_diff")
    if candidate.get("tool_activity_detected"):
        result["validation_status"] = "invalid_tool_activity"
        return result
    if not diff:
        result["validation_status"] = "no_parseable_diff"
        return result
    allowed, changed = allowed_diff_paths(diff, task)
    result["changed_paths"] = changed
    if not allowed:
        result["validation_status"] = "disallowed_or_empty_diff_paths"
        return result

    repo = Path(task.repo_path).expanduser().resolve()
    if not (repo / ".git").exists():
        result["validation_status"] = "missing_git_repository"
        result["repository"] = str(repo)
        return result

    task_root = run_dir / "validation_worktrees" / safe_name(task.task_id)
    worktree = task_root / f"{safe_name(str(candidate.get('model_label')))}_{candidate.get('candidate_index')}"
    patch_path = task_root / f"{safe_name(str(candidate.get('model_label')))}_{candidate.get('candidate_index')}.diff"
    patch_path.parent.mkdir(parents=True, exist_ok=True)
    patch_path.write_text(diff + "\n", encoding="utf-8")

    if worktree.exists():
        result["validation_status"] = "worktree_already_exists"
        result["worktree"] = str(worktree)
        return result

    add_worktree = run_git(["worktree", "add", "--detach", str(worktree), task.source_revision], repo)
    result["logs"]["worktree_add"] = add_worktree
    if add_worktree["returncode"] != 0:
        result["validation_status"] = "worktree_creation_failed"
        return result

    try:
        pre_fix, build_commands, targeted, regression_commands, timeout = validation_commands(task)
        check = run_git(["apply", "--check", "--whitespace=nowarn", str(patch_path)], worktree)
        result["logs"]["git_apply_check"] = check
        if check["returncode"] != 0:
            result["validation_status"] = "patch_not_applicable"
            return result
        apply = run_git(["apply", "--whitespace=nowarn", str(patch_path)], worktree)
        result["logs"]["git_apply"] = apply
        if apply["returncode"] != 0:
            result["validation_status"] = "patch_apply_failed"
            return result
        result["applicable"] = True

        # The pre-fix reproduction must be executed on a separate worktree. It
        # is intentionally not inferred from a post-patch test failure.
        if pre_fix:
            baseline = worktree.with_name(worktree.name + "_baseline")
            baseline_add = run_git(["worktree", "add", "--detach", str(baseline), task.source_revision], repo)
            result["logs"]["baseline_worktree_add"] = baseline_add
            if baseline_add["returncode"] == 0:
                try:
                    pre_result = run_user_command(pre_fix, baseline, timeout)
                    result["logs"]["pre_fix_command"] = pre_result
                    result["pre_fix_failure_observed"] = pre_result["returncode"] != 0
                finally:
                    if cleanup:
                        run_git(["worktree", "remove", "--force", str(baseline)], repo)

        build_results = [run_user_command(command, worktree, timeout) for command in build_commands]
        result["logs"]["build_commands"] = build_results
        result["build_import_pass"] = bool(build_results) and all(
            item["returncode"] == 0 for item in build_results
        )

        if targeted:
            targeted_result = run_user_command(targeted, worktree, timeout)
            result["logs"]["targeted_test_command"] = targeted_result
            result["targeted_test_pass"] = targeted_result["returncode"] == 0

        regression_results = [
            run_user_command(command, worktree, timeout) for command in regression_commands
        ]
        result["logs"]["regression_commands"] = regression_results
        result["regression_pass"] = all(item["returncode"] == 0 for item in regression_results)

        result["executable_validation_pass"] = bool(
            result["pre_fix_failure_observed"]
            and result["build_import_pass"]
            and result["targeted_test_pass"]
            and result["regression_pass"]
        )
        result["validation_status"] = "completed"
        return result
    except subprocess.TimeoutExpired as error:
        result["validation_status"] = "command_timeout"
        result["logs"]["timeout"] = str(error)
        return result
    finally:
        if cleanup and worktree.exists():
            run_git(["worktree", "remove", "--force", str(worktree)], repo)


def candidate_records(run_dir: Path) -> Iterable[Path]:
    yield from sorted((run_dir / "candidates").glob("*/*/candidate_*.json"))


def command_validate(args: argparse.Namespace) -> int:
    tasks_path = Path(args.tasks).resolve()
    run_dir = Path(args.run_dir).resolve()
    tasks = {task.task_id: task for task in load_tasks(tasks_path)}
    output = run_dir / "validation_summary.jsonl"
    records = list(candidate_records(run_dir))
    if not records:
        raise ManifestError(f"No candidate records found under {run_dir / 'candidates'}")
    print(f"Validating {len(records)} candidate records. Commands in the task manifest are trusted inputs.")
    for record_path in records:
        candidate = json.loads(record_path.read_text(encoding="utf-8"))
        task_id = candidate.get("task_id")
        if task_id not in tasks:
            raise ManifestError(f"Candidate {record_path} references unknown task_id {task_id!r}")
        validation_path = record_path.with_name(record_path.stem + ".validation.json")
        if args.resume and validation_path.exists():
            print(f"[resume] {record_path}")
            continue
        result = validate_one_candidate(
            task=tasks[task_id],
            candidate=candidate,
            run_dir=run_dir,
            cleanup=args.cleanup_worktrees,
        )
        write_json(validation_path, result)
        append_jsonl(output, {key: value for key, value in result.items() if key != "logs"})
        print(f"[{result['validation_status']}] {candidate.get('model_label')} / {task_id}")
    return 0


def command_summarize(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    validation_paths = sorted((run_dir / "candidates").glob("*/*/candidate_*.validation.json"))
    if not validation_paths:
        raise ManifestError("No validation records found; run the validate command first")

    tasks: dict[tuple[str, str], dict[str, Any]] = {}
    for path in validation_paths:
        record = json.loads(path.read_text(encoding="utf-8"))
        key = (str(record["model_label"]), str(record["task_id"]))
        aggregate = tasks.setdefault(
            key,
            {
                "model_label": record["model_label"],
                "task_id": record["task_id"],
                "candidate_count": 0,
                "any_applicable": False,
                "any_build_import_pass": False,
                "any_executable_validation_pass": False,
                "manual_semantic_review": "pending",
            },
        )
        aggregate["candidate_count"] += 1
        aggregate["any_applicable"] |= bool(record.get("applicable"))
        aggregate["any_build_import_pass"] |= bool(record.get("build_import_pass"))
        aggregate["any_executable_validation_pass"] |= bool(record.get("executable_validation_pass"))

    rows = list(tasks.values())
    output = run_dir / "task_level_summary.json"
    by_model_group: dict[str, dict[str, int]] = {}
    for row in rows:
        key = f"{row['model_label']}::{row.get('group', 'unknown')}"
        totals = by_model_group.setdefault(
            key,
            {"tasks": 0, "any_applicable": 0, "any_build_import_pass": 0, "any_executable_validation_pass": 0},
        )
        totals["tasks"] += 1
        for metric in ("any_applicable", "any_build_import_pass", "any_executable_validation_pass"):
            totals[metric] += int(bool(row[metric]))
    write_json(
        output,
        {"created_at": utc_now(), "by_model_group": by_model_group, "task_level_records": rows},
    )
    print(json.dumps(by_model_group, ensure_ascii=False, indent=2))
    print(f"Wrote {output}")
    return 0


def command_validate_manifest(args: argparse.Namespace) -> int:
    tasks = load_tasks(Path(args.tasks).resolve())
    counts = {"small": 0, "medium": 0}
    for task in tasks:
        counts[task.group] += 1
    print(f"Manifest valid: {len(tasks)} tasks ({counts['small']} small, {counts['medium']} medium).")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("validate-manifest", help="validate task fields and leakage markers")
    check.add_argument("--tasks", required=True, help="JSONL task manifest")
    check.set_defaults(handler=command_validate_manifest)

    generate = subparsers.add_parser("generate", help="render prompts and request candidate patches")
    generate.add_argument("--tasks", required=True, help="JSONL task manifest")
    generate.add_argument("--models", required=True, help="JSON model-endpoint manifest")
    generate.add_argument("--run-dir", required=True, help="directory for immutable run artifacts")
    generate.add_argument("--template", help="prompt-template Markdown file; defaults to v2")
    generate.add_argument("--dry-run", action="store_true", help="render and log requests without API calls")
    generate.add_argument("--resume", action="store_true", help="skip existing candidate files")
    generate.add_argument("--max-tasks", type=int, help="limit tasks for a controlled pilot")
    generate.add_argument("--sleep-seconds", type=float, default=0.0, help="delay between requests")
    generate.set_defaults(handler=command_generate)

    validate = subparsers.add_parser("validate", help="apply patches and execute pre-registered commands")
    validate.add_argument("--tasks", required=True, help="JSONL task manifest")
    validate.add_argument("--run-dir", required=True, help="generation run directory")
    validate.add_argument("--resume", action="store_true", help="skip existing validation records")
    validate.add_argument(
        "--cleanup-worktrees",
        action="store_true",
        help="remove only worktrees created under this run after each validation",
    )
    validate.set_defaults(handler=command_validate)

    summarize = subparsers.add_parser("summarize", help="write task-level validation aggregates")
    summarize.add_argument("--run-dir", required=True, help="generation run directory")
    summarize.set_defaults(handler=command_summarize)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.handler(args))
    except (ManifestError, RuntimeError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
