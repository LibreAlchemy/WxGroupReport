import pytest
import json
from pathlib import Path


def test_load_members_from_directory(tmp_path):
    members_dir = tmp_path / "members"
    members_dir.mkdir()

    (members_dir / "wx1.json").write_text(
        json.dumps(
            {
                "wxid": "wx1",
                "nickname": "User1",
                "messages": [{"content": "hello", "timestamp": "2026-02-01T00:00:00Z"}],
            }
        )
    )

    from analyze import load_members

    members = load_members(str(members_dir))
    assert len(members) == 1
    assert members[0]["wxid"] == "wx1"
