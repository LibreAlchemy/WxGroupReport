**统计周期**: {{ period_start }} ~ {{ period_end }}

# 计算口径
综合分 = {{ activity_score_count_weight }} × 发言分 + {{ activity_score_quality_weight }} × 质量分
发言分 = min(100, 成员发言数量 / P75 × 100)
质量分 = 由 AI 结合发言上下文、信息密度、持续输出情况和实际价值进行评分

注：P75 值表示有 25% 成员的发言数量大于等于该值。成员发言数大于等于该值时，发言分记为 100。
注：本期 P75 = {{ p75_msg_count }}

{%- for group in score_groups %}
## {{ group.title }}（{{ group.count }}人）

{%- for member in group.members %}
{%- if group.status == "zero_activity" %}
- {{ member.name | replace("|", "\\|") }}{% if member.summary %}：{{ member.summary }}{% endif %}
{%- else %}
- {{ member.name | replace("|", "\\|") }}（综合分 {{ "%.1f"|format(member.activity_score) }}）{% if member.summary %}：{{ member.summary }}{% endif %}
{%- endif %}
{%- endfor %}
{%- else %}
- 本期无低质成员
{%- endfor %}
