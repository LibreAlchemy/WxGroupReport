import importlib.util
import json
import sys
from pathlib import Path


def load_apply_whitelist_module():
    script_path = (
        Path(__file__).resolve().parents[1]
        / ".agents"
        / "skills"
        / "import-chat-data"
        / "scripts"
        / "apply_whitelist.py"
    )
    spec = importlib.util.spec_from_file_location("apply_whitelist", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write_member(path: Path, wxid: str, nickname: str):
    path.write_text(
        json.dumps({"wxid": wxid, "nickname": nickname}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def test_main_marks_members_by_wxid_and_nickname(tmp_path, monkeypatch, capsys):
    module = load_apply_whitelist_module()
    members_dir = tmp_path / "out" / "members"
    members_dir.mkdir(parents=True)
    write_member(members_dir / "wx1.json", "wx1", "Alice")
    write_member(members_dir / "wx2.json", "wx2", "Bob")
    (tmp_path / "whitelist.md").write_text(
        "|昵称|wxid|\n|----|----|\n|Alice|unused|\n|Ignored|wx2|\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["apply_whitelist.py", "-o", "out"])

    module.main()

    alice = json.loads((members_dir / "wx1.json").read_text(encoding="utf-8"))
    bob = json.loads((members_dir / "wx2.json").read_text(encoding="utf-8"))
    assert alice["isWhitelist"] is True
    assert bob["isWhitelist"] is True
    assert "Done" in capsys.readouterr().out


def test_main_skips_when_whitelist_missing(tmp_path, monkeypatch, capsys):
    module = load_apply_whitelist_module()
    (tmp_path / "out" / "members").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["apply_whitelist.py", "-o", "out"])

    module.main()

    assert "skipping" in capsys.readouterr().out.lower()


def test_main_skips_invalid_member_json(tmp_path, monkeypatch, capsys):
    module = load_apply_whitelist_module()
    members_dir = tmp_path / "out" / "members"
    members_dir.mkdir(parents=True)
    (members_dir / "broken.json").write_text("{invalid", encoding="utf-8")
    write_member(members_dir / "ok.json", "wx1", "Alice")
    (tmp_path / "whitelist.md").write_text(
        "|昵称|wxid|\n|----|----|\n|Alice|wx1|\n", encoding="utf-8"
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["apply_whitelist.py", "-o", "out"])

    module.main()

    out = capsys.readouterr().out
    assert "Skip broken.json" in out
    ok = json.loads((members_dir / "ok.json").read_text(encoding="utf-8"))
    assert ok["isWhitelist"] is True


def test_main_supports_custom_whitelist_path(tmp_path, monkeypatch):
    module = load_apply_whitelist_module()
    members_dir = tmp_path / "out" / "members"
    members_dir.mkdir(parents=True)
    write_member(members_dir / "wx1.json", "wx1", "Alice")

    custom_dir = tmp_path / "config"
    custom_dir.mkdir()
    custom_whitelist = custom_dir / "team-whitelist.md"
    custom_whitelist.write_text(
        "|昵称|wxid|\n|----|----|\n|Ignored|wx1|\n", encoding="utf-8"
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "apply_whitelist.py",
            "-o",
            "out",
            "--whitelist",
            str(custom_whitelist),
        ],
    )

    module.main()

    member = json.loads((members_dir / "wx1.json").read_text(encoding="utf-8"))
    assert member["isWhitelist"] is True
