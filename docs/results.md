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

## Where the agent was wrong and why

- `readiness_dependency_down` run 1: predicted `crashloop_bad_config` (correct=False, evidence_ok=False, stopped=completed, error=none)
- `readiness_dependency_down` run 2: predicted `error` (correct=False, evidence_ok=False, stopped=error, error='dict' object has no attribute 'lower')
- `readiness_dependency_down` run 3: predicted `crashloop_bad_config` (correct=False, evidence_ok=False, stopped=completed, error=none)
- `readiness_dependency_down` run 4: predicted `error` (correct=False, evidence_ok=False, stopped=error, error='dict' object has no attribute 'lower')
- `readiness_dependency_down` run 5: predicted `error` (correct=False, evidence_ok=False, stopped=error, error='dict' object has no attribute 'lower')
- `wrong_dependency_url` run 1: predicted `readiness_dependency_down` (correct=False, evidence_ok=True, stopped=completed, error=none)
- `wrong_dependency_url` run 3: predicted `unknown` (correct=False, evidence_ok=False, stopped=invalid_schema, error=none)
- `worker_backlog` run 1: predicted `error` (correct=False, evidence_ok=False, stopped=error, error=Groq rate-limited after 6 retries: Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gpt-oss-120b` in organization `org_01kqcgm76qeggag1mx548fvxe3` service tier `on_demand` on tokens per day (TPD): Limit 200000, Used 199325, Requested 3231. Please try again in 18m24.192s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}})
- `worker_backlog` run 2: predicted `error` (correct=False, evidence_ok=False, stopped=error, error=Groq rate-limited after 6 retries: Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gpt-oss-120b` in organization `org_01kqcgm76qeggag1mx548fvxe3` service tier `on_demand` on tokens per day (TPD): Limit 200000, Used 199077, Requested 3259. Please try again in 16m49.151999999s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}})
- `worker_backlog` run 3: predicted `error` (correct=False, evidence_ok=False, stopped=error, error=Groq rate-limited after 6 retries: Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gpt-oss-120b` in organization `org_01kqcgm76qeggag1mx548fvxe3` service tier `on_demand` on tokens per day (TPD): Limit 200000, Used 198834, Requested 3463. Please try again in 16m32.304s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}})
- `worker_backlog` run 4: predicted `error` (correct=False, evidence_ok=False, stopped=error, error=Groq rate-limited after 6 retries: Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gpt-oss-120b` in organization `org_01kqcgm76qeggag1mx548fvxe3` service tier `on_demand` on tokens per day (TPD): Limit 200000, Used 198586, Requested 3112. Please try again in 12m13.536s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}})
- `worker_backlog` run 5: predicted `error` (correct=False, evidence_ok=False, stopped=error, error=Groq rate-limited after 6 retries: Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gpt-oss-120b` in organization `org_01kqcgm76qeggag1mx548fvxe3` service tier `on_demand` on tokens per day (TPD): Limit 200000, Used 198339, Requested 4030. Please try again in 17m3.408s. Need more tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', 'type': 'tokens', 'code': 'rate_limit_exceeded'}})

## Secondary LLM-as-judge column

Not used. Scoring is rule-based: exact category match plus required evidence strings.

