import os
import shutil
import fnmatch
import re
import time
import datetime
from collections import deque
from langchain_core.tools import tool

# --- WORKSPACE PATH CONFIGURATION ---
# Isolated session workspace resolution directory
WORKSPACE_DIR = os.path.abspath(os.environ.get("AGENT_WORKSPACE", "workspace"))
APP_START_DIR = os.path.abspath(os.environ.get("APP_START_DIR", os.getcwd()))
os.makedirs(WORKSPACE_DIR, exist_ok=True)

def resolve_workspace_path(path_str: str) -> str:
    """Resolves relative file path targets to default under the dynamic session workspace folder (Used for sandbox Writes)."""
    if not path_str:
        return WORKSPACE_DIR
    cleaned = path_str.strip().strip("'").strip('"')
    if not cleaned:
        return WORKSPACE_DIR
    if os.path.isabs(cleaned):
        return cleaned
    full_path = os.path.abspath(cleaned)
    if full_path.startswith(WORKSPACE_DIR):
        return full_path
    return os.path.abspath(os.path.join(WORKSPACE_DIR, cleaned))


def resolve_search_path(path_str: str) -> str:
    """
    Resolves paths for read/search operations, checking both the isolated workspace
    and the application's startup directory as part of the expanded search space.
    """
    if not path_str:
        return WORKSPACE_DIR
    cleaned = str(path_str).strip().strip("'").strip('"')
    if not cleaned:
        return WORKSPACE_DIR
    if os.path.isabs(cleaned):
        return cleaned
        
    workspace_path = os.path.abspath(os.path.join(WORKSPACE_DIR, cleaned))
    if os.path.exists(workspace_path):
        return workspace_path
        
    start_dir_path = os.path.abspath(os.path.join(APP_START_DIR, cleaned))
    if os.path.exists(start_dir_path):
        return start_dir_path
        
    return workspace_path


def _get_clamped_timeout(timeout_minutes: float) -> float:
    return max(5.0, min(15.0, timeout_minutes)) * 60.0


@tool
def get_pwd(timeout_minutes: float = 5.0) -> str:
    """Returns the absolute path of the session workspace directory."""
    try:
        return f"SUCCESS: Current Working Directory Context is '{WORKSPACE_DIR}'"
    except Exception as e:
        return f"ERROR: Failed to retrieve current working directory. Details: {str(e)}"


@tool
def get_system_datetime(timeout_minutes: float = 5.0) -> str:
    """Returns the current local date, time, and timezone of the host system."""
    try:
        now = datetime.datetime.now()
        local_timezone = now.astimezone().tzname() or "UTC"
        formatted_dt = now.strftime("%Y-%m-%d %H:%M:%S")
        return f"SUCCESS: Current system date and time is '{formatted_dt} {local_timezone}'."
    except Exception as e:
        return f"ERROR: Failed to retrieve system date and time. Details: {str(e)}"


@tool
def list_directory(path: str = ".", timeout_minutes: float = 5.0) -> str:
    """Lists directory contents inside the search space, displaying folders and file sizes."""
    try:
        resolved_target = resolve_search_path(path)
            
        if not os.path.exists(resolved_target):
            return f"ERROR: Path '{resolved_target}' does not exist on this machine."
        if not os.path.isdir(resolved_target):
            return f"ERROR: Path '{resolved_target}' is a file, not a directory."
        
        items = os.listdir(resolved_target)
        if not items:
            return f"SUCCESS: Directory '{resolved_target}' is empty."
        
        formatted_items = []
        ignored_items = []
        
        for item in sorted(items):
            full_path = os.path.join(resolved_target, item)
            try:
                if os.path.isdir(full_path):
                    formatted_items.append(f"[DIR]  {item}/")
                else:
                    size = os.path.getsize(full_path)
                    formatted_items.append(f"[FILE] {item} ({size} bytes)")
            except (PermissionError, OSError) as pe:
                ignored_items.append(f"{item} (Reason: {str(pe)})")
                    
        res = f"SUCCESS: Directory listing of '{resolved_target}':\n" + "\n".join(formatted_items)
        if ignored_items:
            res += "\n\nIGNORED PATHS DUE TO PERMISSION ERRORS:\n" + "\n".join(ignored_items)
        return res
    except Exception as e:
        return f"ERROR: Failed to list directory contents. Details: {str(e)}"


