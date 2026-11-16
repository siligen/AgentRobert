import os
import subprocess
import base64
import csv
import time
import re
from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from pypdf import PdfReader
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

# Modular imports for System Tools
from src.tools.system_tools import get_pwd, get_system_datetime, list_directory, make_directory, change_directory, copy_file_or_dir, find_files, grep_file

# Modular imports for Git and SSH Tools
from src.tools.vcs_network_tools import (
    git_init, git_status, git_clone, git_add, git_commit,
    git_checkout, git_branch, git_log, git_pull, git_push,
    ssh_run_command
)

# Modular imports for Programming Environment & Automated Debugging Tools
from src.tools.code_exec_tools import (
    write_code_file, patch_code_file, setup_python_env,
    pip_install, execute_script, execute_python_with_auto_debug
)

# Modular imports for Code Mapping and Verification Tools
try:
    from src.tools.code_map_tools import CODE_MAP_TOOLS, map_code_tree_sitter, verify_python_ast, verify_python_compile
except ImportError:
    CODE_MAP_TOOLS = []

# Modular imports for email, WhatsApp, and Telegram integrations
from src.tools.communication_tools import (
    register_email_credentials,
    fetch_unopened_emails,
    draft_or_send_email,
    whatsapp_send_or_draft,
    telegram_send_or_draft
)

# Import the new Skill Manager and RAG Manager
try:
    from src.tools.skill_manager import SkillManager
except ImportError:
    SkillManager = None

try:
    from src.tools.rag_manager import RAGManager
except ImportError:
    RAGManager = None

# Dynamic imports with graceful fallbacks
try:
    import pandas as pd
except ImportError:
    pd = None

try:
    from pptx import Presentation
except ImportError:
    Presentation = None

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    Image = None

DEFAULT_MODEL_NAME = "gemma4:31b"
OLLAMA_URL = "http://localhost:11434"

# --- WORKSPACE DIRECTORY SETUP AND RESOLUTION HELPER ---
# Using environment variables ensures cross-process session folder isolation
WORKSPACE_DIR = os.path.abspath(os.environ.get("AGENT_WORKSPACE", "workspace"))
APP_START_DIR = os.path.abspath(os.environ.get("APP_START_DIR", os.getcwd()))
os.makedirs(WORKSPACE_DIR, exist_ok=True)

def resolve_workspace_path(path_str: str) -> str:
    """
    Resolves relative paths within the dedicated workspace directory (Used for sandbox Writes).
    Absolute paths remain unchanged.
    """
    if not path_str:
        return WORKSPACE_DIR
    cleaned = str(path_str).strip().strip("'").strip('"')
    if not cleaned:
        return WORKSPACE_DIR
    if os.path.isabs(cleaned):
        return cleaned
    # Prevent double nesting if path is already resolved inside WORKSPACE_DIR
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

# Strict Isolation system instruction for Agent Robert (Master Orchestrator)
MASTER_SYSTEM_PROMPT = (
    "You are Agent Robert, the Master Orchestrator of a highly advanced multi-agent cognitive workspace.\n"
    "Your ONLY role is to act as the interface, coordinate workflows, and delegate tasks to sub-agents.\n"
    "CRITICAL MANDATE: You do not have direct file reading, file writing, or file creation tools.\n"
    "CRITICAL RAG POLICY: You are strictly prohibited from accessing RAG (Retrieval-Augmented Generation) directly. You must NOT attempt to retrieve document context yourself. "
    "However, you may instruct your spawned sub-agents to use the `retrieve_rag_context` tool if the task requires knowledge from the indexed documents.\n"
    "You MUST delegate all tasks (e.g., reading files, compiling documents, translating, copywriting, analyzing data, running directory operations, VCS commits, SSH executions, "
    "generating diagrams with Graphviz, or writing, compiling, running, and debugging code in Python, Perl, Tcl, Shell, or C++) "
    "to a specialized sub-agent using the `spawn_agent` tool. When directing sub-agents, you MUST mandate that they prioritize existing tools over custom scripts. "
    "If modifying codebase, agents MUST first use the `map_code_tree_sitter` tool to understand file structure efficiently without reading the whole file. "
    "After applying updates, they MUST use `verify_python_ast` and `verify_python_compile` to ensure the patched code has no syntax errors before concluding. "
    "if a previous agent has already confirmed that the required functionality is missing from the toolset or if you have received an explicit request for a new script.\n"
    "Every spawned sub-agent automatically generates a comprehensive execution log (.md format) and returns its path "
    "(e.g., [Log File Path]: log_xxx.md) along with their task result. "
    "CRITICAL CONTEXT GUARD: You must NOT open, read, or parse this log file unless the user explicitly asks you to inspect, "
    "summarize, or troubleshoot the step-by-step execution details of that specific run. This preserves your active system context tokens.\n"
    "CRITICAL FIREWALL POLICY: The system enforces a strict external sandbox. All tools executing internet network requests (like ssh, cloning, downloading) "
    "will prompt the user for authorization first. If the user denies connection access, the tool will abort. You must expect "
    "denials and elegantly implement fallback courses of action (such as generating local mock structures, planning script execution, or saving code as drafts) without crashing.\n"
    "CREDENTIALS KNOWLEDGE: You and your sub-agents have awareness of the 'config/credentials.md' file. This file contains all stored API keys and communication credentials (Email, Telegram, WhatsApp). Read it to verify available communication channels before executing communication tools.\n"
    "Once the sub-agent reports completion and returns the final result, synthesize or present that result "
    "directly as your final output. Do not attempt to process content yourself; let your spawned agents do the work."
)

def _get_clamped_timeout(timeout_minutes: float) -> float:
    """Clamps timeouts strictly within 5 to 15 minutes as mandated by safety protocols."""
    return max(5.0, min(15.0, timeout_minutes)) * 60.0

