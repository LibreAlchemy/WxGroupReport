from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    _reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(_reconfigure):
        _reconfigure(encoding="utf-8")
except Exception:
    pass


def load_nickname_whitelist_md(file_path: str) -> list[str]:
    """兼容历史函数名：返回“昵称列表”。

    当前推荐改用 `load_whitelist_md()`，它会解析表格第二列的 wxid，
    并在应用白名单时优先按 wxid 精确命中。
    """

    entries = load_whitelist_md(file_path)
    nicknames: list[str] = []
    seen: set[str] = set()

    for e in entries:
        n = str(e.get("nickname") or "").strip()
        if not n:
            continue
        if n in seen:
            continue
        seen.add(n)
        nicknames.append(n)

    return nicknames


def load_whitelist_md(file_path: str) -> list[dict]:
    """从 Markdown 文件中读取白名单条目。

    支持两种写法：
    1) 一行一个昵称（或 Markdown 列表/勾选框）：只提供 nickname
    2) Markdown 表格：第一列 nickname，第二列 wxid（优先匹配）

    返回：
    - entries: [{"nickname": str|None, "wxid": str|None}, ...]
    """

    entries: list[dict] = []
    seen_wxid: set[str] = set()
    seen_nickname: set[str] = set()

    # 经验规则：微信 wxid 一般以 wxid 开头；若第二列不符合该形态，则按“备注列”处理。
    wxid_re = re.compile(r"^wxid[0-9A-Za-z_\-]+$")

    in_code_block = False
    in_html_comment = False

    list_prefix_re = re.compile(r"^\s*(?:[-*+]\s+|\d+\.\s+)")
    task_prefix_re = re.compile(r"^\s*[-*+]\s*\[[xX \t]\]\s+")

    with open(file_path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue

            # HTML 注释块（可能是单行或多行）。
            if in_html_comment:
                if "-->" in line:
                    in_html_comment = False
                continue
            if line.startswith("<!--"):
                if "-->" not in line:
                    in_html_comment = True
                continue

            if line.startswith("```"):
                in_code_block = not in_code_block
                continue
            if in_code_block:
                continue

            if line.startswith("#"):
                continue

            # 水平线或纯分隔符。
            if line in {"---", "***", "___"}:
                continue

            # Markdown 表格行。
            if line.startswith("|") and "|" in line[1:]:
                cells = [c.strip() for c in line.strip("|").split("|")]
                if not cells:
                    continue
                first = cells[0]
                first_norm = first.strip().lower()
                if first_norm in {"nickname", "nick", "昵称"}:
                    # 表头行。
                    continue
                if not first or set(first) <= {"-", ":"}:
                    continue

                nickname = first.strip().strip("`")
                wxid = ""
                if len(cells) >= 2:
                    wxid = cells[1].strip().strip("`")

                if wxid and not wxid_re.match(wxid):
                    wxid = ""

                if wxid:
                    if wxid in seen_wxid:
                        continue
                    seen_wxid.add(wxid)
                    entries.append({"nickname": nickname or None, "wxid": wxid})
                    continue

                if nickname:
                    if nickname in seen_nickname:
                        continue
                    seen_nickname.add(nickname)
                    entries.append({"nickname": nickname, "wxid": None})
                    continue

                continue
            else:
                value = line
                value = task_prefix_re.sub("", value)
                value = list_prefix_re.sub("", value)

            value = value.strip().strip("`")
            if not value:
                continue

            # 非表格行：视为“昵称条目”。
            if value in seen_nickname:
                continue
            seen_nickname.add(value)
            entries.append({"nickname": value, "wxid": None})

    return entries


def apply_nickname_whitelist_to_members_dict(members_by_wxid: dict, whitelist_nicknames: list[str]) -> dict:
    """兼容历史函数名：按昵称应用白名单。"""

    entries = [{"nickname": n, "wxid": None} for n in (whitelist_nicknames or [])]
    return apply_whitelist_to_members_dict(members_by_wxid, entries)


def apply_whitelist_to_members_dict(members_by_wxid: dict, whitelist_entries: list[dict]) -> dict:
    """把白名单应用到 {wxid: member} 映射上。

    匹配顺序：
    - 如果条目提供 wxid：优先按 wxid 精确命中
    - 否则：按 nickname 与 member.nickname 做 strip 后精确相等
    """

    nickname_to_wxids: dict[str, list[str]] = {}
    for wxid, m in (members_by_wxid or {}).items():
        if not isinstance(m, dict):
            continue
        nick = str(m.get("nickname") or "").strip()
        if not nick:
            continue
        nickname_to_wxids.setdefault(nick, []).append(str(wxid))

    unmatched: list[str] = []
    ambiguous: dict[str, list[str]] = {}
    matched_wxids: set[str] = set()

    unmatched_wxids: list[str] = []

    for entry in whitelist_entries or []:
        if not isinstance(entry, dict):
            continue

        wxid = str(entry.get("wxid") or "").strip()
        nickname = str(entry.get("nickname") or "").strip()

        if wxid:
            m = members_by_wxid.get(wxid)
            if isinstance(m, dict):
                m["isWhitelist"] = True
                matched_wxids.add(str(wxid))
            else:
                unmatched_wxids.append(wxid)
            continue

        if not nickname:
            continue

        wxids = nickname_to_wxids.get(nickname, [])
        if not wxids:
            unmatched.append(nickname)
            continue
        if len(wxids) > 1:
            ambiguous[nickname] = list(wxids)
        for w in wxids:
            m = members_by_wxid.get(w)
            if isinstance(m, dict):
                m["isWhitelist"] = True
                matched_wxids.add(str(w))

    return {
        "whitelistEntries": list(whitelist_entries or []),
        "matchedMembers": int(len(matched_wxids)),
        "unmatchedWxids": unmatched_wxids,
        "unmatchedNicknames": unmatched,
        "ambiguousNicknames": ambiguous,
    }


def _move_key_after(obj: dict, key: str, after_key: str) -> None:
    """Move `key` to be right after `after_key` in-place.

    Python dict preserves insertion order; re-creating the dict is the
    most predictable way to adjust field order for JSON output.
    """

    if not isinstance(obj, dict):
        return
    if key not in obj or after_key not in obj:
        return

    keys = list(obj.keys())
    try:
        after_idx = keys.index(after_key)
        key_idx = keys.index(key)
    except ValueError:
        return

    if key_idx == after_idx + 1:
        return

    value = obj.get(key)
    new_obj: dict = {}
    inserted = False
    for k in keys:
        if k == key:
            continue
        new_obj[k] = obj.get(k)
        if k == after_key:
            new_obj[key] = value
            inserted = True
    if not inserted:
        new_obj[key] = value

    obj.clear()
    obj.update(new_obj)


def _reorder_member_fields_for_output(member: dict) -> None:
    # Requirement: `isWhitelist` should be placed right after `avatar`.
    _move_key_after(member, "isWhitelist", "avatar")


def _sanitize_windows_filename(value: str) -> str:
    s = re.sub(r"[<>:\"/\\|?*]+", "_", value)
    s = re.sub(r"\s+", " ", s).strip()
    return s or "unknown"


def _choose_default_out_path(input_path: Path, raw: dict) -> Path:
    group_name = ""
    group_info = raw.get("group_info")
    if isinstance(group_info, dict):
        group_name = str(group_info.get("name") or "").strip()

    stem = _sanitize_windows_filename(group_name or input_path.stem)
    out = Path("output") / f"whitelist_applied_{stem}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    if not out.exists():
        return out

    i = 2
    while True:
        cand = out.with_name(out.stem + f"_{i}" + out.suffix)
        if not cand.exists():
            return cand
        i += 1


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("root JSON must be an object")
    return data


def _is_processed_group_json(raw: dict) -> bool:
    members = raw.get("members")
    return isinstance(members, dict)


def _is_member_json(raw: dict) -> bool:
    wxid = raw.get("wxid")
    return isinstance(wxid, str) and wxid.strip() != ""


def _iter_member_json_files(root_dir: Path) -> list[Path]:
    """Return member json file paths under a directory.

    Layouts supported:
    - <root>/members/*.json (preferred)
    - <root>/*.json where each file is a member object
    """

    members_dir = root_dir / "members"
    if members_dir.exists() and members_dir.is_dir():
        return sorted(members_dir.glob("*.json"), key=lambda p: p.name.lower())
    return sorted(root_dir.glob("*.json"), key=lambda p: p.name.lower())


def _choose_default_out_dir(input_dir: Path) -> Path:
    stem = _sanitize_windows_filename(input_dir.name)
    out = Path("output") / f"whitelist_applied_{stem}"
    out.mkdir(parents=True, exist_ok=True)
    if not out.exists():
        return out
    return out


def _apply_whitelist_to_member_files(
    member_files: list[Path],
    whitelist_entries: list[dict],
) -> tuple[dict[str, dict], dict]:
    """Load member json files, apply whitelist, and return updated members + stats.

    Returns:
    - members_by_wxid: {wxid: member_dict}
    - stats: output of apply_whitelist_to_members_dict
    """

    members_by_wxid: dict[str, dict] = {}
    for p in member_files:
        try:
            raw = _load_json(p)
        except Exception:
            continue

        if not _is_member_json(raw):
            continue

        wxid = str(raw.get("wxid") or "").strip()
        if not wxid:
            continue
        if not isinstance(raw, dict):
            continue
        members_by_wxid[wxid] = raw

    stats = apply_whitelist_to_members_dict(members_by_wxid, whitelist_entries)
    return members_by_wxid, stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "将 whitelist.md 中的昵称白名单应用到 processed JSON，并对命中的成员写入 isWhitelist=true。"
        )
    )
    parser.add_argument(
        "file",
        help=(
            "输入路径：可以是 processed 群 JSON 文件；也可以是目录（例如 group/ 或 group/members/），"
            "目录下每个成员一个 JSON 文件"
        ),
    )
    parser.add_argument(
        "--whitelist",
        dest="whitelist_path",
        default=".opencode/skills/import-chat-data/references/whitelist.md",
        help="白名单 Markdown 路径（昵称；建议一行一个）",
    )
    parser.add_argument(
        "--out",
        dest="out_path",
        default=None,
        help="输出 JSON 路径（默认 output/whitelist_applied_<群名>.json）",
    )

    args = parser.parse_args()

    whitelist_path = args.whitelist_path.strip() if isinstance(args.whitelist_path, str) else ""
    if not whitelist_path:
        whitelist_path = ".opencode/skills/import-chat-data/references/whitelist.md"
    out_path = args.out_path.strip() if isinstance(args.out_path, str) else None
    if out_path == "":
        out_path = None

    in_file = Path(args.file)
    if not in_file.exists():
        print(f"error: input file not found: {in_file}")
        return 2

    wl_file = Path(whitelist_path)
    if not wl_file.exists() or wl_file.is_dir():
        print(f"error: whitelist file not found: {wl_file}")
        return 2

    whitelist_entries = load_whitelist_md(str(wl_file))

    # Directory mode: apply to per-member JSON files.
    if in_file.is_dir():
        member_files = _iter_member_json_files(in_file)
        if not member_files:
            print(f"error: no member .json files found under directory: {in_file}")
            return 2

        members_by_wxid, stats = _apply_whitelist_to_member_files(member_files, whitelist_entries)
        if not members_by_wxid:
            print(f"error: no valid member JSON objects found under directory: {in_file}")
            return 2

        out_dir = Path(out_path) if out_path else _choose_default_out_dir(in_file)
        if out_dir.suffix.lower() == ".json":
            print("error: when input is a directory, --out must be a directory path (not a .json file)")
            return 2
        out_dir.mkdir(parents=True, exist_ok=True)

        wxid_to_src_path: dict[str, Path] = {}
        for p in member_files:
            try:
                raw = _load_json(p)
            except Exception:
                continue
            if not isinstance(raw, dict):
                continue
            if not _is_member_json(raw):
                continue
            wxid = str(raw.get("wxid") or "").strip()
            if not wxid:
                continue
            wxid_to_src_path[wxid] = p

        saved_files = 0
        for wxid, member in members_by_wxid.items():
            src = wxid_to_src_path.get(wxid)
            name = src.name if isinstance(src, Path) else f"{wxid}.json"
            out_file = out_dir / name
            with out_file.open("w", encoding="utf-8") as f:
                _reorder_member_fields_for_output(member)
                json.dump(member, f, ensure_ascii=False, indent=2)
            saved_files += 1

        unmatched = stats.get("unmatchedNicknames") or []
        unmatched_wxids = stats.get("unmatchedWxids") or []
        ambiguous = stats.get("ambiguousNicknames") or {}
        print(f"saved_dir: {out_dir}")
        print(f"saved_files: {saved_files}")
        print(f"matched_members: {stats.get('matchedMembers')}")
        print(f"unmatched_wxids: {len(unmatched_wxids)}")
        print(f"unmatched_nicknames: {len(unmatched)}")
        print(f"ambiguous_nicknames: {len(ambiguous)}")
        return 0

    # File mode: processed group JSON or single member JSON.
    try:
        raw = _load_json(in_file)
    except json.JSONDecodeError as e:
        print(f"error: JSON decode error: {e}")
        return 2
    except Exception as e:
        print(f"error: failed to load JSON: {e}")
        return 2

    if _is_processed_group_json(raw):
        members = raw.get("members")
        assert isinstance(members, dict)
        stats = apply_whitelist_to_members_dict(members, whitelist_entries)

        for _, m in members.items():
            if isinstance(m, dict):
                _reorder_member_fields_for_output(m)

        out_file = Path(out_path) if out_path else _choose_default_out_path(in_file, raw)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with out_file.open("w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False, indent=2)

        unmatched = stats.get("unmatchedNicknames") or []
        unmatched_wxids = stats.get("unmatchedWxids") or []
        ambiguous = stats.get("ambiguousNicknames") or {}
        print(f"saved: {out_file}")
        print(f"matched_members: {stats.get('matchedMembers')}")
        print(f"unmatched_wxids: {len(unmatched_wxids)}")
        print(f"unmatched_nicknames: {len(unmatched)}")
        print(f"ambiguous_nicknames: {len(ambiguous)}")
        return 0

    if _is_member_json(raw):
        wxid = str(raw.get("wxid") or "").strip()
        stats = apply_whitelist_to_members_dict({wxid: raw}, whitelist_entries)

        _reorder_member_fields_for_output(raw)

        out_file = Path(out_path) if out_path else (Path("output") / in_file.name)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with out_file.open("w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False, indent=2)

        unmatched = stats.get("unmatchedNicknames") or []
        unmatched_wxids = stats.get("unmatchedWxids") or []
        ambiguous = stats.get("ambiguousNicknames") or {}
        print(f"saved: {out_file}")
        print(f"matched_members: {stats.get('matchedMembers')}")
        print(f"unmatched_wxids: {len(unmatched_wxids)}")
        print(f"unmatched_nicknames: {len(unmatched)}")
        print(f"ambiguous_nicknames: {len(ambiguous)}")
        return 0

    print("error: unrecognized JSON structure; expected processed group JSON (with members) or member JSON (with wxid)")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
