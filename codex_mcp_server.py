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
import logging
import signal
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

# 配置日志系统
logging.basicConfig(
    filename='/tmp/codex_mcp_debug.log',
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - [%(funcName)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logging.info("=== Codex MCP Server Starting ===")

# 任务存储目录
TASK_DIR = Path("/tmp/codex_tasks")
TASK_DIR.mkdir(exist_ok=True)

# ============================================
# 僵尸进程自动回收机制
# ============================================
def sigchld_handler(signum, frame):
    """
    SIGCHLD 信号处理器：自动回收已终止的子进程，防止僵尸进程累积

    当子进程终止时，内核会向父进程发送 SIGCHLD 信号。
    这个处理器会被自动调用，通过 os.waitpid() 回收所有已终止的子进程。
    """
    while True:
        try:
            # os.waitpid(-1, os.WNOHANG):
            #   -1: 等待任意子进程
            #   os.WNOHANG: 非阻塞模式，如果没有已终止的子进程立即返回 (0, 0)
            pid, status = os.waitpid(-1, os.WNOHANG)

            if pid == 0:
                # 没有更多已终止的子进程
                break

            # 记录回收信息
            exit_code = os.WEXITSTATUS(status) if os.WIFEXITED(status) else -1
            logging.debug(f"Reaped child process PID {pid}, exit_code={exit_code}, status={status}")

        except ChildProcessError:
            # 没有子进程了
            break
        except Exception as e:
            # 处理其他异常（不应该发生，但保险起见）
            logging.warning(f"Error in SIGCHLD handler: {e}")
            break

# 注册 SIGCHLD 信号处理器
signal.signal(signal.SIGCHLD, sigchld_handler)
logging.info("SIGCHLD handler registered for automatic zombie process reaping")

def safe_read_file(file_path: Path) -> str:
    """安全地读取文件，处理各种编码和异常问题"""
    if not file_path.exists():
        logging.debug(f"File {file_path} does not exist")
        return ""

    try:
        # 优先尝试严格的 UTF-8 读取
        content = file_path.read_text(encoding='utf-8')
        logging.debug(f"Successfully read {file_path} with UTF-8 encoding ({len(content)} chars)")
        return content
    except UnicodeDecodeError as e:
        # 降级为 replace 模式
        logging.warning(f"UTF-8 decode error for {file_path}: {e}, using replace mode")
        try:
            content = file_path.read_text(encoding='utf-8', errors='replace')
            logging.debug(f"Read {file_path} with replace mode ({len(content)} chars)")
            return content
        except Exception as e2:
            logging.error(f"Failed to read {file_path} even with replace mode: {e2}")
            return f"[Error reading file: {e2}]"
    except PermissionError as e:
        logging.error(f"Permission denied reading {file_path}: {e}")
        return f"[Permission denied: {e}]"
    except Exception as e:
        logging.error(f"Unexpected error reading {file_path}: {e}")
        return f"[Unexpected error: {e}]"

def is_process_alive(pid: int) -> bool:
    """检测进程是否还在运行（排除僵尸进程）"""
    if pid is None:
        return False

    try:
        # 发送信号 0 检测进程是否存在
        os.kill(pid, 0)

        # 进程存在，但需要检查是否为僵尸进程
        try:
            # 使用 ps 命令检查进程状态
            result = subprocess.run(
                ['ps', '-p', str(pid), '-o', 'stat='],
                stdin=subprocess.DEVNULL,  # 避免从父进程 stdin 读取
                capture_output=True,
                text=True,
                timeout=1
            )
            if result.returncode == 0:
                stat = result.stdout.strip()
                # 如果状态以 'Z' 开头，说明是僵尸进程
                if stat.startswith('Z'):
                    logging.debug(f"PID {pid} is a zombie process")
                    return False
                return True
            else:
                # ps 命令失败，进程可能已经不存在
                return False
        except Exception as e:
            logging.warning(f"Failed to check process state for PID {pid}: {e}")
            # 如果无法检查状态，保守地认为进程还活着
            return True

    except ProcessLookupError:
        # 进程不存在
        return False
    except PermissionError:
        # 进程存在但没有权限，假设它还活着
        return True
    except Exception as e:
        logging.warning(f"Unexpected error checking PID {pid}: {e}")
        return False

def send_response(response: Dict[str, Any]) -> None:
    """发送JSON-RPC响应到stdout"""
    try:
        # 添加 ensure_ascii=False 支持中文
        output = json.dumps(response, ensure_ascii=False)
        print(output, flush=True)
        logging.debug(f"Sent response: id={response.get('id')}, size={len(output)} bytes")
    except (TypeError, ValueError) as e:
        # 序列化失败，返回错误响应
        logging.error(f"Failed to serialize response: {e}, response={response}")
        error_response = {
            'jsonrpc': '2.0',
            'id': response.get('id'),
            'error': {
                'code': -32603,
                'message': f'Response serialization failed: {str(e)}'
            }
        }
        print(json.dumps(error_response), flush=True)

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

    logging.info(f"Starting async task {task_id}: subcommand={subcommand}, prompt={prompt[:50] if prompt else 'N/A'}...")

    # 构建命令
    cmd = ['codex', subcommand]
    if prompt:
        cmd.append(prompt)
    cmd.extend(args)
    # 添加 --skip-git-repo-check 避免在非 git 目录下运行失败
    if '--skip-git-repo-check' not in cmd:
        cmd.append('--skip-git-repo-check')

    # 创建任务文件
    stdout_file = task_path.with_suffix('.stdout')
    stderr_file = task_path.with_suffix('.stderr')

    # 启动后台进程
    try:
        with open(stdout_file, 'w') as stdout_f, open(stderr_file, 'w') as stderr_f:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,  # 重定向 stdin 到 /dev/null，避免子进程竞争读取父进程的 stdin
                stdout=stdout_f,
                stderr=stderr_f,
                text=True,
                start_new_session=True  # 创建新session，脱离父进程
            )

        logging.info(f"Task {task_id} started with PID {proc.pid}")

        # 保存任务元数据（包含 PID）
        metadata = {
            'task_id': task_id,
            'pid': proc.pid,
            'status': 'running',
            'command': ' '.join(cmd),
            'started_at': time.time()
        }

        with open(task_path.with_suffix('.meta'), 'w') as f:
            json.dump(metadata, f, indent=2)

        logging.debug(f"Task {task_id} metadata saved")

        return task_id

    except Exception as e:
        logging.error(f"Failed to start async task {task_id}: {e}\n{traceback.format_exc()}")
        raise

def check_task_status(task_id: str) -> Dict[str, Any]:
    """检查任务状态并返回结果"""
    logging.debug(f"Checking status for task {task_id}")
    task_path = TASK_DIR / task_id
    meta_file = task_path.with_suffix('.meta')

    if not meta_file.exists():
        logging.warning(f"Task {task_id} not found")
        return {
            'status': 'not_found',
            'error': f'Task {task_id} not found'
        }

    # 读取元数据（带异常处理）
    try:
        with open(meta_file, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        logging.debug(f"Task {task_id} metadata loaded: PID={metadata.get('pid')}")
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logging.error(f"Invalid metadata for task {task_id}: {e}")
        return {
            'status': 'error',
            'error': f'Invalid metadata: {str(e)}'
        }
    except Exception as e:
        logging.error(f"Failed to read metadata for task {task_id}: {e}")
        return {
            'status': 'error',
            'error': f'Failed to read metadata: {str(e)}'
        }

    pid = metadata.get('pid')

    # 检查进程是否还在运行（混合检测）
    stdout_file = task_path.with_suffix('.stdout')
    stderr_file = task_path.with_suffix('.stderr')

    # 1. 优先检测 PID 是否存活
    process_alive = is_process_alive(pid)

    # 2. 检查文件修改时间
    is_running = False
    if stdout_file.exists() or stderr_file.exists():
        latest_mtime = max(
            stdout_file.stat().st_mtime if stdout_file.exists() else 0,
            stderr_file.stat().st_mtime if stderr_file.exists() else 0
        )
        idle_time = time.time() - latest_mtime
        logging.debug(f"Task {task_id} idle time: {idle_time:.1f}s, process_alive={process_alive}")

        # 混合判断：进程存活 AND 最近有输出（或刚启动）
        if process_alive:
            if idle_time < 10:
                is_running = True
            else:
                # 进程存活但长时间无输出，仍认为在运行（可能是长耗时任务）
                is_running = True
        else:
            # 进程已退出
            is_running = False
    else:
        # 文件不存在，但进程可能刚启动
        is_running = process_alive

    if is_running:
        elapsed = time.time() - metadata['started_at']
        logging.debug(f"Task {task_id} is still running, elapsed={elapsed:.1f}s")
        return {
            'status': 'running',
            'task_id': task_id,
            'elapsed_seconds': int(elapsed),
            'command': metadata['command']
        }
    else:
        # 任务已完成，读取结果（使用安全读取）
        logging.debug(f"Task {task_id} completed, reading output files")

        try:
            stdout = safe_read_file(stdout_file)
            stderr = safe_read_file(stderr_file)

            result = extract_result_from_codex_output(stdout, stderr)

            # 使用输出文件的修改时间作为完成时间（而不是当前时间！）
            if stdout_file.exists() or stderr_file.exists():
                completed_at = max(
                    stdout_file.stat().st_mtime if stdout_file.exists() else 0,
                    stderr_file.stat().st_mtime if stderr_file.exists() else 0
                )
            else:
                completed_at = time.time()

            # 更新元数据
            metadata['status'] = 'completed'
            metadata['completed_at'] = completed_at
            try:
                with open(meta_file, 'w') as f:
                    json.dump(metadata, f, indent=2)
            except Exception as e:
                logging.warning(f"Failed to update metadata for task {task_id}: {e}")

            logging.info(f"Task {task_id} completed successfully, result length={len(result)}")

            return {
                'status': 'completed',
                'task_id': task_id,
                'result': result,
                'elapsed_seconds': int(completed_at - metadata['started_at'])
            }
        except Exception as e:
            logging.error(f"Failed to read output for task {task_id}: {e}\n{traceback.format_exc()}")
            return {
                'status': 'error',
                'task_id': task_id,
                'error': f'Failed to read output: {str(e)}'
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
    # 添加 --skip-git-repo-check 避免在非 git 目录下运行失败
    if '--skip-git-repo-check' not in cmd:
        cmd.append('--skip-git-repo-check')

    try:
        result = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,  # 避免子进程从父进程的 stdin 读取
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

    elif method == 'notifications/initialized':
        # 这是一个通知，不需要响应（id 为 None）
        logging.debug("Received initialized notification, no response needed")
        # 通知不需要发送响应，直接返回
        return

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
    logging.info("Main loop starting")
    logging.debug(f"stdin closed={sys.stdin.closed}, stdout closed={sys.stdout.closed}")
    request_count = 0
    try:
        for line in sys.stdin:
            request_count += 1
            logging.debug(f"Read line #{request_count}, length={len(line)}")
            line = line.strip()
            if not line:
                logging.debug(f"Empty line, skipping")
                continue

            try:
                request = json.loads(line)
                logging.debug(f"Received request #{request_count}: method={request.get('method')}, id={request.get('id')}")

                # 添加全局异常保护
                try:
                    handle_request(request)
                    logging.debug(f"Request {request.get('id')} handled successfully")
                except Exception as e:
                    # 捕获所有未预料的异常，返回错误而不是崩溃
                    logging.error(f"handle_request failed: {e}\n{traceback.format_exc()}")
                    send_response({
                        'jsonrpc': '2.0',
                        'id': request.get('id'),
                        'error': {
                            'code': -32603,
                            'message': f'Internal server error: {str(e)}'
                        }
                    })

            except json.JSONDecodeError as e:
                logging.warning(f"JSON parse error: {e}")
                send_response({
                    'jsonrpc': '2.0',
                    'id': None,
                    'error': {
                        'code': -32700,
                        'message': f'Parse error: {str(e)}'
                    }
                })

    except KeyboardInterrupt:
        logging.info("Codex MCP Server stopped by user (Ctrl+C)")
    except Exception as e:
        logging.critical(f"Fatal error in main loop: {e}\n{traceback.format_exc()}")
        raise
    finally:
        logging.info(f"=== Codex MCP Server Stopped === (processed {request_count} lines)")
        logging.debug(f"stdin closed={sys.stdin.closed}, stdout closed={sys.stdout.closed}")
        logging.info("Main loop exited normally (EOF on stdin)")

if __name__ == '__main__':
    main()
