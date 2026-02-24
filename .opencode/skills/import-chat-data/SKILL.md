---
name: import-chat-data
description: Use when processing WeChat export JSON into member files and applying whitelist.md matches (wxid-first).
---

# Skill: import-chat-data

## Overview

Process WeChat export JSON into per-member JSON files, then apply whitelist marks.

## Workflow

### Step 1: Preprocess

```bash
python ".opencode/skills/import-chat-data/scripts/preprocessor.py"
```

### Step 2: Apply Whitelist

```bash
python ".opencode/skills/import-chat-data/scripts/apply_whitelist.py"
```

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
