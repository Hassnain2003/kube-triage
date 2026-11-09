CLUSTER ?= kube-triage
NS ?= demo
PYTHON ?= $(firstword $(wildcard .venv/bin/python) python3)
export NS

.PHONY: help cluster-up cluster-down restore demo eval test lint rbac-check \
	fault-crashloop_bad_config fault-oomkilled fault-imagepull_wrong_tag \
	fault-readiness_dependency_down fault-wrong_dependency_url fault-worker_backlog

help:
	@echo "cluster-up / cluster-down  kind cluster with demo-app"
	@echo "demo                       inject crashloop, run agent, restore"
	@echo "eval                       5 runs per fault with rule-based scoring"
	@echo "test / lint                pytest + ruff"
	@echo "fault-* / restore          reversible fault injection"

cluster-up:
	kind create cluster --name $(CLUSTER) --config kind.yaml || true
	docker build -t kube-triage-orders:dev demo-app/orders
	docker build -t kube-triage-worker:dev demo-app/worker
	kind load docker-image kube-triage-orders:dev kube-triage-worker:dev --name $(CLUSTER)
	kubectl apply -f demo-app/k8s
	kubectl -n $(NS) rollout status deploy/redis --timeout=120s
	kubectl -n $(NS) rollout status deploy/orders --timeout=180s
	kubectl -n $(NS) rollout status deploy/worker --timeout=120s
	./scripts/write_triage_kubeconfig.sh .kube/triage.kubeconfig

cluster-down:
	kind delete cluster --name $(CLUSTER)

restore:
	kubectl apply -f demo-app/k8s
	kubectl -n $(NS) scale deploy/redis --replicas=1
	kubectl -n $(NS) rollout restart deploy/orders deploy/worker deploy/redis
	kubectl -n $(NS) rollout status deploy/redis --timeout=120s
	kubectl -n $(NS) rollout status deploy/orders --timeout=180s
	kubectl -n $(NS) rollout status deploy/worker --timeout=120s

fault-crashloop_bad_config:
	kubectl -n $(NS) patch configmap orders-config --type merge -p '{"data":{"CRASH_ON_START":"1"}}'
	kubectl -n $(NS) rollout restart deploy/orders

fault-oomkilled:
	kubectl -n $(NS) patch configmap orders-config --type merge -p '{"data":{"ALLOCATE_MB":"64"}}'
	kubectl -n $(NS) patch deploy/orders --type json -p '[{"op":"replace","path":"/spec/template/spec/containers/0/resources/limits/memory","value":"32Mi"},{"op":"replace","path":"/spec/template/spec/containers/0/resources/requests/memory","value":"16Mi"}]'

fault-imagepull_wrong_tag:
	kubectl -n $(NS) set image deploy/orders orders=busybox:this-tag-does-not-exist-kube-triage
	kubectl -n $(NS) patch deploy/orders --type json -p '[{"op":"replace","path":"/spec/template/spec/containers/0/imagePullPolicy","value":"Always"}]'

fault-readiness_dependency_down:
	kubectl -n $(NS) scale deploy/redis --replicas=0

fault-wrong_dependency_url:
	kubectl -n $(NS) patch configmap orders-config --type merge -p '{"data":{"REDIS_HOST":"redis.invalid"}}'
	kubectl -n $(NS) rollout restart deploy/orders

fault-worker_backlog:
	kubectl -n $(NS) set env deploy/worker WORKER_STUCK=1
	kubectl -n $(NS) rollout status deploy/worker --timeout=120s
	kubectl -n $(NS) exec deploy/orders -- python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/orders', data=b'', timeout=5)" || true

rbac-check:
	./scripts/check_rbac.sh

demo: cluster-up
	$(MAKE) fault-crashloop_bad_config
	@echo "waiting for CrashLoopBackOff"
	@for i in 1 2 3 4 5 6 7 8 9 10 11 12; do \
	  kubectl -n $(NS) get pods | grep -q CrashLoopBackOff && break; \
	  sleep 5; \
	done
	KUBECONFIG=.kube/triage.kubeconfig $(PYTHON) -m kube_triage.cli --namespace $(NS)
	$(MAKE) restore

eval:
	$(PYTHON) -m kube_triage.eval_harness

test:
	$(PYTHON) -m pytest --cov=kube_triage --cov-report=term-missing

lint:
	$(PYTHON) -m ruff check src tests
	$(PYTHON) -m ruff format --check src tests
