# Architecture

`fusionframe` keeps the root import surface stable, but the repository is now organized around a few internal groupings so the codebase can grow without turning into a flat module list forever.

## Package Layout

- [fusionframe/core](../fusionframe/core/__init__.py)
  - app lifecycle
  - request/response primitives
  - middleware, routing, plugins, testing
- [fusionframe/security](../fusionframe/security/__init__.py)
  - auth, authorization, sessions, CSRF
- [fusionframe/data](../fusionframe/data/__init__.py)
  - database, ORM, migrations, pagination
- [fusionframe/integrations](../fusionframe/integrations/__init__.py)
  - templates, static assets, SPA mounting, GraphQL, service client
- [fusionframe/operations](../fusionframe/operations/__init__.py)
  - jobs, cache, rate limiting

## Stability

- The supported public API is still the root `fusionframe` package.
- These grouped subpackages are primarily organizational and future-facing.
- They make internal ownership and future refactors cleaner without forcing import churn on users.

## Practical Rule

- application code should continue to prefer `from fusionframe import ...`
- framework contributors can use the grouped subpackages to understand where new code belongs
