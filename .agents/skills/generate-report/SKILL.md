---
name: generate-report
description: Generate Markdown reports (`report.md` and `low_quality_members.md`) from analyzed data.
---
# Skill: generate-report

## Overview

Generate two Markdown files with Jinja2 templates:
- main report: `output/report.md`
- low-quality report: `output/low_quality_members.md`

## When to Use

- user asks to generate a report
- need Markdown output from analyzed data

## Workflow (must follow)

1. Load templates from this skill:
   - `references/template.md`
   - `references/low_quality_template.md`
2. Prepare template context:
   - period / generated time / report number
   - summary counts: `total_members`, `active_members`, `low_quality_count`, `highlights_count`
   - `top_members`: top 10 by computed activity score
   - highlights split by type
   - `low_quality_members` and grouped `low_quality_groups`
3. Render the template with the context.
4. Write both output files.

## Input / Output

### Input (ReportInput)

```ts
interface ReportInput {
  memberScores: MemberScore[];
  highlights: Highlight[];
  config?: {
    period?: { start: string; end: string; };
    reportNumber?: number;
  };
}
```

### Output (ReportOutput)

```ts
interface ReportOutput {
  success: boolean;
  data?: {
    reportPath: string;
    lowQualityPath: string;
  };
  error?: {
    code: string;
    message: string;
  };
}
```

## Template

Use templates in `references/` directory.

## Script

Use `.agents/skills/generate-report/scripts/generate_report.py` to render reports from JSON inputs.
Scripts support both command-line arguments and environment variables (via `.env`).

### Command Line Arguments

- `-o, --output`: Output directory (overrides `OUTPUT_DIR`, default: `output`)
- `--low-quality-template`: Optional low-quality template path
- `--low-quality-output`: Optional low-quality output path

### Environment Variables

- `OUTPUT_DIR` (default `output`)
- `LOW_QUALITY_TEMPLATE_PATH` (optional override, default uses script sibling `references/low_quality_template.md`)
- `LOW_QUALITY_OUTPUT_PATH` (optional override, default `output/low_quality_members.md`)

## Notes

- Main template path is fixed in script and resolves from script location.
- Do not emit large JSON blobs in chat output.
