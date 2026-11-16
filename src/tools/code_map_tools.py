import os
import ast
import py_compile
import traceback
from langchain_core.tools import tool

@tool
def verify_python_ast(file_path: str) -> str:
    """Verifies Python code syntax using ast.parse(). Use this after patching a file to ensure syntax remains valid."""
    try:
        if not os.path.exists(file_path):
            return f"ERROR: File not found at {file_path}"
            
        with open(file_path, 'r', encoding='utf-8') as f:
            source = f.read()
            
        ast.parse(source)
        return f"SUCCESS: {file_path} parsed successfully with no syntax errors. The patch is syntactically sound."
    except SyntaxError as e:
        return f"SYNTAX ERROR in {file_path}:\n{traceback.format_exc()}\nPlease review and fix the syntax."
    except Exception as e:
        return f"ERROR reading or parsing {file_path}: {str(e)}"

@tool
def verify_python_compile(file_path: str) -> str:
    """Verifies Python code by attempting to compile it to bytecode using py_compile. Use for deep verification."""
    try:
        if not os.path.exists(file_path):
            return f"ERROR: File not found at {file_path}"

        py_compile.compile(file_path, doraise=True)
        return f"SUCCESS: {file_path} compiled successfully into bytecode."
    except py_compile.PyCompileError as e:
        return f"COMPILE ERROR in {file_path}:\n{str(e)}\nThe code contains compilation errors."
    except Exception as e:
        return f"ERROR compiling {file_path}: {str(e)}"

@tool
def map_code_tree_sitter(file_path: str, language: str = 'python') -> str:
    """Maps a code file using Tree-sitter to extract classes, functions, and structural hierarchy without reading the whole file body.
    Helps agents understand code structure quickly."""
    try:
        # UPDATE: Swapped tree-sitter-languages for tree-sitter-language-pack
        from tree_sitter import Parser
        import tree_sitter_language_pack as tslp
    except ImportError:
        return "ERROR: 'tree_sitter' or 'tree_sitter_language_pack' not installed. Please run 'pip install tree-sitter tree-sitter-language-pack' first."

    if not os.path.exists(file_path):
        return f"ERROR: File not found at {file_path}"

    try:
        # UPDATE: Initialize modern tree-sitter parser with the language pack
        lang_instance = tslp.get_language(language)
        parser = Parser(lang_instance)
        
        with open(file_path, 'r', encoding='utf-8') as f:
            source_code = f.read()
        
        tree = parser.parse(bytes(source_code, "utf8"))
        root_node = tree.root_node
        
        mapping = []
        
        def traverse(node, depth=0):
            indent = "  " * depth
            
            # Extract Classes and Functions
            if node.type in ['class_definition', 'function_definition']:
                name = "Unknown"
                for child in node.children:
                    if child.type == 'identifier':
                        name = source_code[child.start_byte:child.end_byte]
                        break
                
                type_label = "Class" if node.type == 'class_definition' else "Function/Method"
                mapping.append(f"{indent}- {type_label}: {name} (Lines {node.start_point[0]+1}-{node.end_point[0]+1})")
            
            # Traverse children. Increase indent only if we just passed a class/function
            for child in node.children:
                next_depth = depth + 1 if node.type in ['class_definition', 'function_definition'] else depth
                traverse(child, next_depth)

        traverse(root_node)
        
        if not mapping:
            return f"Mapped {file_path}: File parsed, but no classes or functions were found at the root level."
        
        return f"Code Architecture Map for {file_path}:\n" + "\n".join(mapping)
        
    except Exception as e:
        return f"ERROR mapping {file_path} with Tree-sitter: {str(e)}"

CODE_MAP_TOOLS = [verify_python_ast, verify_python_compile, map_code_tree_sitter]
