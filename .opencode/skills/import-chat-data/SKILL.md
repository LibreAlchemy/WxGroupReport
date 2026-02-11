---
name: import-chat-data
description: Use when processing WeChat export JSON into member files and applying whitelist.md matches (wxid-first) with .env-driven config and simple error handling.
---

# Skill: import-chat-data

## Overview

Process WeChat export JSON into per-member JSON files using `.opencode/skills/import-chat-data/scripts/preprocessor.py`, then apply whitelist matches from `.opencode/skills/import-chat-data/reference/whitelist.md` (wxid first, nickname fallback) to set `isWhitelist: true`. All input/output paths and flags are read from `.env` at runtime. Do not add new scripts.

## When to Use

Use this skill when the user asks to:

- run `.opencode/skills/import-chat-data/scripts/preprocessor.py` to split message JSON into member JSON using environment variables
- apply whitelist entries (wxid preferred, nickname fallback) to member JSON and set `isWhitelist: true`
- add simple error handling around env loading or file parsing

```bash
python ".opencode/skills/import-chat-data/scripts/preprocessor.py"
```

3. Apply whitelist marks to the processed output. Match order: wxid exact match first, fallback to nickname exact match.
   - For member JSON output, set `isWhitelist: true` on matched members only.
   - Preserve key order; if `avatar` exists, place `isWhitelist` after `avatar`.
   - Do not add new scripts; use an inline one-off Python command if needed.
4. Return results with minimal output:
   - `白名单标记完成`
   - Output path(s)
   - Only include match statistics if user explicitly asks.

## Output

- Processed output directory containing main JSON and `members/*.json`.
- For matched members, `isWhitelist: true` is written.

## Quick Reference

| Task | Command / Location |
| --- | --- |
| Preprocess export JSON | `python ".opencode/skills/import-chat-data/scripts/preprocessor.py"` |
| Apply whitelist | Inline one-off Python (no new scripts) |
| Whitelist file (default) | `.opencode/skills/import-chat-data/reference/whitelist.md` |
| Required env | `INPUT_PATH` or `DATA_PATH` |
| Member output | `<OUTPUT_DIR>/members/*.json` |

## Whitelist File

- Default location: `.opencode/skills/import-chat-data/reference/whitelist.md`
- Table or list format allowed; match by wxid if provided, otherwise nickname exact match.

## Example

`.env`:

```env
INPUT_PATH=group/chat_export.json
OUTPUT_DIR=output
INCLUDE_MEDIA=false
INCLUDE_JOIN_TIME=true
```

Run preprocessing, then apply whitelist to `output/members/` (inline, no new scripts):

```bash
python ".opencode/skills/import-chat-data/scripts/preprocessor.py"
python - <<'PY'
import json
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv is None:
    raise SystemExit("missing python-dotenv")

load_dotenv()
input_path = os.getenv("WHITELIST_INPUT")
output_path = os.getenv("WHITELIST_OUTPUT")
whitelist_path = os.getenv("WHITELIST_PATH", ".opencode/skills/import-chat-data/reference/whitelist.md")
output_dir = os.getenv("OUTPUT_DIR", "output")

if not input_path:
    input_path = str(Path(output_dir) / "members")
if not output_path:
    output_path = input_path
input_dir = Path(input_path)
output_dir = Path(output_path)

if not input_dir.exists():
    raise SystemExit(f"missing input directory: {input_dir}")
if not Path(whitelist_path).exists():
    raise SystemExit(f"missing whitelist file: {whitelist_path}")

def parse_whitelist(path: Path):
    entries = []
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("|") and line.endswith("|"):
                parts = [p.strip() for p in line.strip("|").split("|")]
                if len(parts) >= 2 and parts[0] != "昵称" and parts[1] != "wxid":
                    entries.append((parts[0], parts[1]))
                continue
            if "|" in line:
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 2:
                    entries.append((parts[0], parts[1]))
                continue
            entries.append((line, ""))
    return entries

whitelist_entries = parse_whitelist(Path(whitelist_path))
whitelist_by_wxid = {wxid: nickname for nickname, wxid in whitelist_entries if wxid}
whitelist_by_name = {nickname for nickname, wxid in whitelist_entries if nickname and not wxid}

output_dir.mkdir(parents=True, exist_ok=True)

for member_file in input_dir.glob("*.json"):
    with member_file.open("r", encoding="utf-8") as handle:
        member = json.load(handle)

    wxid = str(member.get("wxid", "")).strip()
    nickname = str(member.get("nickname", "")).strip()
    matched = False

    if wxid and wxid in whitelist_by_wxid:
        matched = True
    elif nickname and nickname in whitelist_by_name:
        matched = True

    if matched:
        if "isWhitelist" not in member:
            ordered = {}
            inserted = False
            for key, value in member.items():
                ordered[key] = value
                if key == "avatar":
                    ordered["isWhitelist"] = True
                    inserted = True
            if not inserted:
                ordered["isWhitelist"] = True
            member = ordered
        else:
            member["isWhitelist"] = True

        out_file = output_dir / member_file.name
        with out_file.open("w", encoding="utf-8") as handle:
            json.dump(member, handle, ensure_ascii=False, indent=2)
    else:
        if output_dir != input_dir:
            out_file = output_dir / member_file.name
            with out_file.open("w", encoding="utf-8") as handle:
                json.dump(member, handle, ensure_ascii=False, indent=2)

PY
```

Expected behavior: member JSON files under `output/members/` are updated so matching members include `isWhitelist: true` (wxid-first, nickname fallback).

## Error Handling (simple)

- Missing `.env` or missing `INPUT_PATH`/`DATA_PATH`: return a clear error and stop.
- JSON parsing errors: return error with filename.
- Missing whitelist file: return error and stop (unless user explicitly disables whitelist step).

## Common Mistakes

- Using `scripts/` path typos (it must be `.opencode/skills/import-chat-data/scripts/preprocessor.py`).
- Forgetting to set `INPUT_PATH`/`DATA_PATH` in `.env`.
- Pointing `WHITELIST_PATH` at the wrong folder (`reference`, not `references`).
- Assuming nickname match when wxid is present (wxid always wins).

## Rationalization Traps

| Excuse | Reality |
| --- | --- |
| "No time, just make it work" | Follow the env-driven preprocessor + whitelist steps; skipping them breaks the contract. |
| "Handle all exports" | Only support documented formats; return a clear error when unsupported. |
| "We already changed a lot" | Avoid destructive refactors; apply the workflow on top of existing changes. |

## Red Flags

- Skipping `.env` loading or hardcoding paths.
- Applying whitelist before preprocessing.
- Guessing unknown input formats without a sample.
- Returning large JSON blobs in chat by default.

## Privacy and Safety

- Output JSON includes full message content; treat as sensitive.
- Do not suggest committing `output/*.json` to git.
