# 群聊周期报告 - {{ group_name }}

**统计周期**: {{ period_start }} ~ {{ period_end }}
**生成时间**: {{ generated_at }}
**报告期号**: 第 {{ report_number }} 期

---

## 数据概览

| 指标 | 数值 |
|------|------|
| 总成员数 | {{ total_members }} |
| 活跃成员数 | {{ active_members }} |
| 低质成员数 | {{ low_quality_count }} |
| 精彩内容数 | {{ highlights_count }} |

---

## 活跃度排行榜 (Top10)

| 排名 | 成员 | 发言数 | 平均分 |
|------|------|--------|--------|
{%- for member in top_members %}
| {{ loop.index }} | {{ member.name | replace("|", "\\|") }} | {{ member.msg_count }} | {{ "%.1f"|format(member.avg_score) }} |
{%- else %}
| - | 暂无 | 0 | 0.0 |
{%- endfor %}

## 本期精彩内容
{% if articles %}
### 公众号/技术文章
{%- for item in articles[:3] %}
- [{{ item.content[:50] }}]({{ item.url }}) @{{ item.author | replace("|", "\\|") }}
{%- endfor %}
{% endif %}
{% if github_items %}
### Github 项目
{%- for item in github_items[:3] %}
- [{{ item.content[:50] }}]({{ item.url }}) @{{ item.author | replace("|", "\\|") }}
{%- endfor %}
{% endif %}
{% if insights %}
### 原创见解
{%- for item in insights[:3] %}
- "{{ item.content[:80] }}" — @{{ item.author | replace("|", "\\|") }}
{%- endfor %}
{% endif %}
{% if opportunities %}
### 机会分享
{%- for item in opportunities[:3] %}
- {{ item.content[:80] }} — @{{ item.author | replace("|", "\\|") }}
{%- endfor %}
{% endif %}

---

## 低质成员名单

{%- for member in low_quality_members %}
### {{ loop.index }}. {{ member.name | replace("|", "\\|") }}
- **发言数**: {{ member.msg_count }}
- **平均分**: {{ "%.1f"|format(member.avg_score) }}
- **原因**: {{ member.reason }}

---
{%- else %}
- 本期无低质成员
{%- endfor %}

## 附录

### 评分维度 (7维度，各1-5分)
| 维度 | 说明 |
|------|------|
| technical | 技术分享 |
| resource | 资源分享 |
| qa | 解答问题 |
| discussion | 深度讨论 |
| insight | 原创观点 |
| opportunity | 机会分享 |
| reply | 互动回复 |

### 低质判定规则
- **零发言**: 周期内无任何有效消息 (严重)
- **低质量**: 平均分 < 15 分 (中等)
- **低频次**: 发言数 < 5 条 (轻微)

---
*报告由群聊分析工具自动生成*
