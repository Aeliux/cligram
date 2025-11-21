from typing import TYPE_CHECKING

from .. import exceptions

if TYPE_CHECKING:
    from .. import Application, Config

_global_config: "Config | None" = None
_running_application: "Application | None" = None


def _set_global_config(config: "Config") -> None:
    """Set the global configuration object.

    Args:
        config: The configuration object to set as global.
    """
    global _global_config

    _global_config = config


def get_global_config() -> "Config | None":
    """Get the global configuration object.

    Returns:
        The global configuration object if set, otherwise None.
    """
    return _global_config


def _set_running_application(app: "Application") -> None:
    """Set the running application object.

    Args:
        app: The application object to set.

    Raises:
        ApplicationAlreadyRunningError: If an application is already running.
    """
    global _running_application

    if _running_application is not None:
        raise exceptions.ApplicationAlreadyRunningError(
            "An application is already running"
        )

    app.add_shutdown_callback(lambda app: _clear_running_application(app))

    _running_application = app


def _clear_running_application(app: "Application") -> None:
    """Clear the running application object.

    Args:
        app: The application object to clear.

    Raises:
        ApplicationNotRunningError: If the provided application is not the running one.
    """
    global _running_application

    if _running_application != app:
        raise exceptions.ApplicationNotRunningError(
            "The provided application is not the running application"
        )

    _running_application = None


def get_running_application() -> "Application | None":
    """Get the running application object.

    Returns:
        The running application object if set, otherwise None.
    """
    return _running_application
