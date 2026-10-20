# Bugs in Reinforcement Learning Frameworks: Replication Package

This package contains the annotations, repair measurements, LLM repair outcomes, stored model responses, prompt, and analysis scripts for a study of 459 bugs in Tianshou, TRL, RLlib, and Stable-Baselines3.

## Quick start

Python 3.10 or later is required. The core analysis uses the Python standard library and runs offline:

```sh
python scripts/reproduce.py
python scripts/validate_release.py --verify-checksums
```

For distribution tests and figures, install the optional dependencies:

```sh
python -m pip install -r requirements.txt
python scripts/distribution_tests.py
python scripts/plot_figures.py
```

Commands can be run from the package directory on Windows, macOS, or Linux. Script paths are resolved relative to the package. Analysis tables are written to `results/`, and plots are written to `figures/`. `requirements-tested.txt` lists the optional library versions used to check the analysis utilities.

## Contents

| Path | Contents |
| --- | --- |
| `data/bugs.csv` | Main table of 459 issues, including category labels, timestamps, repair measurements, and four narrative summaries |
| `bug_issue_data.xlsx` | Earlier repository snapshot; the current 459-issue release is `data/bugs.csv` |
| `data/rq5_outcomes.csv` | Final binary repair judgments for 229 tasks and three models |
| `data/model_output_index.csv` | Index of 687 expected task-model responses, with paths to the 395 stored responses |
| `data/model_outputs/` | Stored model responses, including successful and unsuccessful candidates |
| `data/reference_rq5_results.json` | Reference results used to check the statistical calculations |
| `prompts/repair_prompt.txt` | Fixed English repair prompt |
| `rq5/settings.json` | Models, decoding parameters, context limits, and review settings |
| `rq5/runner/` | Runner utility, configuration examples, and task preparation instructions |
| `docs/` | Data dictionary, category definitions, review protocol, and translation procedure |
| `scripts/` | Analysis, plotting, and validation scripts |
| `results/` | Tables generated from the current data |
| `figures/` | Manuscript figure assets |

CSV files use UTF-8. Empty cells represent missing or unannotated values. `data/bugs.csv` is the main annotation table; the former separate narrative table has been merged into it.

## Dataset and results

The dataset contains 54 Tianshou, 126 TRL, 179 RLlib, and 100 Stable-Baselines3 issues. Excluding two zero-LOC records leaves 457 positive patches, with a median size of 35 LOC. The 229 issues with `1 <= patch_loc <= 35` form the RQ5 evaluation set; 109 have patches of 1-10 LOC.

Across the 229 tasks, GPT-5.3-Codex, DeepSeek-Flash, and Qwen3.5-122B-A10B have 98, 92, and 92 successful repairs (42.8%, 40.2%, and 40.2%). Cochran's Q is 1.636, with p = 0.441. On the 109 small-LOC tasks, they have 60, 60, and 59 successful repairs (55.0%, 55.0%, and 54.1%). Cochran's Q is 0.105, with p = 0.949.

Repair success is determined by manual semantic assessment against developer patches, as described in `docs/review_protocol.md`. The statistical scripts calculate repair rates, Wilson intervals, overlap counts, and stratified results from the final judgments. Stored response text is available for 395 of 687 task-model pairs; empty index paths identify the other 292 pairs.

The runner accepts task manifests containing issue text, pre-fix commits, and source-file paths. To regenerate model responses, supply those task inputs and the model-serving configuration. The package includes the prompt and runner examples; original task snapshots, request logs, and exact local checkpoint revisions are not included.

The six `annotated_fix_strategy` labels retain the broad taxonomy in the source workbook. Their definitions and relationship to RQ4 are given in `docs/annotation_codebook.md`.
