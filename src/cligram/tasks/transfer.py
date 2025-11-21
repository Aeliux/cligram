import base64
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

import aiofiles
import questionary
from click import ClickException
from rich import get_console
from rich.progress import BarColumn, Progress, TextColumn
from rich.status import Status

from .. import DEFAULT_PATH, GLOBAL_CONFIG_PATH, CustomSession, exceptions, utils

if TYPE_CHECKING:
    from .. import Application, CustomSession

TRANSFER_PROTOCOL_VERSION = 1


class _FileType(Enum):
    UNKNOWN = "unknown"
    CONFIG = "config"
    DOTENV = "dotenv"
    SESSION = "session"
    STATE = "state"


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


@dataclass
class _ImportConfig:
    """Configuration for import task."""

    input_value: Optional[str | Path] = None
    is_data: bool = False
    password: Optional[str] = None
    _valid_entries: list[utils.ArchiveEntry] = field(default_factory=list, init=False)
    _need_exit: bool = field(default=False, init=False)


async def export(app: "Application"):
    """Export cligram data."""
    app.status.update("Preparing export...")

    cfg: _ExportConfig = app.config.temp["cligram.transfer:export"]
    interactive = cfg == _ExportConfig()

    sessions = CustomSession.list_sessions()
    enable_dotenv = app.config.telegram.api.from_env and app.config.telegram.api.valid

    if interactive:
        app.status.stop()

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
                "cligram.transfer.type": _FileType.CONFIG.value,
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
                "cligram.transfer.type": _FileType.DOTENV.value,
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
                "cligram.transfer.type": _FileType.SESSION.value,
                "cligram.transfer.session.name": session_name,
                "cligram.transfer.session.suffix": session_suffix,
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
                "cligram.transfer.type": _FileType.STATE.value,
                "cligram.transfer.state.name": state_name,
                "cligram.transfer.state.type": type(state).__name__,
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


async def import_early(cfg: _ImportConfig):
    """Early import phase to import configurations before app start."""
    console = get_console()
    status = Status("Preparing import...", spinner="dots", console=console)
    status.start()

    data: bytes
    if cfg.is_data:
        if isinstance(cfg.input_value, str):
            # trim any whitespace/newlines
            b64d = cfg.input_value.strip().strip('"').strip("'").strip("\n").strip("\r")
            data = base64.b64decode(b64d)
        else:
            raise TypeError("Input value must be a base64 string when is_data is True.")
    else:
        if isinstance(cfg.input_value, Path):
            path = cfg.input_value
        elif isinstance(cfg.input_value, str):
            path = Path(cfg.input_value)
        else:
            raise TypeError("Input value must be a file path or base64 string.")

        async with aiofiles.open(path, "rb") as f:
            data = await f.read()

    status.update("Loading archive...")

    try:
        archive = await _load_archive(cfg.password, data)
    except ClickException:
        status.stop()
        if not cfg.password:
            password = await questionary.password(
                "The archive is password protected. Please enter the password:",
            ).ask_async()
            archive = await _load_archive(password, data)
            status.start()
        else:
            raise

    config_entry: Optional[utils.ArchiveEntry] = None
    config_path: str = str(GLOBAL_CONFIG_PATH)
    dotenv_entry: Optional[utils.ArchiveEntry] = None
    other_data_found = False

    for entry in archive:
        if entry.file_type != utils.archive.FileType.FILE or not entry.content:
            continue
        headers = entry.pax_headers
        if verstr := headers.get("cligram.transfer.version") != str(
            TRANSFER_PROTOCOL_VERSION
        ):
            try:
                ver = int(verstr)
                if ver > TRANSFER_PROTOCOL_VERSION:
                    console.print(
                        f"[red]Unsupported transfer protocol version: {verstr}[/red]"
                    )
                    continue
            except Exception:
                console.print(
                    f"[red]Unsupported transfer protocol version: {verstr}[/red]"
                )
                continue

        try:
            ttype = _FileType(headers.get("cligram.transfer.type"))
        except (ValueError, KeyError):
            ttype = _FileType.UNKNOWN
        if ttype == _FileType.CONFIG:
            if config_entry is not None:
                console.print(
                    "[yellow]Multiple configuration entries found in archive. Using the first one.[/yellow]"
                )
                continue
            config_entry = entry
        elif ttype == _FileType.DOTENV:
            if dotenv_entry is not None:
                console.print(
                    "[yellow]Multiple .env entries found in archive. Using the first one.[/yellow]"
                )
                continue
            dotenv_entry = entry
        elif ttype == _FileType.UNKNOWN:
            continue
        else:
            cfg._valid_entries.append(entry)
            other_data_found = True

    status.stop()

    if config_entry is not None:
        consent = await questionary.confirm(
            "An exported configuration was found in the archive. Do you want to import it?",
            default=True,
        ).ask_async()

        if consent:
            config_path = await questionary.path(
                "Enter the path to save the imported configuration file:",
                default=config_path,
            ).ask_async()
        else:
            config_entry = None

    if dotenv_entry is not None:
        consent = await questionary.confirm(
            "An exported .env file was found in the archive. Do you want to import it?",
            default=False,
        ).ask_async()

        if not consent:
            dotenv_entry = None

    progress = Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console,
    )
    progress.start()

    if config_entry is not None:
        task = progress.add_task("Importing configuration", total=1)

        config_data: bytes = config_entry.content  # type: ignore
        async with aiofiles.open(config_path, "wb") as f:
            await f.write(config_data)
        progress.update(task, advance=1)
        progress.stop_task(task)

    if dotenv_entry is not None:
        task = progress.add_task("Importing .env file", total=1)

        dotenv_data: bytes = dotenv_entry.content  # type: ignore
        dotenv_path = DEFAULT_PATH / ".env"
        async with aiofiles.open(dotenv_path, "wb") as f:
            await f.write(dotenv_data)
        progress.update(task, advance=1)
        progress.stop_task(task)

    progress.stop()

    imported = any([config_entry, dotenv_entry])
    if imported:
        cfg._need_exit = True
        console.print("[green]Import completed successfully.[/green]")
        if other_data_found:
            console.print(
                "[yellow]Importing other data requires configuration reload.[/yellow]"
            )
            console.print(
                "[yellow]Please restart the import process and reject configuration and .env import to continue.[/yellow]"
            )


