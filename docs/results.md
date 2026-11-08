# kube-triage eval results

Numbers in this file come from `make eval` in this repository. They are not estimates.

## Environment

- Date (UTC): 2026-11-07
- Git commit: `4b5f9a16d405d76abc769ac06db0c4cc75a22782`
- Model: `openai/gpt-oss-120b`
- kind: kind v0.30.0 go1.24.6 linux/amd64
- kubectl: Client Version: v1.31.4
- Hardware: 8 CPUs; `Linux xaidi-Latitude-5400 7.0.0-42-generic #42-Ubuntu SMP PREEMPT_DYNAMIC Thu Oct 15 08:06:44 UTC 2026 x86_64 GNU/Linux`
- Command: `make eval`

## Per-fault accuracy (5 runs)

| Fault | Correct | Evidence cited | Mean tool calls | Mean input tokens | Mean output tokens | Mean seconds | 429 retries |
| --- | --- | --- | --- | --- | --- | --- | --- |
| crashloop_bad_config | 5/5 | 5/5 | 14.6 | 5819 | 1228 | 5.7 | 0 |
| oomkilled | 5/5 | 5/5 | 16.0 | 6219 | 1187 | 7.2 | 0 |
| imagepull_wrong_tag | 5/5 | 5/5 | 15.8 | 6094 | 1138 | 12.5 | 0 |
| readiness_dependency_down | 0/5 | 0/5 | 6.4 | 2403 | 765 | 8.0 | 0 |
| wrong_dependency_url | 3/5 | 4/5 | 15.8 | 6199 | 1193 | 18.1 | 3 |
| worker_backlog | 0/5 | 0/5 | 0.0 | 0 | 0 | 0.0 | 0 |

## Averages across all runs

- Accuracy (category): 60%
- Evidence cited: 63%
- Mean tool calls: 11.4
- Mean input tokens: 4456
- Mean output tokens: 918
- Mean wall-clock seconds: 8.6
- Total 429 retries: 3

## Secondary LLM-as-judge column

Not used. Scoring is rule-based: exact category match plus required evidence strings.

