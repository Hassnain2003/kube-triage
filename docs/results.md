# kube-triage eval results

Numbers in this file come from `make eval` in this repository. They are not estimates.

## Environment

- Date (UTC): 2026-11-09
- Git commit: `21cf659d4ed51175f3a293245c204edfda6b1555`
- Model: `openai/gpt-oss-120b`
- kind: kind v0.30.0 go1.24.6 linux/amd64
- kubectl: Client Version: v1.31.4
- Hardware: 8 CPUs; `Linux xaidi-Latitude-5400 7.0.0-42-generic #42-Ubuntu SMP PREEMPT_DYNAMIC Thu Oct 15 08:06:44 UTC 2026 x86_64 GNU/Linux`
- Command: `make eval`

## Per-fault accuracy (5 runs)

| Fault | Correct | Evidence cited | Mean tool calls | Mean input tokens | Mean output tokens | Mean seconds | 429 retries |
| --- | --- | --- | --- | --- | --- | --- | --- |
| crashloop_bad_config | 4/5 | 4/5 | 15.8 | 7771 | 1405 | 25.6 | 23 |
| oomkilled | 5/5 | 5/5 | 18.8 | 7790 | 1350 | 31.8 | 27 |
| imagepull_wrong_tag | 5/5 | 5/5 | 17.4 | 7366 | 1072 | 41.6 | 33 |
| readiness_dependency_down | 5/5 | 5/5 | 19.6 | 7767 | 1279 | 26.9 | 32 |
| wrong_dependency_url | 5/5 | 5/5 | 21.0 | 8678 | 1470 | 37.6 | 40 |
| worker_backlog | 5/5 | 5/5 | 18.6 | 7307 | 1856 | 20.2 | 34 |

## Averages across all runs

- Accuracy (category): 97%
- Evidence cited: 97%
- Mean tool calls: 18.5
- Mean input tokens: 7780
- Mean output tokens: 1405
- Mean wall-clock seconds: 30.6
- Total 429 retries: 189

## Where the agent was wrong and why

- `crashloop_bad_config` run 2: predicted `unknown` (correct=False, evidence_ok=False, stopped=invalid_schema, error=none)

## Secondary LLM-as-judge column

Not used. Scoring is rule-based: exact category match plus required evidence strings.