def _extract_file_content_helper(file_path: str) -> tuple[str, str]:
    """Helper function to extract clean text representation from all supported formats."""
    # Expanding read space to include app start dir fallback
    resolved_path = resolve_search_path(file_path)
    if not os.path.exists(resolved_path):
        raise FileNotFoundError(f"Target path parameter missing or unreachable: {file_path} (Resolved: {resolved_path})")

    ext = os.path.splitext(resolved_path)[1].lower()
    content = ""

    # ... parsing blocks for Docs, PDFs, CSV, Code, Images
    if ext == ".docx":
        doc = Document(resolved_path)
        content = "\n".join([p.text for p in doc.paragraphs])
    elif ext == ".doc":
        cmd = ["textutil", "-convert", "txt", "-stdout", resolved_path]
        content = subprocess.check_output(cmd).decode("utf-8")
    elif ext == ".pdf":
        reader = PdfReader(resolved_path)
        pages = []
        for idx, page in enumerate(reader.pages):
            text = page.extract_text()
            if text: pages.append(f"--- PAGE {idx+1} ---\n{text}")
        content = "\n".join(pages)
    elif ext == ".csv":
        try:
            rows_data = []
            with open(resolved_path, "r", encoding="utf-8", errors="ignore") as csv_file:
                reader = csv.reader(csv_file)
                for r_idx, row in enumerate(reader):
                    rows_data.append(f"Row {r_idx + 1}: " + ", ".join(row))
            content = "### CSV Spreadsheet Content ###\n" + "\n".join(rows_data)
        except Exception as ex:
            content = f"[CSV Parse Failure: {str(ex)}]"
    elif ext in [".xlsx", ".xls"]:
        if pd is None:
            content = "[System Alert: 'pandas' or 'openpyxl' is missing on the local machine. Cannot extract spreadsheet structural data directly. Please run 'pip install pandas openpyxl' to enable full read operations.]"
        else:
            try:
                xls = pd.ExcelFile(resolved_path)
                sheets_data = []
                for sheet_name in xls.sheet_names:
                    df = pd.read_excel(xls, sheet_name=sheet_name)
                    sheets_data.append(f"### Sheet: {sheet_name} ###\n{df.to_string(index=False)}")
                content = "\n\n".join(sheets_data)
            except Exception as ex:
                content = f"[Spreadsheet Parse Failure: {str(ex)}]"
    elif ext in [".pptx", ".ppt"]:
        if Presentation is None:
            content = "[System Alert: 'python-pptx' is missing on local machine. Please run 'pip install python-pptx' to enable presentation slide reading.]"
        else:
            try:
                prs = Presentation(resolved_path)
                slides_data = []
                for idx, slide in enumerate(prs.slides):
                    slide_text = []
                    for shape in slide.shapes:
                        if hasattr(shape, "text") and shape.text.strip():
                            slide_text.append(shape.text.strip())
                    slides_data.append(f"--- Slide {idx+1} ---\n" + ("\n".join(slide_text) if slide_text else "[Empty Shape/Layout]"))
                content = "\n\n".join(slides_data)
            except Exception as ex:
                content = f"[Presentation Parse Failure: {str(ex)}]"
    elif ext in [
        ".txt", ".md", ".py", ".vhdl", ".v", ".vs", ".vh", 
        ".cpp", ".h", ".hpp", ".cc", ".cxx", ".c", ".java", 
        ".json", ".sh", ".bat", ".xml", ".yaml", ".yml",
        ".pl", ".tcl"
    ]:
        with open(resolved_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    elif ext in [".png", ".jpg", ".jpeg", ".gif", ".bmp"]:
        if Image is None:
            content = "[System Alert: 'Pillow' is missing on the local machine. Please run 'pip install Pillow' to enable image inspections.]"
        else:
            try:
                with Image.open(resolved_path) as img:
                    img_info = [
                        f"Format: {img.format}",
                        f"Mode: {img.mode}",
                        f"Size: {img.width}x{img.height} pixels",
                        f"Info dictionary: {img.info}"
                    ]
                    content = "### Image Metadata Inspection ###\n" + "\n".join(img_info)
            except Exception as img_err:
                content = f"[Image Metadata Extraction Failure: {str(img_err)}]"
    else:
        raise ValueError(f"Unsupported file format: {ext}")
        
    if not content.strip():
        raise ValueError("No readable content found inside document.")
    return content, os.path.basename(resolved_path)

def set_cell_background(cell, fill_hex):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), fill_hex)
    tc_pr.append(shd)

def _add_table_to_docx(doc, rows_data):
    if not rows_data: return
    valid_rows = [r for r in rows_data if any(cell.strip() for cell in r if cell)]
    if not valid_rows: return
    
    num_cols = max(len(row) for row in valid_rows)
    num_rows = len(valid_rows)

    table = doc.add_table(rows=num_rows, cols=num_cols)
    table.style = 'Table Grid'

    for r_idx, row in enumerate(valid_rows):
        is_header = (r_idx == 0)
        for c_idx, val in enumerate(row):
            if c_idx < num_cols:
                cell = table.cell(r_idx, c_idx)
                cell.text = val
                
                for paragraph in cell.paragraphs:
                    paragraph.paragraph_format.space_before = Pt(4)
                    paragraph.paragraph_format.space_after = Pt(4)
                    if is_header:
                        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        for run in paragraph.runs:
                            run.font.bold = True
                            run.font.name = 'Calibri'
                            run.font.size = Pt(11)
                            run.font.color.rgb = RGBColor(255, 255, 255)
                    else:
                        paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
                        for run in paragraph.runs:
                            run.font.name = 'Calibri'
                            run.font.size = Pt(10)
                            run.font.color.rgb = RGBColor(51, 51, 51)
                
                if is_header: set_cell_background(cell, "0D47A1")
                elif r_idx % 2 == 0: set_cell_background(cell, "F2F5F9")

