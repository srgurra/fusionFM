# Releasing

## Local release checks

```bash
pytest -q
python -m compileall fusionframe tests example.py
python scripts/benchmark.py
rm -rf dist build fusionframe.egg-info
python -m build --no-isolation
twine check dist/*
```

## Publish manually

```bash
python -m twine upload dist/*
```

## GitHub Actions

- `.github/workflows/ci.yml` runs tests and packaging checks on pushes and pull requests.
- `.github/workflows/publish.yml` publishes on GitHub release publication.

## Release checklist

1. Ensure tests are green.
2. Update version in `pyproject.toml` and `fusionframe.__version__`.
3. Confirm README and docs match current behavior.
4. Build and validate distributions.
5. Create a Git tag and GitHub release.
