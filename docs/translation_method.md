# Translation procedure

The four Chinese narrative fields were translated into English using Qwen3.5-122B-A10B deployed on the laboratory server. Translation covered 1,836 segments across 459 issues: issue, symptom, root-cause, and repair summaries.

Translation requests preserved technical claims, qualifications, numbers, URLs, API names, and code identifiers. Returned segments were checked for matching IDs, complete coverage, nonempty text, and remaining Chinese characters. Technical passages were spot-checked against the source annotations, and selected summaries were revised against the corresponding GitHub issues and PRs.

Category codes, numerical measurements, and repair-outcome labels were retained. Code diffs were preserved verbatim. In the stored DeepSeek response for TRL #3666, the Chinese explanatory paragraph was translated while the diff remained unchanged.
