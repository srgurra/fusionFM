import json
from urllib.request import Request, urlopen


class ServiceClient:
    def __init__(self, base_url, timeout=5):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def get(self, path, headers=None):
        return self.request("GET", path, headers=headers)

    def post(self, path, json_body=None, headers=None):
        return self.request("POST", path, json_body=json_body, headers=headers)

    def request(self, method, path, json_body=None, headers=None):
        url = f"{self.base_url}/{path.lstrip('/')}"
        data = None
        request_headers = dict(headers or {})

        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")

        request = Request(url, data=data, headers=request_headers, method=method)
        with urlopen(request, timeout=self.timeout) as response:
            raw = response.read()
            content_type = response.headers.get("Content-Type", "")
            if "application/json" in content_type:
                return json.loads(raw.decode("utf-8"))
            return raw
