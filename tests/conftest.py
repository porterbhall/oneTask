import os

import pytest


@pytest.fixture(autouse=True)
def clean_onetask_env(monkeypatch):
    """Isolate every test from the developer's real shell environment.

    Found during v2.6.0 release prep (2026-09-17): without this, ONETASK_*
    vars set in a real shell profile (ONETASK_PASSWORD for LAN access,
    ONETASK_DEFAULT_DURATION for a personal default, etc.) leak into the
    Flask test client and cause spurious 401s / wrong-default-duration
    failures that look like real regressions but are pure environment noise.
    Prefix-matched rather than an explicit list so a newly added ONETASK_*
    var (e.g. ONETASK_ESTIMATE_BUTTONS) is covered automatically.
    """
    for var in list(os.environ):
        if var.startswith('ONETASK_'):
            monkeypatch.delenv(var, raising=False)