async def _load_archive(password: str | None, data: bytes) -> utils.Archive:
    try:
        return await utils.Archive.from_bytes(
            data=data, password=password, compression="xz"
        )
    except exceptions.ArchiveError as e:
        raise ClickException(f"Failed to load archive: {e}") from e


async def import_data(app: "Application"):
    """Import cligram data."""
    from ..session import get_global_session_path

    app.status.update("Preparing data import...")

    cfg: _ImportConfig = app.config.temp["cligram.transfer:import"]

    session_entries: List[utils.ArchiveEntry] = []
    state_entries: List[utils.ArchiveEntry] = []
    _state_imported: bool = False
    _imported: bool = False

    for entry in cfg._valid_entries:
        type_string = entry.pax_headers.get("cligram.transfer.type")

        if type_string == _FileType.SESSION.value:
            session_entries.append(entry)
        elif type_string == _FileType.STATE.value:
            state_entries.append(entry)

    app.status.update("Importing data...")
    progress = Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
    )
    progress.start()

    for entry in session_entries:
        session_name = entry.pax_headers.get(
            "cligram.transfer.session.name", Path(entry.name).stem
        )
        session_suffix = entry.pax_headers.get(
            "cligram.transfer.session.suffix", ".session"
        )
        task = progress.add_task(f"Importing {session_name} session", total=1)

        session_data: bytes = entry.content  # type: ignore
        session_path = (
            get_global_session_path(app.config) / f"{session_name}{session_suffix}"
        )
        if session_path.exists():
            c = 1
            while True:
                session_name = f"{session_name}_{c}"
                new_path = session_path.with_stem(session_name)
                if not new_path.exists():
                    session_path = new_path
                    progress.update(
                        task, description=f"Importing {session_name} session (renamed)"
                    )
                    break
                c += 1
        async with aiofiles.open(session_path, "wb") as f:
            await f.write(session_data)
        progress.update(task, advance=1)
        progress.stop_task(task)
        _imported = True

    for entry in state_entries:
        state_name = entry.pax_headers.get(
            "cligram.transfer.state.name", Path(entry.name).stem
        )
        state_type = entry.pax_headers.get("cligram.transfer.state.type", None)
        task = progress.add_task(f"Importing {state_name} state", total=4)

        if state_name not in app.state.states:
            progress.update(
                task, description=f"Skipping {state_name} state (not registered)"
            )
            progress.stop_task(task)
            continue

        if not state_type:
            progress.update(
                task, description=f"Skipping {state_name} state (unknown type)"
            )
            progress.stop_task(task)
            continue

        state = app.state.get(state_name)
        if type(state).__name__ != state_type:
            progress.update(
                task, description=f"Skipping {state_name} state (type mismatch)"
            )
            progress.stop_task(task)
            continue
        progress.update(task, advance=1)

        state_data: str = entry.content.decode("utf-8")  # type: ignore
        progress.update(task, advance=1)

        data_dict = utils.json.loads(state_data)
        progress.update(task, advance=1)

        state.load(data_dict)
        state.set_changed(True)
        progress.update(task, advance=1)
        progress.stop_task(task)
        _state_imported = True
        _imported = True

    if _state_imported:
        fin_state = progress.add_task("Finalizing state imports", total=1)
        await app.state.save()
        progress.update(fin_state, advance=1)
        progress.stop_task(fin_state)

    progress.stop()

    if _imported:
        app.console.print("[green]Data import completed successfully.[/green]")
