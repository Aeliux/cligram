import datetime
from platform import node, release, system
from typing import Optional

from telethon import TelegramClient
from telethon.tl.custom.dialog import Dialog
from telethon.tl.types import (
    Channel,
    Chat,
    ChatPhoto,
    ChatPhotoEmpty,
    User,
    UserProfilePhoto,
    UserProfilePhotoEmpty,
    UserStatusEmpty,
    UserStatusLastMonth,
    UserStatusLastWeek,
    UserStatusOffline,
    UserStatusOnline,
    UserStatusRecently,
)

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
        "app_version": __version__,  # Package version
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


def get_status(entity: User):
    """Get the status of a Telegram user."""
    status = entity.status
    if status is None or isinstance(status, UserStatusEmpty):
        return "N/A"
    elif isinstance(status, UserStatusOnline):
        return "Online"
    elif isinstance(status, UserStatusOffline):
        return f"Last seen at {status.was_online.strftime('%Y-%m-%d %H:%M:%S')}"
    elif isinstance(status, UserStatusRecently):
        return "Last seen recently"
    elif isinstance(status, UserStatusLastWeek):
        return "Last seen within the last week"
    elif isinstance(status, UserStatusLastMonth):
        return "Last seen within the last month"
    else:
        return "N/A"


def get_id_from_input_peer(input_peer) -> int:
    """Extract the unique ID from an input peer object."""
    if hasattr(input_peer, "user_id") and input_peer.user_id is not None:
        return input_peer.user_id
    elif hasattr(input_peer, "chat_id") and input_peer.chat_id is not None:
        return input_peer.chat_id
    elif hasattr(input_peer, "channel_id") and input_peer.channel_id is not None:
        return input_peer.channel_id
    else:
        raise ValueError("Input peer does not have a valid ID attribute.")


def has_profile_photo(entity: User | Chat | Channel) -> bool:
    """Check if the entity has a profile photo."""
    photo = getattr(entity, "photo", None)
    if isinstance(photo, (UserProfilePhoto, ChatPhoto)):
        return True
    return False


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
