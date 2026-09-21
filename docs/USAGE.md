# Loop workflow

## Run the local example

```sh
python3 kit.py inspect
python3 kit.py run
python3 kit.py status
python3 kit.py resume
```

The deterministic worker needs two attempts in the example. Each result is independently tested. Resuming a completed run verifies its recorded inputs and any retained successful JUnit report, then returns the same run without invoking the worker again. Missing or changed evidence is rejected.

## Configure a real goal

Edit `.agentkit/loop.json`:

- `goal`: a concrete intended result.
- `worker`: `provider` and a declared command receiving a JSON task on stdin.
- `verifier`: a command and `format` (`exit` or `junit`).
- `protected_inputs`: requirements, test code and other files the worker must not change.
- `progress_inputs`: files whose changes count as observable progress.
- `max_attempts`, `max_seconds`, `stagnation_limit`, `backoff_seconds`: finite execution limits.

The verifier must not modify the product. An exit-format verifier uses its process result as the declared contract; a JUnit verifier also requires actual nonempty test results with no errors/skips and consistent totals. The quality of a verification criterion is still the operator's responsibility.

## Use an installed provider

```sh
python3 kit.py configure-agent claude
python3 kit.py run --allow-agent --new
```

Use `codex` instead of `claude` to choose that preset. Configure your real goal, protected inputs and verifier first. The opt-in allows model use for this command; it does not change account permissions or grant a general spending authorization. The preset and local runner have their own bounds. A command provider cannot offer a universal hard token/cost cap: configure a provider-supported limit and account budget when needed.

## Stop and resume contracts

States include `running`, `completed`, `blocked`, `exhausted` and `interrupted`. Worker errors stop the run. Verification failure feeds a bounded excerpt back to the next attempt. Repeated failure with unchanged declared product hashes stops at `stagnation_limit`; varying log timestamps do not count as progress.

Starting over requires `run --new`; previous records are archived. Configuration/protected-input changes require a new run. An interrupted attempt may already have side effects, so `resume --retry-interrupted` requires inspection rather than promising exactly-once execution. Attempt and elapsed-time budgets persist across resume. A killed controller can leave a lock; inspect the recorded owner/process first, then use `unlock --token <exact-token>` only after it has stopped. The tool will not silently steal a live lock.

There is no hidden daemon or automatic external scheduler. Invoke `run` from your chosen scheduler/event system if recurrence is needed; the project lock prevents overlapping local writers.
