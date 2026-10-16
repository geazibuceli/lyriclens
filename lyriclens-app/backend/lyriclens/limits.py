from starlette.responses import JSONResponse
from starlette.exceptions import HTTPException


class UploadTooLarge(Exception):
    pass


class UploadLimit:
    """Bound the multipart body while receiving, before multipart spooling."""
    def __init__(self, app, max_bytes):
        self.app = app
        self.limit = max_bytes + 65536  # bounded multipart headers and form fields

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"] != "/api/jobs":
            return await self.app(scope, receive, send)
        count, started = 0, False
        async def bounded_receive():
            nonlocal count
            message = await receive()
            count += len(message.get("body", b""))
            if count > self.limit:
                raise HTTPException(413, "Upload exceeds configured size limit")
            return message
        async def track_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)
        try:
            headers = dict(scope["headers"])
            length = int(headers.get(b"content-length", b"0"))
            if length > self.limit:
                raise UploadTooLarge()
            await self.app(scope, bounded_receive, track_send)
        except UploadTooLarge:
            if not started:
                await JSONResponse({"detail":"Upload exceeds configured size limit"}, status_code=413)(scope, receive, send)
