from pathlib import Path
from string import Template

from .http import Response


class TemplateEngine:
    def __init__(self, directory="templates"):
        self.directory = Path(directory)

    def render(self, template_name, context=None):
        template_path = self.directory / template_name
        content = template_path.read_text(encoding="utf-8")
        return Template(content).safe_substitute(context or {})

    def response(self, template_name, context=None, status_code=200, headers=None):
        html = self.render(template_name, context=context)
        return Response(
            html,
            status_code=status_code,
            headers=headers,
            content_type="text/html; charset=utf-8",
        )
