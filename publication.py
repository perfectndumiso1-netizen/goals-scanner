"""Transactional stage boundary for app-data publication.

The scanner supplies three explicit operations: build the staging tree, validate it,
and promote it. A failed validation leaves the live publication untouched.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class PublicationResult:
    published: bool
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def publish(staging: Path, build: Callable[[], None],
            validate: Callable[[], tuple[list[str], list[str]]],
            promote: Callable[[], None]) -> PublicationResult:
    """Run one publication transaction using caller-owned stage operations.

    `build` writes only into `staging`; `validate` returns (errors, warnings); and
    `promote` applies the validated export to its destination. Validation failures
    never call `promote`; destination-specific code owns rollback if promotion fails.
    Staging is removed on both success and failure.
    """
    staging = Path(staging)
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)
    try:
        build()
        errors, warnings = validate()
        if errors:
            return PublicationResult(False, tuple(errors), tuple(warnings))
        promote()
        return PublicationResult(True, (), tuple(warnings))
    finally:
        shutil.rmtree(staging, ignore_errors=True)
