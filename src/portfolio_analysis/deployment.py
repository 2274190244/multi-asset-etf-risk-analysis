"""Lazy, offline initialization for a fresh Streamlit deployment.

Only the default missing result package is generated. Existing archives and
explicit user-selected directories remain read-only. No market requests occur.
"""
from pathlib import Path
import errno
import threading

from .research_bundle import build_bundle, REQUIRED_TABLES
from .research_display import read_table, result_root

_BUILD_LOCK = threading.Lock()


def default_results_missing(root):
    """Return whether the default package may be created for this repository.

    An explicit ETF_RESEARCH_RESULTS setting is an operator choice, including
    when it points to a missing path. Never replace that choice with a demo.
    """
    import os
    root = Path(root)
    return (not os.environ.get("ETF_RESEARCH_RESULTS")
            and result_root(root) == root / "research_results"
            and not (root / "research_results").exists())


def ensure_default_results(root):
    """Create the missing default package once; return True only if built here.

    Serializes sessions within a Streamlit process. Across processes the
    existing builder publishes by atomic rename without replacing saved results;
    a losing worker accepts a competing publication only after table validation.
    Errors propagate to the startup UI. Failed calculations are not cached.
    """
    root = Path(root)
    with _BUILD_LOCK:
        if not default_results_missing(root):
            return False
        built_here = True
        try:
            build_bundle(root / "research_results", inputs=root / "data/research_demo")
        except OSError as error:
            race = isinstance(error, FileExistsError) or error.errno == errno.ENOTEMPTY
            if not race or not (root / "research_results").is_dir():
                raise
            built_here = False
        for phase, names in REQUIRED_TABLES.items():
            for name in names:
                read_table(root, phase, name)
        return built_here
