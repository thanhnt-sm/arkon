from __future__ import annotations

from app.utils.text import parse_json_loose


def test_parse_json_loose_repairs_missing_field_commas():
    raw = """{
      "entities": []
      "concepts": [
        {
          "term": "A"
          "definition_excerpt": "B"
          "local_offset": 0
        }
      ]
      "claims": []
    }"""

    parsed = parse_json_loose(raw)

    assert parsed["concepts"][0]["term"] == "A"
    assert parsed["claims"] == []


def test_parse_json_loose_repairs_missing_array_item_commas():
    raw = """[
      {"name": "A"}
      {"name": "B"}
    ]"""

    parsed = parse_json_loose(raw)

    assert [item["name"] for item in parsed] == ["A", "B"]
