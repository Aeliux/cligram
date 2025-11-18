import asyncio
import base64
import io
import os
import tarfile
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Union

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


@dataclass(frozen=True, slots=True)
class ArchiveEntry:
    """Represents an entry in the archive.

    This is an immutable value object that represents a file, directory, or symlink
    in an archive. Content hash is computed lazily on first access and cached.
    """

    name: str
    """Entry name/path in the archive."""

    size: int
    """Size of the entry in bytes."""

    file_type: FileType
    """Type of the entry."""

    mode: int
    """File mode/permissions."""

    mtime: datetime
    """Last modification time."""

    _content: Optional[bytes] = None
    """Content of the file entry. Should only be set for FILE type."""

    uid: int = 0
    """User ID of the entry."""

    gid: int = 0
    """Group ID of the entry."""

    _uname: str = ""
    """User name of the entry (cached)."""

    _gname: str = ""
    """Group name of the entry (cached)."""

    pax_headers: Dict[str, str] = field(default_factory=dict)
    """PAX extended attributes/headers."""

    _content_hash_cache: Optional[bytes] = field(default=None, init=False)
    """Cached SHA-256 hash of content."""

    def __post_init__(self):
        """Validate entry and pre-compute expensive operations."""
        # Validation
        if self.file_type == FileType.FILE and self._content is None:
            raise ValueError("File entries must have content.")
        if self.file_type != FileType.FILE and self._content is not None:
            raise ValueError("Only file entries can have content.")

        # Pre-compute and cache content hash for files to avoid recomputation
        # This is critical for __hash__ and __eq__ performance
        if self._content is not None:
            digest = hashes.Hash(hashes.SHA256())
            digest.update(self._content)
            # Use object.__setattr__ because dataclass is frozen
            object.__setattr__(self, "_content_hash_cache", digest.finalize())

    @property
    def content(self) -> Optional[bytes]:
        """Get content bytes.

        Returns:
            File content or None for non-file entries
        """
        return self._content

    @property
    def content_hash(self) -> Optional[bytes]:
        """Get SHA-256 hash of the content.

        Hash is computed once and cached for performance.

        Returns:
            SHA-256 hash bytes or None for non-file entries
        """
        return self._content_hash_cache

    @property
    def uname(self) -> str:
        """Get user name (lazy computation with fallback).

        Returns:
            User name or empty string if unavailable
        """
        if self._uname:
            return self._uname

        try:
            import pwd

            return pwd.getpwuid(self.uid).pw_name  # type: ignore
        except (ImportError, KeyError, OSError):
            return ""

    @property
    def gname(self) -> str:
        """Get group name (lazy computation with fallback).

        Returns:
            Group name or empty string if unavailable
        """
        if self._gname:
            return self._gname

        try:
            import grp

            return grp.getgrgid(self.gid).gr_name  # type: ignore
        except (ImportError, KeyError, OSError):
            return ""

    @classmethod
    def from_tar_member(
        cls, member: tarfile.TarInfo, content: Optional[bytes] = None
    ) -> "ArchiveEntry":
        """Create ArchiveEntry from TarInfo.

        Args:
            member: TarInfo object
            content: File content bytes (required for files)

        Returns:
            New ArchiveEntry instance
        """
        if member.isdir():
            file_type = FileType.DIRECTORY
        elif member.issym() or member.islnk():
            file_type = FileType.SYMLINK
        else:
            file_type = FileType.FILE

        # Extract PAX headers if available
        pax_headers = {}
        if hasattr(member, "pax_headers") and member.pax_headers:
            pax_headers = dict(member.pax_headers)

        return cls(
            name=member.name,
            size=member.size,
            file_type=file_type,
            mode=member.mode,
            mtime=datetime.fromtimestamp(member.mtime),
            _content=content,
            uid=member.uid,
            gid=member.gid,
            _uname=member.uname,
            _gname=member.gname,
            pax_headers=pax_headers,
        )

    @classmethod
    async def from_file(
        cls, file_path: Path, arcname: Optional[str] = None
    ) -> "ArchiveEntry":
        """Create ArchiveEntry from file system path.

        Args:
            file_path: Path to file or directory
            arcname: Name to use in archive (defaults to file name)

        Returns:
            New ArchiveEntry instance
        """
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
            _content=content,
            uid=getattr(stat, "st_uid", 0),
            gid=getattr(stat, "st_gid", 0),
        )

    def to_tar_info(self) -> tarfile.TarInfo:
        """Convert to TarInfo for writing to tar archive.

        Returns:
            TarInfo object ready for tar.addfile()
        """
        info = tarfile.TarInfo(name=self.name)
        info.size = self.size
        info.mode = self.mode
        info.mtime = int(self.mtime.timestamp())
        info.uid = self.uid
        info.gid = self.gid
        info.uname = self.uname
        info.gname = self.gname

        # Set PAX headers if available
        if self.pax_headers:
            info.pax_headers = self.pax_headers.copy()

        if self.file_type == FileType.DIRECTORY:
            info.type = tarfile.DIRTYPE
        elif self.file_type == FileType.SYMLINK:
            info.type = tarfile.SYMTYPE
        else:
            info.type = tarfile.REGTYPE

        return info

    def to_dict(self) -> dict:
        """Convert to dictionary representation.

        Returns:
            Dictionary with entry metadata (excludes content)
        """
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
            "content_hash": self.content_hash.hex() if self.content_hash else None,
            "pax_headers": self.pax_headers,
        }

    def __hash__(self) -> int:
        """Compute hash for use in sets and dicts.

        Uses cached content hash for performance. Does not include
        uname/gname as they can vary by system.

        Returns:
            Hash value
        """
        # Convert pax_headers dict to tuple of sorted items for hashing
        pax_tuple = tuple(sorted(self.pax_headers.items())) if self.pax_headers else ()

        return hash(
            (
                self.name,
                self.size,
                self.file_type,
                self._content_hash_cache,  # Use cached hash
                self.mode,
                int(self.mtime.timestamp()),  # Convert to int for consistency
                self.uid,
                self.gid,
                pax_tuple,
            )
        )

    def __eq__(self, other: object) -> bool:
        """Check equality with another ArchiveEntry.

        Uses cached content hash for performance. Does not compare
        uname/gname as they can vary by system.

        Args:
            other: Object to compare with

        Returns:
            True if entries are equal
        """
        if not isinstance(other, ArchiveEntry):
            return NotImplemented

        # Fast path: check identity
        if self is other:
            return True

        return (
            self.name == other.name
            and self.size == other.size
            and self.file_type == other.file_type
            and self._content_hash_cache == other._content_hash_cache  # Cached
            and self.mode == other.mode
            and self.mtime == other.mtime
            and self.uid == other.uid
            and self.gid == other.gid
            and self.pax_headers == other.pax_headers
        )

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"ArchiveEntry(name={self.name!r}, "
            f"type={self.file_type.value}, "
            f"size={self.size}, "
            f"mode=0o{self.mode:o})"
        )


