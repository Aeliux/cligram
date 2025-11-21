import asyncio
import base64
import os
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from cligram import exceptions
from cligram.utils.archive import (
    Archive,
    ArchiveEntry,
    CompressionType,
    FileType,
)


class TestArchiveEntry:
    """Tests for ArchiveEntry class."""

    def test_create_file_entry(self):
        """Test creating a file entry."""
        content = b"test content"
        entry = ArchiveEntry(
            name="test.txt",
            size=len(content),
            file_type=FileType.FILE,
            mode=0o644,
            mtime=datetime.now(),
            _content=content,
        )

        assert entry.name == "test.txt"
        assert entry.size == len(content)
        assert entry.file_type == FileType.FILE
        assert entry.content == content
        assert entry.content_hash is not None

    def test_create_directory_entry(self):
        """Test creating a directory entry."""
        entry = ArchiveEntry(
            name="testdir",
            size=0,
            file_type=FileType.DIRECTORY,
            mode=0o755,
            mtime=datetime.now(),
        )

        assert entry.name == "testdir"
        assert entry.file_type == FileType.DIRECTORY
        assert entry.content is None
        assert entry.content_hash is None

    def test_file_entry_requires_content(self):
        """Test that file entries must have content."""
        with pytest.raises(ValueError, match="File entries must have content"):
            ArchiveEntry(
                name="test.txt",
                size=10,
                file_type=FileType.FILE,
                mode=0o644,
                mtime=datetime.now(),
            )

    def test_non_file_cannot_have_content(self):
        """Test that non-file entries cannot have content."""
        with pytest.raises(ValueError, match="Only file entries can have content"):
            ArchiveEntry(
                name="testdir",
                size=0,
                file_type=FileType.DIRECTORY,
                mode=0o755,
                mtime=datetime.now(),
                _content=b"invalid",
            )

    def test_entry_equality(self):
        """Test entry equality comparison."""
        content = b"test"
        mtime = datetime.now()

        entry1 = ArchiveEntry(
            name="test.txt",
            size=len(content),
            file_type=FileType.FILE,
            mode=0o644,
            mtime=mtime,
            _content=content,
        )

        entry2 = ArchiveEntry(
            name="test.txt",
            size=len(content),
            file_type=FileType.FILE,
            mode=0o644,
            mtime=mtime,
            _content=content,
        )

        assert entry1 == entry2
        assert hash(entry1) == hash(entry2)

    def test_entry_inequality_different_content(self):
        """Test entries with different content are not equal."""
        mtime = datetime.now()

        entry1 = ArchiveEntry(
            name="test.txt",
            size=4,
            file_type=FileType.FILE,
            mode=0o644,
            mtime=mtime,
            _content=b"test",
        )

        entry2 = ArchiveEntry(
            name="test.txt",
            size=5,
            file_type=FileType.FILE,
            mode=0o644,
            mtime=mtime,
            _content=b"other",
        )

        assert entry1 != entry2

    def test_entry_with_pax_headers(self):
        """Test entry with PAX headers."""
        pax_headers = {"key": "value", "another": "data"}
        entry = ArchiveEntry(
            name="test.txt",
            size=4,
            file_type=FileType.FILE,
            mode=0o644,
            mtime=datetime.now(),
            _content=b"test",
            pax_headers=pax_headers,
        )

        assert entry.pax_headers == pax_headers

    def test_entry_to_dict(self):
        """Test converting entry to dictionary."""
        content = b"test content"
        entry = ArchiveEntry(
            name="test.txt",
            size=len(content),
            file_type=FileType.FILE,
            mode=0o644,
            mtime=datetime.now(),
            _content=content,
        )

        d = entry.to_dict()
        assert d["name"] == "test.txt"
        assert d["size"] == len(content)
        assert d["type"] == "file"
        assert d["content_hash"] is not None

    @pytest.mark.asyncio
    async def test_from_file(self, tmp_path):
        """Test creating entry from file."""
        test_file = tmp_path / "test.txt"
        content = b"test content"
        test_file.write_bytes(content)

        entry = await ArchiveEntry.from_file(test_file)

        assert entry.name == "test.txt"
        assert entry.size == len(content)
        assert entry.file_type == FileType.FILE
        assert entry.content == content