@tool
def make_directory(dir_path: str, timeout_minutes: float = 5.0) -> str:
    """Creates a new directory structure inside workspace (similar to 'mkdir -p')."""
    try:
        resolved_target = resolve_workspace_path(dir_path)
        os.makedirs(resolved_target, exist_ok=True)
        return f"SUCCESS: Directory structure '{resolved_target}' created successfully (including intermediate paths)."
    except Exception as e:
        return f"ERROR: Failed to create directory structure. Details: {str(e)}"


@tool
def change_directory(path: str, timeout_minutes: float = 5.0) -> str:
    """Changes the active workspace directory context target."""
    try:
        resolved_target = resolve_workspace_path(path)
        if not os.path.exists(resolved_target):
            return f"ERROR: Path '{resolved_target}' does not exist."
        os.chdir(resolved_target)
        return f"SUCCESS: Changed workspace working directory context to '{os.getcwd()}'."
    except Exception as e:
        return f"ERROR: Failed to change directory context. Details: {str(e)}"


@tool
def copy_file_or_dir(src: str, dest: str, timeout_minutes: float = 5.0) -> str:
    """Copies a file or recursively copies a directory from the search space to a new target path inside the workspace."""
    try:
        # Allowing source file to be retrieved from the expanded search space
        src_clean = resolve_search_path(src)
        # Enforcing writes to target ONLY the isolated workspace sandbox
        dest_clean = resolve_workspace_path(dest)
        
        if not os.path.exists(src_clean):
            return f"ERROR: Source path '{src_clean}' does not exist."
            
        timeout_secs = _get_clamped_timeout(timeout_minutes)
        start_time = time.time()
        
        if os.path.isfile(src_clean):
            os.makedirs(os.path.dirname(dest_clean), exist_ok=True)
            shutil.copy2(src_clean, dest_clean)
            return f"SUCCESS: Copied file from '{src_clean}' to '{dest_clean}'."
            
        ignored_paths = []
        copied_files_count = 0
        timed_out = False
        remaining_work = []
        
        stack = [(src_clean, dest_clean)]
        
        while stack:
            if time.time() - start_time > timeout_secs:
                timed_out = True
                remaining_work = [item[0] for item in stack]
                break
                
            curr_src, curr_dest = stack.pop()
            
            try:
                os.makedirs(curr_dest, exist_ok=True)
                items = os.listdir(curr_src)
            except (PermissionError, OSError) as pe:
                ignored_paths.append(f"{curr_src} (Reason: {str(pe)})")
                continue
                
            for item in items:
                s_item = os.path.join(curr_src, item)
                d_item = os.path.join(curr_dest, item)
                
                try:
                    if os.path.isdir(s_item):
                        stack.append((s_item, d_item))
                    else:
                        shutil.copy2(s_item, d_item)
                        copied_files_count += 1
                except (PermissionError, OSError) as pe:
                    ignored_paths.append(f"{s_item} (Reason: {str(pe)})")
                    
        if timed_out:
            ignored_str = "\n".join(ignored_paths) if ignored_paths else "[None]"
            remaining_str = "\n".join(remaining_work) if remaining_work else "[None]"
            return (
                f"TIMEOUT WARNING (PARTIAL SUCCESS): Recursive copy operations exceeded execution limit.\n"
                f"Successfully copied {copied_files_count} files.\n\n"
                f"ADAPTIVE STRATEGY ACTION REQUIRED:\n"
                f"We recommend resolving remaining folder actions sequentially:\n{remaining_str}\n\n"
                f"IGNORED PATHS DUE TO PERMISSIONS:\n{ignored_str}"
            )
            
        res = f"SUCCESS: Recursively copied directory structure from '{src_clean}' to '{dest_clean}'. Total copied: {copied_files_count} files."
        if ignored_paths:
            res += "\n\nIGNORED PATHS DUE TO PERMISSION ERRORS:\n" + "\n".join(ignored_paths)
        return res
    except Exception as e:
        return f"ERROR: Directory copy operation aborted. Details: {str(e)}"


