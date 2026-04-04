def get_openapi(title, version, routes_meta):
    paths = {}

    for route in routes_meta:
        path = route["path"]
        method = route["method"].lower()

        paths.setdefault(path, {})
        paths[path][method] = {
            "summary": route["handler"],
            "responses": {
                "200": {
                    "description": "Successful Response"
                }
            },
        }

        if route.get("model"):
            paths[path][method]["requestBody"] = {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {
                            "title": route["model"]
                        }
                    }
                },
            }

    return {
        "openapi": "3.0.0",
        "info": {
            "title": title,
            "version": version,
        },
        "paths": paths,
    }


def get_swagger_ui_html(openapi_url="/openapi.json", title="fusionFM Docs"):
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