from __future__ import annotations

PAID_PLANS = {"pro", "admin"}
PRO_EXPORT_FORMATS = {"pdf", "docx"}


def can_export_format(user_plan: str | None, export_format: str) -> bool:
    plan = (user_plan or "free").strip().lower()
    fmt = (export_format or "").strip().lower()
    if fmt not in PRO_EXPORT_FORMATS:
        return True
    return plan in PAID_PLANS
