import pytest

from labtrack import consents


def test_required_and_ai_kinds_are_known() -> None:
    assert set(consents.VERSIONS) >= consents.REQUIRED
    assert set(consents.VERSIONS) >= consents.AI_EXTRACTION
    assert not consents.REQUIRED & consents.AI_EXTRACTION  # AI stays optional


def test_draft_texts_never_reach_production(monkeypatch: pytest.MonkeyPatch) -> None:
    for env in ("dev", "test", "staging"):
        consents.assert_releasable(env)
    with pytest.raises(RuntimeError, match="Q12"):
        consents.assert_releasable("production")
    for kind in list(consents.VERSIONS):
        monkeypatch.setitem(consents.VERSIONS, kind, "1")
    consents.assert_releasable("production")
