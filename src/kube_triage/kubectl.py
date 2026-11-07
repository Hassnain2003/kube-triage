"""Thin kubectl subprocess wrapper used by read-only tools."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Sequence


class KubectlError(RuntimeError):
    def __init__(self, args: Sequence[str], returncode: int, stderr: str) -> None:
        self.args_list = list(args)
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(f"kubectl {' '.join(args)} failed ({returncode}): {stderr.strip()}")


def run_kubectl(
    args: Sequence[str],
    *,
    timeout: int = 30,
    kubeconfig: str | None = None,
) -> str:
    env = os.environ.copy()
    if kubeconfig:
        env["KUBECONFIG"] = kubeconfig
    proc = subprocess.run(
        ["kubectl", *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    if proc.returncode != 0:
        raise KubectlError(args, proc.returncode, proc.stderr or proc.stdout)
    return proc.stdout
