# Mistral cloud task — Modularize Golem

Work in the Simulacra checkout that contains `scripts/relationship_memory.py`. Extract the stages of Golem’s Python body tick into modules. Keep the tick deterministic and leave behavioral decisions to Simulacra and its host.

## Establish a baseline

Read `scripts/golem.py`, especially `run_golem`, together with `scripts/golem_loop.py`, `scripts/relationship_memory.py`, `scripts/run.py`, and `deploy_framework.py`. Identify callers that import Golem and callers that execute scripts directly. From the repository root, record the starting commit, test results, and benchmark timings.

```sh
python3 -m unittest discover -s tests
python3 benchmarks/bench_runtime.py --events 10
```

Capture complete tick outputs using fixed synthetic cards, event times, stimuli, and histories. Cover a same-instant appraisal, a long idle interval, a switch between two speakers, and two independent character databases.

## Extract the stages

1. Start with leaf functions such as `event_clock` and somatic calibration. Trace the inputs and outputs of autonomic response, affect, and drive arbitration before extracting those stages one at a time.
2. Keep `run_golem(state, stimulus, realm_data, history)` as the orchestrator. Preserve existing imports, defaults, stage order, snapshots, triggered rules, and `next_history`. Keep tick state local to each call and retain the existing host entry points.
3. Keep relationship persistence in `scripts/relationship_memory.py`. The event loop supplies the active speaker’s bond, Golem calculates bodily state, and Simulacra chooses a response. Preserve private database ownership, speaker routing, elapsed-time drift, transaction boundaries, pending-turn recovery, and delivery retries.
4. Add each extracted runtime module to the in-place updater in `deploy_framework.py`. Exercise an updated installation through `scripts/run.py` and direct package imports.

## Verify and report

Compare the complete tick outputs with the saved baseline, including history after each event. Rerun the test suite and benchmark using the commands above. Leave the changes in the cloud checkout for review and report the modules extracted, compatibility results, before-and-after timings, and any remaining failures.
