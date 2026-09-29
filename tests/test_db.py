from db import _jloads


def test_jloads_passthrough_dict():
    value = {"a": 1}
    assert _jloads(value) is value


def test_jloads_passthrough_list():
    value = [1, 2, 3]
    assert _jloads(value) is value


def test_jloads_parses_json_string():
    assert _jloads('{"a": 1}') == {"a": 1}


def test_jloads_parses_json_array_string():
    assert _jloads("[1, 2, 3]") == [1, 2, 3]