class TestArchiveBasics:
    """Tests for basic Archive operations."""

    @pytest.mark.asyncio
    async def test_create_empty_archive(self):
        """Test creating an empty archive."""
        archive = Archive()
        assert archive.is_empty()
        assert archive.get_file_count() == 0
        assert archive.get_size() == 0

    @pytest.mark.asyncio
    async def test_create_archive_with_password(self):
        """Test creating archive with password."""
        archive = Archive(password="secret123")
        assert archive._password == "secret123"
        assert archive._cipher is not None

    @pytest.mark.asyncio
    async def test_create_archive_with_compression_type(self):
        """Test creating archive with different compression types."""
        for comp_type in CompressionType:
            archive = Archive(compression=comp_type)
            assert archive.compression == comp_type

    @pytest.mark.asyncio
    async def test_create_archive_with_string_compression(self):
        """Test creating archive with string compression type."""
        archive = Archive(compression="gz")
        assert archive.compression == CompressionType.GZIP

    @pytest.mark.asyncio
    async def test_invalid_compression_type(self):
        """Test invalid compression type raises error."""
        with pytest.raises(exceptions.InvalidCompressionTypeError):
            Archive(compression="invalid")

    @pytest.mark.asyncio
    async def test_add_bytes(self):
        """Test adding bytes as file."""
        archive = Archive()
        content = b"test content"

        entry = archive.add_bytes("test.txt", content)

        assert entry.name == "test.txt"
        assert entry.size == len(content)
        assert archive.has_file("test.txt")
        assert archive.get_file("test.txt") == content

    @pytest.mark.asyncio
    async def test_add_file(self, tmp_path):
        """Test adding file to archive."""
        test_file = tmp_path / "test.txt"
        content = b"test content"
        test_file.write_bytes(content)

        archive = Archive()
        entry = await archive.add_file(test_file)

        assert entry.name == "test.txt"
        assert archive.has_file("test.txt")
        assert archive.get_file("test.txt") == content

    @pytest.mark.asyncio
    async def test_add_file_with_arcname(self, tmp_path):
        """Test adding file with custom archive name."""
        test_file = tmp_path / "test.txt"
        test_file.write_bytes(b"content")

        archive = Archive()
        await archive.add_file(test_file, arcname="custom_name.txt")

        assert archive.has_file("custom_name.txt")
        assert not archive.has_file("test.txt")

    @pytest.mark.asyncio
    async def test_add_nonexistent_file(self, tmp_path):
        """Test adding non-existent file raises error."""
        archive = Archive()

        with pytest.raises(FileNotFoundError):
            await archive.add_file(tmp_path / "nonexistent.txt")

    @pytest.mark.asyncio
    async def test_get_entry(self):
        """Test getting archive entry."""
        archive = Archive()
        archive.add_bytes("test.txt", b"content")

        entry = archive.get_entry("test.txt")
        assert entry.name == "test.txt"

    @pytest.mark.asyncio
    async def test_get_nonexistent_entry(self):
        """Test getting non-existent entry raises error."""
        archive = Archive()

        with pytest.raises(FileNotFoundError):
            archive.get_entry("nonexistent.txt")

    @pytest.mark.asyncio
    async def test_remove_file(self):
        """Test removing file from archive."""
        archive = Archive()
        archive.add_bytes("test.txt", b"content")

        removed = archive.remove_file("test.txt")

        assert removed.name == "test.txt"
        assert not archive.has_file("test.txt")

    @pytest.mark.asyncio
    async def test_remove_nonexistent_file(self):
        """Test removing non-existent file raises error."""
        archive = Archive()

        with pytest.raises(FileNotFoundError):
            archive.remove_file("nonexistent.txt")

    @pytest.mark.asyncio
    async def test_list_files(self):
        """Test listing files in archive."""
        archive = Archive()
        archive.add_bytes("file1.txt", b"content1")
        archive.add_bytes("file2.txt", b"content2")

        files = archive.list_files()
        names = archive.list_file_names()

        assert len(files) == 2
        assert len(names) == 2
        assert "file1.txt" in names
        assert "file2.txt" in names

    @pytest.mark.asyncio
    async def test_clear(self):
        """Test clearing archive."""
        archive = Archive()
        archive.add_bytes("test.txt", b"content")

        archive.clear()

        assert archive.is_empty()


class TestArchiveDirectory:
    """Tests for directory operations."""

    @pytest.mark.asyncio
    async def test_add_directory(self, tmp_path):
        """Test adding directory to archive."""
        test_dir = tmp_path / "testdir"
        test_dir.mkdir()
        (test_dir / "file1.txt").write_bytes(b"content1")
        (test_dir / "file2.txt").write_bytes(b"content2")

        subdir = test_dir / "subdir"
        subdir.mkdir()
        (subdir / "file3.txt").write_bytes(b"content3")

        archive = Archive()
        entries = await archive.add_directory(test_dir)

        assert len(entries) > 0
        assert archive.has_file("testdir/file1.txt")
        assert archive.has_file("testdir/file2.txt")
        assert archive.has_file("testdir/subdir/file3.txt")

    @pytest.mark.asyncio
    async def test_add_nonexistent_directory(self, tmp_path):
        """Test adding non-existent directory raises error."""
        archive = Archive()

        with pytest.raises(FileNotFoundError):
            await archive.add_directory(tmp_path / "nonexistent")

    @pytest.mark.asyncio
    async def test_from_directory(self, tmp_path):
        """Test creating archive from directory."""
        test_dir = tmp_path / "testdir"
        test_dir.mkdir()
        (test_dir / "file1.txt").write_bytes(b"content1")

        archive = await Archive.from_directory(test_dir)

        assert not archive.is_empty()
        assert archive.has_file("testdir/file1.txt")


