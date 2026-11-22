import asyncio
from types import SimpleNamespace

from app.services.map_preview_storage_service import MapPreviewStorageService


class _FakeContent:
    def __init__(self, chunks):
        self.chunks = chunks

    async def iter_chunked(self, _size):
        for chunk in self.chunks:
            yield chunk


class _FakeResponse:
    status = 200

    def __init__(self, chunks):
        self.content = _FakeContent(chunks)

    async def __aenter__(self):
        return self

    async def __aexit__(self, _exc_type, _exc, _traceback):
        return False


class _FakeSession:
    def __init__(self, chunks):
        self.chunks = chunks
        self.requests = []

    def get(self, url, allow_redirects=True):
        self.requests.append((url, allow_redirects))
        return _FakeResponse(self.chunks)


def test_map_preview_is_saved_once_for_normalized_map_name(tmp_path):
    storage = MapPreviewStorageService(tmp_path)
    image = b"\x89PNG\r\n\x1a\n" + b"preview"
    session = _FakeSession([image])

    saved = asyncio.run(
        storage.download(
            "  Fords   of Isen  ",
            "https://bfmeladder.com/maps/fords.png",
            session,
        )
    )
    saved_again = asyncio.run(
        storage.download(
            "fords of isen",
            "https://bfmeladder.com/maps/fords.png",
            session,
        )
    )

    assert saved is True
    assert saved_again is True
    assert len(session.requests) == 1
    assert storage.public_url("Fords of Isen").startswith(
        "/api/v1/statistics/map-previews/",
    )


def test_map_preview_rejects_non_image_file(tmp_path):
    storage = MapPreviewStorageService(tmp_path)
    session = _FakeSession([b"not an image"])

    saved = asyncio.run(
        storage.download(
            "Broken map",
            "https://bfmeladder.com/maps/broken.txt",
            session,
        )
    )

    assert saved is False
    assert storage.public_url("Broken map") is None


def test_map_preview_uses_local_catalog_when_public_api_has_no_source(tmp_path):
    storage = MapPreviewStorageService(tmp_path)
    match = SimpleNamespace(
        map_name="Pinnath Gelin",
        map_id="maps_5Cmap_20mp_20pinnath_20gelin_5Cmap_20mp_20pinnath_20gelin_2Emap",
        map_preview_source=None,
    )
    session = _FakeSession([b"\x89PNG\r\n\x1a\n" + b"team map"])

    saved = asyncio.run(storage.download_match(match, session))

    assert saved is True
    assert len(session.requests) == 1
    assert session.requests[0][0].startswith("https://workshop-files.bfmeladder.com/")
