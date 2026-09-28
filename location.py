#!/usr/bin/env python3
"""
Backwards-compatibility shim.

The engine now lives in the `locan` package (see locan/__init__.py). This module
keeps `import location` and the `location:main` console script working; new code
should import from `locan` directly.
"""

from locan import *  # noqa: F401,F403  (re-export the public API)
from locan import (  # noqa: F401  (names used by app.py and scripts)
    cache,
    cli,
    config,
    corrections,
    geo,
    guardrail,
    llm,
    logging_utils,
    pipeline,
    ratelimit,
    report,
    reviews,
    scoring,
    scraper,
    sentiment,
    ui,
    verify,
)
from locan.cli import main  # noqa: F401

if __name__ == "__main__":
    main()