def add_custom_heading(doc, text, level):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(16)
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.keep_with_next = True
    run = p.add_run(text)
    run.bold = True
    run.font.name = 'Calibri'
    if level == 1:
        run.font.size = Pt(18)
        run.font.color.rgb = RGBColor(13, 71, 161)
    elif level == 2:
        run.font.size = Pt(14)
        run.font.color.rgb = RGBColor(21, 101, 192)
    else:
        run.font.size = Pt(12)
        run.font.color.rgb = RGBColor(33, 150, 243)
    return p

def add_custom_paragraph(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(8)
    p.paragraph_format.line_spacing = 1.15
    run = p.add_run(text)
    run.font.name = 'Calibri'
    run.font.size = Pt(11)
    run.font.color.rgb = RGBColor(51, 51, 51)
    return p

def _parse_and_write_docx_content(doc, text_content):
    lines = text_content.split("\n")
    in_table = False
    table_rows = []
    image_pattern = re.compile(r'!\[(.*?)\]\((.*?)\)')

    for line in lines:
        striped_line = line.strip()
        is_table_line = '|' in striped_line
        is_separator = False
        
        if is_table_line:
            cleaned = striped_line.replace('-', '').replace('|', '').replace(':', '').replace(' ', '')
            if len(cleaned) == 0 and '-' in striped_line:
                is_separator = True
        
        img_match = image_pattern.search(striped_line)
        if img_match:
            if in_table:
                _add_table_to_docx(doc, table_rows)
                in_table = False
                table_rows = []
                
            alt_text = img_match.group(1)
            img_path = img_match.group(2).strip().strip("'\"")
            resolved_img = resolve_search_path(img_path) # Images inside docx read using expanded search space
            
            if os.path.exists(resolved_img):
                try:
                    p = doc.add_paragraph()
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    p.paragraph_format.space_before = Pt(12)
                    p.paragraph_format.space_after = Pt(6)
                    run = p.add_run()
                    run.add_picture(resolved_img)
                    
                    if alt_text:
                        caption_p = doc.add_paragraph()
                        caption_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        caption_p.paragraph_format.space_before = Pt(2)
                        caption_p.paragraph_format.space_after = Pt(12)
                        c_run = caption_p.add_run(f"Figure: {alt_text}")
                        c_run.font.italic = True
                        c_run.font.size = Pt(9.5)
                        c_run.font.color.rgb = RGBColor(120, 120, 120)
                except Exception as img_err:
                    add_custom_paragraph(doc, f"[Image Render Error: {str(img_err)}]")
            else:
                add_custom_paragraph(doc, f"[Image Missing: {resolved_img}]")
            continue
                
        if is_table_line:
            if not in_table:
                in_table = True
                table_rows = []
            if is_separator: continue
                
            cells = [c.strip() for c in striped_line.split('|')]
            if striped_line.startswith('|'): cells = cells[1:]
            if striped_line.endswith('|'):
                if cells and cells[-1] == '': cells = cells[:-1]
            if cells: table_rows.append(cells)
        else:
            if in_table:
                _add_table_to_docx(doc, table_rows)
                in_table = False
                table_rows = []
                
            if striped_line:
                if striped_line.startswith("#"):
                    level = 0
                    for char in striped_line:
                        if char == '#': level += 1
                        else: break
                    header_text = striped_line[level:].strip()
                    add_custom_heading(doc, header_text, level=min(level, 3))
                else:
                    add_custom_paragraph(doc, striped_line)
            else:
                doc.add_paragraph("")
                
    if in_table and table_rows:
        _add_table_to_docx(doc, table_rows)

def _write_docx_file_helper(filename: str, text_content: str, timeout_seconds: float = 300.0) -> str:
    start_time = time.time()
    try:
        resolved_filename = resolve_workspace_path(filename)
        if not resolved_filename.lower().endswith(".docx"):
            resolved_filename += ".docx"
        doc = Document()

        style = doc.styles['Normal']
        style.font.name = 'Calibri'
        style.font.size = Pt(11)
        style.font.color.rgb = RGBColor(51, 51, 51)
        
        title_p = doc.add_paragraph()
        title_p.paragraph_format.space_before = Pt(0)
        title_p.paragraph_format.space_after = Pt(12)
        run_title = title_p.add_run("AI Generated Document Workspace")
        run_title.bold = True
        run_title.font.size = Pt(18)
        run_title.font.color.rgb = RGBColor(13, 71, 161)
        
        _parse_and_write_docx_content(doc, text_content)
        
        if time.time() - start_time > timeout_seconds:
            return f"TIMEOUT ERROR: DOCX generator exceeded execution threshold."
            
        doc.save(resolved_filename)
        return f"SUCCESS: Document safely generated and saved locally as '{resolved_filename}'."
    except Exception as e:
        return f"ERROR: Failed to write file layout. Details: {str(e)}"

@tool
def create_docx_file(filename: str, text_content: str, timeout_minutes: float = 5.0) -> str:
    """Creates a new Microsoft Word (.docx) file inside the isolated workspace directory."""
    timeout_secs = _get_clamped_timeout(timeout_minutes)
    return _write_docx_file_helper(filename, text_content, timeout_seconds=timeout_secs)

@tool
def read_local_file(file_path: str, timeout_minutes: float = 5.0) -> str:
    """Reads and extracts text content/metadata from any supported local file within the search space."""
    try:
        # Prevent LLM parsing dictionaries
        if isinstance(file_path, dict):
            file_path = file_path.get("file_path", file_path.get("filepath", file_path.get("path", str(file_path))))
        
        cleaned_path = str(file_path).strip()
        if (cleaned_path.startswith('"') and cleaned_path.endswith('"')) or (cleaned_path.startswith("'") and cleaned_path.endswith("'")):
            cleaned_path = cleaned_path[1:-1].strip()
        resolved_path = resolve_search_path(cleaned_path)
        timeout_secs = _get_clamped_timeout(timeout_minutes)
        start_time = time.time()
        content, filename = _extract_file_content_helper(resolved_path)
        if time.time() - start_time > timeout_secs:
            return f"TIMEOUT ERROR: Ingestion of file '{filename}' exceeded limit."
        return f"SUCCESS (Loaded file '{filename}'):\n---START CONTENT---\n{content}\n---END CONTENT---"
    except Exception as e:
        return f"ERROR: Failed to read local file. Details: {str(e)}"

@tool
def write_local_file(file_path: str, content: str, file_type: str = "text", timeout_minutes: float = 5.0) -> str:
    """Writes or updates files inside the sandboxed workspace folder (.py, .cpp, .csv, etc.)."""
    try:
        # Handle cases where the LLM improperly passes a JSON dictionary object instead of string
        if isinstance(file_path, dict):
            file_path = file_path.get("file_path", file_path.get("filepath", file_path.get("path", str(file_path))))
            
        cleaned_path = str(file_path).strip()
        if (cleaned_path.startswith('"') and cleaned_path.endswith('"')) or (cleaned_path.startswith("'") and cleaned_path.endswith("'")):
            cleaned_path = cleaned_path[1:-1].strip()

        resolved_path = resolve_workspace_path(cleaned_path)
        
        # Explicit guard to intercept infinite retry loops when the path resolves to an existing directory
        if os.path.isdir(resolved_path) or cleaned_path.endswith('/') or cleaned_path.endswith('\\'):
            return f"ERROR: The path '{resolved_path}' indicates a directory. You must specify an explicit file name to write to."

        ext = os.path.splitext(resolved_path)[1].lower()
        timeout_secs = _get_clamped_timeout(timeout_minutes)
        content = str(content)

        if ext == ".docx" or file_type == "docx":
            return _write_docx_file_helper(resolved_path, content, timeout_seconds=timeout_secs)

        os.makedirs(os.path.dirname(resolved_path), exist_ok=True)

        if ext == ".csv" or file_type == "csv":
            if not resolved_path.lower().endswith(".csv"): resolved_path += ".csv"
            lines = [line.split(",") for line in content.strip().split("\n") if line.strip()]
            with open(resolved_path, "w", newline="", encoding="utf-8") as csv_file:
                writer = csv.writer(csv_file)
                writer.writerows(lines)
            return f"SUCCESS: CSV spreadsheet created and saved to '{resolved_path}' with {len(lines)} rows."

        elif ext in [".xlsx", ".xls"] or file_type == "excel":
            if pd is None: return f"ERROR: 'pandas' missing."
            if not resolved_path.lower().endswith((".xlsx", ".xls")): resolved_path += ".xlsx"
            lines = [line.split(",") for line in content.strip().split("\n") if line.strip()]
            if not lines: return "ERROR: Empty data content provided for writing Excel sheet."
            headers = lines[0]
            rows = lines[1:] if len(lines) > 1 else []
            df = pd.DataFrame(rows, columns=headers)
            df.to_excel(resolved_path, index=False)
            return f"SUCCESS: Spreadsheet created and saved to '{resolved_path}' with {len(df)} rows."

        elif ext in [".pptx", ".ppt"] or file_type == "powerpoint":
            if Presentation is None: return f"ERROR: 'python-pptx' missing."
            if not resolved_path.lower().endswith((".pptx", ".ppt")): resolved_path += ".pptx"
            prs = Presentation()
            slide_layout = prs.slide_layouts[1]
            blocks = content.strip().split("\n\n")
            for block in blocks:
                lines = block.split("\n")
                if not lines: continue
                slide = prs.slides.add_slide(slide_layout)
                title_shape = slide.shapes.title
                body_shape = slide.placeholders[1]
                title_shape.text = lines[0].replace("#", "").strip()
                if len(lines) > 1:
                    tf = body_shape.text_frame
                    tf.text = lines[1]
                    for sub_line in lines[2:]:
                        p = tf.add_paragraph()
                        p.text = sub_line
                        p.level = 1
            prs.save(resolved_path)
            return f"SUCCESS: Slide presentation created at '{resolved_path}' with {len(blocks)} slides."

        elif ext in [".png", ".jpg", ".jpeg", ".bmp", ".gif"] or file_type.startswith("image"):
            if Image is None: return f"ERROR: 'Pillow' missing."
            if file_type == "image_base64":
                header_offset = content.find("base64,")
                cleaned_base64 = content[header_offset + 7:] if header_offset != -1 else content
                binary_data = base64.b64decode(cleaned_base64.strip())
                with open(resolved_path, "wb") as f:
                    f.write(binary_data)
                return f"SUCCESS: Base64 image written safely to disk at '{resolved_path}'."
            
            img = Image.new("RGB", (800, 600), color=(18, 18, 18))
            draw = ImageDraw.Draw(img)
            draw.text((40, 40), content, fill=(129, 199, 132))
            img.save(resolved_path)
            return f"SUCCESS: Rendered text content visually into system image saved at '{resolved_path}'."

        else:
            with open(resolved_path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"SUCCESS: File created and populated at '{resolved_path}'."

    except Exception as e:
        return f"ERROR: Failed to execute write operation. Details: {str(e)}"

@tool
def generate_graph_image(dot_source: str, output_filepath: str, timeout_minutes: float = 5.0) -> str:
    """Generates a visualization graph inside the workspace directory using Graphviz DOT syntax."""
    try:
        if not dot_source: return "ERROR: Missing dot_source parameter."
        if not output_filepath: return "ERROR: Missing output_filepath parameter."

        resolved_path = resolve_workspace_path(output_filepath)
        dir_name = os.path.dirname(resolved_path)
        if dir_name: os.makedirs(dir_name, exist_ok=True)
            
        try:
            import graphviz
            src = graphviz.Source(dot_source)
            png_data = src.pipe(format='png')
            with open(resolved_path, 'wb') as f: f.write(png_data)
            return f"SUCCESS: Graph image successfully generated using python-graphviz at '{os.path.abspath(resolved_path)}'."
        except Exception as e_gv:
            dot_temp = resolved_path + ".dot"
            with open(dot_temp, "w", encoding="utf-8") as f: f.write(dot_source)
            cmd = ["dot", "-Tpng", dot_temp, "-o", resolved_path]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_minutes * 60.0)
            if os.path.exists(dot_temp): os.remove(dot_temp)
            if res.returncode == 0:
                return f"SUCCESS: Graph image successfully generated using system Graphviz CLI at '{os.path.abspath(resolved_path)}'."
            else:
                return f"ERROR: Graphviz generation failed. Python exception: {str(e_gv)}\nCLI run stderr: {res.stderr}"
    except Exception as e:
        return f"ERROR: Failed to run Graphviz pipeline. Details: {str(e)}"

class DocumentAIEngine:
    def __init__(self, model_name=DEFAULT_MODEL_NAME, ollama_url=OLLAMA_URL):
        self.chat_history = []
        self.state_callback = None
        self.permission_callback = None 
        self.credentials_callback = None
        self.is_cancelled = False 
        
        self.model_name = model_name
        self.ollama_url = ollama_url

        os.makedirs(WORKSPACE_DIR, exist_ok=True)
        
        # Cache for active RAG managers to avoid redundant initializations
        self.active_rag_managers = {}
        
        # Initialize RAG Manager
        if RAGManager:
            self.rag_manager = RAGManager(
                index_dir=os.path.join(WORKSPACE_DIR, ".rag_index"),
                notification_callback=lambda msg: self.trigger_callback("rag_notification", {"message": msg})
            )
        else:
            self.rag_manager = None

        # Initialize Skill Manager
        self.skill_manager = None
        if SkillManager:
            self.skill_manager = SkillManager(WORKSPACE_DIR, APP_START_DIR)

        self.shared_tools = [
            create_docx_file, 
            read_local_file, 
            write_local_file,
            get_pwd, get_system_datetime, list_directory, make_directory,
            change_directory, copy_file_or_dir, find_files, grep_file,
            git_init, git_status, git_clone, git_add, git_commit, 
            git_checkout, git_branch, git_log, git_pull, git_push, 
            ssh_run_command, write_code_file, patch_code_file,
            setup_python_env, pip_install, execute_script,
            execute_python_with_auto_debug, generate_graph_image,
            register_email_credentials, fetch_unopened_emails,
            draft_or_send_email, whatsapp_send_or_draft, telegram_send_or_draft
        ]
        
        # Create and add the RAG tools for sub-agents
        self.rag_tool = self._create_rag_tool()
        self.index_tool = self._create_index_tool()
        self.shared_tools.append(self.rag_tool)
        self.shared_tools.append(self.index_tool)
        
        self.orchestrator_tools = [self.create_spawn_agent_tool()]

        self.llm = ChatOllama(
            model=self.model_name, 
            base_url=self.ollama_url, 
            timeout=45, 
            validate_model_on_init=True
        ).bind_tools(self.orchestrator_tools)

    def _create_rag_tool(self):
        """Creates the tool for sub-agents to access RAG context."""
        @tool
        def retrieve_rag_context(query: str, top_k: int = 5, index_path: str = None) -> str:
            """Retrieves relevant context from the indexed documents based on a query. 
            Optionally provide 'index_path' to query from a specific session index."""
            if not RAGManager:
                return "RAG Manager is not available in this environment."
            
            target_dir = index_path if index_path else os.path.join(WORKSPACE_DIR, ".rag_index")
            try:
                if target_dir in self.active_rag_managers:
                    mgr = self.active_rag_managers[target_dir]
                else:
                    mgr = RAGManager(
                        index_dir=target_dir, 
                        notification_callback=lambda msg: self.trigger_callback("rag_notification", {"message": msg})
                    )
                    self.active_rag_managers[target_dir] = mgr
                return mgr.retrieve_context(query, top_k=top_k)
            except Exception as e:
                return f"ERROR: Retrieval failed for index at {target_dir}: {str(e)}"
        return retrieve_rag_context

    def _create_index_tool(self):
        """Creates the tool for sub-agents to index files into a specific RAG index."""
        @tool
        def index_rag_file(file_path: str, index_path: str = None) -> str:
            """Indexes a file into a specific RAG index. 
            Use the provided 'index_path' to maintain a session-specific knowledge base."""
            if not RAGManager:
                return "RAG Manager is not available in this environment."

            target_dir = index_path if index_path else os.path.join(WORKSPACE_DIR, ".rag_index")
            try:
                if target_dir in self.active_rag_managers:
                    mgr = self.active_rag_managers[target_dir]
                else:
                    mgr = RAGManager(
                        index_dir=target_dir, 
                        notification_callback=lambda msg: self.trigger_callback("rag_notification", {"message": msg})
                    )
                    self.active_rag_managers[target_dir] = mgr
                mgr.index_file(file_path)
                return f"SUCCESS: File {file_path} indexed into {target_dir}."
            except Exception as e:
                return f"ERROR: Indexing failed for {file_path} at {target_dir}: {str(e)}"
        return index_rag_file

    def update_model(self, new_model_name: str):
        """Allows dynamically switching the LLM model powering the engine."""
        self.model_name = new_model_name
        self.llm = ChatOllama(
            model=self.model_name,
            base_url=self.ollama_url,
            timeout=45,
            validate_model_on_init=True
        ).bind_tools(self.orchestrator_tools)

    def trigger_callback(self, event_type: str, payload: dict):
        if self.state_callback: self.state_callback(event_type, payload)

    def check_internet_permission(self, description: str) -> bool:
        if self.permission_callback: return self.permission_callback(description)
        return False

    def _get_tokens(self, response):
        """Extracts prompt and completion tokens from response metadata."""
        metadata = getattr(response, 'response_metadata', {})
        if not metadata:
            return 0
        p_tokens = metadata.get('prompt_eval_count', 0)
        c_tokens = metadata.get('eval_count', 0)
        if p_tokens == 0 and c_tokens == 0:
            return 0
        return p_tokens + c_tokens

    def _check_and_prompt_credentials(self, tool_name: str) -> bool:
        """Determines if the requested tool is missing explicitly required configuration keys before execution."""
        required = []
        if tool_name == "fetch_unopened_emails":
            required = ["IMAP_SERVER", "EMAIL_ADDRESS", "EMAIL_PASSWORD"]
        elif tool_name == "draft_or_send_email":
            required = ["SMTP_SERVER", "IMAP_SERVER", "EMAIL_ADDRESS", "EMAIL_PASSWORD", "AUTHORIZED_OWNER"]
        elif tool_name == "telegram_send_or_draft":
            required = ["TELEGRAM_BOT_TOKEN"]
        elif tool_name == "whatsapp_send_or_draft":
            required = ["WHATSAPP_API_TOKEN", "WHATSAPP_PHONE_ID"]
            
        if not required:
            return True
            
        missing = []
        cred_path = os.path.abspath("config/credentials.md")
        creds = {}
        if os.path.exists(cred_path):
            with open(cred_path, "r") as f:
                for line in f:
                    if ":" in line and not line.startswith("#"):
                        k, v = line.split(":", 1)
                        creds[k.strip().replace("**", "")] = v.strip()
                        
        for req in required:
            if not creds.get(req): missing.append(req)
            
        if missing:
            if self.credentials_callback:
                return self.credentials_callback(missing)
            return False
        return True

    def find_tool(self, tool_name: str):
        for t in self.orchestrator_tools + self.shared_tools:
            t_name = getattr(t, "name", getattr(t, "__name__", None))
            if t_name == tool_name: return t
        return None

    def run_orchestrator(self, user_message: str) -> str:
        if not self.chat_history or not any(isinstance(msg, SystemMessage) and "Master Orchestrator" in msg.content for msg in self.chat_history):
            # Inject discovered skills into the system prompt
            prompt = MASTER_SYSTEM_PROMPT
            if self.skill_manager:
                prompt += "\n\nSKILLS SYSTEM:\n" + self.skill_manager.get_all_skills_summary() + \
                          "\nTo use a skill, read its definition file (e.g., 'skills/skill_name/SKILL.md') to understand its capabilities and instructions."
            
            self.chat_history.insert(0, SystemMessage(content=prompt))
            
        # RAG Integration: REMOVED automatic retrieval for Master Orchestrator to comply with strict isolation rules
        enhanced_user_message = user_message
            
        if not self.chat_history or not isinstance(self.chat_history[-1], HumanMessage) or self.chat_history[-1].content != enhanced_user_message:
            self.chat_history.append(HumanMessage(content=enhanced_user_message))
            
        self.trigger_callback("master_status_change", {"status": "Thinking..."})
        
        total_tokens = 0
        turn_subagent_usage = {}
        while True:
            if getattr(self, "is_cancelled", False):
                self.trigger_callback("master_status_change", {"status": "Idle"})
                return "Pipeline execution stopped by user."
                
            response = self.llm.invoke(self.chat_history)
            self.chat_history.append(response)
            
            # Token tracking
            tokens_used = self._get_tokens(response)
            total_tokens += tokens_used
            self.trigger_callback("master_token_update", {"tokens": total_tokens})
            
            if not response.tool_calls:
                self.trigger_callback("master_status_change", {"status": "Idle"})
                
                sub_total = 0
                usage_summary = ["\n---", "[Sub-Agent Usage]:"]
                for role, tokens in turn_subagent_usage.items():
                    usage_summary.append(f"- {role}: {tokens} tokens")
                    sub_total += tokens
                if not turn_subagent_usage:
                    usage_summary.append("None")
                
                usage_summary.append(f"[Master Usage]: {total_tokens} tokens")
                usage_summary.append(f"Total Turn Usage: {sub_total + total_tokens} tokens")
                
                return f"{response.content}\n\n" + "\n".join(usage_summary)
                
            for tool_call in response.tool_calls:
                if getattr(self, "is_cancelled", False):
                    self.trigger_callback("master_status_change", {"status": "Idle"})
                    return "Pipeline execution stopped by user."
                    
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                
                self.trigger_callback("master_tool_start", {"tool_name": tool_name})
                
                target_tool = self.find_tool(tool_name)
                if target_tool:
                    try:
                        is_allowed = True
                        internet_facing_tools = ["git_clone", "git_pull", "git_push", "ssh_run_command"]
                        if tool_name in internet_facing_tools:
                            desc = f"VCS/SSH transaction on '{tool_name}' with parameters {tool_args}"
                            is_allowed = self.check_internet_permission(desc)
                            
                        if is_allowed:
                            if self._check_and_prompt_credentials(tool_name):
                                if hasattr(target_tool, "invoke"):
                                    result_str = target_tool.invoke(tool_args)
                                else:
                                    result_str = target_tool(**tool_args)
                            else:
                                result_str = f"ABORTED: Required communication credentials missing and not provided."
                        else:
                            result_str = f"ABORTED: User explicitly blocked internet access for '{tool_name}'. You must make local course corrections."
                    except Exception as e:
                        result_str = f"Error executing tool {tool_name}: {str(e)}"
                else:
                    result_str = f"Error: Tool '{tool_name}' could not be resolved."
                    
                # Extract sub-agent tokens if the tool returned a successful agent run
                if "[Agent:" in result_str and "[Context Usage:" in result_str:
                    agent_match = re.search(r'\[Agent: (.*?) Success\]', result_str)
                    token_match = re.search(r'\[Context Usage: (\d+) tokens\]', result_str)
                    if agent_match and token_match:
                        role = agent_match.group(1)
                        tokens = int(token_match.group(1))
                        turn_subagent_usage[role] = turn_subagent_usage.get(role, 0) + tokens

                self.chat_history.append(ToolMessage(content=result_str, tool_call_id=tool_call["id"]))
                self.trigger_callback("master_tool_end", {"tool_name": tool_name})

    def create_spawn_agent_tool(self):
        @tool
        def spawn_agent(role: str, task: str) -> str:
            """Spawns a specialized sub-agent persona to systematically tackle an instruction."""
            self.trigger_callback("spawn_agent_start", {"role": role, "task": task})

            # Dynamically uses the engine's currently selected model for sub-agents
            sub_llm = ChatOllama(
                model=self.model_name, base_url=self.ollama_url, timeout=60, validate_model_on_init=False
            ).bind_tools(self.shared_tools + self.orchestrator_tools)

            # Add skills knowledge to sub-agent prompt
            skills_context = ""
            if self.skill_manager:
                skills_context = "\n\nAVAILABLE SYSTEM SKILLS:\n" + self.skill_manager.get_all_skills_summary() + \
                                 "\nTo utilize these specialized capabilities, read the corresponding 'SKILL.md' file in the 'skills/' directory."

            # Define session-specific RAG index for this agent
            sanitized_role = re.sub(r'[^a-zA-Z0-9_]', '_', role.lower())
            agent_index_path = os.path.join(WORKSPACE_DIR, f".rag_index_{sanitized_role}")

            messages = [
                SystemMessage(content=(
                    f"You are a specialized sub-agent spawned by Agent Robert (Master Orchestrator).\n"
                    f"YOUR DESIGNATED ROLE: {role}\n"
                    f"Your objective is to execute the assigned task efficiently.\n"
                    f"CRITICAL PLAN & ADAPTABLE TODO PROTOCOL:\n"
                    f"1. Before calling any tools, you MUST formulate a clear, numbered [TODO LIST] representing your step-by-step plan.\n"
                    f"2. You must dynamically adapt this plan based on reality. If a tool fails (e.g., directory error, compile error), you MUST update your plan and try an alternative approach. Do not get stuck in infinite loops; if an approach fails twice, explicitly pivot strategy.\n"
                    f"3. In each turn, reference your plan, check off items, and amend if errors arise.\n"
                    f"4. KNOWLEDGE: You are fully aware of 'config/credentials.md'. This file stores all communication configurations (Email, Telegram, WhatsApp API keys). Read it to see what channels are active.\n"
                    f"RAG ACCESS CONTROL: You MUST ONLY use the `retrieve_rag_context` tool if Agent Robert (Master Orchestrator) has explicitly granted you permission to do so in your task instructions. "
                    f"If permission is granted, you are responsible for determining the best search queries and may perform multiple retrievals as needed to complete the task.\n"
                    f"CRITICAL SECURE CHANNELS & EMAIL GATES POLICY:\n"
                    f"- IMPORTANT RULE: You have ABSOLUTELY NO AUTHORITY to send an email to any address other than the strictly configured AUTHORIZED_OWNER.\n"
                    f"- If asked to draft or send communications to other addresses, you MUST create local drafts.\n"
                    f"- External communication transactions (email, telegram, whatsapp) are auto-authorized for configured channels.\n"
                    f"- VCS and SSH operations will prompt the user for permission. Expect pop-ups.\n"
                    f"CRITICAL COGNITIVE ENVIRONMENT: All files you create or modify reside safely inside this session's workspace subfolder. You can also read and search files in the application startup directory.\n"
                    f"YOUR SESSION-SPECIFIC RAG INDEX PATH: {agent_index_path}\n"
                    f"Use this path when calling 'index_rag_file' and 'retrieve_rag_context' to maintain your own isolated knowledge base.\n"
                    f"{skills_context}"
                )),
                HumanMessage(content=task)
            ]

            execution_log_lines = [
                f"# Agent Execution Log: {role}",
                f"- **Designated Role**: {role}",
                f"- **Start Timestamp**: {time.strftime('%Y-%m-%d %H:%M:%S')}",
                f"- **Initial Task Context**:\n```text\n{task}\n```\n",
                "## Step-by-Step History Log\n"
            ]
            
            step_counter = 1
            agent_tokens = 0

            try:
                while True:
                    if getattr(self, "is_cancelled", False):
                        self.trigger_callback("spawn_agent_end", {"role": role, "tokens": agent_tokens})
                        log_filename = f"log_{sanitized_role}_{int(time.time())}_cancelled.md"
                        log_filepath = os.path.join(WORKSPACE_DIR, log_filename)
                        execution_log_lines.append("\n## STATUS: EXECUTION INTERRUPTED/CANCELLED BY USER")
                        try:
                            with open(log_filepath, "w", encoding="utf-8") as lf: lf.write("\n".join(execution_log_lines))
                        except Exception: pass
                        return f"[Agent: {role} Cancelled] Partial log saved: {log_filename}"
                        
                    response = sub_llm.invoke(messages)
                    messages.append(response)
                    
                    # Token tracking
                    tokens_used = self._get_tokens(response)
                    agent_tokens += tokens_used
                    self.trigger_callback("sub_agent_token_update", {"role": role, "tokens": agent_tokens})
                    
                    if response.content:
                        execution_log_lines.append(f"### Turn {step_counter}: Agent Thoughts & Plan Status\n{response.content}\n")
                        
                    if response.tool_calls:
                        for tool_call in response.tool_calls:
                            t_name = tool_call["name"]
                            t_args = tool_call["args"]
                            execution_log_lines.append(f"**Executing Tool**: `{t_name}`\n- **Parameters**: `{t_args}`")
                    
                    if not response.tool_calls:
                        log_filename = f"log_{sanitized_role}_{int(time.time())}.md"
                        log_filepath = os.path.join(WORKSPACE_DIR, log_filename)
                        execution_log_lines.append("\n## STATUS: SUCCESSFULLY COMPLETED")
                        with open(log_filepath, "w", encoding="utf-8") as lf: lf.write("\n".join(execution_log_lines))
                        self.trigger_callback("spawn_agent_end", {"role": role, "tokens": agent_tokens})
                        return (f"[Agent: {role} Success] Task completed.\n[Log File Path]: {log_filename}\nOutput:\n{response.content}\n[Context Usage: {agent_tokens} tokens]")
                    
                    for tool_call in response.tool_calls:
                        if getattr(self, "is_cancelled", False):
                            self.trigger_callback("spawn_agent_end", {"role": role, "tokens": agent_tokens})
                            return f"[Agent: {role} Cancelled] Execution stopped by user."
                            
                        tool_name = tool_call["name"]
                        tool_args = tool_call["args"]
                        self.trigger_callback("sub_agent_tool_start", {"role": role, "tool_name": tool_name})
                        
                        t_func = self.find_tool(tool_name)
                        if t_func:
                            try:
                                is_allowed = True
                                internet_facing_tools = ["git_clone", "git_pull", "git_push", "ssh_run_command"]
                                if tool_name in internet_facing_tools:
                                    desc = f"External transaction requesting '{tool_name}' using configuration: {tool_args}"
                                    is_allowed = self.check_internet_permission(desc)

                                if is_allowed:
                                    # Enforce missing configuration validation block UI before execution
                                    if self._check_and_prompt_credentials(tool_name):
                                        if tool_name == "draft_or_send_email":
                                            target_recipient = tool_args.get("to_address", "").strip()
                                            
                                            # Secure fetch AUTHORIZED_OWNER configuration from memory
                                            auth_owner = ""
                                            cred_path = os.path.abspath("config/credentials.md")
                                            if os.path.exists(cred_path):
                                                with open(cred_path, "r") as f:
                                                    for line in f:
                                                        if ":" in line and not line.startswith("#"):
                                                            k, v = line.split(":", 1)
                                                            if k.strip().replace("**", "") == "AUTHORIZED_OWNER":
                                                                auth_owner = v.strip()
                                                                
                                            if auth_owner and target_recipient.lower() != auth_owner.lower() and not tool_args.get("draft_only", False):
                                                tool_args["draft_only"] = True
                                                execution_log_lines.append(f"⚠️ SECURITY GUARD TRIGGERED: Intercepted and forced Draft mode because recipient '{target_recipient}' is not the explicitly configured authorized owner.")

                                        if hasattr(t_func, "invoke"):
                                            tool_result = t_func.invoke(tool_args)
                                        else:
                                            tool_result = t_func(**tool_args)
                                    else:
                                        tool_result = "ABORTED: Missing mandatory credentials configurations."
                                else:
                                    tool_result = f"ABORTED: Internet network permission explicitly DENIED by the user. You must proceed with a local offline fallback strategy."
                            except Exception as e:
                                tool_result = f"Error: {str(e)}"
                            messages.append(ToolMessage(content=tool_result, tool_call_id=tool_call["id"]))
                            execution_log_lines.append(f"- **Execution Result Output**:\n```text\n{tool_result}\n```\n")
                        else:
                            error_result = f"Error: Tool {tool_name} not found."
                            messages.append(ToolMessage(content=error_result, tool_call_id=tool_call["id"]))
                            execution_log_lines.append(f"- **Execution Result Output**: {error_result}\n")
                        
                        self.trigger_callback("sub_agent_tool_end", {"role": role})
                        
                    step_counter += 1
            except Exception as e:
                self.trigger_callback("spawn_agent_end", {"role": role, "tokens": agent_tokens})
                log_filename = f"log_{sanitized_role}_{int(time.time())}_failed.md"
                log_filepath = os.path.join(WORKSPACE_DIR, log_filename)
                execution_log_lines.append(f"\n## STATUS: AGENT RUNTIME CRASHED\n- **Error Details**: {str(e)}")
                try:
                    with open(log_filepath, "w", encoding="utf-8") as lf: lf.write("\n".join(execution_log_lines))
                except Exception: pass
                return f"[Agent: {role} Failure] Run encountered an error: {str(e)}. Partial log saved: {log_filename}"

        return spawn_agent

    def _normalize_path(self, path_input):
        if not path_input: return ""
        # Safely extract from dict if LLM hallucinates JSON formatting 
        if isinstance(path_input, dict):
            for k in ["file_path", "filepath", "path", "filename", "name"]:
                if k in path_input:
                    path_input = path_input[k]
                    break

        if isinstance(path_input, (tuple, list)):
            if len(path_input) > 0: path_str = str(path_input[0]).strip()
            else: return ""
        else: path_str = str(path_input).strip()
        
        if (path_str.startswith('"') and path_str.endswith('"')) or (path_str.startswith("'") and path_str.endswith("'")):
            path_str = path_str[1:-1].strip()
        return path_str

    def extract_text(self, path_input):
        file_path = self._normalize_path(path_input)
        return _extract_file_content_helper(file_path)

    def attach_file(self, path_input):
        normalized = self._normalize_path(path_input)
        # Logic changed: No more automatic indexing.
        # Append the path to the Master Orchestrator's prompt as a reference.
        prompt = (
            f"SYSTEM CONTEXT: The following path has been selected as a reference document/directory.\n"
            f"PATH: {normalized}\n"
            f"Please use this as a reference for subsequent tasks. If indexing is required for RAG, "
            f"instruct a sub-agent to use the 'index_rag_file' tool."
        )
        self.chat_history.append(SystemMessage(content=prompt))
        return f"Reference added: {normalized}"

    def generate_chat_log(self):
        lines = []
        for msg in self.chat_history:
            if isinstance(msg, HumanMessage): lines.append(f"YOU: {msg.content}")
            elif isinstance(msg, AIMessage): lines.append(f"AI: {msg.content}")
        return "\n\n".join(lines)
