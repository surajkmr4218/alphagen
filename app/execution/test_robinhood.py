import pytest

from app.execution.robinhood import RobinhoodBroker

_payload = RobinhoodBroker._payload


def test_json_text_block_parses():
    res = [{"type": "text", "text": '{"data": {"order": {"id": "x"}}}'}]
    assert _payload(res) == {"data": {"order": {"id": "x"}}}


def test_structured_dict_fallback():
    res = {"data": {"results": []}}
    assert _payload(res) == {"data": {"results": []}}


def test_plain_text_error_surfaces_raw_message():
    # A broker error/notice comes back as a plain-text block, not JSON. The raw
    # message must survive into the exception (it becomes the order's reason).
    res = [{"type": "text", "text": "Insufficient buying power for this order"}]
    with pytest.raises(RuntimeError, match="Insufficient buying power"):
        _payload(res)


def test_text_block_before_json_block_still_parses():
    res = [
        {"type": "text", "text": "Order created successfully."},
        {"type": "text", "text": '{"data": {}}'},
    ]
    assert _payload(res) == {"data": {}}


def test_empty_blocks_raise_shape_error():
    with pytest.raises(RuntimeError, match="unexpected MCP result shape"):
        _payload([{"type": "text", "text": ""}])