class Archive:
    """High-performance async archive with encryption and streaming support.

    The archive data is held in memory by default for fast operations.
    Decryption happens only on load, encryption only on export.

    Examples:
        ```
        # Create archive from directory and save to file
        async with Archive.from_directory("my_folder", password="secret") as archive:
            await archive.write("archive.tar.gz")

        # Load archive from file and extract
        async with await Archive.load("archive.tar.gz", password="secret") as archive:
            await archive.extract("output_folder")

        # Create archive from bytes
        data = b"..."  # Encrypted archive bytes
        async with await Archive.from_bytes(data, password="secret") as archive:
            file_content = await archive.get_file("document.txt")
        ```
    """

    # Maximum archive size in memory (50 MB)
    MAX_SIZE = 50 * 1024 * 1024

    def __init__(
        self,
        password: Optional[str] = None,
        compression: Union[str, CompressionType] = CompressionType.GZIP,
        salt: Optional[bytes] = None,
    ):
        # Handle both string and enum for compression
        if isinstance(compression, str):
            try:
                self.compression = CompressionType(compression)
            except ValueError:
                raise ValueError(f"Invalid compression type: {compression}")
        else:
            self.compression = compression

        self._cipher: Optional[Fernet] = None
        self._salt = salt
        self._entries: Dict[str, ArchiveEntry] = {}  # In-memory storage
        self._password = password

        if password:
            self._cipher = self._create_cipher()

    @classmethod
    async def load(
        cls,
        path: Union[str, Path],
        **kwargs,
    ) -> "Archive":
        """Load archive from file.

        Args:
            path: Path to archive file
            **kwargs: Additional arguments for Archive constructor

        Returns:
            Archive instance with loaded data
        """
        archive = cls(**kwargs)
        await archive.read(path)
        return archive

    @classmethod
    async def from_bytes(
        cls,
        data: bytes,
        **kwargs,
    ) -> "Archive":
        """Load archive from bytes.

        Args:
            data: Archive data bytes
            **kwargs: Additional arguments for Archive constructor

        Returns:
            Archive instance with loaded data
        """
        archive = cls(**kwargs)
        await archive._load_from_bytes(data)
        return archive

    @classmethod
    async def from_base64(
        cls,
        b64_string: str,
        **kwargs,
    ) -> "Archive":
        """Load archive from base64 string.

        Args:
            b64_string: Base64 encoded archive
            **kwargs: Additional arguments for Archive constructor

        Returns:
            Archive instance with loaded data
        """
        loop = asyncio.get_event_loop()
        # Handle both str and bytes input
        b64_bytes = (
            b64_string.encode("utf-8") if isinstance(b64_string, str) else b64_string
        )
        data = await loop.run_in_executor(None, base64.b64decode, b64_bytes)
        return await cls.from_bytes(data, **kwargs)

    @classmethod
    async def from_directory(
        cls,
        directory: Union[str, Path],
        **kwargs,
    ) -> "Archive":
        """Create archive from directory.

        Args:
            directory: Directory to archive
            **kwargs: Additional arguments for Archive constructor

        Returns:
            Archive instance with directory contents
        """
        archive = cls(**kwargs)
        await archive.add_directory(directory)
        return archive

    def _create_cipher(self) -> Fernet:
        """Create Fernet cipher from password."""
        if not self._password:
            raise ValueError("Password is required for encryption/decryption.")

        if self._salt is None:
            self._salt = os.urandom(16)

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=self._salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(self._password.encode()))
        return Fernet(key)

    def get_salt(self) -> Optional[bytes]:
        """Get the salt used for encryption."""
        return self._salt

    def _get_tar_mode(self, mode: str) -> str:
        """Get tarfile mode with compression."""
        if self.compression == CompressionType.NONE:
            return mode
        return f"{mode}:{self.compression.value}"

    def _get_tar_format(self) -> int:
        """Get tar format (PAX by default)."""
        return tarfile.PAX_FORMAT

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
        tar: tarfile.TarFile

        # Try to open with specified compression first
        try:
            mode = self._get_tar_mode("r")
            with tarfile.open(fileobj=buffer, mode=mode) as tar:  # type: ignore
                for member in tar.getmembers():
                    content = None
                    if member.isfile():
                        file_obj = tar.extractfile(member)
                        if file_obj:
                            content = file_obj.read()

                    entry = ArchiveEntry.from_tar_member(member, content)
                    entries[entry.name] = entry
        except (tarfile.ReadError, tarfile.CompressionError):
            # Fallback to auto-detect compression if specified mode fails
            buffer.seek(0)
            with tarfile.open(fileobj=buffer, mode="r:*") as tar:
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
        tar: tarfile.TarFile

        mode = self._get_tar_mode("w")
        with tarfile.open(fileobj=buffer, mode=mode, format=self._get_tar_format()) as tar:  # type: ignore
            for entry in self._entries.values():
                tar_info = entry.to_tar_info()

                if entry.file_type == FileType.FILE and entry.content:
                    tar.addfile(tar_info, io.BytesIO(entry.content))
                else:
                    tar.addfile(tar_info)

        return buffer.getvalue()

    async def read(self, path: Union[str, Path]) -> None:
        """Read archive from file.

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
        """Write archive to file.

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
        """Get archive as bytes.

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
        """Get archive as base64 string.

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
        """Add file to archive.

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
        """Add directory to archive.

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

    def add_bytes(
        self,
        name: str,
        data: bytes,
        mode: int = 0o644,
        pax_headers: Optional[Dict[str, str]] = None,
    ) -> ArchiveEntry:
        """Add file from bytes to archive.

        Args:
            name: Name in archive
            data: File content
            mode: File mode (default: 0o644)
            pax_headers: Optional PAX extended attributes

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
            _content=data,
            pax_headers=pax_headers or {},
        )

        self._entries[name] = entry
        return entry

    def get_entry(self, name: str) -> ArchiveEntry:
        """Get archive entry by name.

        Args:
            name: Entry name

        Returns:
            ArchiveEntry
        """
        if name not in self._entries:
            raise FileNotFoundError(f"Entry not found in archive: {name}")
        return self._entries[name]

    def get_file(self, name: str) -> bytes:
        """Get content of a file from archive.

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
        """Remove file from archive.

        Args:
            name: Entry name

        Returns:
            Removed ArchiveEntry
        """
        if name not in self._entries:
            raise FileNotFoundError(f"Entry not found in archive: {name}")
        return self._entries.pop(name)

    def list_files(self) -> List[ArchiveEntry]:
        """List all entries in archive.

        Returns:
            List of ArchiveEntry objects
        """
        return list(self._entries.values())

    def list_file_names(self) -> List[str]:
        """List all entry names in archive.

        Returns:
            List of entry names
        """
        return list(self._entries.keys())

    async def extract(self, output_dir: Union[str, Path] = ".") -> Path:
        """Extract archive to directory.

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

    def get_size(self) -> int:
        """Get total size of archive contents in bytes."""
        return sum(entry.size for entry in self._entries.values())

    def get_file_count(self) -> int:
        """Get number of files in archive."""
        return sum(
            1 for entry in self._entries.values() if entry.file_type == FileType.FILE
        )

    def clear(self) -> None:
        """Clear archive contents."""
        self._entries.clear()

    def is_empty(self) -> bool:
        """Check if archive is empty."""
        return len(self._entries) == 0

    def close(self) -> None:
        """Close the archive and release resources."""
        self.clear()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    def __iter__(self) -> Iterator[ArchiveEntry]:
        """Iterator over archive entries."""
        return iter(self._entries.values())

    def __hash__(self):
        """Hash of the archive based on its contents."""
        # entries provide their hashes
        return hash(frozenset(self._entries.items()))

    def __eq__(self, other: object) -> bool:
        """Check equality with another Archive.

        Args:
            other: Object to compare with

        Returns:
            True if archives are equal
        """
        if not isinstance(other, Archive):
            return NotImplemented

        # Fast path: check identity
        if self is other:
            return True

        return (
            self._entries == other._entries
            and self.compression == other.compression
            and self._password == other._password
            and self._salt == other._salt
        )

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        self.close()
