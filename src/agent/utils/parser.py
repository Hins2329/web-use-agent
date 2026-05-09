"""
LLM 响应通用解析器

功能：
- 解析任何形式的 LLM 响应（API 原始文本、Markdown 代码块、纯 JSON 等）
- 提取标准的 JSON 结构
- 返回统一的 Dict 格式，包含 thought, action, target, input 等字段
- 支持容错和兜底处理

核心设计原则：
1. 入口函数必须始终返回 Dict[str, Any]，绝不返回字符串
2. 如果解析失败，返回安全的默认值
3. 支持 Markdown ```json``` 代码块格式
4. 支持纯 JSON 格式
5. 支持不完整的 JSON（尽量提取现有字段）
"""

import json
import re
from typing import Dict, Any, Optional


def normalize_llm_response(response: Any) -> Dict[str, Any]:
    """
    LLM 响应标准化统一入口。

    支持字符串响应和字典响应，始终返回标准 Dict。
    """
    if isinstance(response, dict):
        return _normalize_response(response.copy())

    if isinstance(response, str):
        return parse_llm_response(response)

    return _default_response(f"解析异常：不支持的响应类型 {type(response).__name__}")


def parse_llm_response(response_text: str) -> Dict[str, Any]:
    """
    解析 LLM 响应，返回标准格式的 Dict
    
    Args:
        response_text: 来自 LLM 的响应文本
                      可能是纯 JSON、Markdown 代码块、或混合文本
    
    Returns:
        Dict[str, Any]: 标准响应格式，至少包含：
            - thought: 推理过程 (str)
            - action: 动作代码 (str, 如 "click", "input", "human_intervene")
            - target: 目标元素 (str, 可选)
            - input: 输入参数 (Dict[str, Any], 可选)
            - confidence: 置信度 (float, 0.0-1.0)
    
    Raises:
        不会抛出异常，所有错误都返回兜底字典
    
    示例：
        1. 纯 JSON：
           {"thought": "点击登录", "action": "click", "target": "login_btn"}
        
        2. Markdown 代码块：
           ```json
           {
             "thought": "填写用户名",
             "action": "input",
             "target": "username_field",
             "input": {"text": "user@example.com"}
           }
           ```
        
        3. 纯文本中的 JSON：
           让我执行点击操作：
           {
             "thought": "...",
             "action": "click"
           }
    """
    
    # 处理 None 或空字符串
    if not response_text or not isinstance(response_text, str):
        return _default_response("解析异常：响应为空或非字符串")
    
    # 步骤 1: 尝试从 Markdown 代码块中提取 JSON
    json_dict = _extract_from_markdown(response_text)
    if json_dict:
        return json_dict
    
    # 步骤 2: 尝试直接解析为 JSON
    json_dict = _extract_json(response_text)
    if json_dict:
        return json_dict
    
    # 步骤 3: 尝试从文本中查找 JSON 对象
    json_dict = _find_json_in_text(response_text)
    if json_dict:
        return json_dict
    
    # 步骤 4: 都失败了，返回兜底响应
    return _default_response(f"无法解析响应，原文：{response_text[:200]}...")


