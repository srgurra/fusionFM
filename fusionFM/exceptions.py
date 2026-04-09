class HTTPException(Exception):
    def __init__(self, status_code, detail, headers=None):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.headers = headers or {}


class WebSocketException(Exception):
    def __init__(self, code=1008, reason="WebSocket error"):
        super().__init__(reason)
        self.code = code
        self.reason = reason
