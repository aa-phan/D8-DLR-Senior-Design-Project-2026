"""
The laptop side of the pandapower reference session (pandapower-solver Phase 1, plan 01-02).

`psse_session.session` is the one command a teammate runs on the PSS/E laptop and
`psse_session.bundle` holds the work folder, the manifest, the verified zip and the masked
summary. Standard library plus psse_job only, Python 3.7 syntax in the psse_job style. This
package never imports pandapower, and it never imports psspy: psspy is reached only through the
loader that backend/psse_pandapower_session.py passes in, so the repository keeps its one psspy
import (psse_run_hourly.load_psspy).
"""
