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

---

## 本期精彩内容

### 公众号/技术文章
{%- for item in articles %}
- [{{ item.title }}]({{ item.url }}) @{{ item.author | replace("|", "\\|") }}
{%- else %}
- 暂无
{%- endfor %}

### Github 项目
{%- for item in github_items %}
- [{{ item.repo }}]({{ item.url }}) @{{ item.author | replace("|", "\\|") }}
{%- else %}
- 暂无
{%- endfor %}

### 原创见解
{%- for item in insights %}
- "{{ item.content }}" — @{{ item.author | replace("|", "\\|") }}
{%- else %}
- 暂无
{%- endfor %}

### 机会分享
{%- for item in opportunities %}
- {{ item.summary }} — @{{ item.author | replace("|", "\\|") }}
{%- else %}
- 暂无
{%- endfor %}

---

## 低质成员名单

{%- for member in low_quality_members %}
### {{ loop.index }}. {{ member.name | replace("|", "\\|") }}
- **发言数**: {{ member.msg_count }}
- **平均分**: {{ "%.1f"|format(member.avg_score) }}
- **原因**: {{ member.reason }}
- **严重程度**: {{ member.severity_label }}

---
{%- else %}
- 本期无低质成员
{%- endfor %}

## 附录

### 低质判定规则
- **零发言**: 周期内无任何有效消息
- **低质量**: 平均分 < 60 分
- **低频次**: 发言数 < 5 条

---
*报告由群聊分析工具自动生成*
