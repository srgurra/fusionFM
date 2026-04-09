import re
import inspect

from .exceptions import HTTPException


class GraphQL:
    def __init__(self):
        self.queries = {}

    def query(self, name=None):
        def decorator(func):
            self.queries[name or func.__name__] = func
            return func

        return decorator

    def mount(self, app, path="/graphql"):
        @app.get(path)
        async def graphql_docs(request):
            return {
                "message": "Send POST requests with a GraphQL query payload.",
                "fields": sorted(self.queries.keys()),
            }

        @app.post(path)
        async def graphql_handler(request):
            payload = request.body or {}
            query = payload.get("query", "")
            variables = payload.get("variables", {}) or {}

            field_name = _extract_field_name(query)
            if field_name not in self.queries:
                raise HTTPException(400, "Unknown GraphQL field")

            result = self.queries[field_name](request, **variables)
            if inspect.isawaitable(result):
                result = await result
            return {"data": {field_name: result}}


def _extract_field_name(query):
    cleaned = query.strip()
    match = re.search(r"\{\s*([A-Za-z_][A-Za-z0-9_]*)", cleaned)
    if not match:
        raise HTTPException(400, "Invalid GraphQL query")
    return match.group(1)
