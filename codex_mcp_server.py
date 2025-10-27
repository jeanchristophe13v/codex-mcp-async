#!/usr/bin/env python3
"""
Codex MCP Server Wrapper with Async Support
将 OpenAI Codex CLI 封装为符合 MCP 协议的 server，支持异步任务
"""
import sys
import json
import subprocess
import re
import uuid
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# 任务存储目录
TASK_DIR = Path("/tmp/codex_tasks")
TASK_DIR.mkdir(exist_ok=True)

def send_response(response: Dict[str, Any]) -> None:
    """发送JSON-RPC响应到stdout"""
    print(json.dumps(response), flush=True)

def extract_result_from_codex_output(stdout: str, stderr: str) -> str:
    """
    从codex输出中提取核心结果，过滤thinking过程
    策略：只保留最后的codex输出，丢弃thinking和exec日志
    """
    result = stdout.strip()
    if not result and stderr:
        # 如果stdout为空，尝试从stderr提取codex的最终输出
        match = re.search(r'codex\n(.+?)(?:tokens used|\Z)', stderr, re.DOTALL)
        if match:
            result = match.group(1).strip()

    return result if result else "No output from Codex"

def start_codex_async(subcommand: str, prompt: str = None, args: List[str] = None) -> str:
    """
    启动异步Codex任务

    Returns:
        task_id: 任务ID，用于后续查询
    """
    args = args or []
    task_id = str(uuid.uuid4())[:8]
    task_path = TASK_DIR / task_id

    # 构建命令
    cmd = ['codex', subcommand]
    if prompt:
        cmd.append(prompt)
    cmd.extend(args)

    # 创建任务文件
    stdout_file = open(task_path.with_suffix('.stdout'), 'w')
    stderr_file = open(task_path.with_suffix('.stderr'), 'w')

    # 启动后台进程（detached, 避免zombie）
    proc = subprocess.Popen(
        cmd,
        stdout=stdout_file,
        stderr=stderr_file,
        text=True,
        start_new_session=True  # 创建新session，脱离父进程
    )

    # 关闭文件句柄（子进程已经继承）
    stdout_file.close()
    stderr_file.close()

    # 保存任务元数据
    metadata = {
        'task_id': task_id,
        'pid': proc.pid,
        'status': 'running',
        'command': ' '.join(cmd),
        'started_at': time.time()
    }

    with open(task_path.with_suffix('.meta'), 'w') as f:
        json.dump(metadata, f, indent=2)

    return task_id

def check_task_status(task_id: str) -> Dict[str, Any]:
    """检查任务状态并返回结果"""
    task_path = TASK_DIR / task_id
    meta_file = task_path.with_suffix('.meta')

    if not meta_file.exists():
        return {
            'status': 'not_found',
            'error': f'Task {task_id} not found'
        }

    # 读取元数据
    with open(meta_file, 'r') as f:
        metadata = json.load(f)

    pid = metadata['pid']

    # 检查进程是否还在运行
    # 注意：不能只用os.kill，因为僵尸进程仍会返回True
    # 更可靠的方法：检查输出文件的修改时间
    stdout_file = task_path.with_suffix('.stdout')
    stderr_file = task_path.with_suffix('.stderr')

    # 如果文件在过去10秒内没有更新，认为已完成
    is_running = False
    if stdout_file.exists() or stderr_file.exists():
        latest_mtime = max(
            stdout_file.stat().st_mtime if stdout_file.exists() else 0,
            stderr_file.stat().st_mtime if stderr_file.exists() else 0
        )
        idle_time = time.time() - latest_mtime
        is_running = (idle_time < 10)  # 10秒内有更新视为still running

    if is_running:
        # 任务仍在运行
        elapsed = time.time() - metadata['started_at']
        return {
            'status': 'running',
            'task_id': task_id,
            'elapsed_seconds': int(elapsed),
            'command': metadata['command']
        }
    else:
        # 任务已完成，读取结果
        stdout_file = task_path.with_suffix('.stdout')
        stderr_file = task_path.with_suffix('.stderr')

        stdout = stdout_file.read_text() if stdout_file.exists() else ""
        stderr = stderr_file.read_text() if stderr_file.exists() else ""

        result = extract_result_from_codex_output(stdout, stderr)

        # 更新元数据
        metadata['status'] = 'completed'
        metadata['completed_at'] = time.time()
        with open(meta_file, 'w') as f:
            json.dump(metadata, f, indent=2)

        return {
            'status': 'completed',
            'task_id': task_id,
            'result': result,
            'elapsed_seconds': int(metadata.get('completed_at', time.time()) - metadata['started_at'])
        }

