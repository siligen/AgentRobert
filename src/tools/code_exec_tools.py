import os
import sys
import subprocess
import time
import re
from langchain_core.tools import tool

def _get_workspace_dir() -> str:
    """Retrieves dynamic compartmentalized session workspace path."""
    wd = os.path.abspath(os.environ.get("AGENT_WORKSPACE", "workspace"))
    os.makedirs(wd, exist_ok=True)
    return wd

def _get_clamped_timeout(timeout_minutes: float) -> float:
    """Clamps requested timeouts strictly within 5 to 15 minutes as mandated by safety protocols."""
    if timeout_minutes is None:
        timeout_minutes = 5.0
    return max(5.0, min(15.0, timeout_minutes)) * 60.0

def _run_cmd_env(cmd: list, cwd: str = None, timeout_seconds: float = 300.0) -> tuple[int, str, str]:
    """Runs shell commands safely and returns structured output data."""
    try:
        target_dir = cwd if cwd and os.path.isabs(cwd) else _get_workspace_dir()
        res = subprocess.run(
            cmd,
            cwd=target_dir,
            capture_output=True,
            text=True,
            shell=False,
            timeout=timeout_seconds,
            errors="ignore"
        )
        return res.returncode, res.stdout, res.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"TIMEOUT ERROR: Command exceeded execution limit of {timeout_seconds}s."
    except Exception as e:
        return -1, "", f"ERROR: Execution failed. Details: {str(e)}"


@tool
def write_code_file(filepath: str, code_content: str, timeout_minutes: float = 5.0, **kwargs) -> str:
    """Creates or overwrites a source code file for any supported programming language."""
    # Defend against instances where LLM hallucinates passing dictionary objects
    if isinstance(filepath, dict):
        filepath = filepath.get("filepath", filepath.get("file_path", filepath.get("path", str(filepath))))
        
    path_str = str(filepath).strip().strip("'").strip('"')
    if not os.path.isabs(path_str):
        path_str = os.path.join(_get_workspace_dir(), path_str)
        
    # Guard to prevent IsADirectoryError which initiates an infinite loop sequence
    if os.path.isdir(path_str) or path_str.endswith('/') or path_str.endswith('\\'):
        return f"ERROR: The path '{path_str}' resolves to a directory. You must strictly provide a valid file name to write code into."
        
    try:
        code_content = str(code_content)
        os.makedirs(os.path.dirname(os.path.abspath(path_str)), exist_ok=True)
        with open(path_str, "w", encoding="utf-8") as f:
            f.write(code_content)
        return f"SUCCESS: File '{path_str}' written successfully."
    except Exception as e:
        return f"ERROR: Could not write file. Details: {str(e)}"


@tool
def patch_code_file(filepath: str, line_number: int, new_content: str, timeout_minutes: float = 5.0) -> str:
    """Patches a specific line in a code file with new content."""
    if isinstance(filepath, dict):
        filepath = filepath.get("filepath", filepath.get("file_path", filepath.get("path", str(filepath))))
        
    path_str = str(filepath).strip().strip("'").strip('"')
    if not os.path.isabs(path_str):
        path_str = os.path.join(_get_workspace_dir(), path_str)
        
    try:
        with open(path_str, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        if 0 < line_number <= len(lines):
            lines[line_number - 1] = str(new_content) + "\n"
            with open(path_str, "w", encoding="utf-8") as f:
                f.writelines(lines)
            return f"SUCCESS: Line {line_number} in '{path_str}' patched successfully."
        return f"ERROR: Line number {line_number} is out of bounds."
    except Exception as e:
        return f"ERROR: Failed to patch file. Details: {str(e)}"


@tool
def setup_python_env(env_name: str = "venv", timeout_minutes: float = 10.0) -> str:
    """Sets up a local python virtual environment."""
    env_name = str(env_name).strip().strip("'").strip('"')
    code, out, err = _run_cmd_env([sys.executable, "-m", "venv", env_name], timeout_seconds=_get_clamped_timeout(timeout_minutes))
    if code == 0:
        return f"SUCCESS: Python environment '{env_name}' initialized."
    return f"ERROR: Failed to create env. {err}"


@tool
def pip_install(packages: str, env_path: str = "venv", timeout_minutes: float = 10.0) -> str:
    """Installs pip packages into the specified virtual environment."""
    packages = str(packages).strip().strip("'").strip('"')
    env_path = str(env_path).strip().strip("'").strip('"')
    
    if not os.path.isabs(env_path):
        env_path = os.path.join(_get_workspace_dir(), env_path)
        
    pip_bin = os.path.join(env_path, "bin", "pip") if os.name != "nt" else os.path.join(env_path, "Scripts", "pip.exe")
    
    code, out, err = _run_cmd_env([pip_bin, "install"] + packages.split(), timeout_seconds=_get_clamped_timeout(timeout_minutes))
    if code == 0:
        return f"SUCCESS: Installed {packages}."
    return f"ERROR: Install failed. {err}"


@tool
def execute_script(filepath: str, timeout_minutes: float = 5.0) -> str:
    """Executes a script file."""
    if isinstance(filepath, dict):
        filepath = filepath.get("filepath", filepath.get("file_path", filepath.get("path", str(filepath))))
        
    path_str = str(filepath).strip().strip("'").strip('"')
    if not os.path.isabs(path_str):
        path_str = os.path.join(_get_workspace_dir(), path_str)
        
    code, out, err = _run_cmd_env([sys.executable, path_str], timeout_seconds=_get_clamped_timeout(timeout_minutes))
    if code == 0:
        return f"SUCCESS: Output:\n{out}"
    return f"ERROR: Execution returned code {code}. Error: {err}"


@tool
def execute_python_with_auto_debug(filepath: str, timeout_minutes: float = 5.0) -> str:
    """Executes a python script and provides debug diagnostics if it fails."""
    if isinstance(filepath, dict):
        filepath = filepath.get("filepath", filepath.get("file_path", filepath.get("path", str(filepath))))
        
    path_clean = str(filepath).strip().strip("'").strip('"')
    if not os.path.isabs(path_clean):
        path_clean = os.path.join(_get_workspace_dir(), path_clean)
        
    code, out, err = _run_cmd_env([sys.executable, path_clean], timeout_seconds=_get_clamped_timeout(timeout_minutes))
    
    if code == 0:
        return f"SUCCESS: Execution complete.\nOutput: {out}"
    
    problematic_line_no = None
    match = re.search(r"line (\d+)", err)
    if match:
        problematic_line_no = int(match.group(1))
        
    debug_diagnostics = []
    if problematic_line_no:
        try:
            with open(path_clean, "r", encoding="utf-8") as f:
                lines = f.readlines()
            start_context = max(0, problematic_line_no - 4)
            end_context = min(len(lines), problematic_line_no + 3)
            debug_diagnostics.append("---------- PROBLEM AREA CONTEXT ----------")
            for idx in range(start_context, end_context):
                line_marker = ">>>" if (idx + 1) == problematic_line_no else "   "
                debug_diagnostics.append(f"{line_marker} Line {idx+1}: {lines[idx].rstrip()}")
            debug_diagnostics.append("------------------------------------------")
        except Exception as file_ex:
            debug_diagnostics.append(f"[File Parse Error: {str(file_ex)}]")
            
    return (
        f"EXECUTION FAILURE (Code {code})\n"
        f"Error: {err}\n"
        f"{chr(10).join(debug_diagnostics)}"
    )