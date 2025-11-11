import asyncio
import base64
import io
import os
import tarfile
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import AsyncIterator, Dict, List, Optional, Union

import aiofiles
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class CompressionType(Enum):
    """Supported compression types."""

    NONE = ""
    GZIP = "gz"
    BZIP2 = "bz2"
    XZ = "xz"


class FileType(Enum):
    """File types in archive."""

    FILE = "file"
    DIRECTORY = "directory"
    SYMLINK = "symlink"


@dataclass
class ArchiveEntry:
    """Represents an entry in the archive."""

    name: str
    size: int
    file_type: FileType
    mode: int
    mtime: datetime
    content: Optional[bytes] = None  # File content for in-memory storage
    uid: int = 0
    gid: int = 0
    uname: str = ""
    gname: str = ""

    @classmethod
    def from_tar_member(
        cls, member: tarfile.TarInfo, content: Optional[bytes] = None
    ) -> "ArchiveEntry":
        """Create ArchiveEntry from TarInfo."""
        if member.isdir():
            file_type = FileType.DIRECTORY
        elif member.issym() or member.islnk():
            file_type = FileType.SYMLINK
        else:
            file_type = FileType.FILE

        return cls(
            name=member.name,
            size=member.size,
            file_type=file_type,
            mode=member.mode,
            mtime=datetime.fromtimestamp(member.mtime),
            content=content,
            uid=member.uid,
            gid=member.gid,
            uname=member.uname,
            gname=member.gname,
        )

    @classmethod
    async def from_file(
        cls, file_path: Path, arcname: Optional[str] = None
    ) -> "ArchiveEntry":
        """Create ArchiveEntry from file."""
        stat = file_path.stat()

        if file_path.is_dir():
            file_type = FileType.DIRECTORY
            content = None
            size = 0
        else:
            file_type = FileType.FILE
            async with aiofiles.open(file_path, "rb") as f:
                content = await f.read()
            size = len(content)

        return cls(
            name=arcname or file_path.name,
            size=size,
            file_type=file_type,
            mode=stat.st_mode,
            mtime=datetime.fromtimestamp(stat.st_mtime),
            content=content,
            uid=stat.st_uid if hasattr(stat, "st_uid") else 0,
            gid=stat.st_gid if hasattr(stat, "st_gid") else 0,
        )

    def to_tar_info(self) -> tarfile.TarInfo:
        """Convert to TarInfo for writing."""
        info = tarfile.TarInfo(name=self.name)
        info.size = self.size
        info.mode = self.mode
        info.mtime = int(self.mtime.timestamp())
        info.uid = self.uid
        info.gid = self.gid
        info.uname = self.uname
        info.gname = self.gname

        if self.file_type == FileType.DIRECTORY:
            info.type = tarfile.DIRTYPE
        elif self.file_type == FileType.SYMLINK:
            info.type = tarfile.SYMTYPE
        else:
            info.type = tarfile.REGTYPE

        return info

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "size": self.size,
            "type": self.file_type.value,
            "mode": self.mode,
            "mtime": self.mtime.isoformat(),
            "uid": self.uid,
            "gid": self.gid,
            "uname": self.uname,
            "gname": self.gname,
        }


