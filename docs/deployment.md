# Deployment

`fusionframe` is an ASGI framework. The practical deployment model is:

1. run the app behind an ASGI server such as `uvicorn`
2. terminate TLS at a reverse proxy or platform edge
3. use a real database and external infrastructure for stateful services

## App Process

```bash
uvicorn example:app --host 0.0.0.0 --port 8000
```

## Recommended Production Defaults

- configure `SESSION_SECRET`
- configure `JWT_SECRET`
- configure `JWT_ISSUER` and `JWT_AUDIENCE`
- run `session_middleware(secure=True)` behind HTTPS
- set a real `DATABASE_URL`
- keep `debug=False`

## Jobs

For in-process work:

- start the normal app process and use `app.jobs`

For broker/worker mode:

- enqueue tasks through `DistributedJobQueue`
- run a separate worker process around `JobWorker`
- use `SQLiteJobStore` only as a lightweight stepping stone, not as a final large-scale broker

## Current Scope

This deployment guidance is intentionally practical, not exhaustive. It covers the expected runtime shape of the framework today, not a complete production platform handbook.
