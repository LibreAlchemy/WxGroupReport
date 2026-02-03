---
type: API文档
stage: active
feature: <功能名称>
version: "1.0"

owner: <作者>
created: <YYYY-MM-DD>
updated: <YYYY-MM-DD>
---

# API: <模块名称>

## 概述

**Base URL**: `/api/v1`

**认证方式**: Bearer Token / API Key / 无

---

## 接口列表

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/resource` | 获取列表 |
| POST | `/resource` | 创建资源 |
| GET | `/resource/{id}` | 获取详情 |
| PUT | `/resource/{id}` | 更新资源 |
| DELETE | `/resource/{id}` | 删除资源 |

---

## 接口详情

### GET /resource

**描述**: 获取资源列表

**请求参数**:

| 参数 | 位置 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| page | query | int | 否 | 页码，默认 1 |
| limit | query | int | 否 | 每页数量，默认 20 |

**响应**:

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [],
    "total": 0,
    "page": 1,
    "limit": 20
  }
}
```

**错误码**:

| code | message | 说明 |
|------|---------|------|
| 0 | success | 成功 |
| 400 | bad request | 参数错误 |
| 401 | unauthorized | 未授权 |

---

### POST /resource

**描述**: 创建资源

**请求体**:

```json
{
  "name": "string",
  "description": "string"
}
```

**响应**:

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "id": 1,
    "name": "string",
    "created_at": "2026-02-02T00:00:00Z"
  }
}
```

---

## 通用错误码

| code | message | 说明 |
|------|---------|------|
| 400 | bad request | 请求参数错误 |
| 401 | unauthorized | 未授权 |
| 403 | forbidden | 无权限 |
| 404 | not found | 资源不存在 |
| 500 | internal error | 服务器错误 |

---

## 更新记录

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0 | YYYY-MM-DD | 初始版本 |

---

**最后更新**: <YYYY-MM-DD>
