Schema Diff in CI (GitHub Actions)
==================================

Strawberry ships a built-in schema diff utility that structurally compares two
GraphQL schemas (via the GraphQL type system, not text diffing) and classifies
each change as **breaking**, **dangerous**, or **safe**.

This guide shows how to fail a pull request when breaking schema changes are
introduced.

Python API
----------

.. code-block:: python

    from strawberry.schema_diff import (
        SchemaDiffConfig,
        ChangeCode,
        ChangeSeverity,
        diff_schemas,
    )
    from strawberry.schema_diff.report import format_markdown

    # Accepts strawberry.Schema instances or SDL strings
    result = diff_schemas(old_schema, new_schema)

    if result.has_breaking:
        print("Breaking changes detected!")
        for change in result.breaking:
            print(f"  [{change.code.value}] {change.path}: {change.message}")

    # Customise behaviour
    config = SchemaDiffConfig(
        ignore_codes={ChangeCode.TYPE_DESCRIPTION_CHANGED},
        ignore_field_patterns=[r"\._"],  # ignore _internal fields
        ignore_type_patterns=[r"^_"],
        severity_overrides={
            ChangeCode.FIELD_ADDED: ChangeSeverity.DANGEROUS,
        },
        include_descriptions=False,
    )
    result = diff_schemas(old_sdl, new_sdl, config=config)

    # GitHub PR comment body
    markdown = format_markdown(result)

CLI
---

.. code-block:: bash

    # Coloured terminal summary (default)
    strawberry schema diff old.graphql new.graphql

    # Markdown table suitable for PR comments
    strawberry schema diff old.graphql new.graphql --output=markdown

    # JSON for programmatic consumption
    strawberry schema diff old.graphql new.graphql --output=json

    # Load Python schemas via module:attribute
    strawberry schema diff myapp.schema:schema myapp.schema:schema

    # Ignore internal fields and description noise
    strawberry schema diff old.graphql new.graphql \
        --ignore-field '\._' \
        --ignore-code TYPE_DESCRIPTION_CHANGED \
        --no-descriptions

    # Override severity (CODE=SEVERITY, repeatable)
    strawberry schema diff old.graphql new.graphql \
        --severity FIELD_ADDED=DANGEROUS

    # Exit codes
    #   0 – no breaking changes (or --no-fail-on-breaking)
    #   1 – breaking changes found (default)
    #   2 – load / parse error
    strawberry schema diff old.graphql new.graphql --fail-on-breaking
    strawberry schema diff old.graphql new.graphql --fail-on-dangerous

GitHub Action: fail on breaking changes
---------------------------------------

Create ``.github/workflows/schema-diff.yml``:

