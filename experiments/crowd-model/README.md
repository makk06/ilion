# Offline crowd model selection

From the repository root (PowerShell):

```powershell
& '.integration-venv/Scripts/python.exe' -B 'experiments/crowd-model/run.py'
& '.integration-venv/Scripts/python.exe' -B -m unittest discover -s 'experiments/crowd-model' -p 'test_*.py' -v
```

Requires the existing NumPy and Django environment and local captured files in
`.integration-artifacts/crowd-validation`. No API request, download or new dependency.
The default output is `experiments/crowd-model/results`, plus the root
`MODEL_SELECTION_REPORT.md`. `--output PATH` changes the JSON destination; the report
always remains at the repository root. The captured inputs are not redistributed here;
the manifest identifies them by SHA-256.

Only the 20 deduplicated population rows in `seoul.json` train the auxiliary models.
Context captures are used for audit and the separate original heuristic function replay.
SQLite files are opened read-only for counts. Backend Python, database and environment
file hashes are checked before/after; hashes of secrets are not exported. Network
connections are blocked, and the heuristic replay rejects ORM queries.

`metrics.json` contains fixed folds, training states, per-row errors and ablations.
`synthetic_checks.json` contains target-mutation checks, never extra observations.
`timings.json` and heuristic timing are nondeterministic measurements; model parameters,
predictions and errors are deterministic. Training diagnostics are resubstitution,
not forward predictions. A 20-row assertion intentionally stops unreviewed dataset changes.

The auxiliary target is provider area population, not crowd labels. All results are
`retrospective_auxiliary`: source observations all precede the first actual receipt.
The production heuristic and its low-confidence prior fallback remain unchanged.

## Validation completion

```powershell
& '.integration-venv/Scripts/python.exe' -B 'experiments/crowd-model/complete_validation.py'
```

Runs the experiment tests, Django check/full regression suite, Flutter crowd contract,
and two separate offline replays. Writes `completion-results/evidence.json`, command logs,
replay hashes, and root `VALIDATION_COMPLETION_REPORT.md`. A failed required command
returns a nonzero exit code and marks stage 1 FAIL. The Flutter SDK path uses this
workspace's existing Windows installation; no SDK or package installation is performed.

`area_validation.py` is a separate read-only assessment, not a production scheduler.
It groups area-core evaluations by model version, baseline policy and horizon, requires
100 paired labels/7 KST issue dates/2 areas/weekdays and weekends, and resamples complete
issue-date clusters 2,000 times with a fixed seed. Insufficient labels remain BLOCKED.
Only synthetic tests exercise its PASS/FAIL branches while the real evaluation table is empty.
