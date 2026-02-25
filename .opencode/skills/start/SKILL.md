---
name: "start"
description: "One-click analysis for WeChat group reports. Executes data import, message analysis, and report generation sequentially. Invoke when the user asks to 'start analysis', 'generate report', or 'run the full pipeline'."
---

# Skill: start

## Overview

This is a composite skill designed to guide the Agent through the complete analysis pipeline for WeChat group chat records automatically and sequentially.

## Workflow

When this skill is invoked, execute the following skills in order:

1. **import-chat-data**
2. **analyze-messages**
3. **generate-report**

## Usage Guidelines

- **Automatic Execution**: Proceed to the next step automatically after each successful step unless a critical error occurs.
- **Progress Updates**: Briefly inform the user of the current progress before starting each sub-skill.
- **Environment**: Reading `.env` files is strictly prohibited. Scripts will load configuration via environment variables at runtime.

## Example Trigger Words

- "start analysis"
- "generate report"
- "analyze this group chat"
- "run the full pipeline"
