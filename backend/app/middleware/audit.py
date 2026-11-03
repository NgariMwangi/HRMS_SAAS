from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.services.audit import record_http_audit, should_skip_audit

_ERROR_BODY_CAP = 8192


class AuditLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if should_skip_audit(request.method, request.url.path):
            return await call_next(request)

        body = await request.body()
        response = await call_next(request)
        error_body: bytes | None = None
        if response.status_code >= 400:
            chunks: list[bytes] = []
            size = 0
            async for chunk in response.body_iterator:
                chunks.append(chunk)
                size += len(chunk)
                if size >= _ERROR_BODY_CAP:
                    break
            error_body = b"".join(chunks)
            headers = {key: value for key, value in response.headers.items() if key.lower() != "content-length"}
            response = Response(
                content=error_body,
                status_code=response.status_code,
                headers=headers,
                media_type=response.media_type,
            )

        await record_http_audit(
            method=request.method,
            path=request.url.path,
            query=request.url.query,
            body=body,
            content_type=request.headers.get("content-type", ""),
            authorization=request.headers.get("authorization"),
            status_code=response.status_code,
            response_body=error_body,
        )
        return response
