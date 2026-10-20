# Repair experiment runner

This runner adapts the project's original `rq5_llm_experiment.py` for portable task manifests and OpenAI-compatible inference endpoints. The published repair outcomes use manual semantic review. The runner also provides optional commands for applying patches and executing task-specific checks in new experiments.

Defaults match the released protocol: one candidate, top_p 1, a 4,096-token output limit, and a 120-second timeout. The runner loads the plain-text prompt from the package. Example configurations specify the three model labels and provide endpoint and checkpoint fields for the user's deployment.

## Offline demonstration

From the package root:

```sh
python rq5/runner/rq5_llm_experiment.py validate-manifest --tasks rq5/runner/tasks.example.jsonl
python rq5/runner/rq5_llm_experiment.py generate --tasks rq5/runner/tasks.example.jsonl --models rq5/runner/models.example.json --run-dir runs/example --dry-run
```

The synthetic example demonstrates the manifest format. Dry-run mode checks task construction without calling a model or requiring an API key.

## Preparing real tasks

Supply issue text, the pre-fix commit, a local repository path, and the allowed source files. Configure the endpoint, model identifier, and credential environment variable for the deployment. Prompts contain the issue and pre-fix code; reference patches and annotation summaries are reserved for evaluation.

The adapter uses an OpenAI-compatible Chat Completions interface and supports loopback HTTP endpoints for local inference. Other API formats require a corresponding adapter. Before generation, check each task against all three tokenizers and enforce the input limit in the serving workflow. Tool access and network restrictions are configured in the serving environment. Endpoint compatibility requires testing against the chosen deployment.

The optional `validate` command applies patches and runs supplied commands in Git worktrees. The statistical analysis reads the final manual judgments from `data/rq5_outcomes.csv`.
