# Bedrock daily news classification — activation handoff

Prepared November 5, 2026. **Integration is ready for review; unattended AWS execution is not enabled.** The owner must provide the OIDC role and confirm recurring spending. PR #3 remains unmerged. Repository variables were empty when inspected; the only existing environment was `github-pages`.

## Message to Anthony

> Hi Anthony — Claude Sonnet 4.6 worked on Bedrock in DTCC account 888840134592, Ohio (us-east-2). We have prepared its integration with the existing daily news pipeline. Could DTCC provide an IAM role that GitHub Actions can assume through OIDC, scoped to this repository's main branch and this Sonnet inference profile? Please also confirm the proposed recurring limit: USD 10 estimated model cost per New York calendar day, at most 100 previously unseen requests per run. This could reach USD 310 in a 31-day month; it is an application estimate, not an AWS billing limit. Candidates always require review and never update the event register automatically. We need the Role ARN only; please do not send access keys or session tokens.

An authorized DTCC administrator configures any AWS identity/trust changes. This implementation does not create IAM users, keys, roles, model subscriptions or other AWS resources. Personal `devx-administrator-access` SSO credentials are not exported to GitHub.

## Exact identity and permissions to review

| Setting | Required value |
|---|---|
| Account / source region | `888840134592` / `us-east-2` |
| Model / inference profile | `anthropic.claude-sonnet-4-6` / `us.anthropic.claude-sonnet-4-6` |
| OIDC provider | `https://token.actions.githubusercontent.com` |
| Audience | `sts.amazonaws.com` |
| Repository | `BigJayJayHuang/DTCC-External-Risk-Intelligence` |
| Allowed branch | `refs/heads/main` |
| Current exact `sub` | `repo:BigJayJayHuang@131898097/DTCC-External-Risk-Intelligence@1419748391:ref:refs/heads/main` |
| Role session | 3,600 seconds; temporary credentials only |

