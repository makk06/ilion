# Mean crowd experiment

Implementation and operating instructions: [docs/mean-crowd.md](../../docs/mean-crowd.md).

`candidates.json` records the three initial area IDs and the existing official geometry provenance used to derive weather grids. It contains no API keys. `results/data-audit.json`, `validation.json` and `shadow.json` are actual local command outputs, not synthetic performance claims.

Current implementation verification:

- Django full regression: **168 passed**, including **36 mean forecast/study tests**.
- Flutter full regression: **84 passed**, including **4 crowd contract tests**.
- Flutter analysis: **no issues**.
- Flutter web build: **passed**.
- Django migration 0008: applied locally; model/migration drift check passed.
- A real Seoul population response passed through the new archive; one usable population observation is present, but no valid hourly training labels yet.
- Backtest and shadow accuracy: **NEEDS_MORE_DATA**. No production promotion.

The study is initialized with three candidates and a quota-derived **10-minute** source polling interval (1,000 Seoul requests/day; existing 20% headroom retained). The existing collector handles hourly shadow jobs when invoked. No new background OS task was installed. Use the existing minute-based `ops/collect-crowd.ps1` scheduling mechanism to keep collection running.

There was one initial failed sandboxed provider attempt; a subsequent direct, quota-accounted request succeeded. API connectivity is distinct from data coverage and forecasting accuracy. Event-area mappings still require verified input rather than inferred proximity.

No neural model, new dependency, or generated training observations were added. Source evidence has a 400-day retention limit; input replay explicitly fails when referenced evidence has expired or changed.
