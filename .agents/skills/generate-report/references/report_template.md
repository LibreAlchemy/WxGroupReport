# 麦田精选

**期号**：第 {{ report_number }} 期
**统计周期**：{{ period_start }} ~ {{ period_end }}

# 数据统计

**总成员数**：{{ total_members }}
**活跃成员数**：{{ active_members }}
**精彩内容数**：{{ highlights_count }}

# 本期排行

| 排名 | 成员 | 综合分 |
|------|------|--------|
{%- for member in top_members %}
| {{ loop.index }} | {{ member.name | replace("|", "\\|") }} | {{ "%.1f"|format(member.activity_score) }} |
{%- else %}
| - | 暂无 | 0.0 |
{%- endfor %}

# 本期看点
{% if articles %}
## 🤩 精选分享
{%- for item in articles %}
{%- if item.url %}
- [{{ item.title }}]({{ item.url }}) @{{ item.author | replace("|", "\\|") }}
{%- else %}
- 《{{ item.title }}》 @{{ item.author | replace("|", "\\|") }}
{%- endif %}
{%- endfor %}
{% endif %}
{% if github_items %}
## 💻 开源项目
{%- for item in github_items %}
- [{{ item.repo }}]({{ item.url }}) @{{ item.author | replace("|", "\\|") }}
{%- endfor %}
{% endif %}
{% if insights %}
## 💡 原创心得
{%- for item in insights %}
- "{{ item.content }}" — @{{ item.author | replace("|", "\\|") }}
{%- endfor %}
{% endif %}