class AsyncArchive:
    """
    High-performance async archive with encryption and streaming support.

    The archive data is held in memory by default for fast operations.
    Decryption happens only on load, encryption only on export.

    Examples:
        # Create new archive
        archive = AsyncArchive(password="secret")
        await archive.add_file("file.txt")
        await archive.write("output.tar.gz")

        # Load existing archive
        archive = await AsyncArchive.load("input.tar.gz", password="secret")
        content = await archive.get_file("file.txt")

        # Work with in-memory data
        data = await archive.to_bytes()
        b64 = await archive.to_base64()
    """

    # Maximum archive size in memory (50 MB)
    MAX_SIZE = 50 * 1024 * 1024

    def __init__(
        self,
        password: Optional[str] = None,
        compression: Union[str, CompressionType] = CompressionType.GZIP,
        salt: Optional[bytes] = None,
        chunk_size: int = 8192,
    ):
        # Handle both string and enum for compression
        if isinstance(compression, str):
            try:
                self.compression = CompressionType(compression)
            except ValueError:
                raise ValueError(f"Invalid compression type: {compression}")
        else:
            self.compression = compression

        self.chunk_size = chunk_size
        self._cipher: Optional[Fernet] = None
        self._salt = salt
        self._entries: Dict[str, ArchiveEntry] = {}  # In-memory storage
        self._password = password

        if password:
            self._cipher = self._create_cipher(password, salt)

    @classmethod
    async def load(
        cls,
        path: Union[str, Path],
        password: Optional[str] = None,
        compression: Union[str, CompressionType] = CompressionType.GZIP,
    ) -> "AsyncArchive":
        """
        Load archive from file.

        Args:
            path: Path to archive file
            password: Password for decryption
            compression: Compression type

        Returns:
            AsyncArchive instance with loaded data
        """
        archive = cls(password=password, compression=compression)
        await archive.read(path)
        return archive

    @classmethod
    async def from_bytes(
        cls,
        data: bytes,
        password: Optional[str] = None,
        compression: Union[str, CompressionType] = CompressionType.GZIP,
    ) -> "AsyncArchive":
        """
        Create archive from bytes.

        Args:
            data: Archive bytes (encrypted if password provided)
            password: Password for decryption
            compression: Compression type

        Returns:
            AsyncArchive instance with loaded data
        """
        archive = cls(password=password, compression=compression)
        await archive._load_from_bytes(data)
        return archive

    @classmethod
    async def from_base64(
        cls,
        b64_string: str,
        password: Optional[str] = None,
        compression: Union[str, CompressionType] = CompressionType.GZIP,
    ) -> "AsyncArchive":
        """
        Create archive from base64 string.

        Args:
            b64_string: Base64 encoded archive
            password: Password for decryption
            compression: Compression type

        Returns:
            AsyncArchive instance with loaded data
        """
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(
            None,
            base64.b64decode,
            b64_string.encode("utf-8"),
        )
        return await cls.from_bytes(data, password, compression)

    @classmethod
    async def from_directory(
        cls,
        directory: Union[str, Path],
        password: Optional[str] = None,
        compression: Union[str, CompressionType] = CompressionType.GZIP,
    ) -> "AsyncArchive":
        """
        Create archive from directory.

        Args:
            directory: Directory to archive
            password: Password for encryption
            compression: Compression type

        Returns:
            AsyncArchive instance with directory contents
        """
        archive = cls(password=password, compression=compression)
        await archive.add_directory(directory)
        return archive

    def _create_cipher(self, password: str, salt: Optional[bytes] = None) -> Fernet:
        """Create Fernet cipher from password."""
        if salt is None:
            salt = os.urandom(16)
            self._salt = salt

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return Fernet(key)

    def get_salt(self) -> Optional[bytes]:
        """Get the salt used for encryption."""
        return self._salt

    def _get_tar_mode(self, mode: str) -> str:
        """Get tarfile mode with compression."""
        if self.compression.value:
            return f"{mode}:{self.compression.value}"
        return mode

    def _check_size_limit(self, additional_size: int = 0) -> None:
        """Check if adding data would exceed size limit."""
        current_size = sum(entry.size for entry in self._entries.values())
        if current_size + additional_size > self.MAX_SIZE:
            raise ValueError(
                f"Archive size would exceed {self.MAX_SIZE / (1024*1024):.1f} MB limit. "
                f"Current: {current_size / (1024*1024):.1f} MB, "
                f"Adding: {additional_size / (1024*1024):.1f} MB"
            )

    async def _load_from_bytes(self, data: bytes) -> None:
        """Load archive from bytes."""
        # Decrypt if needed
        if self._cipher:
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, self._cipher.decrypt, data)

        # Check size
        if len(data) > self.MAX_SIZE:
            raise ValueError(
                f"Archive size {len(data) / (1024*1024):.1f} MB exceeds {self.MAX_SIZE / (1024*1024):.1f} MB limit"
            )

        # Parse tar archive
        loop = asyncio.get_event_loop()
        self._entries = await loop.run_in_executor(
            None,
            self._parse_tar_to_entries,
            data,
        )

    def _parse_tar_to_entries(self, data: bytes) -> Dict[str, ArchiveEntry]:
        """Parse tar archive to entries (sync)."""
        buffer = io.BytesIO(data)
        entries = {}

        with tarfile.open(fileobj=buffer, mode=self._get_tar_mode("r")) as tar:  # type: ignore
            for member in tar.getmembers():
                content = None
                if member.isfile():
                    file_obj = tar.extractfile(member)
                    if file_obj:
                        content = file_obj.read()

                entry = ArchiveEntry.from_tar_member(member, content)
                entries[entry.name] = entry

        return entries

    def _build_tar_from_entries(self) -> bytes:
        """Build tar archive from entries."""
        buffer = io.BytesIO()

        with tarfile.open(fileobj=buffer, mode=self._get_tar_mode("w")) as tar:  # type: ignore
            for entry in self._entries.values():
                tar_info = entry.to_tar_info()

                if entry.file_type == FileType.FILE and entry.content:
                    tar.addfile(tar_info, io.BytesIO(entry.content))
                else:
                    tar.addfile(tar_info)

        return buffer.getvalue()

    async def read(self, path: Union[str, Path]) -> None:
        """
        Read archive from file.

        Args:
            path: Path to archive file
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Archive file not found: {path}")

        async with aiofiles.open(path, "rb") as f:
            data = await f.read()

        await self._load_from_bytes(data)

    async def write(self, path: Union[str, Path]) -> None:
        """
        Write archive to file.

        Args:
            path: Output path
        """
        if not self._entries:
            raise ValueError("Archive is empty. Nothing to write.")

        data = await self.to_bytes()

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        async with aiofiles.open(path, "wb") as f:
            await f.write(data)

    async def to_bytes(self) -> bytes:
        """
        Get archive as bytes.

        Returns:
            Archive bytes
        """
        if not self._entries:
            raise ValueError("Archive is empty.")

        # Build tar archive
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, self._build_tar_from_entries)

        # Encrypt if needed
        if self._cipher:
            data = await loop.run_in_executor(None, self._cipher.encrypt, data)

        return data

    async def to_base64(self) -> str:
        """
        Get archive as base64 string.

        Returns:
            Base64 encoded archive
        """
        data = await self.to_bytes()
        loop = asyncio.get_event_loop()
        encoded = await loop.run_in_executor(None, base64.b64encode, data)
        return encoded.decode("utf-8")

    async def add_file(
        self, file_path: Union[str, Path], arcname: Optional[str] = None
    ) -> ArchiveEntry:
        """
        Add file to archive.

        Args:
            file_path: Path to file
            arcname: Name in archive (defaults to filename)

        Returns:
            Created ArchiveEntry
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if not file_path.is_file():
            raise ValueError(f"Path is not a file: {file_path}")

        name = arcname or file_path.name
        entry = await ArchiveEntry.from_file(file_path, name)

        # Check size limit
        self._check_size_limit(entry.size)

        self._entries[name] = entry
        return entry

    async def add_directory(
        self, dir_path: Union[str, Path], arcname: Optional[str] = None
    ) -> List[ArchiveEntry]:
        """
        Add directory to archive.

        Args:
            dir_path: Path to directory
            arcname: Name in archive (defaults to directory name)

        Returns:
            List of created ArchiveEntry objects
        """
        dir_path = Path(dir_path)

        if not dir_path.exists():
            raise FileNotFoundError(f"Directory not found: {dir_path}")

        if not dir_path.is_dir():
            raise NotADirectoryError(f"Path is not a directory: {dir_path}")

        base_name = arcname or dir_path.name
        entries = []

        # Add directory entry itself
        dir_entry = await ArchiveEntry.from_file(dir_path, base_name)
        self._entries[base_name] = dir_entry
        entries.append(dir_entry)

        # Add all files recursively
        for src_file in dir_path.rglob("*"):
            rel_path = src_file.relative_to(dir_path)
            arc_path = f"{base_name}/{rel_path}".replace("\\", "/")

            entry = await ArchiveEntry.from_file(src_file, arc_path)
            self._check_size_limit(entry.size)

            self._entries[arc_path] = entry
            entries.append(entry)

        return entries

    async def add_bytes(
        self, name: str, data: bytes, mode: int = 0o644
    ) -> ArchiveEntry:
        """
        Add file from bytes to archive.

        Args:
            name: Name in archive
            data: File content
            mode: File mode (default: 0o644)

        Returns:
            Created ArchiveEntry
        """
        self._check_size_limit(len(data))

        entry = ArchiveEntry(
            name=name,
            size=len(data),
            file_type=FileType.FILE,
            mode=mode,
            mtime=datetime.now(),
            content=data,
        )

        self._entries[name] = entry
        return entry

    def get_entry(self, name: str) -> ArchiveEntry:
        """
        Get archive entry by name.

        Args:
            name: Entry name

        Returns:
            ArchiveEntry
        """
        if name not in self._entries:
            raise FileNotFoundError(f"Entry not found in archive: {name}")
        return self._entries[name]

    async def get_file(self, name: str) -> bytes:
        """
        Get content of a file from archive.

        Args:
            name: Path of file within archive

        Returns:
            File content as bytes
        """
        entry = self.get_entry(name)

        if entry.file_type != FileType.FILE:
            raise ValueError(f"Entry is not a file: {name}")

        if entry.content is None:
            raise ValueError(f"File has no content: {name}")

        return entry.content

    def has_file(self, name: str) -> bool:
        """Check if archive contains a file."""
        return name in self._entries

    def remove_file(self, name: str) -> ArchiveEntry:
        """
        Remove file from archive.

        Args:
            name: Entry name

        Returns:
            Removed ArchiveEntry
        """
        if name not in self._entries:
            raise FileNotFoundError(f"Entry not found in archive: {name}")
        return self._entries.pop(name)

    def list_files(self) -> List[ArchiveEntry]:
        """
        List all entries in archive.

        Returns:
            List of ArchiveEntry objects
        """
        return list(self._entries.values())

    def list_file_names(self) -> List[str]:
        """
        List all entry names in archive.

        Returns:
            List of entry names
        """
        return list(self._entries.keys())

    async def extract(self, output_dir: Union[str, Path] = ".") -> Path:
        """
        Extract archive to directory.

        Args:
            output_dir: Directory to extract to

        Returns:
            Path to extracted directory
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        for entry in self._entries.values():
            entry_path = output_dir / entry.name

            # Security check
            if not entry_path.resolve().is_relative_to(output_dir.resolve()):
                raise ValueError(f"Attempted path traversal: {entry.name}")

            if entry.file_type == FileType.DIRECTORY:
                entry_path.mkdir(parents=True, exist_ok=True)
            elif entry.file_type == FileType.FILE and entry.content:
                entry_path.parent.mkdir(parents=True, exist_ok=True)
                async with aiofiles.open(entry_path, "wb") as f:
                    await f.write(entry.content)

                # Set permissions
                try:
                    entry_path.chmod(entry.mode)
                except (OSError, NotImplementedError):
                    pass  # Permission setting might not be supported

        return output_dir

    async def stream_files(self) -> AsyncIterator[ArchiveEntry]:
        """
        Stream entries from archive.

        Yields:
            ArchiveEntry objects
        """
        for entry in self._entries.values():
            yield entry

    def get_size(self) -> int:
        """Get total size of archive contents in bytes."""
        return sum(entry.size for entry in self._entries.values())

    def get_file_count(self) -> int:
        """Get number of files in archive."""
        return sum(
            1 for entry in self._entries.values() if entry.file_type == FileType.FILE
        )

    async def clear(self) -> None:
        """Clear archive contents."""
        self._entries.clear()

    def is_empty(self) -> bool:
        """Check if archive is empty."""
        return len(self._entries) == 0

    async def __aenter__(self):
        """Context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        pass  # Nothing to cleanup with in-memory storage
