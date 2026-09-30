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
```

The benchmark reports separate-process and cache-warm timings. The optional
FastEmbed/BGE run downloads model files on first use; it is not required for
the dependency-free synthetic-vault example.
