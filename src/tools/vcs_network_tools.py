import os
import subprocess
from langchain_core.tools import tool

def _get_workspace_dir() -> str:
    """Retrieves dynamic compartmentalized session workspace path."""
    wd = os.path.abspath(os.environ.get("AGENT_WORKSPACE", "workspace"))
    os.makedirs(wd, exist_ok=True)
    return wd

def _run_cmd(cmd: list, cwd: str = None, timeout_seconds: float = 300.0) -> str:
    """Helper function to execute system commands safely with a strict time limit."""
    try:
        target_dir = cwd if cwd and os.path.isabs(cwd) else _get_workspace_dir()
        result = subprocess.run(
            cmd,
            cwd=target_dir,
            capture_output=True,
            text=True,
            shell=False,
            timeout=timeout_seconds,
            errors="ignore"
        )
        if result.returncode == 0:
            return f"SUCCESS:\n{result.stdout.strip() if result.stdout else '[Empty Output]'}"
        else:
            return f"ERROR (Exit Code {result.returncode}):\n{result.stderr.strip() if result.stderr else '[Unknown execution error]'}"
    except subprocess.TimeoutExpired:
        return f"TIMEOUT ERROR: Command {' '.join(cmd)} exceeded the configured execution limit of {timeout_seconds / 60.0:.1f} minutes."
    except FileNotFoundError:
        return f"ERROR: System command binary not found. Please verify that the target CLI (e.g., git or ssh) is installed and configured in your system's PATH."
    except Exception as e:
        return f"ERROR: Execution failed. Details: {str(e)}"


def _get_clamped_timeout(timeout_minutes: float) -> float:
    """Clamps requested timeouts strictly within 5 to 15 minutes as mandated by safety protocols."""
    return max(5.0, min(15.0, timeout_minutes)) * 60.0


@tool
def git_init(path: str = ".", timeout_minutes: float = 5.0) -> str:
    """Initializes a new git repository."""
    path_str = path.strip().strip("'").strip('"')
    return _run_cmd(["git", "init", path_str], timeout_seconds=_get_clamped_timeout(timeout_minutes))


@tool
def git_status(timeout_minutes: float = 5.0) -> str:
    """Returns the status of the current git repository."""
    return _run_cmd(["git", "status"], timeout_seconds=_get_clamped_timeout(timeout_minutes))


@tool
def git_clone(repo_url: str, dest: str = "", timeout_minutes: float = 5.0) -> str:
    """Clones a remote git repository."""
    repo_url = repo_url.strip().strip("'").strip('"')
    dest = dest.strip().strip("'").strip('"')
    cmd = ["git", "clone", repo_url]
    if dest:
        cmd.append(dest)
    return _run_cmd(cmd, timeout_seconds=_get_clamped_timeout(timeout_minutes))


@tool
def git_add(files: str, timeout_minutes: float = 5.0) -> str:
    """Adds files to the git staging area."""
    files = files.strip().strip("'").strip('"')
    return _run_cmd(["git", "add", files], timeout_seconds=_get_clamped_timeout(timeout_minutes))


@tool
def git_commit(message: str, timeout_minutes: float = 5.0) -> str:
    """Commits staged changes."""
    message = message.strip().strip("'").strip('"')
    return _run_cmd(["git", "commit", "-m", message], timeout_seconds=_get_clamped_timeout(timeout_minutes))


@tool
def git_checkout(branch: str, timeout_minutes: float = 5.0) -> str:
    """Checks out a branch or file."""
    branch = branch.strip().strip("'").strip('"')
    return _run_cmd(["git", "checkout", branch], timeout_seconds=_get_clamped_timeout(timeout_minutes))


@tool
def git_branch(branch: str = "", timeout_minutes: float = 5.0) -> str:
    """Lists or creates branches."""
    cmd = ["git", "branch"]
    if branch:
        cmd.append(branch.strip().strip("'").strip('"'))
    return _run_cmd(cmd, timeout_seconds=_get_clamped_timeout(timeout_minutes))


@tool
def git_log(timeout_minutes: float = 5.0) -> str:
    """Shows the commit log."""
    return _run_cmd(["git", "log", "--oneline", "-n", "10"], timeout_seconds=_get_clamped_timeout(timeout_minutes))


@tool
def git_pull(remote: str = "origin", branch: str = "main", timeout_minutes: float = 5.0) -> str:
    """Pulls changes from a remote repository."""
    remote = remote.strip().strip("'").strip('"')
    branch = branch.strip().strip("'").strip('"')
    return _run_cmd(["git", "pull", remote, branch], timeout_seconds=_get_clamped_timeout(timeout_minutes))


@tool
def git_push(remote: str = "origin", branch: str = "main", timeout_minutes: float = 5.0) -> str:
    """Pushes changes to a remote repository."""
    remote = remote.strip().strip("'").strip('"')
    branch = branch.strip().strip("'").strip('"')
    return _run_cmd(["git", "push", remote, branch], timeout_seconds=_get_clamped_timeout(timeout_minutes))


@tool
def ssh_run_command(host: str, username: str, command: str, key_file: str = "", port: int = 22, timeout_minutes: float = 5.0) -> str:
    """
    Establishes an SSH connection and runs a shell command on a remote host.
    """
    clean_host = host.strip().strip("'").strip('"')
    clean_user = username.strip().strip("'").strip('"')
    clean_cmd = command.strip().strip("'").strip('"')
    clean_key = key_file.strip().strip("'").strip('"')
    
    ssh_cmd = [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=no",
        "-p", str(port),
        f"{clean_user}@{clean_host}"
    ]
    
    if clean_key:
        ssh_cmd.extend(["-i", clean_key])
        
    ssh_cmd.append(clean_cmd)
    
    return _run_cmd(ssh_cmd, timeout_seconds=_get_clamped_timeout(timeout_minutes))