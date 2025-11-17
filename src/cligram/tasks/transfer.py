from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from .. import CustomSession, exceptions, utils

if TYPE_CHECKING:
    from .. import Application, CustomSession


class _ExportType(Enum):
    FILE = "file"
    BASE64 = "base64"


@dataclass
class _ExportConfig:
    """Configuration for export task."""

    export_config: bool = True
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
    """Export cligram data"""
    app.status.stop()

    cfg: _ExportConfig = app.config.temp["cligram.transfer:export"]
    interactive = cfg == _ExportConfig()

    sessions = CustomSession.list_sessions()

    if interactive:
        import questionary

        cfg.export_config = await questionary.confirm(
            "Do you want to include the current configuration in the export?",
            default=True,
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

    ex_all_sessions = "*" in cfg.exported_sessions
    ex_all_states = "*" in cfg.exported_states

    cfg.exported_sessions = [
        path
        for path in sessions
        if ex_all_sessions or Path(path).stem in cfg.exported_sessions
    ]

    if ex_all_states:
        cfg.exported_states = list(app.state.states.keys())

    async with utils.Archive(password=cfg.password, compression="xz") as archive:
        if cfg.export_config:
            data = app.config.to_dict()
            json = utils.json.dumps(data, indent=4)
            archive.add_bytes("config.json", json.encode("utf-8"))
        for session_path in cfg.exported_sessions:
            session_name = Path(session_path).name
            await archive.add_file(Path(session_path), f"sessions/{session_name}")
        for state_name in cfg.exported_states:
            state = app.state.states[state_name]
            data = state.export()
            json = utils.json.dumps(data, indent=4)
            archive.add_bytes(
                f"states/{state_name}{state.suffix}", json.encode("utf-8")
            )

        if cfg.export_type == _ExportType.FILE and cfg.path is not None:
            await archive.write(cfg.path)
        elif cfg.export_type == _ExportType.BASE64:
            b64 = await archive.to_base64()
            print("Exported Data (Base64):")
            print(b64)
        app.console.print(
            f"[green]Exported {len(await archive.to_bytes())} bytes[/green]"
        )
