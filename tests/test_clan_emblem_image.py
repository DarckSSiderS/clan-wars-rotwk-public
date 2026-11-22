import io
from pathlib import Path

import pytest
from fastapi import HTTPException
from PIL import Image

from app.api.v1.clans import get_static_map_emblem, remove_map_emblem_preview
from app.config import settings
from app.utils.image_processor import process_avatar_image


def make_two_frame_gif() -> bytes:
    first = Image.new("RGB", (32, 24), (240, 20, 20))
    second = Image.new("RGB", (32, 24), (20, 40, 240))
    output = io.BytesIO()
    first.save(
        output,
        format="GIF",
        save_all=True,
        append_images=[second],
        duration=[100, 100],
        loop=0,
    )
    return output.getvalue()


def test_static_avatar_mode_saves_only_first_gif_frame_as_webp(tmp_path):
    output_path = tmp_path / "clan.webp"

    success = process_avatar_image(
        make_two_frame_gif(),
        str(output_path),
        preserve_animation=False,
    )

    assert success is True
    with Image.open(output_path) as result:
        assert result.format == "WEBP"
        assert result.size == (150, 150)
        assert getattr(result, "n_frames", 1) == 1
        red, green, blue = result.convert("RGB").getpixel((75, 75))
        assert red > 200
        assert green < 50
        assert blue < 50


def test_default_avatar_mode_keeps_gif_animation(tmp_path):
    output_path = tmp_path / "user.gif"

    success = process_avatar_image(make_two_frame_gif(), str(output_path))

    assert success is True
    with Image.open(output_path) as result:
        assert result.format == "GIF"
        assert result.n_frames == 2


def test_map_emblem_endpoint_creates_static_preview_without_changing_source(
    tmp_path,
    monkeypatch,
):
    clan_dir = tmp_path / "clans"
    clan_dir.mkdir()
    source_path = clan_dir / "animated.gif"
    source_content = make_two_frame_gif()
    source_path.write_bytes(source_content)
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))

    response = get_static_map_emblem("animated.gif")

    preview_path = Path(response.path)
    assert preview_path == clan_dir / "map-emblems" / "animated.gif.webp"
    assert source_path.read_bytes() == source_content
    with Image.open(preview_path) as preview:
        assert preview.format == "WEBP"
        assert getattr(preview, "n_frames", 1) == 1
    assert list(preview_path.parent.iterdir()) == [preview_path]


def test_map_emblem_endpoint_rejects_path_traversal():
    with pytest.raises(HTTPException) as error:
        get_static_map_emblem("../secret.gif")

    assert error.value.status_code == 400


def test_old_map_emblem_preview_is_removed_without_deleting_source(
    tmp_path,
    monkeypatch,
):
    clan_dir = tmp_path / "clans"
    preview_dir = clan_dir / "map-emblems"
    preview_dir.mkdir(parents=True)
    source_path = clan_dir / "old.gif"
    preview_path = preview_dir / "old.gif.webp"
    source_path.write_bytes(make_two_frame_gif())
    preview_path.write_bytes(b"cached")
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))

    remove_map_emblem_preview("/images/clans/old.gif")

    assert source_path.exists()
    assert not preview_path.exists()
