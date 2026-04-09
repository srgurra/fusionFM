# Full App Workflow

The intended `fusionframe` workflow is:

1. scaffold a project
2. build APIs and rendered views in one app
3. add auth and sessions early
4. use admin for operations and internal tooling
5. add jobs for recurring or asynchronous work
6. mount a frontend if needed without leaving the framework

## Recommended stack

- `App`
- `AppSettings`
- `session_middleware`
- `auth_middleware`
- `security_headers_middleware`
- SQLAlchemy models through `Model`
- Alembic-backed migrations
- `AdminPanel`
- `TemplateEngine`
- `mount_static` / `mount_spa`
- `app.jobs`

## Example commands

```bash
fusionframe scaffold myproject
fusionframe migrations-init
fusionframe makemigration myproject.app:app -m "initial schema"
fusionframe migrate myproject.app:app
fusionframe run myproject.app:app
```

## Reference example

See [examples/saas_app.py](../examples/saas_app.py) for the full-stack pattern:

- session login
- admin
- GraphQL
- versioned API
- jobs
- SPA mount
