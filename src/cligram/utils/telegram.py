import datetime
from platform import node, release, system
from typing import Optional

from telethon import TelegramClient
from telethon.tl.custom.dialog import Dialog
from telethon.tl.types import Channel, Chat, User

from ..config import Config
from ..proxy_manager import Proxy
from ..session import CustomSession


def get_client(
    config: Config, proxy: Optional[Proxy], session: Optional[CustomSession]
) -> TelegramClient:
    """
    Create a Telethon TelegramClient from the given configuration.
    """
    from .. import __version__

    params = {
        "session": session or get_session(config),
        "api_id": config.telegram.api.id,  # API ID from my.telegram.org
        "api_hash": config.telegram.api.hash,  # API hash from my.telegram.org
        "connection_retries": 2,  # Number of attempts before failing
        "device_model": node(),  # Real device model
        "system_version": f"{system()} {release()}",  # Real system details
        "app_version": f"cligram v{__version__}",  # Package version
        "lang_code": "en",  # Language to use for Telegram
        "timeout": 10,  # Timeout in seconds for requests
    }

    if proxy and not proxy.is_direct:
        params.update(proxy.export())

    return TelegramClient(**params)


def get_session(config: Config, create: bool = False) -> CustomSession:
    """
    Load a CustomSession based on the configuration.
    """
    return CustomSession(session_id=config.telegram.session, create=create)


def get_entity_name(
    entity: User | Chat | Channel,
):
    """Get the display name of a Telegram entity."""
    if hasattr(entity, "first_name") and entity.first_name:
        name = entity.first_name
        if hasattr(entity, "last_name") and entity.last_name:
            name += f" {entity.last_name}"
        return name.strip()
    elif hasattr(entity, "title") and entity.title:
        return entity.title
    elif hasattr(entity, "username") and entity.username:
        return f"@{entity.username}"
    else:
        return "Unknown"


def _is_dialog_muted(dialog: Dialog) -> bool:
    try:
        if not dialog.dialog.notify_settings.mute_until:
            return False

        return (
            dialog.dialog.notify_settings.mute_until.timestamp()
            > datetime.datetime.now().timestamp()
        )
    except Exception:
        return False
