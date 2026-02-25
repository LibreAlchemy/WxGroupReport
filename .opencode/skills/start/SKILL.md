---
name: "start"
description: "One-click analysis for WeChat group reports. Executes data import, message analysis, and report generation sequentially. Invoke when the user asks to 'start analysis', 'generate report', or 'run the full pipeline'."
---

# Skill: start

## Overview

This is a composite skill designed to guide the Agent through the complete analysis pipeline for WeChat group chat records automatically and sequentially.

## Workflow

When this skill is invoked, execute the following skills in order:

1.  **import-chat-data**: 
    - **Purpose**: Preprocess `chat.json` raw data, split by member, and apply whitelist.
    - **Verification**: Ensure member JSON files are generated in the `output/members/` directory.

2.  **analyze-messages**: 
    - **Purpose**: Invoke Gemini API to summarize and score member messages.
    - **Verification**: Ensure `output/analyze-messages.json` is generated.

3.  **generate-report**: 
    - **Purpose**: Render the final Markdown report based on analysis results.
    - **Verification**: Ensure `output/report.md` is generated.

## Usage Guidelines

- **Automatic Execution**: Proceed to the next step automatically after each successful step unless a critical error occurs.
- **Progress Updates**: Briefly inform the user of the current progress before starting each sub-skill.
- **Environment Check**: Before starting, verify that the `.env` file is properly configured (especially `GOOGLE_API_KEY` and `INPUT_PATH`).

## Example Trigger Words

- "start analysis"
- "generate report"
- "analyze this group chat"
- "run the full pipeline"
