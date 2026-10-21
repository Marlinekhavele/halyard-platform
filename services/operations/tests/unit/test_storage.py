"""Tests for operations.storage.LocalStorage."""

import pytest

from operations.core import storage


async def test_save_read_delete_round_trip(tmp_path):
    files = storage.LocalStorage(tmp_path / "docs")
    assert not (tmp_path / "docs").exists()  # Created lazily.

    await files.save("company/shipment/doc-1", b"data")

    assert await files.read("company/shipment/doc-1") == b"data"
    await files.delete("company/shipment/doc-1")
    await files.delete("company/shipment/doc-1")  # Deleting twice is fine.
    with pytest.raises(FileNotFoundError):
        await files.read("company/shipment/doc-1")


async def test_keys_cannot_escape_the_root(tmp_path):
    files = storage.LocalStorage(tmp_path / "docs")

    with pytest.raises(ValueError):
        await files.save("../outside", b"x")
    assert not (tmp_path / "outside").exists()
