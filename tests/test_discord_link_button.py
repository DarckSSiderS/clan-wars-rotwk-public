from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.discord_bot.community import RolePanel


@pytest.mark.asyncio
async def test_link_button_uses_command_checks_and_callback():
    command = SimpleNamespace(_check_can_run=AsyncMock(return_value=True), callback=AsyncMock())
    bot = SimpleNamespace(tree=SimpleNamespace(get_command=Mock(return_value=command)))
    panel = RolePanel(bot)
    button = next(b for b in panel.children if b.custom_id == "palantir:link")
    interaction = object()
    await button.callback(interaction)
    command._check_can_run.assert_awaited_once_with(interaction)
    command.callback.assert_awaited_once_with(interaction)
    command._check_can_run.return_value = False
    command.callback.reset_mock()
    await button.callback(interaction)
    command.callback.assert_not_awaited()
