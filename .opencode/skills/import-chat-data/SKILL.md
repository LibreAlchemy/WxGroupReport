---
name: import-chat-data
description: Use when processing WeChat export JSON into member files and applying whitelist.md matches (wxid-first).
---

# Skill: import-chat-data

## Overview

Process WeChat export JSON into per-member JSON files, then apply whitelist marks.

## Workflow

Scripts support both command-line arguments and environment variables (via `.env`).

### Step 1: Preprocess

```bash
python ".opencode/skills/import-chat-data/scripts/preprocessor.py" -i path/to/input.json -o output
```

**Arguments**:
- `-i, --input`: Input JSON file path (overrides `INPUT_PATH`)
- `-o, --output`: Output directory (overrides `OUTPUT_DIR`, default: `output`)
- `--include-media`: Include media messages
- `--no-join-time`: Do not extract join time
- `--no-individual`: Do not save individual member files

### Step 2: Apply Whitelist

```bash
python ".opencode/skills/import-chat-data/scripts/apply_whitelist.py" -o output
```

**Arguments**:
- `-o, --output`: Output directory (overrides `OUTPUT_DIR`, default: `output`)

**Note**: Run scripts and check console output for file locations.

## Error Handling

- Missing input file: error
- Missing whitelist file: skip whitelist step
- JSON parse error: skip that file

## Quick Reference

All scripts are in the `scripts/` subdirectory of this skill.

Agent execution: 
- Use this `SKILL.md` file's path as SKILL_DIR
- Use `${SKILL_DIR}/scripts/<script-name>.py` as script path.

| Script | Purpose |
|--------|---------|
| scripts/preprocessor.py | Preprocess chat data, split by member |
| scripts/apply_whitelist.py | Apply whitelist marks to members |
