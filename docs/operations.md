# Operations

This guide describes the production-oriented pieces currently built into `fusionframe`.

## Health And Readiness

Use lifecycle hooks and `app.state` to distinguish startup completion from simple liveness.

```python
@app.on_startup
async def startup():
    app.state.ready = True

@app.get("/health")
async def health(request):
    return {
        "status": "ok",
        "ready": app.state.get("ready", False),
        "startup_time_ms": app.state.get("startup_time_ms"),
    }
```

## Security Baseline

- body size limits through `App(max_body_size=...)`
- signed sessions with CSRF support
- security headers middleware
- bearer token and session-based auth middleware

## Job Modes

`fusionframe` has two job execution styles:

- `JobQueue`
  - in-process execution
  - lifecycle-managed scheduler
  - retries, cancellation, timeouts, and durable state when paired with `SQLiteJobStore`
- `DistributedJobQueue` + `JobWorker`
  - enqueue named tasks into a broker
  - process them from a separate worker loop
  - current broker implementation: `SQLiteJobStore`

## CI

The repo CI already runs:

- tests on Python 3.10 through 3.13
- compile validation
- build + `twine check`

## Current Operational Limits

- distributed jobs are broker/worker foundations, not a full fleet orchestration system
- observability is still basic
- deployment guidance is still intentionally lightweight
