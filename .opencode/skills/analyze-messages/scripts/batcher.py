"""
负载均衡分批器
"""

from typing import List, Dict, Any


def balance_members(
    members: List[Dict[str, Any]], num_buckets: int = 5
) -> List[List[Dict[str, Any]]]:
    """
    按消息数量均衡分配成员到多个桶

    策略: 按消息数量降序排序后，轮询分配到各桶
    """
    sorted_members = sorted(
        members, key=lambda m: len(m.get("messages", 0)), reverse=True
    )

    buckets = [[] for _ in range(num_buckets)]
    bucket_sizes = [0] * num_buckets

    for member in sorted_members:
        min_bucket = bucket_sizes.index(min(bucket_sizes))
        buckets[min_bucket].append(member)
        bucket_sizes[min_bucket] += len(member.get("messages", []))

    return buckets


def create_batches(
    messages: List[Dict[str, Any]], batch_size: int = 100
) -> List[List[Dict[str, Any]]]:
    """将消息列表分批，每批最多 batch_size 条"""
    batches = []
    for i in range(0, len(messages), batch_size):
        batches.append(messages[i : i + batch_size])
    return batches


def split_member_messages(
    member: Dict[str, Any], batch_size: int = 100
) -> List[Dict[str, Any]]:
    """
    将成员消息拆分为多个批次

    返回: [{"wxid": "...", "nickname": "...", "messages": [...]}]
    """
    messages = member.get("messages", [])
    batches = create_batches(messages, batch_size)

    return [
        {
            "wxid": member["wxid"],
            "nickname": member.get("nickname", ""),
            "messages": batch,
            "batch_index": i,
            "total_batches": len(batches),
        }
        for i, batch in enumerate(batches)
    ]
