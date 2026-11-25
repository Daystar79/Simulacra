# Runtime Optimization Results — Resident Character Architecture

Baseline: `main` before optimization. Optimized: this branch. All numbers are
measured on the same VM with `benchmarks/bench_runtime.py` (deterministic
event script, 25 events, medians over the run). Machine-dependent absolute
values; ratios are the meaningful comparison.

## Measured comparison

| Metric | Baseline | Optimized | Change |
|---|---|---|---|
| Cold character initialization | 6.3 ms | 9.8 ms | +3.5 ms one-time (WAL setup + separate hydrate persist) |
| CLI-style prepare (per event) | 7.7 ms | 7.7 ms | unchanged (dominated by the Golem tick) |
| CLI-style resolve (per event) | 2.9 ms | 0.35 ms | **-88%** (resident card replaces per-reply YAML parse) |
| Resident wake (per event, no instrumentation) | ~36 ms | ~23 ms | **-37%** |
| Runtime row size | 3,345 B | 1,384 B | **-59%** (hydrated character no longer rewritten per event) |
| tracemalloc peak per resident run | 264 KB | 232 KB | -12% |
| Serialized request bytes | 12,533 B | 12,533 B | identical packet (behavioral equivalence) |
| SQLite reads/writes per wake | 21.8 / 7.6 | 21.8 / 7.6 | unchanged; per-wake *connections* 6 → 1 |

## Host packet size — compact context and at-rest omission

`golem modularization` follow-up, measured with the same 25-event script
(`compact_request_bytes_median` is now emitted by the benchmark):

| Metric | Value |
|---|---|
| Stored request bytes (SQLite, `request_bytes_median`) | 12,549 B, unchanged — full fidelity returned by `pending` and `compact=False` |
| Host-facing compact packet (`compact_request_bytes_median`) | 5,499 B (**-56%**) |
| 7-exchange session, per-tick compact packet | 2,636 B first tick (was 2,990), 3,808 B after six exchanges (was 4,244) |

Mechanisms: compact decision context is now the `wake_character` default; body
fields at their resting value (`0`, `false`, `none`, empty `somatic_map`) are
omitted from the compact projection; older recent-episode entries cap
context/reply text at 120 characters (current turn keeps 320); CLI `prepare`
prints tight JSON separators. Physiology, snapshots, rules, `next_history`,
and the stored request are unchanged (109/109 tests, byte-identical tick
fixtures).

## What changed

1. **Resident character instance.** `load_cached_character` memoizes the
   hydrated (state, card, durable) triple per process, keyed by card/log path,
   slug, character id, file mtimes, and pending goal changes. A resident host
   hydrates once and reuses the instance between wakes. The tick path no longer
   deep-copies the state via a JSON round trip: `run_golem` is read-only over
   state (8 reads, 0 writes, verified by test and by audit), so the shared
   instance is safe. Any card or log file change rehydrates automatically.
2. **Hydrate persisted in its own table.** The hydrated character moved from
   the `runtime` row to `character_cache(id, data)`. The runtime row, which is
   rewritten on every event, no longer carries the full character state.
   Legacy databases migrate transparently on first read: the embedded blob is
   moved to the cache table and the row is rewritten once.
3. **One connection per wake.** `wake_character` opens one SQLite connection
   and commits each stage (`BEGIN IMMEDIATE` per stage) on it, instead of
   opening and closing a connection per stage. Durability contract is
   unchanged: the event and body tick are committed before host inference
   work starts, and each stage remains transactional.
4. **WAL + synchronous=NORMAL.** Databases switch to WAL journal mode with
   `synchronous=NORMAL` (durable under WAL), removing the rollback-journal
   fsync from every commit. WAL persists in the database file; existing
   multi-host file locking is unaffected.
5. **ensure_activity_schema memo.** The idempotent schema-ensure work runs
   once per database per process (validated against the db file mtime),
   instead of on every transaction.

## Behavioral equivalence evidence

- Full test suite passes (95 tests, 1 skip), including the request-content
  assertions (identity anchor, emotions, body values, memory recall).
- The serialized pending-request bytes are identical to baseline (12,533 B
  median) for the same event script: the inference packet is unchanged.
- Golem's physiology and arithmetic are untouched; deltas are confined to
  state loading, storage layout, and connection management.

## Request size and 8B model context

The compact wake request is the *inference packet* (identity anchor, stimulus,
current body, relevant memories/expectations/goals, recent window, guidance):
12.5 KB ≈ 3,100 tokens of ASCII, already inside the 2,000-4,000 token target
without truncating decision-relevant context. Namespace note: `request` and
`wake_character` hosts share one 8B model by construction; each character's
packet is built from its own database. Stable identity conditioning and
framework guidance are cacheable prompt prefixes for backends that support
prefix/KV caching; that remains a host-side, backend-specific option.

## Remaining limitations and risks

- Absolute timings are VM-bound; rerun `benchmarks/bench_runtime.py` on target
  hardware for deployment-relevant numbers.
- Cold initialization pays ~3 ms more (WAL setup plus hydrate persistence).
- Between process restarts the CLI pays one JSON parse of the hydrate from
  `character_cache` (cheaper than YAML, only on the first op per process).
- Inline model inference latency, quantized-8B throughput, and KV-cache hit
  ratios require hardware testing outside this VM.
- The linter's embedded cache vocabulary and `Muse.AI` guidance are untouched.

## Reproduce

```bash
python3 benchmarks/bench_runtime.py --events 25 --json results.json
```