@tool
def find_files(pattern: str, search_path: str = ".", timeout_minutes: float = 5.0) -> str:
    """Finds files matching a wildcard pattern within the search space (workspace and app start directory trees)."""
    try:
        cleaned_pat = pattern.strip()
        search_path_clean = search_path.strip().strip("'").strip('"')
        
        # If searching the root directory, search both spaces
        if search_path_clean in [".", "", "./"]:
            search_roots = [WORKSPACE_DIR, APP_START_DIR]
        else:
            search_roots = [resolve_search_path(search_path_clean)]
            
        timeout_secs = _get_clamped_timeout(timeout_minutes)
        start_time = time.time()
        
        matches = []
        ignored_paths = []
        unvisited_paths = []
        timed_out = False
        
        queue = deque(search_roots)
        visited = set()
        
        while queue:
            if time.time() - start_time > timeout_secs:
                timed_out = True
                unvisited_paths = list(queue)
                break
                
            curr_dir = queue.popleft()
            abs_curr_dir = os.path.abspath(curr_dir)
            
            # Prevent infinite looping if workspace is nested inside the app start dir
            if abs_curr_dir in visited:
                continue
            visited.add(abs_curr_dir)
            
            if not os.path.exists(curr_dir):
                continue
            
            try:
                items = os.listdir(curr_dir)
            except (PermissionError, OSError) as pe:
                ignored_paths.append(f"{curr_dir} (Reason: {str(pe)})")
                continue
                
            for item in items:
                full_item_path = os.path.join(curr_dir, item)
                
                try:
                    if fnmatch.fnmatch(item, cleaned_pat):
                        matches.append(full_item_path)
                        
                    if os.path.isdir(full_item_path):
                        queue.append(full_item_path)
                except (PermissionError, OSError) as pe:
                    ignored_paths.append(f"{full_item_path} (Reason: {str(pe)})")
                    
        if timed_out:
            matches_str = "\n".join(matches) if matches else "[No matches found before timeout]"
            ignored_str = "\n".join(ignored_paths) if ignored_paths else "[None]"
            
            unvisited_targets = unvisited_paths[:10]
            unvisited_str = "\n".join(unvisited_targets)
            if len(unvisited_paths) > 10:
                unvisited_str += f"\n... and {len(unvisited_paths) - 10} more unvisited folder trees."
                
            return (
                f"TIMEOUT WARNING (PARTIAL RESULTS): Recursive search exceeded time limits.\n\n"
                f"PARTIAL DISCOVERIES SO FAR:\n{matches_str}\n\n"
                f"ADAPTIVE RESOLUTION PLAN:\n"
                f"The walk was forced to stop. Query remaining segments one-by-one:\n{unvisited_str}\n\n"
                f"IGNORED PATHS DUE TO PERMISSIONS:\n{ignored_str}"
            )
            
        res_str = f"SUCCESS: Walk completed. Discovered {len(matches)} matches matching '{cleaned_pat}':\n" + "\n".join(matches)
        if ignored_paths:
            res_str += "\n\nIGNORED PATHS DUE TO PERMISSION ERRORS:\n" + "\n".join(ignored_paths)
        return res_str
        
    except Exception as e:
        return f"ERROR: File finder failed. Details: {str(e)}"