def call_codex_sync(subcommand: str, prompt: str = None, args: List[str] = None, timeout: int = None) -> str:
    """
    同步调用codex（保留向后兼容）
    """
    args = args or []
    cmd = ['codex', subcommand]
    if prompt:
        cmd.append(prompt)
    cmd.extend(args)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return extract_result_from_codex_output(result.stdout, result.stderr)
    except subprocess.TimeoutExpired:
        return "Error: Codex execution timed out"
    except Exception as e:
        return f"Error calling Codex: {str(e)}"

def handle_request(request: Dict[str, Any]) -> None:
    """处理MCP请求"""
    method = request.get('method')
    request_id = request.get('id')
    params = request.get('params', {})

    if method == 'initialize':
        send_response({
            'jsonrpc': '2.0',
            'id': request_id,
            'result': {
                'protocolVersion': '2024-11-05',
                'capabilities': {'tools': {}},
                'serverInfo': {
                    'name': 'codex-mcp',
                    'version': '0.2.0'
                }
            }
        })

    elif method == 'tools/list':
        send_response({
            'jsonrpc': '2.0',
            'id': request_id,
            'result': {
                'tools': [
                    {
                        'name': 'codex_execute',
                        'description': 'Execute OpenAI Codex (GPT-5) synchronously with full control over subcommand and arguments. Returns only the core result, filtering out thinking process to save context. Common usage: subcommand="exec", prompt="your task", args=["--full-auto"]',
                        'inputSchema': {
                            'type': 'object',
                            'properties': {
                                'subcommand': {
                                    'type': 'string',
                                    'description': 'Codex subcommand to execute',
                                    'enum': ['exec', 'apply', 'resume', 'sandbox'],
                                    'default': 'exec'
                                },
                                'prompt': {
                                    'type': 'string',
                                    'description': 'Main prompt/argument for the command (required for exec, optional for others)'
                                },
                                'args': {
                                    'type': 'array',
                                    'items': {'type': 'string'},
                                    'description': 'Additional command-line arguments. Model selection: ["-m", "gpt-5-codex"] for coding (default) or ["-m", "gpt-5"] for analysis. Reasoning effort: ["--config", "model_reasoning_effort=low|medium|high"] (gpt-5-codex supports low/medium/high; gpt-5 supports minimal/low/medium/high). Example: ["--full-auto", "-m", "gpt-5", "--config", "model_reasoning_effort=high"]. Always include "--full-auto" for non-interactive execution.'
                                },
                                'timeout': {
                                    'type': 'integer',
                                    'description': 'Timeout in seconds (default: no limit)'
                                }
                            },
                            'required': []
                        }
                    },
                    {
                        'name': 'codex_execute_async',
                        'description': 'Start a Codex task in the background and return immediately with a task_id. Use codex_check_result to retrieve the result later. This allows you to continue working while Codex runs.',
                        'inputSchema': {
                            'type': 'object',
                            'properties': {
                                'subcommand': {
                                    'type': 'string',
                                    'description': 'Codex subcommand to execute',
                                    'enum': ['exec', 'apply', 'resume', 'sandbox'],
                                    'default': 'exec'
                                },
                                'prompt': {
                                    'type': 'string',
                                    'description': 'Main prompt/argument for the command'
                                },
                                'args': {
                                    'type': 'array',
                                    'items': {'type': 'string'},
                                    'description': 'Additional command-line arguments. Model selection: ["-m", "gpt-5-codex"] for coding (default) or ["-m", "gpt-5"] for analysis. Reasoning effort: ["--config", "model_reasoning_effort=low|medium|high"] (gpt-5-codex supports low/medium/high; gpt-5 supports minimal/low/medium/high). Example: ["--full-auto", "-m", "gpt-5", "--config", "model_reasoning_effort=high"]. Always include "--full-auto" for non-interactive execution.'
                                }
                            },
                            'required': []
                        }
                    },
                    {
                        'name': 'codex_check_result',
                        'description': 'Check the status of an async Codex task. Returns running/completed status and the result if available.',
                        'inputSchema': {
                            'type': 'object',
                            'properties': {
                                'task_id': {
                                    'type': 'string',
                                    'description': 'The task_id returned by codex_execute_async'
                                }
                            },
                            'required': ['task_id']
                        }
                    }
                ]
            }
        })

    elif method == 'tools/call':
        tool_name = params.get('name')
        arguments = params.get('arguments', {})

        if tool_name == 'codex_execute':
            # 同步执行
            subcommand = arguments.get('subcommand', 'exec')
            prompt = arguments.get('prompt')
            args = arguments.get('args', [])
            timeout = arguments.get('timeout')

            result = call_codex_sync(
                subcommand=subcommand,
                prompt=prompt,
                args=args,
                timeout=timeout
            )

            send_response({
                'jsonrpc': '2.0',
                'id': request_id,
                'result': {
                    'content': [{'type': 'text', 'text': result}]
                }
            })

        elif tool_name == 'codex_execute_async':
            # 异步启动
            subcommand = arguments.get('subcommand', 'exec')
            prompt = arguments.get('prompt')
            args = arguments.get('args', [])

            task_id = start_codex_async(
                subcommand=subcommand,
                prompt=prompt,
                args=args
            )

            send_response({
                'jsonrpc': '2.0',
                'id': request_id,
                'result': {
                    'content': [{
                        'type': 'text',
                        'text': f'Codex task started in background.\nTask ID: {task_id}\n\nUse codex_check_result(task_id="{task_id}") to retrieve the result.'
                    }]
                }
            })

        elif tool_name == 'codex_check_result':
            # 检查任务状态
            task_id = arguments.get('task_id')

            if not task_id:
                send_response({
                    'jsonrpc': '2.0',
                    'id': request_id,
                    'error': {
                        'code': -32602,
                        'message': 'task_id is required'
                    }
                })
                return

            status_info = check_task_status(task_id)

            # 格式化响应
            if status_info['status'] == 'running':
                text = f"Task {task_id} is still running.\nElapsed: {status_info['elapsed_seconds']}s\nCommand: {status_info['command']}"
            elif status_info['status'] == 'completed':
                text = f"Task {task_id} completed in {status_info['elapsed_seconds']}s.\n\nResult:\n{status_info['result']}"
            else:
                text = status_info.get('error', 'Unknown error')

            send_response({
                'jsonrpc': '2.0',
                'id': request_id,
                'result': {
                    'content': [{'type': 'text', 'text': text}]
                }
            })

        else:
            send_response({
                'jsonrpc': '2.0',
                'id': request_id,
                'error': {
                    'code': -32601,
                    'message': f'Unknown tool: {tool_name}'
                }
            })

    else:
        send_response({
            'jsonrpc': '2.0',
            'id': request_id,
            'error': {
                'code': -32601,
                'message': f'Method not found: {method}'
            }
        })

def main():
    """主循环：从stdin读取请求，处理后写入stdout"""
    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue

            try:
                request = json.loads(line)
                handle_request(request)
            except json.JSONDecodeError as e:
                send_response({
                    'jsonrpc': '2.0',
                    'id': None,
                    'error': {
                        'code': -32700,
                        'message': f'Parse error: {str(e)}'
                    }
                })
    except KeyboardInterrupt:
        pass

if __name__ == '__main__':
    main()
