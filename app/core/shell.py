"""与桌面环境交互：打开资源管理器 / 终端 / VS Code。"""
import os
import shutil
import subprocess

_CREATE_NEW_CONSOLE = 0x00000010


def open_in_explorer(path: str) -> None:
    os.startfile(path)  # noqa: S606 - Windows 打开目录


def open_terminal(path: str) -> None:
    """优先 Windows Terminal，回退到 PowerShell 新窗口。"""
    wt = shutil.which("wt.exe") or shutil.which("wt")
    if wt:
        subprocess.Popen([wt, "-d", path], close_fds=True)
        return
    safe = path.replace("'", "''")
    subprocess.Popen(
        ["powershell.exe", "-NoExit", "-Command", f"Set-Location -LiteralPath '{safe}'"],
        creationflags=_CREATE_NEW_CONSOLE, close_fds=True)


def open_vscode(path: str) -> None:
    code = shutil.which("code") or shutil.which("code.cmd")
    if not code:
        raise RuntimeError("未找到 code 命令：请安装 VS Code 并勾选「添加到 PATH」")
    if code.lower().endswith((".cmd", ".bat")):
        # CreateProcess 不能直接执行批处理，交给 cmd.exe
        subprocess.Popen(f'"{code}" "{path}"', shell=True, close_fds=True)
    else:
        subprocess.Popen([code, path], close_fds=True)
