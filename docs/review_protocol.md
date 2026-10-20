# RQ5 protocol

## Selection and inputs

Exclude zero-LOC records and retain issues whose positive patch size does not exceed the median, 35 LOC. The resulting evaluation set contains 229 tasks, including 109 tasks with 1-10 LOC.

Each task uses the issue title, sanitized issue body, and complete pre-fix contents of the relevant functional source or executable configuration files. Reference patches identify files and guide manual review; they are not model inputs. PR URLs, commit messages, post-fix code, reference diffs, root-cause labels, and repair summaries must not be supplied to the model.

The fixed English prompt is in `prompts/repair_prompt.txt`. Limits are 28,672 input tokens and 4,096 output tokens within a 32,768-token total window. One candidate is generated per model and task in an independent context, using temperature 0 and top_p 1. No seed is set. The timeout is 120 seconds. Browsing, retrieval, GitHub access, MCP, and other external tools are disabled during repair inference.

## Manual semantic assessment

Two authors independently review each candidate while blinded to the model name. They use the developer's PR as the main reference and consult the issue, pre-fix code, and candidate diff. Correctness does not require textual identity with the developer patch; a defensible alternative must address the core cause and remain consistent with the existing interfaces and code context.

Disagreements are discussed after rechecking the issue, code, and reference patch. A third expert with five years of software repair experience adjudicates disagreements that remain after discussion. The pre-discussion Cohen's kappa is 0.86. The released outcome table contains the final judgments; individual pre-discussion labels are not included.

The outcome columns record manual semantic judgments. Stored response availability is listed in `data/model_output_index.csv`.

## Statistics

For each model, Top-1 success rate is the number of tasks judged correct divided by the number of evaluated tasks. The analysis computes two-sided 95% Wilson intervals and Cochran's Q for paired binary results across the three models. For three models, the chi-square survival function with two degrees of freedom is exp(-Q/2). Cochran's Q is nonsignificant in the overall and small-LOC analyses.

Root-cause, framework, and small-LOC analyses are descriptive. The 1-10 LOC subset is nested within the overall evaluation set. Temporal boundaries are 2025-08-31 for GPT-5.3-Codex, 2025-05-31 for DeepSeek-Flash, and 2025-07-31 for Qwen3.5-122B-A10B. For DeepSeek and Qwen, the supplied cutoff months are represented by their final calendar days. Time stratification measures sensitivity to these boundaries; it is not a direct test of training-data membership.
