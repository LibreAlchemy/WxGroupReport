---
name: generate-report
description: generate group report based on analyzed data.
---
# Skill: generate-report

## Overview

Generate a Markdown report using Jinja2 templates based on analyzed data. Input includes group info, member scores, highlights, and low-quality members. Output is Markdown content and optional file write.

## When to Use

- user asks to generate a report
- need Markdown output from analyzed data

## Workflow (must follow)

1. Load `template.md` from this skill directory.
2. Prepare template context:
   - `group_name` from `groupInfo.name`
   - `period_start`, `period_end` from `config.period` if provided, otherwise `-`
   - `generated_at` ISO timestamp (now)
   - `report_number` from `config.reportNumber` (default 1)
   - Summary counts: `total_members`, `active_members`, `low_quality_count`, `highlights_count`
   - `top_members`: top 10 by `messageCount` desc; each item fields `name`, `msg_count`, `avg_score`
   - `articles`, `github_items`, `insights`, `opportunities`: pick the top item per type from `highlights`
   - `low_quality_members`: include `name`, `msg_count`, `avg_score`, `reason`, `severity_label`
3. Render the template with the context.
4. If `config.outputPath` is provided, write the Markdown file and return `filePath`.
5. Return `content` and `summary` fields in the output.

## Input / Output

### Input (ReportInput)

```ts
interface ReportInput {
  groupInfo: GroupInfo;
  memberScores: MemberScore[];
  highlights: Highlight[];
  lowQualityMembers: LowQualityMember[];
  config?: {
    period?: { start: string; end: string; };
    outputPath?: string;
    reportNumber?: number;
  };
}
```

### Output (ReportOutput)

```ts
interface ReportOutput {
  success: boolean;
  data?: {
    content: string;
    filePath?: string;
    summary: {
      totalMembers: number;
      activeMembers: number;
      lowQualityCount: number;
      highlightsCount: number;
    };
  };
  error?: {
    code: string;
    message: string;
  };
}
```

## Template

Use `template.md` in this directory. Keep output concise, readable, and stable for missing data.

## Script

Use `.opencode/skills/generate-report/scripts/generate_report.py` to render the report from JSON inputs.
The script will auto-install dependencies using `REQUIREMENTS_PATH` if `jinja2` is missing.
Required env vars:

- `OUTPUT_DIR` (default `output`)

Behavior:

- Picks the most recently modified `*_processed.json` in `OUTPUT_DIR`
- Reads analysis from `OUTPUT_DIR/analyze-messages.json`
- Writes report to `OUTPUT_DIR/report.md` unless `OUTPUT_PATH` is set

Optional env vars:

- `TEMPLATE_PATH` (default `.opencode/skills/generate-report/template.md`)
- `OUTPUT_PATH` (default `OUTPUT_DIR/report.md`)
- `REQUIREMENTS_PATH` (default `.opencode/skills/generate-report/requirements.txt`)

## Notes

- Whitelisted members are included in ranking and summary counts.
- Low-quality list excludes whitelisted members.
- Do not emit large JSON blobs in chat output.
