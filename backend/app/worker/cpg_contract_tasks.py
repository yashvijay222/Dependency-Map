"""Optional bridge from hosted workers to the offline CPG invariant scorer."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


def run_cpg_contract_score_sync(
    repo_root: str,
    out_dir: str,
    base: str,
    head: str,
) -> dict[str, Any]:
    """Run :func:`cpg_builder.scorer.score_repository` on a materialized repo directory.

    Intended for Celery workers that already extracted a repository to ``repo_root``.
    """
    from cpg_builder.scorer import score_repository

    root = Path(repo_root)
    out = Path(out_dir)
    if not root.is_dir():
        raise FileNotFoundError(f"repo_root is not a directory: {root}")
    out.mkdir(parents=True, exist_ok=True)
    artifacts = score_repository(root, out, base=base, head=head)
    log.info(
        "cpg contract score finished run_id=%s surfaced=%s",
        artifacts.run_id,
        len(artifacts.violations),
    )
    return {
        "run_id": artifacts.run_id,
        "run_metadata": artifacts.run_metadata,
        "violations_count": len(artifacts.violations),
        "out_dir": str(out),
    }