class TestArchiveSerialization:
    """Tests for archive serialization/deserialization."""

    @pytest.mark.asyncio
    async def test_to_bytes_and_from_bytes(self):
        """Test converting archive to bytes and back."""
        archive1 = Archive()
        archive1.add_bytes("test.txt", b"test content")

        data = await archive1.to_bytes()
        archive2 = await Archive.from_bytes(data)

        assert archive2.has_file("test.txt")
        assert archive2.get_file("test.txt") == b"test content"

    @pytest.mark.asyncio
    async def test_to_base64_and_from_base64(self):
        """Test converting archive to base64 and back."""
        archive1 = Archive()
        archive1.add_bytes("test.txt", b"test content")

        b64_string = await archive1.to_base64()
        assert isinstance(b64_string, str)

        archive2 = await Archive.from_base64(b64_string)

        assert archive2.has_file("test.txt")
        assert archive2.get_file("test.txt") == b"test content"

    @pytest.mark.asyncio
    async def test_write_and_load(self, tmp_path):
        """Test writing archive to file and loading it."""
        archive_path = tmp_path / "test.tar.gz"

        archive1 = Archive()
        archive1.add_bytes("test.txt", b"test content")

        await archive1.write(archive_path)
        assert archive_path.exists()

        archive2 = await Archive.load(archive_path)

        assert archive2.has_file("test.txt")
        assert archive2.get_file("test.txt") == b"test content"

    @pytest.mark.asyncio
    async def test_empty_archive_to_bytes_raises_error(self):
        """Test that empty archive cannot be converted to bytes."""
        archive = Archive()

        with pytest.raises(exceptions.EmptyArchiveError):
            await archive.to_bytes()


class TestArchiveEncryption:
    """Tests for archive encryption."""

    @pytest.mark.asyncio
    async def test_encrypted_archive(self):
        """Test creating and loading encrypted archive."""
        password = "secret123"

        archive1 = Archive(password=password)
        archive1.add_bytes("test.txt", b"secret content")

        data = await archive1.to_bytes()

        # Should fail with wrong password
        with pytest.raises(exceptions.InvalidPasswordError):
            await Archive.from_bytes(data, password="wrongpassword")

        # Should succeed with correct password
        archive2 = await Archive.from_bytes(data, password=password)
        assert archive2.get_file("test.txt") == b"secret content"

    @pytest.mark.asyncio
    async def test_encrypted_archive_with_salt(self):
        """Test encrypted archive maintains salt."""
        password = "secret123"

        archive1 = Archive(password=password)
        salt1 = archive1.get_salt()
        assert salt1 is not None

        archive1.add_bytes("test.txt", b"content")
        data = await archive1.to_bytes()

        archive2 = await Archive.from_bytes(data, password=password, salt=salt1)
        assert archive2.get_file("test.txt") == b"content"


class TestArchiveExtraction:
    """Tests for archive extraction."""

    @pytest.mark.asyncio
    async def test_extract_archive(self, tmp_path):
        """Test extracting archive to directory."""
        archive = Archive()
        archive.add_bytes("test.txt", b"test content")
        archive.add_bytes("subdir/file.txt", b"file content")

        extract_dir = tmp_path / "extract"
        await archive.extract(extract_dir)

        assert (extract_dir / "test.txt").exists()
        assert (extract_dir / "test.txt").read_bytes() == b"test content"
        assert (extract_dir / "subdir" / "file.txt").exists()
        assert (extract_dir / "subdir" / "file.txt").read_bytes() == b"file content"

    @pytest.mark.asyncio
    async def test_extract_prevents_path_traversal(self):
        """Test that extraction prevents path traversal attacks."""
        archive = Archive()
        # Try to add entry with path traversal
        archive.add_bytes("../../../etc/passwd", b"malicious")

        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(ValueError, match="path traversal"):
                await archive.extract(tmpdir)


