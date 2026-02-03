# 群聊分析工具 - 文档中心

> 📅 创建日期: 2026-02-02  
> 🎯 本文档为 AI Agent 导航入口

---

## 📁 文档结构

```
docs/
├── 00-业务需求/     → BRD (业务方)
├── 01-产品设计/     → PRD (@莫)
├── 02-技术设计/     → TDD/系分 (@Kyle)
├── 03-测试分析/     → TAD (@seasyec)
├── 04-项目管理/     → 排期 (@Napstablook)
├── 05-评审记录/     → 评审结论
├── 06-开发文档/     → API、技术实现
├── templates/       → 文档模板
└── 归档/            → 过期文档
```

---

## 🔄 当前状态

| 文档类型 | 状态 | 负责人 | 路径 |
|----------|------|--------|------|
| BRD | draft | 业务方 | [BRD_群聊分析工具](./00-业务需求/BRD_群聊分析工具_2026-02-02.md) |
| PRD | 待创建 | @莫 | - |
| TDD | 待创建 | @Kyle | - |
| TAD | 待创建 | @seasyec | - |
| 排期 | 待创建 | @Napstablook | - |

---

## 👥 团队分工

| 角色 | 人员 | 职责 | 交付物 |
|------|------|------|--------|
| 业务方 | (你) | 提需求、定时间 | BRD |
| 产品 | @莫 | 需求转化、评审组织 | PRD |
| 技术负责人 | @Kyle | 技术方案、工作量评估 | TDD(系分) |
| 开发 | @Kyle @七里香 | 代码实现 | 软件 |
| QA | @seasyec | 测试分析、验收 | TAD |
| PM | @Napstablook | 排期、进度跟踪 | 排期计划 |

---

## 📋 工作流

```
BRD(draft) → BRD(review) → BRD(approved)
                              ↓
PRD(draft) → PRD(review) → PRD(approved)
                              ↓
              ┌───────────────┴───────────────┐
              ↓                               ↓
TDD(draft) → TDD(review) → TDD(approved)    TAD(draft)
              ↓
         排期(approved)
              ↓
         开发执行
              ↓
         测试验收
              ↓
           上线
```

---

## 🤖 Agent 指令

### 查找下一步工作

```
1. 读取本文件获取当前状态
2. 找到 stage=approved 的最新文档
3. 检查其 blocks 字段，创建下游文档
```

### 创建新文档

```
1. 确认上游文档 stage=approved
2. 从 templates/ 选择对应模板
3. 填充 depends_on 和元数据
4. 通知 owner
```

---

## 🔗 快速链接

- [文档格式规范](./通用文档格式规范.md)
- [BRD 模板](./templates/BRD_模板.md)
- [PRD 模板](./templates/PRD_模板.md)
- [TDD 模板](./templates/TDD_系分_模板.md)
- [TAD 模板](./templates/TAD_测试分析_模板.md)
- [排期模板](./templates/SCHEDULE_排期_模板.md)
- [评审记录模板](./templates/REVIEW_评审记录_模板.md)

---

**最后更新**: 2026-02-02
