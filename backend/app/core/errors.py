from fastapi.responses import JSONResponse


def openai_error(
    status: int,
    message: str,
    *,
    code: str | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    error_type = (
        "insufficient_quota"
        if code == "insufficient_quota"
        else ("server_error" if status >= 500 else "invalid_request_error")
    )
    return JSONResponse(
        {
            "error": {
                "message": message,
                "type": error_type,
                "param": None,
                "code": code,
            }
        },
        status_code=status,
        headers={"Cache-Control": "no-store", **(headers or {})},
    )
