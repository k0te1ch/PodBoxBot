"""Тесты чистого draft.js-билдера (без зависимости от либы boosty)."""

import json

from app.publishers.Boosty.content import build_post_data


def _parse(data: str) -> list[dict]:
    return json.loads(data)


class TestBuildPostData:
    def test_returns_json_string(self):
        out = build_post_data("hello")
        assert isinstance(out, str)
        assert isinstance(_parse(out), list)

    def test_text_block_shape_matches_reference(self):
        # Формат подтверждён реверсом HOCKI1/py_boosty_api:
        # text-блок + BLOCK_END, content — вложенный json.dumps.
        blocks = _parse(build_post_data("hello"))
        assert blocks[0]["type"] == "text"
        assert blocks[0]["modificator"] == ""
        assert json.loads(blocks[0]["content"]) == ["hello", "unstyled", []]
        assert blocks[1] == {"type": "text", "content": "", "modificator": "BLOCK_END"}

    def test_paragraphs_split_on_newline(self):
        blocks = _parse(build_post_data("first\nsecond"))
        texts = [json.loads(b["content"])[0] for b in blocks if b["modificator"] == ""]
        assert texts == ["first", "second"]

    def test_blank_lines_skipped(self):
        blocks = _parse(build_post_data("a\n\n   \nb"))
        texts = [json.loads(b["content"])[0] for b in blocks if b["modificator"] == ""]
        assert texts == ["a", "b"]

    def test_chapters_appended(self):
        blocks = _parse(build_post_data("body", chapters=[["00:00", "Intro"], ["01:00", "Mid"]]))
        texts = [json.loads(b["content"])[0] for b in blocks if b["modificator"] == ""]
        assert "00:00 — Intro" in texts
        assert "01:00 — Mid" in texts

    def test_empty_body_produces_non_empty_post(self):
        # Boosty не принимает пустой data — даём хотя бы один блок.
        blocks = _parse(build_post_data(""))
        assert len(blocks) >= 2
        assert blocks[-1]["modificator"] == "BLOCK_END"

    def test_unicode_not_escaped(self):
        out = build_post_data("Привет")
        # ensure_ascii=False на обоих слоях → кириллица не \uXXXX.
        assert "Привет" in out

    def test_one_element_chapter_uses_first(self):
        blocks = _parse(build_post_data("", chapters=[["solo"]]))
        texts = [json.loads(b["content"])[0] for b in blocks if b["modificator"] == ""]
        assert "solo" in texts
