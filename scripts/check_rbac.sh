#!/usr/bin/env bash
# Prove the triage ServiceAccount cannot mutate the cluster or read Secrets.
set -euo pipefail
NS="${NS:-demo}"
AS="system:serviceaccount:${NS}:kube-triage"

fail=0
expect_no() {
  local verb="$1"
  local resource="$2"
  local extra="${3:-}"
  if kubectl auth can-i "$verb" "$resource" --as="$AS" -n "$NS" $extra | grep -qx yes; then
    echo "FAIL: $AS can $verb $resource (expected no)"
    fail=1
  else
    echo "ok: $AS cannot $verb $resource"
  fi
}

expect_yes() {
  local verb="$1"
  local resource="$2"
  if kubectl auth can-i "$verb" "$resource" --as="$AS" -n "$NS" | grep -qx yes; then
    echo "ok: $AS can $verb $resource"
  else
    echo "FAIL: $AS cannot $verb $resource (expected yes)"
    fail=1
  fi
}

expect_yes get pods
expect_yes list pods
expect_yes watch pods
expect_yes get deployments.apps
expect_yes get configmaps
expect_yes get events
expect_yes get services
expect_yes get endpoints

expect_no create pods
expect_no update pods
expect_no delete pods
expect_no patch pods
expect_no create deployments.apps
expect_no update deployments.apps
expect_no delete deployments.apps
expect_no patch deployments.apps
expect_no create configmaps
expect_no patch configmaps
expect_no delete configmaps
expect_no get secrets
expect_no list secrets
expect_no watch secrets
expect_no create secrets
expect_no update secrets
expect_no delete secrets
expect_no patch secrets

if [[ "$fail" -ne 0 ]]; then
  echo "RBAC check failed"
  exit 1
fi
echo "RBAC check passed: mutate and secrets access are denied"
