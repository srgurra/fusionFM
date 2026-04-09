from pathlib import Path
from string import Template

from .http import Response


class TemplateEngine:
    def __init__(self, directory="templates", *, globals=None):
        self.directory = Path(directory)
        self.globals = dict(globals or {})

    def add_global(self, name, value):
        self.globals[name] = value

    def render(self, template_name, context=None):
        template_path = self.directory / template_name
        content = template_path.read_text(encoding="utf-8")
        merged = {**self.globals, **(context or {})}
        return Template(content).safe_substitute(merged)

    def render_string(self, source, context=None):
        merged = {**self.globals, **(context or {})}
        return Template(source).safe_substitute(merged)

    def response(self, template_name, context=None, status_code=200, headers=None):
        html = self.render(template_name, context=context)
        return Response(
            html,
            status_code=status_code,
            headers=headers,
            content_type="text/html; charset=utf-8",
        )


class JinjaTemplateEngine:
    def __init__(self, directory="templates", *, globals=None, autoescape=True):
        try:
            from jinja2 import Environment, FileSystemLoader, select_autoescape
        except ImportError as exc:
            raise RuntimeError(
                "Jinja2 support requires the 'jinja2' package. Install it with "
                "'pip install jinja2' or add it to your project dependencies."
            ) from exc

        self.directory = Path(directory)
        self.globals = dict(globals or {})
        self.environment = Environment(
            loader=FileSystemLoader(str(self.directory)),
            autoescape=select_autoescape(["html", "xml"]) if autoescape else False,
        )
        self.environment.globals.update(self.globals)

    def add_global(self, name, value):
        self.globals[name] = value
        self.environment.globals[name] = value

    def render(self, template_name, context=None):
        template = self.environment.get_template(template_name)
        return template.render(**{**self.globals, **(context or {})})

    def render_string(self, source, context=None):
        template = self.environment.from_string(source)
        return template.render(**{**self.globals, **(context or {})})

    def response(self, template_name, context=None, status_code=200, headers=None):
        html = self.render(template_name, context=context)
        return Response(
            html,
            status_code=status_code,
            headers=headers,
            content_type="text/html; charset=utf-8",
        )
