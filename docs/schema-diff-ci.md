# Schema Diff in CI (GitHub Actions)

Fail the build when a PR introduces **breaking** GraphQL schema changes using
Strawberry's built-in schema diff utility.

## Quick start

1. Export (or commit) your schema SDL, e.g. via:

   ```bash
   strawberry export-schema app:schema -o schema.graphql
   ```

2. Compare the PR version against the base branch:

   ```bash
   strawberry schema diff base-schema.graphql schema.graphql --fail-on-breaking
   ```

3. Optionally emit a markdown report for the PR body:

   ```bash
   strawberry schema diff base-schema.graphql schema.graphql --output=markdown >> $GITHUB_STEP_SUMMARY
   ```

## Example workflow

Save as `.github/workflows/schema-diff.yml`:

```yaml
name: Schema Diff

on:
  pull_request:
    paths:
      - "**/*.graphql"
      - "**/schema.py"
      - "**/types/**"

jobs:
  schema-diff:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install project
        run: |
          pip install -e ".[cli]"
          # or: pip install "strawberry-graphql[cli]" rich

      - name: Export current schema
        run: strawberry export-schema myapp.schema:schema -o /tmp/new.graphql

      - name: Export base-branch schema
        run: |
          git show origin/${{ github.base_ref }}:schema.graphql > /tmp/old.graphql \
            || git show "origin/${{ github.base_ref }}:path/to/schema.graphql" > /tmp/old.graphql

      - name: Diff schemas (fail on breaking)
        run: |
          strawberry schema diff /tmp/old.graphql /tmp/new.graphql \
            --output=markdown \
            --fail-on-breaking \
            --ignore-path '.*\._.*' \
            | tee -a "$GITHUB_STEP_SUMMARY"
```

## Configuration flags

| Flag | Purpose |
| --- | --- |
| `--fail-on-breaking` | Exit `1` if any entry has severity `breaking` |
| `--output=markdown` | Emit a PR-friendly markdown table |
| `--output=term` | Coloured `rich` table (default) |
| `--ignore-code CODE` | Drop entries with that stable change code (repeatable) |
| `--ignore-path REGEX` | Drop entries whose path matches (repeatable) |
| `--severity CODE=level` | Force severity (`breaking` / `dangerous` / `safe`) |

## Python API

```python
from strawberry.schema_registry import (
    ChangeKind,
    SchemaDiffConfig,
    Severity,
    diff_schemas,
)

config = SchemaDiffConfig(
    ignore_change_kinds={ChangeKind.TYPE_DESCRIPTION_CHANGED},
    ignore_path_patterns=[r"\._"],  # underscore-prefixed fields
    severity_overrides={ChangeKind.FIELD_ADDED: Severity.BREAKING},
)

result = diff_schemas("old.graphql", "new.graphql", config=config)

if result.has_breaking:
    for entry in result.breaking:
        print(entry.change_kind.value, entry.path, entry.message)
    raise SystemExit(1)
```

`diff_schemas` accepts `strawberry.Schema` instances, `graphql.GraphQLSchema`
objects, raw SDL strings, or filesystem paths — the same structural comparison
is performed regardless of input form. Entries are sorted by
`(path, change_kind, message, severity)` so repeated CI runs are deterministic.
