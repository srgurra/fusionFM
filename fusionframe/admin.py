from html import escape


class AdminPanel:
    def __init__(self, title="fusionframe Admin"):
        self.title = title
        self.models = []

    def register(self, model):
        self.models.append(model)
        return model

    def install(self, app, get_session, prefix="/admin"):
        @app.get(prefix, dependencies={"db": get_session})
        async def admin_index(request, db):
            links = []
            for model in self.models:
                name = model.__name__
                table = getattr(model, "__tablename__", name.lower())
                count = len(model.all(db))
                links.append(
                    f'<li><a href="{escape(prefix)}/{escape(table)}">{escape(name)}</a> ({count})</li>'
                )

            html = (
                f"<html><body><h1>{escape(self.title)}</h1><ul>{''.join(links)}</ul></body></html>"
            )
            return html, 200

        @app.get(f"{prefix}/{{model_name}}", dependencies={"db": get_session})
        async def admin_model(request, db):
            model_name = request.params["model_name"]
            model = next(
                (
                    item
                    for item in self.models
                    if getattr(item, "__tablename__", item.__name__.lower()) == model_name
                ),
                None,
            )
            if not model:
                return {"error": "Model not found"}, 404

            rows = model.all(db)
            headers = [column.name for column in model.__table__.columns]
            body_rows = []
            for row in rows:
                values = "".join(
                    f"<td>{escape(str(getattr(row, column)))}</td>" for column in headers
                )
                body_rows.append(f"<tr>{values}</tr>")

            table_html = (
                f"<table border='1'><thead><tr>{''.join(f'<th>{escape(header)}</th>' for header in headers)}</tr></thead>"
                f"<tbody>{''.join(body_rows)}</tbody></table>"
            )
            html = f"<html><body><h1>{escape(model.__name__)}</h1>{table_html}</body></html>"
            return html, 200
