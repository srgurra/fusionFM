# Compatibility

`fusionframe` now treats API stability as an explicit contract instead of an informal goal.

## Contract

- The current API compatibility version is `1`.
- The supported root import surface is defined in [fusionframe/stability.py](../fusionframe/stability.py).
- Root exports from `fusionframe` are the default public API.
- `fusionframe.db` and `fusionframe.orm` are also considered stable integration modules.
- Other submodules should be treated as implementation details unless they are explicitly documented as stable.

## Deprecation Policy

- New APIs can be added in the current compatibility version.
- Existing public APIs should not be removed or renamed without first being deprecated.
- Deprecations should include:
  - documentation updates
  - runtime markers when practical
  - a migration path
- Final removal should coincide with a compatibility version change.

## Testing

- The stability contract is enforced by tests against:
  - `fusionframe.PUBLIC_API`
  - `fusionframe.__all__`
  - documented compatibility metadata

## Practical Guidance

- Prefer `from fusionframe import ...` for application code.
- Avoid importing from internal modules like `fusionframe.routing` or `fusionframe.docs` unless you are actively contributing to framework internals.
- If a helper needs to be part of the long-term contract, add it to the stability source of truth first instead of exporting it ad hoc.
