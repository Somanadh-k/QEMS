import pytest

from app.api.v1.deps import require_role
from app.core.exceptions import PermissionDeniedError


class _FakeUser:
    def __init__(self, roles: list[str]):
        self._roles = roles

    @property
    def role_names(self) -> list[str]:
        return self._roles


@pytest.mark.asyncio
async def test_require_role_allows_matching_role():
    guard = require_role("QA Reviewer", "Admin")
    user = _FakeUser(["QA Reviewer"])
    result = await guard(user=user)
    assert result is user


@pytest.mark.asyncio
async def test_require_role_rejects_non_matching_role():
    guard = require_role("QA Reviewer", "Admin")
    user = _FakeUser(["Viewer"])
    with pytest.raises(PermissionDeniedError):
        await guard(user=user)
