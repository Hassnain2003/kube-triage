# kube-triage eval results

Numbers in this file come from `make eval` in this repository. They are not estimates.

## Environment

- Date (UTC): 2026-11-09
- Git commit: `792828fc44ae25d14341bfe60c8e4c1cbb90d7d1`
- Model: `openai/gpt-oss-120b`
- kind: kind v0.30.0 go1.24.6 linux/amd64
- kubectl: Client Version: v1.31.4
- Hardware: 8 CPUs; `Linux xaidi-Latitude-5400 7.0.0-42-generic #42-Ubuntu SMP PREEMPT_DYNAMIC Thu Oct 15 08:06:44 UTC 2026 x86_64 GNU/Linux`
- Command: `make eval`

## Per-fault accuracy (5 runs)

| Fault | Correct | Evidence cited | Mean tool calls | Mean input tokens | Mean output tokens | Mean seconds | 429 retries |
| --- | --- | --- | --- | --- | --- | --- | --- |
| crashloop_bad_config | 5/5 | 5/5 | 14.6 | 7509 | 1395 | 27.7 | 0 |
| oomkilled | 0/5 | 1/5 | 15.4 | 6324 | 1582 | 29.8 | 2 |
| imagepull_wrong_tag | 5/5 | 5/5 | 17.6 | 7198 | 1139 | 22.0 | 6 |
| readiness_dependency_down | 5/5 | 5/5 | 20.6 | 7763 | 1403 | 43.2 | 10 |
| wrong_dependency_url | 5/5 | 5/5 | 21.0 | 8682 | 1670 | 36.7 | 13 |
| worker_backlog | 5/5 | 5/5 | 19.0 | 7351 | 2027 | 29.5 | 19 |

## Averages across all runs

- Accuracy (category): 83%
- Evidence cited: 87%
- Mean tool calls: 18.0
- Mean input tokens: 7471
- Mean output tokens: 1536
- Mean wall-clock seconds: 31.5
- Total 429 retries: 50

## Where the agent was wrong and why

- `oomkilled` run 1: predicted `crashloop_bad_config` (correct=False, evidence_ok=True, stopped=completed, error=none)
- `oomkilled` run 2: predicted `error` (correct=False, evidence_ok=False, stopped=error, error=Error code: 400 - {'error': {'message': "Failed to generate JSON. Please adjust your prompt. See 'failed_generation' for more details.", 'type': 'invalid_request_error', 'code': 'json_validate_failed', 'failed_generation': '{"root_cause_category":"crashloop_bad_config","explanation":"The orders pod is in CrashLoopBackOff with a restart count >0 and its readiness probe is failing, causing it to stay not Ready. The pod description reports CrashLoopBackOff and BackOff warnings, indicating a bad configuration or startup failure.","evidence":[{"tool":"list_pods","source_ref":"list_pods:1","excerpt":"orders-8488f49698-dpc6p   0/1     Running       1 (2s ago)"}},{"tool":"describe_pod","source_ref":"describe_pod:15","excerpt":"Reason: CrashLoopBackOff"},{"tool":"describe_pod","source_ref":"describe_pod:15","excerpt":"Warning  BackOff    2s (x2 over 3s)   kubelet            Back-off restarting failed container orders"}},{"tool":"get_events","source_ref":"get_events:2","excerpt":"Readiness probe failed: Get \\"http://10.244.0.50:8080/ready\\": context deadline exceeded"}],"suggested_fix":"Check the container startup command and environment variables (e.g., CRASH_ON_START). Ensure the application listens on the expected port and that the readiness probe path /ready returns 200 within the timeout. If the crash is due to missing configuration, update the ConfigMap or image. After fixing, redeploy the pod.","confidence":0.96}'}})
- `oomkilled` run 3: predicted `worker_backlog` (correct=False, evidence_ok=False, stopped=completed, error=none)
- `oomkilled` run 4: predicted `worker_backlog` (correct=False, evidence_ok=False, stopped=completed, error=none)
- `oomkilled` run 5: predicted `crashloop_bad_config` (correct=False, evidence_ok=False, stopped=completed, error=none)

## Secondary LLM-as-judge column

Not used. Scoring is rule-based: exact category match plus required evidence strings.

