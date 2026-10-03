"""M0 统一异常体系与响应包装（§7.1、附录 B）。"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)


class BizError(Exception):
    def __init__(self, code: int = 40001, http_status: int = 400, message: str = "请求错误", data=None):
        super().__init__(message)
        self.code = code
        self.http_status = http_status
        self.message = message
        self.data = data


class BadRequest(BizError):
    def __init__(self, message: str, data=None):
        super().__init__(40001, 400, message, data)


class Unauthorized(BizError):
    def __init__(self, message: str = "未登录或登录已失效", data=None):
        super().__init__(40101, 401, message, data)


class LoginFailed(BizError):
    def __init__(self, message: str = "用户名或密码错误"):
        super().__init__(40102, 401, message)


class Forbidden(BizError):
    def __init__(self, message: str = "无权限访问该资源"):
        super().__init__(40301, 403, message)


class NotFound(BizError):
    def __init__(self, message: str = "资源不存在"):
        super().__init__(40401, 404, message)


class Conflict(BizError):
    def __init__(self, message: str, data=None):
        super().__init__(40901, 409, message, data)


def ok(data=None, message: str = "ok"):
    return {"code": 0, "message": message, "data": data}


FRIENDLY_MESSAGES = {
    "string_too_short": "长度不足",
    "string_too_long": "长度超限",
    "string_pattern_mismatch": "格式不合法",
    "greater_than_equal": "取值过小",
    "less_than_equal": "取值过大",
    "int_parsing": "必须为整数",
    "bool_parsing": "必须为布尔值",
    "datetime_parsing": "时间格式不合法（需 ISO 8601 UTC）",
    "datetime_from_date_parsing": "时间格式不合法（需 ISO 8601 UTC）",
    "literal_error": "取值不在允许范围内",
    "missing": "缺少必填参数",
}


def _error_type(error: dict) -> str:
    return str(error.get("type", ""))


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(BizError)
    async def _biz_error(request: Request, exc: BizError):
        return JSONResponse(
            status_code=exc.http_status,
            content={"code": exc.code, "message": exc.message, "data": exc.data},
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(part) for part in first.get("loc", ()) if part != "body")
        raw_message = str(first.get("msg", "参数错误"))
        friendly = FRIENDLY_MESSAGES.get(_error_type(first)) or (
            "参数格式不合法" if raw_message.lower().startswith("value is") else raw_message
        )
        message = f"{loc}：{friendly}" if loc else friendly
        return JSONResponse(status_code=400, content={"code": 40001, "message": message, "data": None})

    @app.exception_handler(IntegrityError)
    async def _integrity_error(request: Request, exc: IntegrityError):
        logger.warning("[errors] 数据冲突 %s %s", request.url.path, exc)
        return JSONResponse(status_code=409, content={"code": 40901, "message": "数据冲突", "data": None})

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        logger.exception("[errors] 未处理异常 %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"code": 50001, "message": "服务器内部错误", "data": None})
