from app.billing.policy import PAID_PLANS, PRO_EXPORT_FORMATS, can_export_format


def test_can_export_format_allows_free_formats():
    assert can_export_format(None, "srt")
    assert can_export_format("free", "vtt")
    assert can_export_format("FREE", "json")


def test_can_export_format_blocks_paid_only_formats_for_free_users():
    assert not can_export_format(None, "pdf")
    assert not can_export_format("free", "docx")


def test_can_export_format_allows_paid_and_admin_users():
    assert can_export_format("pro", "pdf")
    assert can_export_format("ADMIN", "docx")


def test_admin_effective_plan_allows_paid_formats():
    assert can_export_format("admin", "pdf")


def test_policy_constants_include_expected_values():
    assert PAID_PLANS == {"pro", "admin"}
    assert PRO_EXPORT_FORMATS == {"pdf", "docx"}