.. code-block:: yaml

    name: Schema Diff

    on:
      pull_request:
        paths:
          - "**.graphql"
          - "**/schema.py"
          - ".github/workflows/schema-diff.yml"

    jobs:
      schema-diff:
        runs-on: ubuntu-latest
        permissions:
          contents: read
          pull-requests: write   # only needed for the optional PR comment step

        steps:
          - name: Checkout PR head
            uses: actions/checkout@v4

          - name: Checkout base schema (old)
            uses: actions/checkout@v4
            with:
              ref: ${{ github.event.pull_request.base.sha }}
              path: base-ref

          - name: Set up Python
            uses: actions/setup-python@v5
            with:
              python-version: "3.12"

          - name: Install dependencies
            run: |
              pip install "strawberry-graphql[cli]"
              # or: pip install -e ".[cli]" for a monorepo checkout

          # ---------------------------------------------------------------
          # Option A – compare committed SDL snapshots
          # ---------------------------------------------------------------
          - name: Diff GraphQL SDL files
            id: diff
            run: |
              set +e
              strawberry schema diff \
                base-ref/schema.graphql \
                schema.graphql \
                --output=markdown \
                --output-file=schema-diff.md \
                --ignore-field '\._' \
                --no-descriptions \
                --fail-on-breaking
              echo "exit_code=$?" >> "$GITHUB_OUTPUT"
            continue-on-error: true

          # ---------------------------------------------------------------
          # Option B – compare live strawberry.Schema objects
          # (uncomment and adjust module paths as needed)
          # ---------------------------------------------------------------
          # - name: Export and diff Python schemas
          #   run: |
          #     PYTHONPATH=base-ref strawberry export-schema myapp.schema:schema \
          #       --output /tmp/old.graphql
          #     strawberry export-schema myapp.schema:schema \
          #       --output /tmp/new.graphql
          #     strawberry schema diff /tmp/old.graphql /tmp/new.graphql \
          #       --output=markdown --output-file=schema-diff.md \
          #       --fail-on-breaking

          - name: Comment diff on PR
            if: always() && hashFiles('schema-diff.md') != ''
            uses: actions/github-script@v7
            with:
              script: |
                const fs = require('fs');
                const body = fs.readFileSync('schema-diff.md', 'utf8');
                const { data: comments } = await github.rest.issues.listComments({
                  owner: context.repo.owner,
                  repo: context.repo.repo,
                  issue_number: context.issue.number,
                });
                const marker = '<!-- strawberry-schema-diff -->';
                const existing = comments.find(c => c.body && c.body.includes(marker));
                const fullBody = marker + '\n' + body;
                if (existing) {
                  await github.rest.issues.updateComment({
                    owner: context.repo.owner,
                    repo: context.repo.repo,
                    comment_id: existing.id,
                    body: fullBody,
                  });
                } else {
                  await github.rest.issues.createComment({
                    owner: context.repo.owner,
                    repo: context.repo.repo,
                    issue_number: context.issue.number,
                    body: fullBody,
                  });
                }

          - name: Fail job on breaking changes
            if: steps.diff.outputs.exit_code == '1'
            run: |
              echo "::error::Breaking schema changes detected. See the PR comment or schema-diff.md for details."
              exit 1

          - name: Fail job on schema load errors
            if: steps.diff.outputs.exit_code == '2'
            run: |
              echo "::error::Failed to load or parse schemas."
              exit 1

Apollo Federation v2
-------------------

When your schemas include Federation directives (``@key``, ``@requires``,
``@provides``, ``@shareable``, ``@inaccessible``, ``@external``, ``@override``,
``@tag``), the diff utility emits specialised change codes such as:

* ``FED_KEY_REMOVED`` / ``FED_KEY_FIELDS_CHANGED`` – **breaking**
* ``FED_REQUIRES_REMOVED`` – **breaking**
* ``FED_SHAREABLE_REMOVED`` – **breaking**
* ``FED_INACCESSIBLE_ADDED`` – **dangerous**
* ``FED_PROVIDES_REMOVED`` – **dangerous**
* ``FED_KEY_ADDED``, ``FED_SHAREABLE_ADDED``, ``FED_TAG_ADDED`` – **safe**

Ensure both SDL files declare the directive definitions (or are exported from
``strawberry.federation.Schema``) so the parser can retain applied directives.

Change codes reference
----------------------

Common codes you may want to ignore or override in CI:

===============================  ==========  =================================
Code                             Default     Typical ignore reason
===============================  ==========  =================================
``TYPE_DESCRIPTION_CHANGED``     SAFE        Docstring-only churn
``FIELD_DESCRIPTION_CHANGED``    SAFE        Docstring-only churn
``FIELD_DEPRECATION_ADDED``      DANGEROUS   Intentional deprecation path
``ENUM_VALUE_ADDED``             SAFE        Usually fine
``FIELD_ADDED``                  SAFE        Usually fine
``TYPE_REMOVED``                 BREAKING    Never ignore in production
``FIELD_REMOVED``                BREAKING    Never ignore in production
``FED_KEY_REMOVED``              BREAKING    Federation contract break
===============================  ==========  =================================

Programmatic CI gate (no CLI)
-----------------------------

.. code-block:: python

    # ci/check_schema.py
    import sys
    from pathlib import Path
    from strawberry.schema_diff import diff_schemas
    from strawberry.schema_diff.report import format_markdown

    old = Path("base-ref/schema.graphql").read_text()
    new = Path("schema.graphql").read_text()
    result = diff_schemas(old, new)

    Path("schema-diff.md").write_text(format_markdown(result))

    if result.has_breaking:
        print("BREAKING CHANGES:", file=sys.stderr)
        for c in result.breaking:
            print(f"  {c.code.value}  {c.path}  {c.message}", file=sys.stderr)
        sys.exit(1)