def _extract_from_markdown(text: str) -> Optional[Dict[str, Any]]:
    """
    从 Markdown 代码块中提取 JSON
    
    支持：
    ```json
    {...}
    ```
    
    或
    ```
    {...}
    ```
    """
    patterns = [
        r'```json\s*([\s\S]*?)```',  # ```json ... ```
        r'`{3,}\s*([\s\S]*?)`{3,}',   # ``` ... ```
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            json_text = match.group(1).strip()
            try:
                return _normalize_response(json.loads(json_text))
            except (json.JSONDecodeError, ValueError):
                continue
    
    return None


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """
    直接尝试将整个文本解析为 JSON
    """
    try:
        result = json.loads(text.strip())
        if isinstance(result, dict):
            return _normalize_response(result)
    except (json.JSONDecodeError, ValueError):
        pass
    
    return None


def _find_json_in_text(text: str) -> Optional[Dict[str, Any]]:
    """
    在文本中寻找 JSON 对象
    
    策略：
    1. 从第一个 { 到最后一个 } 之间的内容
    2. 尝试解析所有可能的 JSON 对象（防止 JSON 中包含其他 { }）
    """
    # 找到第一个和最后一个大括号
    first_brace = text.find('{')
    last_brace = text.rfind('}')
    
    if first_brace == -1 or last_brace == -1 or first_brace >= last_brace:
        return None
    
    # 提取可能的 JSON 部分
    potential_json = text[first_brace:last_brace + 1]
    
    # 尝试解析
    try:
        result = json.loads(potential_json)
        if isinstance(result, dict):
            return _normalize_response(result)
    except (json.JSONDecodeError, ValueError):
        pass
    
    # 如果完整解析失败，尝试修复常见的 JSON 错误
    try:
        # 移除尾部的逗号
        fixed = re.sub(r',\s*}', '}', potential_json)
        fixed = re.sub(r',\s*]', ']', fixed)
        
        result = json.loads(fixed)
        if isinstance(result, dict):
            return _normalize_response(result)
    except (json.JSONDecodeError, ValueError):
        pass
    
    return None


def _normalize_response(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    规范化响应格式 - 强制单层扁平结构，禁止嵌套
    
    确保返回的字典包含标准字段（严格遵循 PROTOCOL.md）：
    - thought: 推理过程 (default: "")
    - action: 动作代码 (default: "wait")  【字符串，严禁字典】
    - target: 目标元素 (default: {})      【字典，严禁字符串】
    - input: 输入参数 (default: {})       【字典，严禁字符串】
    - options: 可选配置 (default: {})     【字典】
    
    关键：处理 LLM 可能返回的嵌套或错误格式，自动拍平和转换。
    """
    
    # 【第一步】处理嵌套 action：{"action": {"action": "click", ...}} → {"action": "click", ...}
    action_value = data.get("action", "wait")
    
    # 如果 action 是字典（嵌套格式），拍平
    if isinstance(action_value, dict):
        flattened = action_value.copy()  # 从嵌套的字典中复制所有字段
        
        # 重新合并所有字段
        for key, val in flattened.items():
            if key not in data or data[key] == action_value:
                # 只在 data 中不存在或原本指向嵌套字典时，才用拍平后的值
                data[key] = val
        
        # 重新获取 action 值
        action_value = flattened.get("action", "wait")
    
    # 【第二步】确保 action 是字符串
    if not isinstance(action_value, str):
        action_value = str(action_value) if action_value else "wait"
    
    # 【第三步】处理 target，确保它是字典
    target_data = data.get("target", {})
    
    # 如果 target 是字符串（错误格式），转为字典
    if isinstance(target_data, str):
        # 把字符串作为 element_id
        target_data = {"element_id": target_data} if target_data else {}
    # 如果 target 根本不是字典（可能是其他类型），转为空字典
    elif not isinstance(target_data, dict):
        target_data = {}
    
    # 【第四步】处理 input，确保它是字典
    input_data = data.get("input", {})
    
    # 如果 input 是字符串（错误格式），尝试转为字典
    if isinstance(input_data, str):
        # 如果是字符串，可能是想表示 text 字段
        input_data = {"text": input_data} if input_data else {}
    # 如果 input 根本不是字典，转为空字典
    elif not isinstance(input_data, dict):
        input_data = {}
    
    # 【第五步】处理 options，确保它是字典
    options_data = data.get("options", {})
    
    # 如果 options 不是字典，转为空字典
    if not isinstance(options_data, dict):
        options_data = {}
    
    # 【第六步】构建标准格式的响应
    normalized = {
        "thought": str(data.get("thought", "")),
        "action": action_value.lower(),  # 统一小写
        "target": target_data,
        "input": input_data,
        "options": options_data,
        "confidence": float(data.get("confidence", 0.5)),
    }
    
    # 确保 confidence 在 0-1 之间
    if not 0.0 <= normalized["confidence"] <= 1.0:
        normalized["confidence"] = 0.5
    
    # 【第七步】保留原始响应中的其他字段（但不覆盖标准字段）
    for key, value in data.items():
        if key not in normalized:
            normalized[key] = value
    
    # 【日志】如果发生了格式转换，记录一下
    if isinstance(action_value, dict) or isinstance(target_data, str) or isinstance(input_data, str):
        import logging
        logger = logging.getLogger(__name__)
        logger.debug(f"✓ Parser 格式规范化完成：检测到非标准格式并已自动转换")
    
    return normalized


def _default_response(reason: str = "解析异常") -> Dict[str, Any]:
    """
    返回安全的默认响应
    
    当所有解析都失败时，返回这个默认值
    这保证了下游代码不会遇到类型错误
    """
    return {
        "thought": reason,
        "action": "wait",
        "target": {},
        "input": {"delay": 1000},
        "options": {},
        "confidence": 0.0,
        "error": True,
        "raw_response": reason,
    }


def validate_action(action: str) -> bool:
    """
    验证 action 是否为有效的动作代码
    
    支持的动作：
    - click: 点击元素
    - input: 输入文本
    - scroll: 滚动页面
    - wait: 等待
    - done: 任务完成
    - human_intervene: 人工接管
    """
    valid_actions = {
        "click",
        "input",
        "scroll",
        "wait",
        "done",
        "human_intervene",
        "navigate",
        "hover",
        "select",
        "submit",
    }
    return action in valid_actions


# 使用示例
if __name__ == "__main__":
    # 测试 1: 纯 JSON
    test1 = '{"thought": "点击按钮", "action": "click", "target": "btn_login"}'
    print("测试 1 (纯 JSON):", parse_llm_response(test1))
    
    # 测试 2: Markdown 代码块
    test2 = '''
    让我执行这个操作：
    ```json
    {
      "thought": "填写用户名",
      "action": "input",
      "target": "username",
      "input": {"text": "demo@example.com"}
    }
    ```
    '''
    print("测试 2 (Markdown):", parse_llm_response(test2))
    
    # 测试 3: 混合文本
    test3 = '''
    我需要执行登录操作
    {
      "thought": "点击登录按钮没有反应，尝试人工操作",
      "action": "human_intervene",
      "target": "login_area"
    }
    随后继续
    '''
    print("测试 3 (混合文本):", parse_llm_response(test3))
    
    # 测试 4: 无效输入
    test4 = "这不是 JSON"
    print("测试 4 (无效输入):", parse_llm_response(test4))
    
    # 测试 5: 空字符串
    test5 = ""
    print("测试 5 (空字符串):", parse_llm_response(test5))
