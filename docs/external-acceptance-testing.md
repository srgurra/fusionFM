# External Acceptance Testing

This example tests `fusionframe` the way an external app builder would use it:

- React/TypeScript frontend
- session login
- CSRF-protected writes
- protected APIs
- external public API aggregation
- GraphQL
- file uploads
- forms
- background tasks
- app-level jobs
- websockets
- static files and SPA mounting

## Backend

Run the backend:

```bash
fusionframe run examples.external_acceptance.backend:app
```

The backend is defined in [backend.py](../examples/external_acceptance/backend.py).

It is wired to public APIs by default:

- GitHub REST API
- PyPI JSON API
- Hacker News Algolia API

The test suite replaces those network calls with a fake adapter so CI stays deterministic and offline-friendly.

## React Client

The React client lives in [frontend](../examples/external_acceptance/frontend).
The committed static build fixture used by backend tests lives in [frontend_build](../examples/external_acceptance/frontend_build).

For manual development:

```bash
cd examples/external_acceptance/frontend
npm install
npm run dev
```

The Vite dev server proxies `/api` to the backend at `127.0.0.1:8000`.

## Automated Test

Run the external acceptance test:

```bash
pytest -q tests/test_external_acceptance_app.py
```

This verifies the framework through public APIs and example-app behavior instead of calling internal implementation helpers directly.
