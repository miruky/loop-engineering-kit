from pathlib import Path
from agentkit import engine
from agentkit.core import KitError, load_json, write_json, state_path, confined
from test_core import ProjectCase


class LoopWorkflow(ProjectCase):
    def test_allowed_large_output_does_not_make_completed_state_unreadable(self):
        cfg = engine.configuration(self.root)
        cfg["worker"] = {"provider":"command", "command":self.command("print('x'*(9*1024*1024))", max_output_bytes=10*1024*1024)}
        cfg["verifier"] = {"format":"exit", "command":self.command("print('verified')")}
        write_json(self.root, engine.CONFIG, cfg)
        finished = engine.run(self.root)
        self.assertEqual(finished["status"], "completed")
        self.assertEqual(engine.run(self.root, resume=True), finished)
        self.assertLess((self.root / state_path("loop")).stat().st_size, 100000)
    def test_verifier_configuration_change_cannot_complete_the_run(self):
        cfg = engine.configuration(self.root)
        cfg["worker"] = {"provider": "command", "command": self.command("print('work')")}
        cfg["verifier"] = {"format": "exit", "command": self.command(
            "import json;from pathlib import Path;p=Path('.agentkit/loop.json');"
            "c=json.loads(p.read_text());c['max_attempts']=9;p.write_text(json.dumps(c))")}
        write_json(self.root, engine.CONFIG, cfg)
        self.assertCode("STALE_INPUTS", lambda: engine.run(self.root))
        self.assertEqual(engine.status(self.root)["status"], "blocked")
    def config(self, function):
        value = engine.configuration(self.root)
        function(value)
        write_json(self.root, engine.CONFIG, value)
    def test_worker_verifier_feedback_reaches_verified_completion(self):
        result = engine.run(self.root)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(result["attempts"]), 2)
        self.assertFalse(result["attempts"][0]["verification"]["ok"])
        self.assertTrue(result["attempts"][1]["verification"]["ok"])
    def test_model_saying_done_cannot_pass_failing_verification(self):
        self.config(lambda c: c["worker"].update(command=self.command("print('All done and verified!')")))
        result = engine.run(self.root)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "repeated_failure")
    def test_changing_logs_without_changing_product_is_stagnation(self):
        self.config(lambda c: c["worker"].update(command=self.command("import time; print(time.time())")))
        result = engine.run(self.root)
        self.assertEqual(result["reason"], "repeated_failure")
        self.assertEqual(len(result["attempts"]), 2)
    def test_attempt_limit_is_not_reset_by_failure(self):
        self.config(lambda c: c.update(max_attempts=1))
        result = engine.run(self.root)
        self.assertEqual(result["status"], "exhausted")
        self.assertEqual(result["reason"], "attempt_limit")
        self.assertEqual(len(result["attempts"]), 1)
    def test_worker_timeout_blocks_instead_of_retrying_forever(self):
        self.config(lambda c: c["worker"].update(command=self.command("import time;time.sleep(10)", timeout=.1)))
        result = engine.run(self.root)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "timeout")
    def test_protected_input_changes_halt_the_run(self):
        code = "from pathlib import Path;Path('project/docs/requirements.md').write_text('weakened')"
        self.config(lambda c: c["worker"].update(command=self.command(code)))
        self.assertCode("STALE_INPUTS", lambda: engine.run(self.root))
        self.assertEqual(engine.status(self.root)["status"], "blocked")
    def test_verifier_may_not_modify_the_product(self):
        code = "from pathlib import Path;Path('project/app/result.json').write_text('{}')"
        self.config(lambda c: c.update(verifier={"format": "exit", "command": self.command(code)}))
        self.assertCode("STALE_INPUTS", lambda: engine.run(self.root))
    def test_provider_invocation_requires_explicit_opt_in(self):
        self.config(lambda c: c["worker"].update(provider="claude"))
        self.assertCode("AGENT_OPT_IN", lambda: engine.run(self.root))
        self.assertFalse(confined(self.root, state_path("loop")).exists())
    def test_existing_run_is_not_overwritten_implicitly(self):
        first = engine.run(self.root)
        self.assertCode("STATE_EXISTS", lambda: engine.run(self.root))
        self.assertEqual(engine.status(self.root)["id"], first["id"])
    def test_completed_resume_is_idempotent_and_checks_new_drift(self):
        first = engine.run(self.root)
        resumed = engine.run(self.root, resume=True)
        self.assertEqual(first["attempts"], resumed["attempts"])
        p = self.root / "project/app/result.json"
        p.write_text(p.read_text() + " ")
        self.assertCode("STALE_INPUTS", lambda: engine.run(self.root, resume=True))
    def test_interrupted_resume_requires_confirmation(self):
        state = engine.run(self.root)
        state["status"] = "interrupted"
        write_json(self.root, state_path("loop"), state)
        self.assertCode("RETRY_CONFIRMATION", lambda: engine.run(self.root, resume=True))
        result = engine.run(self.root, resume=True, retry_interrupted=True)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(result["attempts"]), 3)
    def test_resume_cannot_change_budget_or_verifier(self):
        engine.run(self.root)
        self.config(lambda c: c.update(max_attempts=99))
        self.assertCode("STALE_INPUTS", lambda: engine.run(self.root, resume=True))
