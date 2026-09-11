import json
import pytest
from yunta.api import Block, BlockType, Message, Role
from yunta.provider import LiteLLMProvider
from yunta.tools.vision import read_image


def test_read_image_success(tmp_path):
    img_file = tmp_path / "sample.png"
    img_file.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01")

    res = read_image(json.dumps({"path": str(img_file)}))
    assert "imagen cargada con éxito: 'sample.png'" in res
    assert "image/png" in res
    assert "[IMAGE_URL: data:image/png;base64," in res


def test_read_image_unsupported_format(tmp_path):
    txt_file = tmp_path / "sample.txt"
    txt_file.write_text("hello", encoding="utf-8")

    with pytest.raises(ValueError, match="formato no soportado"):
        read_image(json.dumps({"path": str(txt_file)}))


def test_read_image_exceeds_size_limit(tmp_path, monkeypatch):
    from yunta.tools import vision
    monkeypatch.setattr(vision, "MAX_IMAGE_SIZE_BYTES", 10)  # 10 bytes limit for test

    img_file = tmp_path / "large.png"
    img_file.write_bytes(b"0123456789ABCDEF")

    with pytest.raises(ValueError, match="la imagen supera el límite"):
        read_image(json.dumps({"path": str(img_file)}))


def test_provider_to_litellm_supports_image_block():
    provider = LiteLLMProvider(system="s")
    msg = Message(
        role=Role.USER,
        content=[
            Block(type=BlockType.TEXT, text="analiza esta UI"),
            Block(type=BlockType.IMAGE, image_url="data:image/png;base64,abcdef"),
        ],
    )
    payload = provider._to_litellm([msg])
    # payload[0] is system, payload[1] is user
    user_payload = payload[1]
    assert user_payload["role"] == "user"
    assert len(user_payload["content"]) == 2
    assert user_payload["content"][0] == {"type": "text", "text": "analiza esta UI"}
    assert user_payload["content"][1] == {"type": "image_url", "image_url": {"url": "data:image/png;base64,abcdef"}}
