from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from app.services.domains import central_hosts, resolve_company


class CompanyDomainMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        host = (request.url.hostname or "").lower().rstrip(".")
        request.state.company_domain = None
        if host not in central_hosts():
            context = await resolve_company(host)
            if context is None:
                return JSONResponse({"detail": "This company address is not connected or is inactive"}, status_code=404, headers={"Cache-Control": "no-store"})
            request.state.company_domain = context
            if request.url.path == "/platform" or request.url.path.startswith("/platform/") or request.url.path == "/auth/register":
                return JSONResponse({"detail": "Use the main HRMS address for platform administration and workspace registration"}, status_code=403)
        response = await call_next(request)
        if request.url.path.startswith("/domains"):
            response.headers["Cache-Control"] = "no-store"
        return response
