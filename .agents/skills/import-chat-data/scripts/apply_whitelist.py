#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Apply whitelist marks to member files based on whitelist.md
"""

import json
import os
import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Apply whitelist marks to member files")
    parser.add_argument("-o", "--output", default="output", help="输出目录，默认 output")
    parser.add_argument(
        "-w",
        "--whitelist",
        default="whitelist.md",
        help="白名单文件路径，默认使用仓库根目录下的 whitelist.md",
    )
    args = parser.parse_args()

    whitelist_file = Path(args.whitelist)
    
    output_dir = Path(args.output)
    members_dir = output_dir / "members"

    if not whitelist_file.exists():
        print(f"Whitelist file not found: {whitelist_file}, skipping...")
        return

    whitelist = set()
    with open(whitelist_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # 跳过空行、注释、表头和分割线
            if not line or line.startswith("#") or "昵称" in line or line.startswith("|---"):
                continue
            
            # 解析 Markdown 表格行: |昵称|wxid|
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) >= 2:
                nickname, wxid = parts[0], parts[1]
                if wxid:
                    whitelist.add(wxid)
                if nickname:
                    whitelist.add(nickname)

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
        nickname = member.get("nickname", "")
        
        # 如果 wxid 或 nickname 在白名单中，则标记
        if wxid in whitelist or nickname in whitelist:
            member["isWhitelist"] = True
            with open(member_file, "w", encoding="utf-8") as f:
                json.dump(member, f, ensure_ascii=False, indent=2)
            print(f"Marked: {nickname} ({wxid})")

    print("Done")


if __name__ == "__main__":
    main()