The repository OIDC API returned `use_default=true`, `use_immutable_subject=true` and the prefix shown above. Verify these settings again during activation; repository transfer or subject customization can change the requirement. This job has no deployment environment, so use its branch subject. Do not substitute an environment or pull-request subject. GitHub documents [immutable subjects](https://docs.github.com/en/actions/reference/security/oidc) and [AWS OIDC configuration](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws).

DTCC should grant only `bedrock:InvokeModel` for the approved profile and its Sonnet 4.6 destination-model ARNs, plus `bedrock:GetFoundationModelAvailability` for the pre-batch check. STS `GetCallerIdentity` checks the expected account. A Converse request uses InvokeModel permission. Cross-region invocation needs the actual foundation-model resources for the profile's destination regions; DTCC should inspect the profile before writing the policy. The `bedrock:InferenceProfileArn` condition can restrict foundation-model invocation to this profile. No model/profile creation, Marketplace subscription or administrator permission is needed by the application. See [AWS inference-profile permissions](https://docs.aws.amazon.com/bedrock/latest/userguide/inference-profiles-prereq.html) and [Converse authorization](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_Converse.html).

## Activation after review

1. DTCC supplies the approved Role ARN and confirms the recurring estimate above.
2. The repository maintainer reviews and merges PR #3. This handoff does not authorize or perform that merge.
3. Set repository Actions variable `BEDROCK_ROLE_ARN` to that ARN. Set `BEDROCK_ENABLED=true` last. Keep it absent or `false` until configuration is complete. No AWS credential secrets are required.
4. Run **Actions → Daily public-data update → Run workflow**, on main. Its existing 22:17 UTC daily schedule then uses the same integration.
5. Verify the `Bedrock review candidates` job: correct account, one availability check when invoking, candidate CSV, raw outputs, token/cost summary, and durable state publication. For a batch with no unseen requests, it makes no AWS calls and writes an empty candidate CSV with a no-op summary.

To stop future classification, set `BEDROCK_ENABLED=false`. A job that has already started retains its configured cap; cancel it if necessary, then recover its reservation before restarting. The news-collection job remains independent.

## How the daily job works

The existing collector runs first, validates and publishes its usual snapshot. Only after a successful collection job does Bedrock download **that same workflow run's** news export from the recovery artifact. The Bedrock job is restricted to main and is disabled unless the variable is exactly `true`.

`llm_daily prepare` examines 28 inclusive publication-date days. It hashes the exact request, including the unchanged prompt, catalog, model, article and supplied register context. Seen hashes are skipped. Changed article/prompt/model/context produces a new request; unchanged records are not paid for again. The completed 481-article Phase 2 run seeds that history and its November 5 cost once. A maximum of 100 pending requests is selected chronologically; more remain pending within the lookback window. Changes older than 28 days need a deliberate backfill.

The daily state accounts for the combined estimate of this automation's runs on one New York calendar day. Other manual scripts or account activity are outside this ledger, except the imported Phase 2 run. Each prepared run reserves the remaining daily allowance. The workflow publishes that reservation **before obtaining AWS credentials or invoking the model**. The classifier then applies its existing per-request reserve, temperature 0, maxTokens 1200, forced tool and throttling-only retry rules.

After execution, returned usage replaces the hold. All responses, including invalid classifications, remain in the evidence and are not automatically retried as new requests. Access/subscription failures stop execution and remain visible as a failed job. A missing-usage or interrupted run keeps an unresolved hold and blocks another paid run until recovery, including on a later day. Budget-limited batches are explicitly partial. The estimate cannot guarantee the account's eventual invoice.

The source-data release is unchanged. Classification state and immutable run ZIPs use a separate `bedrock-candidates` prerelease. Each ZIP contains the prepared source rows, candidate CSV, supplied text, raw outputs and summaries. `classifier_state.json` is the durable request/cost ledger. The immutable evidence ZIP uploads before the final state checkpoint releases unused budget. There is also a 30-day Actions recovery artifact. No candidate is added to `event_register.csv`; no unreviewed candidate is published as an approved risk score.

## Local preview and recovery

From `Capstone_Project/`, after installing `validation/requirements-llm.txt`:

```bash
python -m validation.llm_daily prepare --dry-run \
  --news data/events/classifier_inputs/2026-11-05/news.csv \
  --run-date 2026-11-05 --run-id preview-example
```

The checked preview in [bedrock_daily_readiness_2026-11-05.json](bedrock_daily_readiness_2026-11-05.json) finds 481 eligible, 481 already classified, zero pending requests and zero new cost. It makes no AWS calls and does not persist budget or processed state. The raw Phase 2 evidence corresponds to classifier source at commit `a697cd7`; later authentication/integration changes do not rewrite that historical run.

Do not discard an unresolved reservation or rerun a paid batch to repair a publication failure. Restore its Actions recovery artifact and the last durable `classifier_state.json`. If the artifact has a finalized classifier summary and matching raw token totals, reconcile the saved run without invoking AWS:

```bash
python -m validation.llm_daily reconcile \
  --state-file data/events/daily_runtime/state.json \
  --plan data/events/daily_runtime/RUN_ID/plan.json
python -m validation.llm_daily_release publish \
  --run-dir data/events/daily_runtime/RUN_ID
```

Replace `RUN_ID` with the actual retained run ID and use the exact code/config/register revision that prepared it. Recovery guards reject changed inputs. If the local artifact already includes the final state, publish that matching evidence/state directly. If usage or final evidence is missing, retain the hold and have DTCC reconcile the actual usage before a maintainer corrects state. A missing release with a surviving tag, or an existing release missing its state asset, stops rather than resetting classification history.

Offline verification:

```bash
python -m unittest validation.test_llm_classifier validation.test_llm_daily -v
python -m validation.test_event_scoring
```

The 26 offline tests cover structured output, existing Event checks, one availability check, deduplication, shared daily costs, pre-call reservation, interrupted-run blocking, evidence-only recovery, bootstrap idempotence and temporary workload authentication. Workflow syntax was checked with actionlint 1.7.7. End-to-end GitHub OIDC invocation awaits DTCC's role; no extra paid test was made during this integration.
