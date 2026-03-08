"""Tests for source_paths utility functions."""

import json
from borgitory.utils.source_paths import parse_source_paths, serialize_source_paths


class TestParseSourcePaths:
    def test_single_path_json_array(self):
        assert parse_source_paths('["/data"]') == ["/data"]

    def test_multiple_paths_json_array(self):
        result = parse_source_paths('["/home/user/src", "/home/user/Documents"]')
        assert result == ["/home/user/src", "/home/user/Documents"]

    def test_empty_string(self):
        assert parse_source_paths("") == []

    def test_whitespace_only(self):
        assert parse_source_paths("   ") == []

    def test_empty_json_array(self):
        assert parse_source_paths("[]") == []

    def test_filters_empty_strings_in_array(self):
        assert parse_source_paths('["/data", "", "  "]') == ["/data"]

    def test_invalid_json_starting_with_bracket(self):
        assert parse_source_paths("[not json") == []

    def test_json_array_with_non_string_elements(self):
        assert parse_source_paths('["/data", 123]') == ["/data"]

    def test_three_paths(self):
        paths = '["/appdata/app1", "/appdata/app2", "/appdata/app3"]'
        result = parse_source_paths(paths)
        assert result == ["/appdata/app1", "/appdata/app2", "/appdata/app3"]

    def test_relative_paths_in_array_returned_as_is(self):
        result = parse_source_paths('["/valid", "relative", "/also-valid"]')
        assert result == ["/valid", "relative", "/also-valid"]

    def test_non_json_input_returns_empty_list(self):
        assert parse_source_paths("/data") == []
        assert parse_source_paths("plain string") == []
        assert parse_source_paths("relative/path") == []


class TestSerializeSourcePaths:
    def test_single_path(self):
        result = serialize_source_paths(["/data"])
        assert json.loads(result) == ["/data"]

    def test_multiple_paths(self):
        result = serialize_source_paths(["/src", "/Documents"])
        assert json.loads(result) == ["/src", "/Documents"]

    def test_empty_list(self):
        assert serialize_source_paths([]) == "[]"

    def test_filters_empty_strings(self):
        result = serialize_source_paths(["/data", "", "  "])
        assert json.loads(result) == ["/data"]

    def test_strips_whitespace(self):
        result = serialize_source_paths(["  /data  "])
        assert json.loads(result) == ["/data"]

    def test_roundtrip(self):
        original = ["/home/user/src", "/home/user/Documents", "/backups"]
        serialized = serialize_source_paths(original)
        parsed = parse_source_paths(serialized)
        assert parsed == original
