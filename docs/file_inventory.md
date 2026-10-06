# Nhiệm vụ từng file Python

| File | Nhiệm vụ |
|---|---|
| `analysis/__init__.py` | Read-only EDA, label review and post-evaluation error diagnostics. |
| `analysis/budget_worker.py` | One process per algorithm: CPU/wall time and OS peak resident working set. |
| `analysis/efficient.py` | Statistical/ML benchmark with small grids and one BLAS thread; no DL dependency. |
| `analysis/errors.py` | Post-test diagnostics; never feeds test mistakes back into feature selection automatically. |
| `analysis/feature_eda.py` | Feature-only diagnostic reports; labels and identities never enter X. |
| `analysis/raw_overview.py` | Generic adapter-level overview for schema fixtures and unlabelled corpora. |
| `analysis/window_rank.py` | Transparent per-incident statistical experiments, not full paper reproductions. |
| `rca_bench/__init__.py` | Internal RCA benchmark. No production action endpoints. |
| `rca_bench/__main__.py` | Module/API __main__ |
| `rca_bench/adapters.py` | Explicit mapping avoids guessing service names from underscore-delimited columns. |
| `rca_bench/cli.py` | Module/API cli |
| `rca_bench/connectors.py` | Bounded, read-only telemetry extraction. Transport is injectable for tests. |
| `rca_bench/data.py` | Incident windows and temporal, group-disjoint dataset preparation. |
| `rca_bench/evaluation.py` | Incident ranking metrics; control-window detection is reported separately. |
| `rca_bench/io.py` | Small, auditable storage primitives; JSON model files never execute code. |
| `rca_bench/models.py` | NumPy baselines: transparent statistics, ML, and actual deep neural training. |
| `rca_bench/monitoring.py` | Module/API monitoring |
| `rca_bench/registry.py` | Local lifecycle registry. It records review; it never deploys or remediates. |
| `rca_bench/runner.py` | Train -> validation selection -> frozen test -> auditable report. |
| `rca_bench/synthetic.py` | Synthetic integration fixture with controls, propagation and distractors. |
| `workbench/__init__.py` | Offline data workbench: no training, model dependency, network or automatic relabelling. |
| `workbench/eda.py` | Offline EDA. Suspected outliers are review candidates, never deleted or relabelled. |
| `workbench/feature_catalog.py` | BA/SME backlog: feature definitions are proposals, not unapproved production rules. |
| `workbench/io.py` | Small, auditable storage primitives; JSON model files never execute code. |
| `workbench/local.py` | Audit messy long/wide telemetry without requiring labels or treating unknown as normal. |
| `workbench/make_demo.py` | Synthetic unlabelled local export for testing data-control rules, not public evidence. |
| `workbench/package.py` | Package only public/demo inputs; private input directory is deliberately excluded. |
| `workbench/readers.py` | Explicit schema mappings preserve source identity and avoid label guessing. |
| `workbench/verify.py` | Audit an EDA report's sealed files without training or network access. |
| `datasets/__init__.py` | Offline dataset readers. No downloads or remote code execution on import. |
| `datasets/fetch_rcaeval_sample.py` | Connected staging only. Fixed RE1-OB CPU subset, pinned HF revision. |
| `datasets/fetch_telecomts_sample.py` | Explicit connected-staging command. Downloads public excerpts, never internal data. |
| `datasets/prepare_rcaeval_sample.py` | Offline conversion of downloaded Parquet; resource-metric subset with explicit units. |
| `datasets/readers.py` | Explicit schema mappings preserve source identity and avoid label guessing. |
| `features/__init__.py` | Module/API __init__ |
| `features/resample.py` | Causal, right-labelled bins. No interpolation across absent samples. |
| `baselines/__init__.py` | Module/API __init__ |
| `baselines/dl/__init__.py` | Module/API __init__ |
| `baselines/ml/__init__.py` | Module/API __init__ |
| `baselines/statistical/__init__.py` | Module/API __init__ |
| `models/__init__.py` | Module/API __init__ |
| `evaluation/__init__.py` | Module/API __init__ |
| `pipelines/__init__.py` | Offline orchestration entry points. |
| `pipelines/export_internal.py` | Bounded read-only exports without invented incidents; credentials stay in env. |
| `pipelines/import_cdr_catalog.py` | Extract schema only from locally supplied documents, never sample subscriber values. |
| `pipelines/internal.py` | Local unlabelled telemetry/CDR experiment; scores are review priorities, not truth. |
| `pipelines/make_fixtures.py` | Generate schema fixtures, explicitly not copies of public datasets. |
| `pipelines/package.py` | Build a portable artifact, excluding runtime binaries, caches and partial attempts. |
| `pipelines/predict_telecomts.py` | Offline scoring of unlabelled TelecomTS-schema windows with a frozen model. |
| `pipelines/project.py` | Single entry point for dataset branches and method profiles. |
| `pipelines/quickstart.py` | One offline entry point for VS Code; each invocation creates a new run directory. |
| `pipelines/report.py` | Produce one readable report; never pool metrics from different tasks. |
| `pipelines/run.py` | python -m pipelines.run --config configs/<dataset>.json --output experiments/<run> |
| `pipelines/suite.py` | Run configs sequentially; failed datasets stay visible, never silently skipped. |
| `pipelines/telecomts.py` | TelecomTS window anomaly classification. KPI arrays only; no answer/label features. |
| `pipelines/verify.py` | Verify sealed snapshots, run artifact hashes and public input downloads offline. |
| `integrations/__init__.py` | Internal endpoints are configured explicitly; offline workflows do not invoke them. |
| `integrations/cdr/__init__.py` | Structured CDR telemetry. No NLP and no implicit business result-code mapping. |
| `integrations/cdr/features.py` | Bounded local JSONL CDR aggregation with event time and arrival cutoff. |
| `integrations/cdr/normalize.py` | Explicit named-field or approved positional CDR mapping; no guessed charge units. |
| `integrations/elasticsearch/__init__.py` | Module/API __init__ |
| `integrations/mano/__init__.py` | Typed, time-versioned MANO/Kubernetes relationships; no automatic remediation. |
| `integrations/mda/__init__.py` | Module/API __init__ |
| `integrations/victoriametrics/__init__.py` | Module/API __init__ |
| `tests/test_analysis.py` | Kiểm thử test_analysis |
| `tests/test_benchmark.py` | Kiểm thử test_benchmark |
| `tests/test_lab.py` | Kiểm thử test_lab |
| `tests/test_unified.py` | Kiểm thử test_unified |
| `tests/test_workbench.py` | Kiểm thử test_workbench |
