#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/.kube/triage.kubeconfig}"
NS="${NS:-demo}"
SA="${SA:-kube-triage}"
CONTEXT="${CONTEXT:-$(kubectl config current-context)}"

mkdir -p "$(dirname "$OUT")"
SERVER="$(kubectl config view --raw --minify -o jsonpath='{.clusters[0].cluster.server}')"
CA="$(kubectl config view --raw --minify -o jsonpath='{.clusters[0].cluster.certificate-authority-data}')"
TOKEN="$(kubectl -n "$NS" create token "$SA" --duration=12h)"

cat > "$OUT" <<EOF
apiVersion: v1
kind: Config
clusters:
  - cluster:
      certificate-authority-data: ${CA}
      server: ${SERVER}
    name: kind-kube-triage
contexts:
  - context:
      cluster: kind-kube-triage
      namespace: ${NS}
      user: kube-triage
    name: kube-triage
current-context: kube-triage
users:
  - name: kube-triage
    user:
      token: ${TOKEN}
EOF
chmod 600 "$OUT"
echo "wrote $OUT for context ${CONTEXT}"
