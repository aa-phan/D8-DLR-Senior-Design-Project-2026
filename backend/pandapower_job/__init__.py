"""
The Mac side of the pandapower solver (pandapower-solver Phase 1, plan 01-06 onward).

Python 3.12, run from this checkout's own .venv with pandapower installed. It may import
`psse_job` and `psse_session.bundle` (one way: the PSS/E job and the session bundle never import
this package), and the laptop side never imports it. `raw` reads a PSS/E RAW file and refuses
anything it does not understand; `network` builds a pandapower network from what `raw` parsed.
Phase 2 extends this package into the solver engine.
"""
