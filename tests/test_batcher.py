import sys
import os

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(__file__),
        "..",
        ".opencode",
        "skills",
        "analyze-messages",
        "scripts",
    ),
)

import pytest
from batcher import balance_members, create_batches


def test_balance_members_equally():
    members = [
        {"wxid": "a", "messages": [{"content": "x"}] * 50},
        {"wxid": "b", "messages": [{"content": "y"}] * 30},
        {"wxid": "c", "messages": [{"content": "z"}] * 20},
    ]
    balanced = balance_members(members, num_buckets=2)
    assert len(balanced) == 2
    total_a = sum(len(m["messages"]) for m in balanced[0])
    total_b = sum(len(m["messages"]) for m in balanced[1])
    assert abs(total_a - total_b) <= 10


def test_create_batches_100_per_batch():
    messages = [{"content": f"msg{i}"} for i in range(250)]
    batches = create_batches(messages, batch_size=100)
    assert len(batches) == 3
    assert len(batches[0]) == 100
    assert len(batches[1]) == 100
    assert len(batches[2]) == 50
