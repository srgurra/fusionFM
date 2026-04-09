# Auth And Accounts

`fusionframe` now has a fuller account lifecycle on top of its auth helpers.

## Building Blocks

- `InMemoryAuthBackend` for password-backed authentication
- `PasswordResetManager` for signed reset tokens
- `AccountManager` for registration, verification, password change, and password reset orchestration
- `require_resource_permission(...)` for resource-scoped authorization checks

## Example

```python
from fusionframe import AccountManager, InMemoryAuthBackend

backend = InMemoryAuthBackend()
accounts = AccountManager(backend)

await accounts.register(
    "owner@example.com",
    "secret",
    identity={"sub": "owner-1", "roles": ["owner"]},
)

token = accounts.issue_verification_token("owner@example.com")
await accounts.mark_verified(token)
user = await accounts.authenticate("owner@example.com", "secret", require_verified=True)
```

## Resource Permissions

Use `require_resource_permission(action, resource_getter)` when access depends on the target object or domain instead of only a static role.

```python
from fusionframe import require_resource_permission

@app.get("/projects/{project_slug}")
@require_resource_permission("read", lambda request: f"projects/{request.params['project_slug']}")
async def project_detail(request):
    return {"ok": True}
```

## Scope

This is still a framework-level foundation, not a complete identity platform. You still need to decide:

- user persistence strategy
- password/email delivery UX
- MFA or social login
- account recovery UI
