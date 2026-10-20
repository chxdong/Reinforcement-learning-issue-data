# Annotation codebook

## Symptoms

- **Crash:** execution terminates with an exception or fatal failure.
- **Functional Failure:** execution does not implement the intended behavior, potentially without an explicit exception.
- **Build Failure:** installation, compilation, import, or construction fails as classified in the source annotations.
- **Low Efficiency:** execution consumes excessive time or computational resources.
- **Hang:** execution stops making progress without terminating normally.

## Root causes

| Code | Category |
| --- | --- |
| C1 | Learning Mechanism Error |
| C2 | Environment Interaction Error |
| C3 | Experience Processing Error |
| C4 | Training State Management Error |
| C5 | Distributed and Parallel Coordination Error |
| C6 | Runtime Resource and Device Management Error |
| C7 | General Implementation Error |
| C8 | Framework Interface and Configuration Error |
| C9 | Dependency and Runtime Compatibility Error |

The category labels follow the final annotation workbook. Classification uses the described failure mechanism and repair.

## RL specificity

**RL-specific** indicates that the cause or correct repair depends on RL-specific semantics, such as episode boundaries, policy-state propagation during environment interaction, or exploration-state maintenance. **General** indicates a state-management defect also found in general software or deep learning, without requiring RL-specific semantics. Blank entries are unannotated. The source includes specificity labels for C1-C4; no labels are inferred for other categories.

## Repair strategy annotations and RQ4

The source workbook's broad strategy labels are:

| Code | English translation |
| --- | --- |
| FS1 | Learning and Numerical Logic Repair |
| FS2 | Interaction Interface and Configuration Alignment |
| FS3 | Experience and Training State Handling Repair |
| FS4 | Parallel Coordination and Resource Management |
| FS5 | General Implementation Robustness Improvement |
| FS6 | Dependency and Runtime Environment Adaptation |
| FX0 | No code change (excluded from repair evaluation) |

The FS1-FS6 labels group repairs by broad functional area. RQ4 also discusses six more specific operations: API replacement and interface-contract adaptation, version compatibility handling, parameter and configuration correction, data representation alignment, boundary condition handling, and numerical stabilization and learning-logic correction. The released issue-level annotations use the broad taxonomy; a mapping to the operation-level taxonomy is not included. `results/rq4_small_loc_cases.csv` contains the 109 issues with positive patches of 1-10 LOC.
