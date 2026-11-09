from __future__ import annotations

import pytest

from kube_triage.kubectl import KubectlError, run_kubectl


def test_run_kubectl_success(monkeypatch: pytest.MonkeyPatch) -> None:
    class Result:
        returncode = 0
        stdout = "ok\n"
        stderr = ""

    monkeypatch.setattr("kube_triage.kubectl.subprocess.run", lambda *a, **k: Result())
    assert run_kubectl(["get", "pods"], kubeconfig="/tmp/kc") == "ok\n"


def test_run_kubectl_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class Result:
        returncode = 1
        stdout = ""
        stderr = "denied"

    monkeypatch.setattr("kube_triage.kubectl.subprocess.run", lambda *a, **k: Result())
    with pytest.raises(KubectlError) as exc:
        run_kubectl(["delete", "pod", "x"])
    assert "denied" in str(exc.value)
    assert exc.value.returncode == 1
