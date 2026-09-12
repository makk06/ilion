# Seoul live validation

Authenticated normalizer probe at 2026-09-12 23:00 KST made four budget-charged HTTP attempts, all successful. Normalized observations are stored in `.integration-artifacts/crowd-validation/seoul.json`; the script can append another round and caps its cumulative HTTP attempts at 20.

| Official area | Code | Population range | Source time | Provider category |
|---|---|---:|---|---|
| 잠실 관광특구 | POI005 | 42,000–44,000 | 22:30 KST | 여유 |
| 홍대 관광특구 | POI007 | 68,000–70,000 | 22:30 KST | 여유 |
| 경복궁 | POI008 | 600–700 | 22:30 KST | 여유 |
| 성수카페거리 | POI068 | 14,000–16,000 | 22:30 KST | 여유 |

All returned valid nonnegative population ranges and non-replaced population. These are authenticated provider responses, not development fixtures; this does not independently verify upstream measurement accuracy. Population age already exceeded 30 minutes at collection, so successful HTTP access must not imply fresh population.

Both subway and bus recent-30-minute alighting ranges were present for all four areas. No minute-level population timestamp was available for transit, and the existing normalizer correctly marked every transit observation `collection_only`. The timestamp is collection time, not verified measurement time. These are area aggregates, not individual station or POI visitor counts. Do not sum overlapping windows or call bus+subway totals unique visitors.

There is no comparable historical transit baseline in this local DB yet. A current-to-normal arrival ratio cannot be validated or computed from these calls alone. Current code excludes the transit score until the same area/mode/window/weekday/hour has four sample days and a median at least 10. Historical collection-only timestamps can still introduce time alignment uncertainty; current quality cap is 0.6.

Code inspection: `save_citydata` deduplicates population by source time, and skips unchanged collection-only transit fingerprints, so repeat fetches do not reset stored freshness. The probe did not insert observations into production observation tables.

## Repeated live observations

Three rounds completed at 23:00:20, 23:06:29 and 23:12:35 KST (12 charged HTTP attempts, all successful). Each area's source population time advanced 22:30 → 22:35 → 22:40. This supports live progression over the measured 12-minute collection interval, while showing 30.3 → 31.5 → 32.6 minute source age. It does not establish day-long availability or exact provider refresh timing.

Population ranges across the three rounds: 잠실 42–44k → 40–42k → 40–42k; 홍대 68–70k → 68–70k → 66–68k; 경복궁 600–700 throughout; 성수 14–16k throughout. All provider categories remained 여유 and all population observations were non-replaced.

All 24 transit records remained `collection_only`. Seven of eight transit fingerprints changed from round one to two; 경복궁 bus stayed identical (0–10 arrivals and departures). All eight changed from round two to three. The stored comparisons report timestamp advancement and unchanged fingerprints. An unchanged range alone cannot prove a frozen upstream observation; fingerprint deduplication is a conservative safeguard with an ambiguity for naturally steady low-volume traffic.

Final extension: rounds four and five completed at 23:18:29 and 23:24:21 KST. Total **20 HTTP attempts, 20 successes**, five samples per area, source times **22:30, 22:35, 22:40, 22:50, 22:55** (25 minutes of source history; about 24 minutes of collection). Last two ages were approximately 28.49 and 29.36 minutes; all 40 transit records were collection-only. No further network calls are permitted by this probe's cap.

The diagnostic replay uses real captured population with an explicitly assumed unknown area profile and area-scope mapping, excluding transit because its comparable baseline is absent. It is not a POI accuracy evaluation. Before the coordinator's EWMA fix, the first four samples retained history lengths 0,0,0,1 because pruning used wall-clock age. After the coordinator changed retention to source-observation time, replay retained **1,2,3,4,5** samples for each area. Freshness remained stale and the trend age gate remained false throughout: samples are older than 10 minutes even when five observations spanning 25 source minutes exist. See `seoul_replay.py` and `seoul-replay.json`.

Operational constraint: the conservative daily 1,000-call global limit gives 800 regular calls, producing a 220-minute full-121-area interval. This exceeds population TTL 60 minutes and transit TTL 30 minutes. Ideal maximum hourly population coverage is approximately 27.3%, below the empirical distribution gate of 70%; 30-minute upstream delay makes live usefulness worse. More elapsed collection days alone cannot solve that scheduling gap. Preserve evidence gates; resolve approved quota and collection strategy explicitly.

## Budget arithmetic

- Samples per area/day at 220 minutes: `1440/220 = 6.545`.
- Upper bound on distinct hourly buckets: `6.545/24 = 27.27%`; repeated source timestamps can reduce this further.
- Theoretical daily calls for 70% hourly coverage: `121*24*0.7 = 2032.8` regular calls, therefore at least `ceil(2032.8/0.8) = 2541` approved total calls. This is a necessary aggregate bound, not sufficient proof of coverage.
- A 5-minute-rounded interval no greater than 85 minutes needs at least `ceil(1440*121/85) = 2050` regular calls; the smallest integer approved limit giving 2050 regular calls after `int(0.8*limit)` is 2563.
- With a consistent 30-minute upstream population delay, remaining useful TTL is 30 minutes: ideal useful time fraction `30/220 = 13.64%`. This is a scenario using observed delay, not a measured long-term uptime.
- Five-minute collection of every area needs `121*288 = 34848` regular calls/day and `43560` approved calls at an 80% budget.
- An 84-day window has 12 occurrences of each weekday. With time coverage 27.27%, mean distinct sample days per weekday/hour is only `12*0.2727 = 3.27`, below the conditional four-day gate. Some cells may reach four, but all cells cannot do so under this aggregate budget.
