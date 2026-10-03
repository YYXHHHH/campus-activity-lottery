"""品牌与术语：把站名、主题色、界面术语收敛到配置，避免散落在模板与 JS 中。

修改方式二选一：
1. 改 `.env` 里的 `BRAND_*` / `UI_LABELS`（推荐，不动代码）；
2. 直接改本文件的 `LABELS` 默认值。
"""

from __future__ import annotations

from typing import Any

from app.config import get_settings

# 品牌相关静态资源路径（由 main.TemplateStaticFiles 生成）
BRAND_CSS_PATH = "api/brand.css"
BRAND_JS_PATH = "api/brand.js"

# 界面术语默认值：按你的业务场景改这里，或全部通过 UI_LABELS 覆盖。
LABELS: dict[str, str] = {
    # --- 站名与通用 ---
    "app.tagline": "报名 · 抽签 · 签到",
    "nav.brand": "Campus Activity Hub",
    # --- 活动 ---
    "activity.title": "Campus Activity Hub",
    "activity.list": "活动列表",
    "activity.list_title": "校园活动",
    "activity.mine_registrations": "我的报名",
    "activity.mine_managed": "我的活动",
    "activity.manage": "活动管理",
    "activity.detail": "活动详情",
    "activity.unit": "活动",
    # --- 人 ---
    "user.list": "用户管理",
    "user.student": "学生",
    "user.organizer": "组织者",
    "user.admin": "管理员",
    # --- 签到 ---
    "checkin.title": "扫码签到",
    "checkin.onsite": "现场签到",
    # --- 认证 ---
    "auth.login": "登录",
    "auth.register": "注册",
    "auth.register_title": "注册新账号",
}

# 状态文案（枚举值 -> 中文），改这里可让徽章与下拉框同步变化。
STATUS_LABELS: dict[str, str] = {
    "DRAFT": "草稿",
    "PUBLISHED": "报名中",
    "LOTTERY_DONE": "已抽签",
    "CANCELLED": "已取消",
}
REGISTRATION_STATUS_LABELS: dict[str, str] = {
    "PENDING": "待抽签",
    "WON": "已中签",
    "WAITING": "候补中",
    "LOST": "未中签",
    "CANCELLED": "已取消",
    "WITHDRAWN": "已退出",
}
ROLE_LABELS: dict[str, str] = {
    "STUDENT": "学生",
    "ORGANIZER": "组织者",
    "ADMIN": "管理员",
}


def _darken(hex_color: str, factor: float = 0.85) -> str:
    """把 #rrggbb 按比例压暗，用于生成 hover 色；非法输入返回 None 交由调用方兜底。"""
    value = hex_color.strip().lstrip("#")
    if len(value) != 6:
        return ""
    try:
        channels = [int(value[i : i + 2], 16) for i in (0, 2, 4)]
    except ValueError:
        return ""
    return "#" + "".join(f"{max(0, min(255, int(channel * factor))):02x}" for channel in channels)


def resolve_labels() -> dict[str, str]:
    """LABELS 默认值 + .env / 环境变量 UI_LABELS 覆盖。"""
    labels = dict(LABELS)
    labels.update(get_settings().brand_labels)
    return labels


def build_branding() -> dict[str, Any]:
    """汇总品牌信息：标题、主题色与全部界面文案（供模板与前端共用）。"""
    settings = get_settings()
    primary = settings.BRAND_COLOR.strip() or "#2563eb"
    primary_dark = _darken(primary) or primary
    labels = resolve_labels()
    return {
        "name": settings.BRAND_NAME,
        "short_name": settings.BRAND_SHORT_NAME,
        "color": primary,
        "palette": {"primary": primary, "primary_dark": primary_dark},
        "labels": labels,
        "status_labels": {**STATUS_LABELS, **{k: labels[k] for k in STATUS_LABELS if k in labels}},
        "registration_status_labels": {
            **REGISTRATION_STATUS_LABELS,
            **{k: labels[k] for k in REGISTRATION_STATUS_LABELS if k in labels},
        },
        "role_labels": {**ROLE_LABELS, **{k: labels[k] for k in ROLE_LABELS if k in labels}},
    }


def build_template_context() -> dict[str, Any]:
    """HTML 服务端注入用上下文。

    可用占位符：`{{BRAND_NAME}}`、`{{BRAND_SHORT}}`、`{{BRAND_COLOR}}`、
    `{{BRAND_PRIMARY_DARK}}`、`{{LABELS[...]}}`。
    """
    brand = build_branding()
    return {
        "BRAND_NAME": brand["name"],
        "BRAND_SHORT": brand["short_name"],
        "BRAND_COLOR": brand["color"],
        "BRAND_PRIMARY_DARK": brand["palette"]["primary_dark"],
        "LABELS": brand["labels"],
    }
