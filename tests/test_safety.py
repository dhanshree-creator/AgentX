"""Safety tests: budgets, permissions, SSRF guard, config validation, provider redaction."""

import pytest

from agent.config import AgentConfig, _truthy
from agent.exceptions import SafetyLimitError, ToolExecutionError
from safety.limits import Budget
from safety.permissions import check_permission
from safety.ssrf import assert_public_url
from safety.validation import validate_arguments

# ---- Budget ----


def test_budget_stops_after_limit():
    b = Budget(max_tool_calls=2, max_turns=5, deadline_s=60)
    b.claim_tool_call()
    b.claim_tool_call()
    with pytest.raises(SafetyLimitError):
        b.claim_tool_call()


def test_turn_budget():
    b = Budget(max_tool_calls=5, max_turns=2, deadline_s=60)
    b.check_turn(0)
    with pytest.raises(SafetyLimitError):
        b.check_turn(2)


def test_deadline():
    import time as _t

    b = Budget(max_tool_calls=5, max_turns=5, deadline_s=0.05)
    _t.sleep(0.08)
    with pytest.raises(SafetyLimitError):
        b.check_deadline()


# ---- Permissions ----


def test_permission_denied():
    class T:
        requires_permission = True
        permission_label = "system command execution"

    with pytest.raises(SafetyLimitError):
        check_permission(T(), approved=set())


def test_permission_granted():
    class T:
        name = "shell"
        requires_permission = True
        permission_label = "approval"

    check_permission(T(), approved={"shell"})  # must not raise


def test_readonly_tools_need_no_permission():
    class T:
        requires_permission = False

    check_permission(T(), approved=set())  # must not raise


# ---- SSRF / URL guard ----


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data",
        "https://localhost/x",
        "https://127.0.0.1/x",
        "https://metadata.google.internal/computeMetadata/v1/",
        "ftp://example.com/file",
        "https://192.168.1.1/admin",
        "https://10.0.0.5/internal",
    ],
)
def test_blocked_urls(url):
    from agent.exceptions import ToolExecutionError

    with pytest.raises(ToolExecutionError):
        assert_public_url(url)


def test_public_https_url_accepted():
    assert_public_url("https://example.com/page")


# ---- Config ----


def test_config_never_exposes_api_key():
    cfg = AgentConfig(base_url="https://api.example.com/v1", api_key="secret-key", model="m")
    dumped = cfg.model_dump()
    assert "secret-key" not in str(dumped)
    assert "secret-key" not in repr(cfg)


def test_config_http_requires_optin():
    with pytest.raises((ValueError, TypeError)):
        AgentConfig(
            base_url="http://api.example.com/v1",
            api_key="k",
            model="m",
            allow_insecure_base_url=False,
        )
    ok = AgentConfig(
        base_url="http://127.0.0.1:8080/v1",
        api_key="k",
        model="m",
        allow_insecure_base_url=True,
    )
    assert ok.base_url.endswith("/v1")


def test_truthy_parsing():
    assert _truthy("1") and _truthy("true") and _truthy("YES")
    assert not _truthy("") and not _truthy("false") and not _truthy(None)


# ---- Provider redaction ----


def test_provider_error_redacts_secrets():
    from agent.provider import ProviderAdapter

    class FakeSdkError(Exception):
        pass

    exc = FakeSdkError("Request failed: api_key=sk-abcdef123456 was rejected")
    desc = ProviderAdapter._describe(exc)
    assert "sk-abcdef123456" not in desc
    assert "[redacted]" in desc


# ---- Validation bridge ----


def test_validation_rejects_unknown_fields():
    from pydantic import BaseModel, ConfigDict

    class Args(BaseModel):
        model_config = ConfigDict(extra="forbid")
        q: str

    class FakeTool:
        name = "fake"

    with pytest.raises(ToolExecutionError):
        validate_arguments(FakeTool(), Args, {"q": "ok", "extra": 1})


def test_validation_accepts_valid_payload():
    from pydantic import BaseModel, ConfigDict

    class Args(BaseModel):
        model_config = ConfigDict(extra="forbid")
        q: str

    class FakeTool:
        name = "fake"

    out = validate_arguments(FakeTool(), Args, {"q": "ok"})
    assert out == {"q": "ok"}
