# React And TypeScript

`fusionframe` is not limited to server-rendered templates. It works as a Python backend for modern React/TypeScript frontends as well.

## Recommended Setup

- frontend: React + TypeScript + Vite
- backend: `fusionframe` API app
- local development:
  - run the backend on `127.0.0.1:8000`
  - run Vite on `127.0.0.1:5173`
  - use either Vite proxying or explicit CORS

## Backend Example

See [react_backend.py](../examples/react_backend.py).

Key piece:

```python
from fusionframe import App, cors_middleware

app = App()
app.use(
    cors_middleware(
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
    )
)
```

## Frontend Example

See [package.json](../examples/react_vite_frontend/package.json) and [App.tsx](../examples/react_vite_frontend/src/App.tsx).

The example uses Vite proxying:

```ts
proxy: {
  "/api": {
    target: "http://127.0.0.1:8000",
    changeOrigin: true,
  },
}
```

## Auth Guidance

For frontend apps:

- bearer-token auth works well for explicit API clients
- cookie/session auth also works, but requires:
  - `allow_credentials=True`
  - frontend requests with `credentials: "include"`
  - secure cookie settings in production

## Why This Matters

The framework’s value proposition is not “templates only.” The better framing is:

- server-rendered apps when you want them
- React/TypeScript-friendly backend APIs when you do not
