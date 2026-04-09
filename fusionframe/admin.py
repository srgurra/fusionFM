from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Callable

from .authorization import authorize
from .exceptions import HTTPException
from .pagination import get_pagination_params, paginate
from .sessions import get_csrf_token, get_session_user, validate_csrf


@dataclass
class AdminModelConfig:
    model: object
    label: str
    table_name: str
    list_display: list[str]
    create_fields: list[str]
    edit_fields: list[str]
    search_fields: list[str]
    detail_fields: list[str]
    field_labels: dict[str, str]
    form_widgets: dict[str, str]
    list_transform: Callable | None = None
    detail_transform: Callable | None = None
    create_transform: Callable | None = None
    edit_transform: Callable | None = None


class AdminPanel:
    def __init__(self, title="fusionframe Admin", *, roles=None, permissions=None):
        self.title = title
        self.roles = roles or []
        self.permissions = permissions or []
        self.models = []

    def register(
        self,
        model,
        *,
        label=None,
        list_display=None,
        create_fields=None,
        edit_fields=None,
        search_fields=None,
        detail_fields=None,
        field_labels=None,
        form_widgets=None,
        list_transform=None,
        detail_transform=None,
        create_transform=None,
        edit_transform=None,
    ):
        default_fields = [column.name for column in model.__table__.columns]
        editable_fields = [
            column.name for column in model.__table__.columns if not column.primary_key
        ]
        config = AdminModelConfig(
            model=model,
            label=label or model.__name__,
            table_name=getattr(model, "__tablename__", model.__name__.lower()),
            list_display=list_display or default_fields,
            create_fields=create_fields or editable_fields,
            edit_fields=edit_fields or create_fields or editable_fields,
            search_fields=search_fields or list_display or default_fields,
            detail_fields=detail_fields or default_fields,
            field_labels=field_labels or {},
            form_widgets=form_widgets or {},
            list_transform=list_transform,
            detail_transform=detail_transform,
            create_transform=create_transform,
            edit_transform=edit_transform,
        )
        self.models.append(config)
        return model

    def install(self, app, get_session, prefix="/admin"):
        async def guard(request):
            user = request.user or get_session_user(request)
            if self.roles or self.permissions:
                if not authorize(
                    user,
                    roles=self.roles or None,
                    permissions=self.permissions or None,
                ):
                    raise HTTPException(403, "Forbidden")

        @app.get(prefix, dependencies={"db": get_session})
        async def admin_index(request, db):
            await guard(request)
            cards = []
            for config in self.models:
                count = len(config.model.all(db))
                cards.append(
                    "<li>"
                    f"<a href=\"{escape(prefix)}/{escape(config.table_name)}\">{escape(config.label)}</a> "
                    f"({count})"
                    "</li>"
                )

            return _page(
                self.title,
                f"<ul>{''.join(cards)}</ul>",
            ), 200

        @app.get(f"{prefix}/{{model_name}}", dependencies={"db": get_session})
        async def admin_model(request, db):
            await guard(request)
            config = self._find_model(request.params["model_name"])
            rows = config.model.all(db)
            query = (request.query.get("q") or [""])[0]
            if config.list_transform:
                transformed = config.list_transform(request, db, rows)
                rows = transformed if transformed is not None else rows
            if query:
                lowered = query.lower()
                rows = [
                    row
                    for row in rows
                    if any(
                        lowered in str(getattr(row, column, "")).lower()
                        for column in config.search_fields
                    )
                ]
            page_data = paginate(rows, **get_pagination_params(request))
            rows = page_data["items"]

            header_html = "".join(
                f"<th>{escape(config.field_labels.get(column, column))}</th>"
                for column in config.list_display
            )
            body_rows = []
            for row in rows:
                values = "".join(
                    f"<td>{escape(str(getattr(row, column, '')))}</td>"
                    for column in config.list_display
                )
                row_id = getattr(row, "id", "")
                body_rows.append(
                    f"<tr>{values}<td>"
                    f"<a href=\"{escape(prefix)}/{escape(config.table_name)}/{escape(str(row_id))}\">View</a> "
                    f"<a href=\"{escape(prefix)}/{escape(config.table_name)}/{escape(str(row_id))}/edit\">Edit</a>"
                    "</td></tr>"
                )

            table_html = (
                f"<form method='get'><input name='q' value='{escape(query)}' placeholder='Search' /><button type='submit'>Search</button></form>"
                f"<p><a href=\"{escape(prefix)}/{escape(config.table_name)}/new\">Create new</a></p>"
                f"<table border='1'><thead><tr>{header_html}<th>Actions</th></tr></thead>"
                f"<tbody>{''.join(body_rows)}</tbody></table>"
                f"<p>Page {page_data['page']} of {page_data['pages'] or 1}</p>"
            )
            return _page(config.label, table_html), 200

        @app.get(f"{prefix}/{{model_name}}/new", dependencies={"db": get_session})
        async def admin_new_form(request, db):
            await guard(request)
            config = self._find_model(request.params["model_name"])
            csrf_token = get_csrf_token(request)
            form = "".join(
                f"<label>{escape(config.field_labels.get(field, field))}"
                f"<input type=\"{escape(config.form_widgets.get(field, 'text'))}\" name=\"{escape(field)}\" />"
                "</label><br/>"
                for field in config.create_fields
            )
            html = (
                f"<form method='post' action='{escape(prefix)}/{escape(config.table_name)}/new'>"
                f"<input type='hidden' name='_csrf_token' value='{escape(csrf_token)}' />"
                f"{form}<button type='submit'>Create</button></form>"
            )
            return _page(f"Create {config.label}", html), 200

        @app.post(f"{prefix}/{{model_name}}/new", dependencies={"db": get_session})
        async def admin_create(request, db):
            await guard(request)
            if not validate_csrf(request):
                raise HTTPException(403, "CSRF validation failed")
            config = self._find_model(request.params["model_name"])
            payload = {}
            for field in config.create_fields:
                value = request.form().get(field, request.body.get(field))
                column = config.model.__table__.columns[field]
                payload[field] = _coerce_value(value, column.type.python_type if hasattr(column.type, "python_type") else str)
            if config.create_transform:
                transformed = config.create_transform(request, db, payload)
                payload = transformed if transformed is not None else payload

            instance = config.model(**payload).save(db)
            return _page(
                f"{config.label} created",
                f"<p>Created record with id {escape(str(getattr(instance, 'id', '')))}</p>",
            ), 201

        @app.get(f"{prefix}/{{model_name}}/{{record_id}}", dependencies={"db": get_session})
        async def admin_record(request, db):
            await guard(request)
            config = self._find_model(request.params["model_name"])
            record = config.model.get(db, int(request.params["record_id"]))
            if not record:
                raise HTTPException(404, "Record not found")
            if config.detail_transform:
                transformed = config.detail_transform(request, db, record)
                record = transformed if transformed is not None else record

            details = "".join(
                f"<li><strong>{escape(config.field_labels.get(field, field))}</strong>: "
                f"{escape(str(getattr(record, field)))}</li>"
                for field in config.detail_fields
            )
            actions = (
                f"<p><a href='{escape(prefix)}/{escape(config.table_name)}/{escape(request.params['record_id'])}/edit'>Edit</a></p>"
                f"<form method='post' action='{escape(prefix)}/{escape(config.table_name)}/{escape(request.params['record_id'])}/delete'>"
                f"<input type='hidden' name='_csrf_token' value='{escape(get_csrf_token(request))}' />"
                "<button type='submit'>Delete</button></form>"
            )
            return _page(config.label, f"<ul>{details}</ul>{actions}"), 200

        @app.get(f"{prefix}/{{model_name}}/{{record_id}}/edit", dependencies={"db": get_session})
        async def admin_edit_form(request, db):
            await guard(request)
            config = self._find_model(request.params["model_name"])
            record = config.model.get(db, int(request.params["record_id"]))
            if not record:
                raise HTTPException(404, "Record not found")

            csrf_token = get_csrf_token(request)
            form = "".join(
                f"<label>{escape(config.field_labels.get(field, field))}"
                f"<input type=\"{escape(config.form_widgets.get(field, 'text'))}\" "
                f"name=\"{escape(field)}\" value=\"{escape(str(getattr(record, field, '')))}\" />"
                "</label><br/>"
                for field in config.edit_fields
            )
            html = (
                f"<form method='post' action='{escape(prefix)}/{escape(config.table_name)}/{escape(request.params['record_id'])}/edit'>"
                f"<input type='hidden' name='_csrf_token' value='{escape(csrf_token)}' />"
                f"{form}<button type='submit'>Save</button></form>"
            )
            return _page(f"Edit {config.label}", html), 200

        @app.post(f"{prefix}/{{model_name}}/{{record_id}}/edit", dependencies={"db": get_session})
        async def admin_edit(request, db):
            await guard(request)
            if not validate_csrf(request):
                raise HTTPException(403, "CSRF validation failed")
            config = self._find_model(request.params["model_name"])
            record = config.model.get(db, int(request.params["record_id"]))
            if not record:
                raise HTTPException(404, "Record not found")
            for field in config.edit_fields:
                value = request.form().get(field, request.body.get(field))
                column = config.model.__table__.columns[field]
                setattr(
                    record,
                    field,
                    _coerce_value(
                        value,
                        column.type.python_type if hasattr(column.type, "python_type") else str,
                    ),
                )
            if config.edit_transform:
                transformed = config.edit_transform(request, db, record)
                record = transformed if transformed is not None else record
            record.save(db)
            return _page(config.label, "<p>Record updated</p>"), 200

        @app.post(f"{prefix}/{{model_name}}/{{record_id}}/delete", dependencies={"db": get_session})
        async def admin_delete(request, db):
            await guard(request)
            if not validate_csrf(request):
                raise HTTPException(403, "CSRF validation failed")
            config = self._find_model(request.params["model_name"])
            record = config.model.get(db, int(request.params["record_id"]))
            if not record:
                raise HTTPException(404, "Record not found")
            record.delete(db)
            return _page(config.label, "<p>Record deleted</p>"), 200

    def _find_model(self, model_name):
        config = next((item for item in self.models if item.table_name == model_name), None)
        if not config:
            raise HTTPException(404, "Model not found")
        return config


def _page(title, content):
    return (
        "<html><body>"
        f"<h1>{escape(title)}</h1>"
        f"{content}"
        "</body></html>"
    )


def _coerce_value(value, python_type):
    if value is None:
        return None
    if python_type is bool:
        return str(value).lower() in {"1", "true", "yes", "on"}
    return python_type(value)
