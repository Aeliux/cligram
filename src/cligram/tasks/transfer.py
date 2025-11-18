import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from rich.progress import BarColumn, Progress, TextColumn

from .. import GLOBAL_CONFIG_PATH, CustomSession, exceptions, utils

if TYPE_CHECKING:
    from .. import Application, CustomSession

TRANSFER_PROTOCOL_VERSION = 1


class _ExportType(Enum):
    FILE = "file"
    BASE64 = "base64"


@dataclass
class _ExportConfig:
    """Configuration for export task."""

    export_config: bool = True
    export_dotenv: bool = False
    exported_sessions: list[str] | str = field(default_factory=list)
    exported_states: list[str] | str = field(default_factory=list)
    export_type: _ExportType = _ExportType.BASE64
    path: Optional[Path] = None
    password: Optional[str] = None

    def __post_init__(self):
        if self.path is not None:
            self.export_type = _ExportType.FILE
        else:
            self.export_type = _ExportType.BASE64


async def export(app: "Application"):
    """Export cligram data."""
    app.status.update("Preparing export...")

    cfg: _ExportConfig = app.config.temp["cligram.transfer:export"]
    interactive = cfg == _ExportConfig()

    sessions = CustomSession.list_sessions()
    enable_dotenv = app.config.telegram.api.from_env and app.config.telegram.api.valid

    if interactive:
        app.status.stop()
        import questionary

        cfg.export_config = await questionary.confirm(
            "Do you want to include the current configuration in the export?"
            + (
                " (including your api credentials)"
                if not enable_dotenv and app.config.telegram.api.valid
                else ""
            ),
            default=True,
        ).ask_async()

        if enable_dotenv:
            cfg.export_dotenv = await questionary.confirm(
                "Do you want to export sensitive data as .env file?",
                default=False,
            ).ask_async()

        session_choices = [Path(s).stem for s in sessions]
        if session_choices:
            cfg.exported_sessions = await questionary.checkbox(
                "Select sessions to export:",
                choices=session_choices,
                use_search_filter=True,
                use_jk_keys=False,
            ).ask_async()

        states = list(app.state.states.keys())
        if states:
            cfg.exported_states = await questionary.checkbox(
                "Select states to export:",
                choices=states,
                use_search_filter=True,
                use_jk_keys=False,
            ).ask_async()

        cfg.export_type = await questionary.select(
            "Select export type:",
            choices=[c.value for c in _ExportType],
        ).ask_async()
        cfg.export_type = _ExportType(cfg.export_type)

        if cfg.export_type == _ExportType.FILE:
            path_str = await questionary.path(
                "Enter the export file path:",
                default="cligram_export.tar.xz",
            ).ask_async()
            cfg.path = Path(path_str)

        password = await questionary.password(
            "Enter a password to encrypt the export file (leave blank for no encryption):"
        ).ask_async()
        cfg.password = password if password else None

        app.status.start()

    ex_all_sessions = "*" in cfg.exported_sessions
    ex_all_states = "*" in cfg.exported_states

    cfg.exported_sessions = [
        path
        for path in sessions
        if ex_all_sessions or Path(path).stem in cfg.exported_sessions
    ]

    if ex_all_states:
        cfg.exported_states = list(app.state.states.keys())

    default_headers = {
        "cligram.transfer.version": str(TRANSFER_PROTOCOL_VERSION),
    }

    app.status.update("Exporting data...")
    progress = Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
    )
    progress.start()

    async with utils.Archive(password=cfg.password, compression="xz") as archive:
        if cfg.export_config:
            task = progress.add_task("Exporting configuration", total=3)

            data = app.config.to_dict()
            progress.update(task, advance=1)

            is_global = app.config.path == GLOBAL_CONFIG_PATH
            json = utils.json.dumps(data, indent=4)
            progress.update(task, advance=1)

            header = {
                "cligram.transfer.type": "config",
                "cligram.transfer.config.type": "local" if not is_global else "global",
            }
            archive.add_bytes(
                name="config.json",
                data=json.encode("utf-8"),
                pax_headers=default_headers | header,
            )
            progress.update(task, advance=1)

        if enable_dotenv and cfg.export_dotenv:
            task = progress.add_task("Exporting .env file", total=2)

            # Export relevant environment variables
            env_vars = {"CLIGRAM_API_ID", "CLIGRAM_API_HASH"}
            dotenv_content = ""
            for var in env_vars:
                value = os.getenv(var)
                if value is not None:
                    dotenv_content += f"{var}={value}\n"
            progress.update(task, advance=1)

            header = {
                "cligram.transfer.type": "dotenv",
            }
            archive.add_bytes(
                name=".env",
                data=dotenv_content.encode("utf-8"),
                pax_headers=default_headers | header,
            )
            progress.update(task, advance=1)

        for session_path in cfg.exported_sessions:
            session_name = Path(session_path).stem
            session_suffix = Path(session_path).suffix
            task = progress.add_task(f"Exporting {session_name} session", total=1)
            header = {
                "cligram.transfer.type": "session",
            }
            await archive.add_file(
                Path(session_path),
                f"sessions/{session_name}{session_suffix}",
                pax_headers=default_headers | header,
            )
            progress.update(task, advance=1)

        for state_name in cfg.exported_states:
            task = progress.add_task(f"Exporting {state_name} state", total=4)

            state = app.state.states[state_name]
            progress.update(task, advance=1)

            data = state.export()
            progress.update(task, advance=1)

            json = utils.json.dumps(data, indent=4)
            progress.update(task, advance=1)

            header = {
                "cligram.transfer.type": "state",
            }
            archive.add_bytes(
                f"states/{state_name}{state.suffix}",
                json.encode("utf-8"),
                pax_headers=default_headers | header,
            )
            progress.update(task, advance=1)

        progress.stop()

        if cfg.export_type == _ExportType.FILE and cfg.path is not None:
            size = await archive.write(cfg.path)
            app.console.print(
                f"[green]Exported data to file: [bold]{cfg.path}[/bold] ({size} bytes)[/green]"
            )
        elif cfg.export_type == _ExportType.BASE64:
            b64 = await archive.to_base64()
            app.console.print("[green]Exported data as base64:[/green]\n")
            app.console.print(b64, markup=False, highlight=False)
