# Example generated output

This example documents the observable contract of Guided Build without committing user data or generated runtime workspaces.

## Input

```json
{
  "project_name": "BTH Control Center",
  "modules": ["worker_monitor", "job_queue", "model_manager"],
  "network_scope": "local",
  "auth_enabled": true,
  "ai_autonomy": "approval_required",
  "theme": "windows_xp.v1",
  "language": ["th", "en"]
}
```

## Pipeline

1. Validate the guided form and create a versioned Project Spec.
2. Freeze the resolved specification so later edits cannot silently change the build contract.
3. Calculate gaps and a dependency-aware task DAG.
4. Generate the workspace in an isolated build directory.
5. Run structural, content and security verification.
6. Promote files only when mandatory checks pass.
7. Record the build and audit evidence, then expose Preview and ZIP export.

## Expected result

```json
{
  "status": "completed",
  "verification": {"status": "passed"},
  "promoted_files": [
    "index.html",
    "styles.css",
    "app.js",
    "build_manifest.json"
  ],
  "preview_url": "/api/projects/<project-id>/workspace/preview/"
}
```

The end-to-end contract is covered by `test_bth_create_guided_build_runs_end_to_end` and related regression tests.
