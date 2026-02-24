#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Apply whitelist marks to member files based on whitelist.md
"""

import json
from pathlib import Path


def main():
    whitelist_file = Path(__file__).parent.parent / "reference" / "whitelist.md"
    members_dir = Path("output/members")

    if not whitelist_file.exists():
        print(f"Whitelist file not found: {whitelist_file}, skipping...")
        return

    whitelist = {}
    with open(whitelist_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "昵称" in line:
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 3:
                nickname, wxid = parts[1], parts[2]
                if wxid:
                    whitelist[wxid] = nickname

    if not whitelist:
        print("No whitelist entries found")
        return

    for member_file in members_dir.glob("*.json"):
        try:
            with open(member_file, "r", encoding="utf-8") as f:
                member = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Skip {member_file.name}: {e}")
            continue

        wxid = member.get("wxid", "")
        if wxid in whitelist:
            member["isWhitelist"] = True
            with open(member_file, "w", encoding="utf-8") as f:
                json.dump(member, f, ensure_ascii=False, indent=2)
            print(f"Marked: {member.get('nickname', wxid)}")

    print("Done")


if __name__ == "__main__":
    main()
