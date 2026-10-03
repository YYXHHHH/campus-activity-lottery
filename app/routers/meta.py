"""站点元信息：品牌、主题色与界面术语，供前端初始化（无需登录即可访问）。"""

from __future__ import annotations

from fastapi import APIRouter

from app.branding import build_branding

router = APIRouter(prefix="/api/meta", tags=["meta"])


@router.get("")
def get_meta():
    """返回站点元信息。

    `labels` 为全部界面术语；`status_labels` / `registration_status_labels` /
    `role_labels` 为枚举值到显示文案的映射，前端徽章与下拉框据此渲染。
    """
    return build_branding()
