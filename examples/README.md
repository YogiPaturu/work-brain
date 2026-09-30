# Synthetic vault

This directory contains only a generator for publication-safe demo data.

```bash
PYTHONPATH=src python3 examples/create_synthetic_vault.py --vault /tmp/work-brain-synthetic
PYTHONPATH=src python3 -m work_brain --vault /tmp/work-brain-synthetic doctor

# Compare a separate cold process with repeated queries in one process.
PYTHONPATH=src python3 examples/benchmark_retrieval.py --vault /tmp/work-brain-synthetic
```
