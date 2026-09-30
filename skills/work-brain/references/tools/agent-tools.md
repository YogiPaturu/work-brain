WORK-BRAIN-TOOLS v1

The model sees intent-level tools only:

- `get_current_state`
- `get_recent_work`
- `search_evidence`
- `hydrate_evidence`
- `commit_session` during the committing phase

Tools return compact typed results and stable references. They never expose raw
SQL, filesystem writes, shell execution, or vector-index operations. Retrieval
implementation belongs behind the application adapter and LLD3 contract.
