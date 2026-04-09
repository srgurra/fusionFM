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