class TestArchiveSizeLimit:
    """Tests for archive size limits."""

    @pytest.mark.asyncio
    async def test_size_limit_on_add_bytes(self):
        """Test size limit when adding bytes."""
        archive = Archive()
        large_data = b"x" * (Archive.MAX_SIZE + 1)

        with pytest.raises(exceptions.SizeLimitExceededError):
            archive.add_bytes("large.bin", large_data)

    @pytest.mark.asyncio
    async def test_size_limit_on_load(self):
        """Test size limit when loading archive."""
        # Create archive that's too large
        archive1 = Archive()
        # Temporarily increase limit to create large archive
        old_limit = Archive.MAX_SIZE
        Archive.MAX_SIZE = 100 * 1024 * 1024

        archive1.add_bytes("large.bin", b"x" * 60_000_000)
        data = await archive1.to_bytes()

        # Restore limit
        Archive.MAX_SIZE = old_limit

        # Should fail to load
        with pytest.raises(exceptions.SizeLimitExceededError):
            await Archive.from_bytes(data)

        # Restore for other tests
        Archive.MAX_SIZE = old_limit

    @pytest.mark.asyncio
    async def test_get_size(self):
        """Test getting archive size."""
        archive = Archive()
        archive.add_bytes("file1.txt", b"12345")
        archive.add_bytes("file2.txt", b"1234567890")

        assert archive.get_size() == 15


class TestArchiveContextManager:
    """Tests for context manager functionality."""

    @pytest.mark.asyncio
    async def test_sync_context_manager(self):
        """Test synchronous context manager."""
        with Archive() as archive:
            archive.add_bytes("test.txt", b"content")
            assert archive.has_file("test.txt")

        # Archive should be cleared after exit
        assert archive.is_empty()

    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        """Test asynchronous context manager."""
        async with Archive() as archive:
            archive.add_bytes("test.txt", b"content")
            assert archive.has_file("test.txt")

        # Archive should be cleared after exit
        assert archive.is_empty()


class TestArchiveEquality:
    """Tests for archive equality."""

    @pytest.mark.asyncio
    async def test_archive_equality(self):
        """Test archive equality comparison."""
        archive1 = Archive()
        archive1.add_bytes("test.txt", b"content")

        archive2 = Archive()
        archive2.add_bytes("test.txt", b"content")

        assert archive1 == archive2

    @pytest.mark.asyncio
    async def test_archive_inequality_different_files(self):
        """Test archives with different files are not equal."""
        archive1 = Archive()
        archive1.add_bytes("test1.txt", b"content")

        archive2 = Archive()
        archive2.add_bytes("test2.txt", b"content")

        assert archive1 != archive2

    @pytest.mark.asyncio
    async def test_archive_hash(self):
        """Test archive hashing."""
        archive1 = Archive()
        archive1.add_bytes("test.txt", b"content")

        archive2 = Archive()
        archive2.add_bytes("test.txt", b"content")

        assert hash(archive1) == hash(archive2)


class TestArchiveIteration:
    """Tests for archive iteration."""

    @pytest.mark.asyncio
    async def test_iterate_over_archive(self):
        """Test iterating over archive entries."""
        archive = Archive()
        archive.add_bytes("file1.txt", b"content1")
        archive.add_bytes("file2.txt", b"content2")

        entries = list(archive)

        assert len(entries) == 2
        names = {entry.name for entry in entries}
        assert names == {"file1.txt", "file2.txt"}


class TestCompressionTypes:
    """Tests for different compression types."""

    @pytest.mark.asyncio
    async def test_no_compression(self):
        """Test archive with no compression."""
        archive = Archive(compression=CompressionType.NONE)
        archive.add_bytes("test.txt", b"test content")

        data = await archive.to_bytes()
        archive2 = await Archive.from_bytes(data, compression=CompressionType.NONE)

        assert archive2.get_file("test.txt") == b"test content"

    @pytest.mark.asyncio
    async def test_gzip_compression(self):
        """Test archive with gzip compression."""
        archive = Archive(compression=CompressionType.GZIP)
        archive.add_bytes("test.txt", b"test content" * 100)

        data = await archive.to_bytes()
        archive2 = await Archive.from_bytes(data, compression=CompressionType.GZIP)

        assert archive2.get_file("test.txt") == b"test content" * 100

    @pytest.mark.asyncio
    async def test_bzip2_compression(self):
        """Test archive with bzip2 compression."""
        archive = Archive(compression=CompressionType.BZIP2)
        archive.add_bytes("test.txt", b"test content" * 100)

        data = await archive.to_bytes()
        archive2 = await Archive.from_bytes(data, compression=CompressionType.BZIP2)

        assert archive2.get_file("test.txt") == b"test content" * 100

    @pytest.mark.asyncio
    async def test_xz_compression(self):
        """Test archive with xz compression."""
        archive = Archive(compression=CompressionType.XZ)
        archive.add_bytes("test.txt", b"test content" * 100)

        data = await archive.to_bytes()
        archive2 = await Archive.from_bytes(data, compression=CompressionType.XZ)

        assert archive2.get_file("test.txt") == b"test content" * 100
