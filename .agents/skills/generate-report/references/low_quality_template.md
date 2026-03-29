**统计周期**: {{ period_start }} ~ {{ period_end }}

# 计算口径
综合分 = 100 × (0.6 × 发言活跃度百分位 + 0.4 × 质量分归一化值)
发言活跃度百分位 = 成员发言数量在全体成员中的相对位置（0-1）
质量分归一化值 = 由 AI 结合发言上下文、信息密度、持续输出情况和实际价值进行综合评分（0-1）

{%- for group in low_quality_groups %}
## {{ group.title }}（{{ group.count }}人）

{%- for member in group.members %}
{%- if group.status == "zero_activity" %}
- {{ member.name | replace("|", "\\|") }}
{%- else %}
- {{ member.name | replace("|", "\\|") }}（综合分 {{ "%.1f"|format(member.activity_score) }}）
{%- endif %}
{%- endfor %}
{%- else %}
- 本期无低质成员
{%- endfor %}
