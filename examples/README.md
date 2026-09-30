# Synthetic vault

This directory contains only a generator for publication-safe demo data.

```bash
PYTHONPATH=src python3 examples/create_synthetic_vault.py --vault /tmp/work-brain-synthetic
PYTHONPATH=src python3 -m work_brain --vault /tmp/work-brain-synthetic doctor

# Compare a separate cold process with repeated queries in one process.
PYTHONPATH=src python3 examples/benchmark_retrieval.py --vault /tmp/work-brain-synthetic
PYTHONPATH=src python3 examples/benchmark_retrieval.py --vault /tmp/work-brain-synthetic --embedding hash
# After: python3 -m pip install -e '.[semantic]'
WORK_BRAIN_EMBEDDING=fastembed work-brain --vault /tmp/work-brain-synthetic reindex
PYTHONPATH=src python3 examples/benchmark_retrieval.py --vault /tmp/work-brain-synthetic --embedding fastembed

# Report recall@3 and recall@5 on the broader synthetic evaluation fixture.
PYTHONPATH=src python3 examples/evaluate_retrieval.py --embedding hash
PYTHONPATH=src python3 examples/evaluate_retrieval.py --embedding fastembed
```

The benchmark reports separate-process and cache-warm timings. The optional
FastEmbed/BGE run downloads model files on first use; it is not required for
the dependency-free synthetic-vault example. The evaluation report is
diagnostic rather than a quality gate: it contains multiple plausible answers
per query and is intended to expose ranking behavior for review.
