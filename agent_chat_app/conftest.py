import pytest


@pytest.fixture(autouse=True)
def _media_storage(settings, tmpdir) -> None:
    settings.MEDIA_ROOT = tmpdir.strpath


@pytest.fixture
def user(db):
    from agent_chat_app.users.tests.factories import UserFactory
    return UserFactory()
