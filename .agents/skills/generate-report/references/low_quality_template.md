# 低质成员名单（{{ low_quality_count }} 人）

**统计周期**: {{ period_start }} ~ {{ period_end }}
**生成时间**: {{ generated_at }}
**报告期号**: 第 {{ report_number }} 期

{%- for group in low_quality_groups %}
## {{ group.title }}（{{ group.count }}人）

{%- for member in group.members %}
{%- if group.status == "zero_activity" %}
- {{ member.name | replace("|", "\\|") }}
{%- else %}
- {{ member.name | replace("|", "\\|") }}（发言数 {{ member.msg_count }}, 综合分 {{ "%.1f"|format(member.activity_score) }}）
{%- endif %}
{%- endfor %}
{%- else %}
- 本期无低质成员
{%- endfor %}
