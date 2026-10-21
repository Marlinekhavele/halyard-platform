"""Document file storage.

``LocalStorage`` keeps files on disk for development. For production, add an
S3-compatible implementation of ``FileStorage``.
"""

import abc
import asyncio
import pathlib


class FileStorage(abc.ABC):
    """Stores document files by key."""

    @abc.abstractmethod
    async def save(self, key: str, data: bytes) -> None:
        """Stores a file, replacing any file with the same key.

        Args:
            key: Relative storage key.
            data: The file content.
        """

    @abc.abstractmethod
    async def read(self, key: str) -> bytes:
        """Reads a stored file.

        Args:
            key: Relative storage key.

        Returns:
            The file content.
        """

    @abc.abstractmethod
    async def delete(self, key: str) -> None:
        """Deletes a stored file if it exists.

        Args:
            key: Relative storage key.
        """


class LocalStorage(FileStorage):
    """Stores files under a directory on the local disk."""

    def __init__(self, root: str | pathlib.Path) -> None:
        """Initialises the storage. Directories are created on first save.

        Args:
            root: The base directory.
        """
        self.root = pathlib.Path(root)

    def _path(self, key: str) -> pathlib.Path:
        path = (self.root / key).resolve()
        if self.root.resolve() not in path.parents:
            raise ValueError("invalid storage key")
        return path

    async def save(self, key: str, data: bytes) -> None:
        """Writes a file.

        Args:
            key: Relative storage key.
            data: The file content.

        Raises:
            ValueError: The key points outside the storage root.
        """
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)

    async def read(self, key: str) -> bytes:
        """Reads a file.

        Args:
            key: Relative storage key.

        Returns:
            The file content.

        Raises:
            ValueError: The key points outside the storage root.
            FileNotFoundError: No file is stored under the key.
        """
        return await asyncio.to_thread(self._path(key).read_bytes)

    async def delete(self, key: str) -> None:
        """Deletes a file if it exists.

        Args:
            key: Relative storage key.

        Raises:
            ValueError: The key points outside the storage root.
        """
        path = self._path(key)
        if path.exists():
            await asyncio.to_thread(path.unlink)
