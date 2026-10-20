# Data dictionary

`issue_html_url` is the canonical issue identifier. `bug_id` combines a framework abbreviation and issue number. Each annotation and outcome table contains one row per issue; the model-response index contains one row per issue and model.

## bugs.csv

| Column | Definition |
| --- | --- |
| `bug_id`, `issue_html_url`, `issue_title` | Compact identifier, canonical issue URL, and original issue title |
| `framework` | Tianshou, TRL, RLlib, or Stable-Baselines3 |
| `symptom` | Symptom category |
| `root_cause_code`, `root_cause` | C1-C9 root-cause code and English name |
| `annotated_fix_strategy_code`, `annotated_fix_strategy` | Broad FS1-FS6 repair-strategy code and English name; FX0 denotes no code change |
| `lifecycle_stage` | Stage at which the defect occurs; blank when unannotated |
| `rl_specificity` | RL-specific or General; blank when unannotated |
| `changed_files` | Recorded number of changed files in the associated PR |
| `patch_loc` | Numeric patch size used in selection and statistics: added plus deleted source-code lines |
| `patch_breakdown_source` | Recorded descriptive patch breakdown |
| `created_at`, `closed_at` | Issue creation and closure timestamps, retaining the source timezone where present |
| `open_days` | Recorded issue open duration in days; 15 missing values were filled with whole elapsed days from the timestamps |
| `issue_comments` | Recorded issue comment count |
| `issue_number`, `github_issue_id`, `state` | Repository issue number, GitHub global identifier where available, and issue state |
| `issue_summary` | Summary of the reported problem |
| `symptom_summary` | Observed failure and its effect on execution or training |
| `root_cause_summary` | Annotated cause or description of the recorded failure mechanism |
| `fix_summary` | Changes made in the associated PR or documented resolution |

The table retains the original numerical measurements. Three changed-file counts were supplemented from PR records, and 15 missing durations were calculated from issue timestamps. Root-cause and repair summaries contain reference information and are excluded from model inputs.

## rq5_outcomes.csv

`gpt_success`, `deepseek_success`, and `qwen_success` record the final semantic judgments as 1 (yes) or 0 (no) for GPT-5.3-Codex, DeepSeek-Flash, and Qwen3.5-122B-A10B. The table also contains issue identifiers, framework, root cause, patch size, creation time, and the supplied task notes.

The Qwen outcome for TRL #2856 is 0 following correction of a source yes label associated with a `NO_PATCH` response.

## model_output_index.csv

The index contains 687 rows covering 229 tasks and three models. `path` is relative to `data/`; an empty path indicates unavailable response text. A total of 395 response texts are stored. `source_text_sha256` fingerprints the source response before translation of any explanatory prose. The stored responses include successful and unsuccessful candidates.

## Derived results

`rq3_long_tail_cases.csv` selects issues with an open duration of at least 28 days, at least four comments, or a patch size of at least 75 LOC. `rq4_small_loc_cases.csv` selects issues with 1-10 LOC. Both are generated from the current main table and use its columns.

Percentages use a 0-100 scale. Wilson intervals are two-sided 95% intervals. RQ3 standard deviations use the sample definition (`ddof=1`). Framework-specific symptom and root-cause percentages use that framework's issue count as denominator. Temporal boundaries are inclusive for the on-or-before group.
