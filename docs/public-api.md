# Public API

`fusionframe` treats root-level imports from `fusionframe` as its primary supported public surface.

Compatibility policy:

- Current API compatibility version: `1`
- Public names exported from `fusionframe` are expected to remain stable within the same compatibility version.
- Behavior-breaking removals or renames require:
  - a deprecation period first
  - documentation updates
  - a compatibility version change for final removal
- Internal implementation modules are not covered by this promise unless explicitly documented.

Supported import boundary:

- Stable: `fusionframe`
- Stable for integration helpers: `fusionframe.db`, `fusionframe.orm`
- Internal/unstable by default: other submodules such as `fusionframe.routing`, `fusionframe.di`, `fusionframe.docs`, `fusionframe.middleware`, and similar implementation modules

- `App`
- `AppSettings`
- `AppState`
- `deprecated`
- `Request`, `Response`, `JSONResponse`, `WebSocket`, `UploadedFile`
- `HTTPException`, `WebSocketException`
- `Plugin`
- `TemplateEngine`
- `GraphQL`
- `VersionedAPI`
- `TestClient`

Core built-ins:

- Routing: `app.get`, `app.post`, `app.put`, `app.delete`, `app.websocket`
- Lifecycle: `app.on_startup`, `app.on_shutdown`
- Error handling: `app.exception_handler`
- Plugins: `app.plugin`
- Versioned APIs: `app.api`

Security and auth helpers:

- `create_token`, `verify_token`
- `require_auth`, `require_role`, `require_permission`
- `session_middleware`
- `auth_middleware`
- `security_headers_middleware`

Application helpers:

- `mount_static`, `mount_spa`
- `paginate`, `get_pagination_params`
- `cache`, `rate_limit`
- `AdminPanel`
- `ServiceClient`

Stability source of truth:

- The canonical supported export list is defined in [fusionframe/stability.py](/Users/srilakshmi/Documents/blogs/fusionFM/fusionframe/stability.py) as `PUBLIC_API`.
- [fusionframe/__init__.py](/Users/srilakshmi/Documents/blogs/fusionFM/fusionframe/__init__.py) derives `__all__` from that list.
- Compatibility tests assert that the exported surface and documented contract stay aligned.

Stability notes:

- Names listed here should remain stable across normal minor releases.
- Experimental behavior should be marked with documentation or deprecation notices before removal.
- Deprecated routes can be marked with `@deprecated(...)`, and OpenAPI will reflect that.