@tool
def grep_file(pattern: str, file_path: str = ".", ignore_case: bool = False, timeout_minutes: float = 5.0) -> str:
    """Scans a single file or traverses a directory tree within the search space, searching line-by-line for matches."""
    try:
        cleaned_pat = pattern.strip()
        file_path_clean = str(file_path).strip().strip("'").strip('"')
        
        if file_path_clean in [".", "", "./"]:
            search_roots = [WORKSPACE_DIR, APP_START_DIR]
        else:
            search_roots = [resolve_search_path(file_path_clean)]
            
        timeout_secs = _get_clamped_timeout(timeout_minutes)
        start_time = time.time()
        
        flags = re.IGNORECASE if ignore_case else 0
        compiled_re = re.compile(cleaned_pat, flags)
        
        matching_lines = []
        ignored_paths = []
        unvisited_paths = []
        timed_out = False
        
        if len(search_roots) == 1 and os.path.isfile(search_roots[0]):
            resolved_path = search_roots[0]
            with open(resolved_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line_num, line in enumerate(f, 1):
                    if time.time() - start_time > timeout_secs:
                        timed_out = True
                        break
                    if compiled_re.search(line):
                        matching_lines.append(f"{os.path.basename(resolved_path)} (Line {line_num}): {line.rstrip()}")
                        
            if timed_out:
                return f"TIMEOUT WARNING (PARTIAL SUCCESS): Scan on file '{resolved_path}' timed out. Matches so far: {len(matching_lines)}"
                
            return f"SUCCESS: Matches in '{resolved_path}':\n" + ("\n".join(matching_lines) if matching_lines else "[No matches]")
            
        queue = deque(search_roots)
        visited = set()
        total_files_scanned = 0
        
        while queue:
            if time.time() - start_time > timeout_secs:
                timed_out = True
                unvisited_paths = list(queue)
                break
                
            curr_dir = queue.popleft()
            abs_curr_dir = os.path.abspath(curr_dir)
            
            if abs_curr_dir in visited:
                continue
            visited.add(abs_curr_dir)
            
            if not os.path.exists(curr_dir):
                continue
                
            try:
                items = os.listdir(curr_dir)
            except (PermissionError, OSError) as pe:
                ignored_paths.append(f"{curr_dir} (Reason: {str(pe)})")
                continue
                
            for item in items:
                full_path = os.path.join(curr_dir, item)
                try:
                    if os.path.isdir(full_path):
                        queue.append(full_path)
                    elif os.path.isfile(full_path):
                        total_files_scanned += 1
                        with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                            for line_num, line in enumerate(f, 1):
                                if time.time() - start_time > timeout_secs:
                                    timed_out = True
                                    break
                                if compiled_re.search(line):
                                    matching_lines.append(f"{full_path} (Line {line_num}): {line.rstrip()}")
                                    
                        if timed_out:
                            break
                except (PermissionError, OSError) as pe:
                    ignored_paths.append(f"{full_path} (Reason: {str(pe)})")
                    
        if timed_out:
            matches_str = "\n".join(matching_lines[:50]) if matching_lines else "[No matches found before timeout]"
            if len(matching_lines) > 50:
                matches_str += f"\n... and {len(matching_lines) - 50} more lines."
                
            ignored_str = "\n".join(ignored_paths) if ignored_paths else "[None]"
            unvisited_targets = unvisited_paths[:10]
            unvisited_str = "\n".join(unvisited_targets)
            if len(unvisited_paths) > 10:
                unvisited_str += f"\n... and {len(unvisited_paths) - 10} more directory branches remaining."
                
            return (
                f"TIMEOUT WARNING (PARTIAL SUCCESS): Recursive directory grep exceeded time limits.\n"
                f"Scanned {total_files_scanned} files.\n\n"
                f"PARTIAL MATCHES FOUND:\n{matches_str}\n\n"
                f"ADAPTIVE STRATEGY PLAN:\n"
                f"Encountered timeout block. Scan remaining unvisited branches separately:\n{unvisited_str}\n\n"
                f"IGNORED PATHS DUE TO PERMISSIONS:\n{ignored_str}"
            )
            
        res_str = f"SUCCESS: Scanned {total_files_scanned} files recursively. Matches found ({len(matching_lines)}):\n" + "\n".join(matching_lines)
        if ignored_paths:
            res_str += "\n\nIGNORED PATHS DUE TO PERMISSION ERRORS:\n" + "\n".join(ignored_paths)
        return res_str
        
    except Exception as e:
        return f"ERROR: Grep scan aborted. Details: {str(e)}"
