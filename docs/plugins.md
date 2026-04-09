# Plugin Ecosystem

Plugins are the main extensibility mechanism for `fusionframe`.

## Plugin shape

```python
from fusionframe import Plugin


class MetricsPlugin(Plugin):
    def setup(self, app):
        @app.get("/metrics-status")
        async def metrics_status(request):
            return {"enabled": True}

    async def startup(self, app):
        app.state.metrics_ready = True

    async def shutdown(self, app):
        app.state.metrics_ready = False
```

Register it:

```python
app.plugin(MetricsPlugin)
```

Or by import path:

```python
app.plugin("myproject.plugins:MetricsPlugin")
```

## Recommended plugin responsibilities

- register routes
- add middleware
- attach lifecycle hooks
- initialize framework subsystems

## Recommended boundaries

- avoid hidden global state
- prefer storing plugin runtime state on `app.state`
- keep plugin configuration explicit
- document any routes, middleware, or jobs registered by the plugin
