"""Offline regression checks for the generated workflow Python blocks."""
import ast
import json
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def python_block(name, marker="python - <<'PY'"):
    text = (WORKFLOWS / name).read_text(encoding="utf-8")
    block = text.split(marker + "\n", 1)[1].split("          PY\n", 1)[0]
    return "\n".join(line[10:] for line in block.splitlines())


class RefValidationTests(unittest.TestCase):
    def test_git_branch_rules(self):
        source = python_block(
            "review-sensei-review.yml",
            'python - "$pull_json" "$EVENT_NAME" "$COMMENT_BODY" <<\'PY\'',
        )
        tree = ast.parse(source)
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "valid_ref")
        namespace = {"subprocess": subprocess}
        exec(compile(ast.Module(body=[function], type_ignores=[]), "workflow", "exec"), namespace)
        for ref in ("main", "feature/c++", "user@topic", "feature/日本語", "topic--next"):
            with self.subTest(ref=ref):
                self.assertTrue(namespace["valid_ref"](ref))
        for ref in (None, "", "-option", "bad\x00ref", "a\nb", "a..b", "a@{b", "a.lock", "a//b", "a b", "/main"):
            with self.subTest(ref=ref):
                self.assertFalse(namespace["valid_ref"](ref))


class CleanupFixture:
    """Persist remote branch/PR state across fresh simulated Actions runners."""

    def __init__(self):
        self.remote_exists = False
        self.prs = []
        self.files_exist = True
        self.calls = []
        self.fail_create = False
        self.remote_error = None
        self.commits = 0
        self.pushes = 0
        self.creates = 0

    def run(self, args, check=False, **kwargs):
        self.calls.append(args)
        status = 0
        if args[1] == "ls-remote":
            status = self.remote_error if self.remote_error is not None else (0 if self.remote_exists else 2)
        elif args[1:4] == ["diff", "--cached", "--quiet"]:
            status = int(self.files_exist)
        elif "commit" in args:
            self.commits += 1
            self.files_exist = False
        elif args[1] == "push":
            self.pushes += 1
            self.remote_exists = True
        elif args[:3] == ["gh", "pr", "create"]:
            self.creates += 1
            if self.fail_create:
                status = 1
            else:
                self.prs = [{"state": "OPEN", "url": "https://example.invalid/cleanup/1"}]
        if check and status:
            raise subprocess.CalledProcessError(status, args)
        return subprocess.CompletedProcess(args, status)

    def output(self, args, **kwargs):
        self.calls.append(args)
        return json.dumps(self.prs)

    def dispatch(self):
        source = python_block("review-sensei-uninstall.yml")
        with patch.dict(os.environ, {"DEFAULT_BRANCH": "main"}), patch.object(subprocess, "run", self.run), patch.object(subprocess, "check_output", self.output):
            try:
                exec(compile(source, "cleanup-workflow", "exec"), {})
            except SystemExit as exc:
                if exc.code != 0:
                    raise


class CleanupTests(unittest.TestCase):
    def test_repeated_dispatch_reuses_pr(self):
        fixture = CleanupFixture()
        fixture.dispatch()
        fixture.dispatch()
        self.assertEqual((fixture.commits, fixture.pushes, fixture.creates), (1, 1, 1))

    def test_recover_push_success_create_failure(self):
        fixture = CleanupFixture()
        fixture.fail_create = True
        with self.assertRaises(subprocess.CalledProcessError):
            fixture.dispatch()
        fixture.fail_create = False
        fixture.dispatch()
        self.assertEqual((fixture.commits, fixture.pushes, fixture.creates), (1, 1, 2))
        self.assertIn(["git", "fetch", "origin", "refs/heads/review-sensei/uninstall"], fixture.calls)
        self.assertIn(["git", "switch", "--create", "review-sensei/uninstall", "FETCH_HEAD"], fixture.calls)

    def test_closed_or_merged_pr_is_preserved(self):
        for state in ("CLOSED", "MERGED"):
            with self.subTest(state=state):
                fixture = CleanupFixture()
                fixture.prs = [{"state": state, "url": "https://example.invalid/cleanup/1"}]
                fixture.dispatch()
                self.assertEqual((fixture.commits, fixture.pushes, fixture.creates), (0, 0, 0))

    def test_already_absent_does_not_publish(self):
        fixture = CleanupFixture()
        fixture.files_exist = False
        fixture.dispatch()
        self.assertEqual((fixture.commits, fixture.pushes, fixture.creates), (0, 0, 0))

    def test_remote_lookup_failure_fails_closed(self):
        fixture = CleanupFixture()
        fixture.remote_error = 128
        with self.assertRaises(SystemExit):
            fixture.dispatch()
        self.assertEqual((fixture.commits, fixture.pushes, fixture.creates), (0, 0, 0))

    def test_serialized_without_cancellation_or_run_specific_branch(self):
        source = (WORKFLOWS / "review-sensei-uninstall.yml").read_text(encoding="utf-8")
        self.assertIn("concurrency:\n  group: review-sensei-uninstall\n  cancel-in-progress: false", source)
        self.assertNotIn("github.run_id", source)
        self.assertNotIn('"--force"', source.split('"git", "push"', 1)[1])


if __name__ == "__main__":
    unittest.main()
