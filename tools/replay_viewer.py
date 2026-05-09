#!/usr/bin/env python3
"""
任务回放日志查看器

用法:
    python tools/replay_viewer.py logs/replay_task_1.jsonl
    python tools/replay_viewer.py logs/replay_task_1.jsonl --filter MILESTONE
    python tools/replay_viewer.py logs/replay_task_1.jsonl --step 5
"""

import json
import sys
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional


def format_timestamp(timestamp_str: str) -> str:
    """
    格式化时间戳为易读格式
    
    Args:
        timestamp_str: ISO 8601 格式的时间戳字符串
        
    Returns:
        str: 格式化后的时间字符串 (YYYY-MM-DD HH:MM:SS)
    """
    try:
        dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return timestamp_str


def format_target(target: Dict[str, Any]) -> str:
    """
    格式化 target 字段为简洁字符串
    
    Args:
        target: target 字典
        
    Returns:
        str: 格式化后的字符串
    """
    if not target:
        return ""
    
    parts = []
    if "element_id" in target:
        parts.append(f"element_id={target['element_id']}")
    if "url" in target:
        parts.append(f"url={target['url']}")
    if "selector" in target:
        parts.append(f"selector={target['selector']}")
    
    return " → " + ", ".join(parts) if parts else ""


def format_state_summary(task_state: Dict[str, Any]) -> str:
    """
    格式化任务状态摘要
    
    Args:
        task_state: task_state_snapshot 字典
        
    Returns:
        str: 格式化后的状态摘要
    """
    sub_goals = task_state.get("sub_goals", [])
    milestones = task_state.get("milestones", [])
    blockers = task_state.get("blockers", [])
    
    # 统计完成的子目标数量
    completed_count = sum(1 for sg in sub_goals if sg.get("status") == "completed")
    total_count = len(sub_goals)
    
    parts = []
    
    # 子目标进度
    if total_count > 0:
        parts.append(f"子目标 {completed_count}/{total_count} 完成")
    
    # 里程碑
    if milestones:
        milestone_str = ", ".join(f"'{m}'" for m in milestones)
        parts.append(f"里程碑: [{milestone_str}]")
    
    # 阻塞项
    if blockers:
        blocker_str = ", ".join(f"'{b}'" for b in blockers)
        parts.append(f"阻塞: [{blocker_str}]")
    
    return ", ".join(parts) if parts else "无状态更新"


def print_log_entry(entry: Dict[str, Any]) -> None:
    """
    打印单条日志记录
    
    Args:
        entry: 日志记录字典
    """
    # 分隔线
    print("─" * 60)
    
    # 第一行：步骤、时间、标签
    step = entry.get("step", "?")
    timestamp = format_timestamp(entry.get("timestamp", ""))
    tag = entry.get("tag", "NORMAL")
    print(f"Step {step} | {timestamp} | {tag}")
    
    # 第二行：动作和目标
    action = entry.get("action", "unknown")
    target = entry.get("target", {})
    target_str = format_target(target)
    print(f"Action : {action}{target_str}")
    
    # 第三行：结果
    result_success = entry.get("result_success", False)
    result_message = entry.get("result_message", "")
    success_icon = "✓" if result_success else "✗"
    print(f"Result : {success_icon} {result_message}")
    
    # 第四行：URL
    url = entry.get("url", "")
    if url:
        print(f"URL    : {url}")
    
    # 第五行：任务状态
    task_state = entry.get("task_state_snapshot", {})
    if task_state:
        state_summary = format_state_summary(task_state)
        print(f"State  : {state_summary}")
    
    print("─" * 60)
    print()


def load_replay_log(log_file: Path) -> List[Dict[str, Any]]:
    """
    加载回放日志文件
    
    Args:
        log_file: 日志文件路径
        
    Returns:
        List[Dict[str, Any]]: 日志记录列表
    """
    entries = []
    
    if not log_file.exists():
        print(f"错误: 日志文件不存在: {log_file}")
        sys.exit(1)
    
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                
                try:
                    entry = json.loads(line)
                    entries.append(entry)
                except json.JSONDecodeError as e:
                    print(f"警告: 第 {line_num} 行 JSON 解析失败: {e}")
                    continue
    except Exception as e:
        print(f"错误: 读取日志文件失败: {e}")
        sys.exit(1)
    
    return entries


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="任务回放日志查看器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python tools/replay_viewer.py logs/replay_task_1.jsonl
  python tools/replay_viewer.py logs/replay_task_1.jsonl --filter MILESTONE
  python tools/replay_viewer.py logs/replay_task_1.jsonl --step 5
        """
    )
    
    parser.add_argument(
        "log_file",
        type=str,
        help="回放日志文件路径 (例如: logs/replay_task_1.jsonl)"
    )
    
    parser.add_argument(
        "--filter",
        type=str,
        choices=["MILESTONE", "ERROR", "NORMAL"],
        help="只显示指定标签的步骤"
    )
    
    parser.add_argument(
        "--step",
        type=int,
        help="跳转到指定步骤"
    )
    
    args = parser.parse_args()
    
    # 加载日志文件
    log_file = Path(args.log_file)
    entries = load_replay_log(log_file)
    
    if not entries:
        print("日志文件为空")
        return
    
    print(f"\n加载了 {len(entries)} 条日志记录\n")
    
    # 应用过滤器
    if args.filter:
        entries = [e for e in entries if e.get("tag") == args.filter]
        print(f"过滤后剩余 {len(entries)} 条记录 (tag={args.filter})\n")
    
    # 跳转到指定步骤
    if args.step is not None:
        entries = [e for e in entries if e.get("step") >= args.step]
        print(f"从步骤 {args.step} 开始显示\n")
    
    # 打印所有记录
    for entry in entries:
        print_log_entry(entry)
    
    print(f"共显示 {len(entries)} 条记录")


if __name__ == "__main__":
    main()
