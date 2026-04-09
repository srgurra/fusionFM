import dataclasses
import inspect
import types
import typing
from typing import Any, get_args, get_origin


def get_openapi(title, version, routes_meta):
    paths = {}
    components = {"schemas": {}, "securitySchemes": _security_schemes(routes_meta)}

    for route in routes_meta:
        path = route["path"]
        method = route["method"].lower()

        operation = {
            "summary": route["handler"],
            "responses": {
                "200": {
                    "description": "Successful Response",
                    "content": {
                        "application/json": {
                            "schema": _schema_for_type(
                                route.get("response_model"),
                                components["schemas"],
                            )
                        }
                    },
                }
            },
        }

        parameters = _path_parameters(path)
        if parameters:
            operation["parameters"] = parameters

        if route.get("deprecated"):
            operation["deprecated"] = True

        request_model = route.get("model")
        if request_model:
            operation["requestBody"] = {
                "required": True,
                "content": {
                    route.get("request_media_type", "application/json"): {
                        "schema": _schema_for_type(
                            request_model,
                            components["schemas"],
                        )
                    }
                },
            }

        if route.get("security"):
            operation["security"] = [{"bearerAuth": []}, {"sessionAuth": []}]

        if route.get("roles"):
            operation["x-required-roles"] = route["roles"]
        if route.get("permissions"):
            operation["x-required-permissions"] = route["permissions"]
        if route.get("policy"):
            operation["x-authorization-policy"] = route["policy"]

        paths.setdefault(path, {})
        paths[path][method] = operation

    return {
        "openapi": "3.0.0",
        "info": {
            "title": title,
            "version": version,
        },
        "paths": paths,
        "components": components,
    }


def get_swagger_ui_html(openapi_url="/openapi.json", title="fusionframe Docs"):
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>{title}</title>
        <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist/swagger-ui.css" />
    </head>
    <body>
        <div id="swagger-ui"></div>
        <script src="https://unpkg.com/swagger-ui-dist/swagger-ui-bundle.js"></script>
        <script>
            SwaggerUIBundle({{
                url: "{openapi_url}",
                dom_id: "#swagger-ui"
            }});
        </script>
    </body>
    </html>
    """


def _security_schemes(routes_meta):
    if not any(route.get("security") for route in routes_meta):
        return {}
    return {
        "bearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        },
        "sessionAuth": {
            "type": "apiKey",
            "in": "cookie",
            "name": "session",
        },
    }


def _path_parameters(path):
    parameters = []
    for part in path.strip("/").split("/"):
        if not (part.startswith("{") and part.endswith("}")):
            continue
        raw = part[1:-1]
        if ":" in raw:
            name, converter = raw.split(":", 1)
        else:
            name, converter = raw, "str"
        parameters.append(
            {
                "name": name,
                "in": "path",
                "required": True,
                "schema": _converter_schema(converter),
            }
        )
    return parameters


def _converter_schema(converter):
    if converter == "int":
        return {"type": "integer"}
    if converter == "float":
        return {"type": "number"}
    return {"type": "string"}


def _schema_for_type(annotation, components):
    if annotation is None:
        return {}
    if annotation is inspect.Signature.empty:
        return {}

    origin = get_origin(annotation)
    if origin in {list, tuple, set}:
        args = get_args(annotation)
        item_type = args[0] if args else Any
        return {
            "type": "array",
            "items": _schema_for_type(item_type, components),
        }
    if origin is dict:
        args = get_args(annotation)
        value_type = args[1] if len(args) > 1 else Any
        return {
            "type": "object",
            "additionalProperties": _schema_for_type(value_type, components),
        }
    if origin in {types.UnionType, typing.Union}:
        args = [arg for arg in get_args(annotation) if arg is not type(None)]
        if len(args) == 1:
            return _schema_for_type(args[0], components)
        return {"oneOf": [_schema_for_type(arg, components) for arg in args]}

    if annotation in {str, int, float, bool}:
        return _primitive_schema(annotation)

    if annotation is None or annotation is type(None):
        return {"nullable": True}

    if getattr(annotation, "__module__", "") == "builtins" and annotation is dict:
        return {"type": "object"}

    model_json_schema = getattr(annotation, "model_json_schema", None)
    if callable(model_json_schema):
        name = annotation.__name__
        if name not in components:
            components[name] = model_json_schema(ref_template="#/components/schemas/{model}")
        return {"$ref": f"#/components/schemas/{name}"}

    if dataclasses.is_dataclass(annotation):
        name = annotation.__name__
        if name not in components:
            properties = {}
            required = []
            for field in dataclasses.fields(annotation):
                properties[field.name] = _schema_for_type(field.type, components)
                if field.default is dataclasses.MISSING and field.default_factory is dataclasses.MISSING:
                    required.append(field.name)
            schema = {"type": "object", "properties": properties}
            if required:
                schema["required"] = required
            components[name] = schema
        return {"$ref": f"#/components/schemas/{name}"}

    if isinstance(annotation, type):
        name = annotation.__name__
        if name not in components:
            components[name] = {"title": name, "type": "object"}
        return {"$ref": f"#/components/schemas/{name}"}

    return {}


def _primitive_schema(annotation):
    mapping = {
        str: {"type": "string"},
        int: {"type": "integer"},
        float: {"type": "number"},
        bool: {"type": "boolean"},
    }
    return mapping.get(annotation, {})
