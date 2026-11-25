"""Per-stage functions of the Golem body tick.

Each module holds one stage of the deterministic tick pipeline in the
original run_golem order. golem.run_golem orchestrates them with a
per-tick context object; the stage functions carry no module state.
"""
