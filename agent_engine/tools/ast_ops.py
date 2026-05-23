import os
import difflib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import tree_sitter
import tree_sitter_language_pack as tslp

# ==============================================================================
# 🌲 INCREMENTAL PARSING & TREE CACHE ENGINE (Module B)
# ==============================================================================

class TreeCache:
    """In-memory cache mapping filepath to (tree, source_bytes)."""
    _cache: Dict[str, Tuple[tree_sitter.Tree, bytes]] = {}

    @classmethod
    def get_language_name(cls, filepath: str) -> str:
        ext = Path(filepath).suffix.lower()
        mapping = {
            ".py": "python",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".html": "html",
            ".htm": "html",
            ".rs": "rust",
            ".go": "go",
            ".cpp": "cpp",
            ".hpp": "cpp",
            ".cc": "cpp",
            ".hh": "cpp",
            ".c": "cpp",
            ".h": "cpp",
            ".java": "java",
            ".php": "php",
            ".cs": "csharp",
        }
        return mapping.get(ext)

    @classmethod
    def get_parser(cls, filepath: str) -> tree_sitter.Parser:
        lang_name = cls.get_language_name(filepath)
        return tslp.get_parser(lang_name)

    @classmethod
    def get_tree(cls, filepath: str, force_reload: bool = False) -> Tuple[tree_sitter.Tree, bytes]:
        abs_path = os.path.abspath(filepath)
        if not os.path.exists(abs_path):
            raise FileNotFoundError(f"File not found: {filepath}")
            
        current_bytes = Path(abs_path).read_bytes()
        # CRLF Auto-Normalization: Translate CRLF to LF internally so Tree-Sitter byte offsets
        # are perfectly uniform and aligned with standard line endings, bypassing \r offset shifts.
        current_bytes = current_bytes.replace(b"\r\n", b"\n")
        
        if not force_reload and abs_path in cls._cache:
            cached_tree, cached_bytes = cls._cache[abs_path]
            if cached_bytes == current_bytes:
                return cached_tree, cached_bytes
                
        # Parse fully
        parser = cls.get_parser(abs_path)
        tree = parser.parse(current_bytes)
        cls._cache[abs_path] = (tree, current_bytes)
        return tree, current_bytes

    @classmethod
    def notify_edit(cls, filepath: str, start_byte: int, old_end_byte: int, new_end_byte: int, new_bytes: bytes):
        """Forces a full re-parse of the file upon edit to ensure absolute coordinate correctness."""
        abs_path = os.path.abspath(filepath)
        cls.get_tree(abs_path, force_reload=True)

    @classmethod
    def get_point_for_byte(cls, source_bytes: bytes, byte_offset: int) -> Tuple[int, int]:
        prefix = source_bytes[:byte_offset]
        row = prefix.count(b"\n")
        last_newline = prefix.rfind(b"\n")
        if last_newline == -1:
            column = len(prefix)
        else:
            column = len(prefix) - last_newline - 1
        return (row, column)

# ==============================================================================
# 🧠 EXPOSED TOOLS (The LLM Interface)
# ==============================================================================

def _is_safe_path(workdir: str, filepath: str) -> bool:
    try:
        w_dir = Path(workdir).resolve()
        target = Path(os.path.join(workdir, filepath)).resolve()
        return w_dir == target or target.is_relative_to(w_dir)
    except (ValueError, OSError):
        return False

async def get_document_map(filepath: str, workdir: str = None) -> dict:
    """
    Gives the LLM a 10,000-foot view of the file without reading the code.
    
    Args:
        filepath: Relative or absolute path to the file.
        workdir: Optional working directory context.
        
    Returns:
        JSON blueprint structure with classes, functions, and imports.
    """
    if workdir:
        if not _is_safe_path(workdir, filepath):
            return {"error": f"Security Error: Access to '{filepath}' is denied. Path is outside the working directory."}
        if not os.path.isabs(filepath):
            filepath = os.path.join(workdir, filepath)
    try:
        tree, source_bytes = TreeCache.get_tree(filepath)
    except Exception as e:
        return {"error": str(e)}

    classes = []
    functions = []
    imports = []

    class_types = {"class_definition", "class_declaration", "struct_specifier", "class_specifier", "type_declaration", "struct_item", "enum_item", "trait_item"}
    func_types = {"function_definition", "function_declaration", "method_definition", "method_declaration", "function_item"}
    import_types = {"import_statement", "import_from_statement", "use_declaration", "import_declaration", "preproc_include", "using_directive", "namespace_use_declaration"}

    def walk(node):
        node_type = node.type
        
        # Extract Classes
        if node_type in class_types:
            name_node = node.child_by_field_name("name")
            name = name_node.text.decode("utf-8", errors="replace") if name_node else "Anonymous"
            classes.append({
                "name": name,
                "start_line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1
            })
            
        # Extract Functions / Methods
        elif node_type in func_types:
            name_node = node.child_by_field_name("name")
            name = name_node.text.decode("utf-8", errors="replace") if name_node else None
            if not name:
                # Fallback to search first identifier
                for child in node.children:
                    if child.type in ("identifier", "type_identifier", "property_identifier"):
                        name = child.text.decode("utf-8")
                        break
            if name:
                functions.append({
                    "name": name,
                    "start_line": node.start_point[0] + 1,
                    "end_line": node.end_point[0] + 1
                })
                
        # Extract Imports
        elif node_type in import_types:
            text = node.text.decode("utf-8", errors="replace").strip()
            imports.append(text)
            
        for child in node.children:
            walk(child)

    walk(tree.root_node)
    return {
        "classes": classes,
        "functions": functions,
        "imports": imports
    }


async def get_entity_coordinates(filepath: str, entity_name: str, entity_type: Optional[str] = None, workdir: str = None, include_content: bool = True) -> dict:
    """
    Fetches the exact byte coordinates and signature/content of a specific class or function.
    
    Args:
        filepath: Relative or absolute path to the target file.
        entity_name: Name of the function/class to target (e.g. 'calculate_tax' or 'User.calculate_tax').
        entity_type: Optional. Type of the entity ('function' or 'class'). If omitted, searches both.
        workdir: Optional working directory context.
        include_content: Optional. Whether to include the full text content in original_text_guard. Default True. Set to False to save token overhead.
        
    Returns:
        Coordinates map, or auto-corrected suggestions if the symbol is not found.
    """
    if workdir:
        if not _is_safe_path(workdir, filepath):
            return {"found": False, "error": f"Security Error: Access to '{filepath}' is denied. Path is outside the working directory."}
        if not os.path.isabs(filepath):
            filepath = os.path.join(workdir, filepath)
    try:
        tree, source_bytes = TreeCache.get_tree(filepath)
    except Exception as e:
        return {"found": False, "error": str(e)}

    class_types = {
        "class_definition", "class_declaration", "struct_specifier", "class_specifier", 
        "type_declaration", "struct_item", "enum_item", "trait_item", "interface_declaration", 
        "type_alias_declaration", "type_spec"
    }
    func_types = {
        "function_definition", "function_declaration", "method_definition", "method_declaration", 
        "function_item", "arrow_function", "lexical_declaration"
    }

    if entity_type == "class":
        target_types = class_types
    elif entity_type == "function":
        target_types = func_types
    else:
        target_types = class_types.union(func_types)

    # Support nested searches like ClassName.method_name
    parent_class_filter = None
    search_name = entity_name
    if "." in entity_name:
        parts = entity_name.split(".")
        parent_class_filter = parts[0]
        search_name = parts[1]

    # For HTML/JSX/TSX files, check if we can locate by tag class or id
    is_html_like = False
    if filepath.endswith((".html", ".htm", ".jsx", ".tsx", ".xml")):
        is_html_like = True

    found_node = None
    all_known_identifiers = set()

    def walk(node, current_parent_class=None):
        nonlocal found_node
        node_type = node.type
        
        # HTML-specific matching for element blocks by class or ID name
        if is_html_like and node_type in ("element", "jsx_element", "jsx_self_closing_element"):
            # Inspect start_tag or the element itself for attributes
            start_tag = node
            if node_type == "element":
                for child in node.children:
                    if child.type == "start_tag":
                        start_tag = child
                        break
            
            # Look through attributes
            for attr in start_tag.children:
                if attr.type == "attribute":
                    attr_name = None
                    attr_val = None
                    for c in attr.children:
                        if c.type == "attribute_name":
                            attr_name = c.text.decode("utf-8")
                        elif c.type in ("quoted_attribute_value", "attribute_value"):
                            # Extract raw text
                            val_node = c
                            if c.type == "quoted_attribute_value":
                                for val_child in c.children:
                                    if val_child.type == "attribute_value":
                                        val_node = val_child
                                        break
                            attr_val = val_node.text.decode("utf-8", errors="replace")
                    
                    if attr_name in ("class", "className", "id") and attr_val:
                        # Split by space for classes
                        class_names = [name.strip() for name in attr_val.split()]
                        if entity_name in class_names or attr_val == entity_name:
                            found_node = node
                            return

        class_name = current_parent_class
        if node_type in class_types:
            name_node = node.child_by_field_name("name")
            if name_node:
                class_name = name_node.text.decode("utf-8")
                all_known_identifiers.add(class_name)
                
        # Capture all identifiers for spelling suggestions
        if node_type in target_types:
            name_node = node.child_by_field_name("name")
            name = name_node.text.decode("utf-8") if name_node else None
            if not name:
                def find_first_identifier(n):
                    if n.type in ("identifier", "type_identifier", "property_identifier"):
                        return n.text.decode("utf-8")
                    for child in n.children:
                        res = find_first_identifier(child)
                        if res:
                            return res
                    return None
                name = find_first_identifier(node)
            if name:
                all_known_identifiers.add(name)
                if name == search_name:
                    if not parent_class_filter or current_parent_class == parent_class_filter:
                        found_node = node
                        return

        for child in node.children:
            walk(child, class_name)
            if found_node:
                return

    walk(tree.root_node)

    if found_node:
        import hashlib
        file_hash = hashlib.sha256(source_bytes).hexdigest()[:16]
        result = {
            "found": True,
            "start_byte": found_node.start_byte,
            "end_byte": found_node.end_byte,
            "version_token": file_hash
        }
        if include_content:
            original_text = source_bytes[found_node.start_byte:found_node.end_byte].decode("utf-8", errors="replace")
            result["original_text_guard"] = original_text
        return result

    # Graceful failure with Levenshtein-based diff suggestions
    suggestions = difflib.get_close_matches(search_name, list(all_known_identifiers), n=3, cutoff=0.4)
    entity_type_str = entity_type or "class/function"
    return {
        "found": False,
        "error": f"Symbol '{entity_name}' of type '{entity_type_str}' not found.",
        "suggestions": suggestions
    }


async def get_references(filepath: str, target_symbol: str, workdir: str = None, limit: int = None, offset: int = 0, include_context: bool = True) -> dict:
    """
    Finds all exact occurrences and usages of the target symbol inside the file.
    
    Args:
        filepath: Target file path.
        target_symbol: Symbol name to look for (variable, function, class, etc.).
        workdir: Optional working directory context.
        limit: Optional. Maximum number of references to return. Omit for all references.
        offset: Optional. Number of references to skip from the start (for pagination). Default 0.
        include_context: Optional. Whether to include the full context line of code. Default True. Set to False to save token overhead.
        
    Returns:
        Array of references containing line number, bytes, and context line.
        When paginated, also returns `total_count` and `has_more` fields.
    """
    if workdir:
        if not _is_safe_path(workdir, filepath):
            return {"error": f"Security Error: Access to '{filepath}' is denied. Path is outside the working directory."}
        if not os.path.isabs(filepath):
            filepath = os.path.join(workdir, filepath)
    try:
        tree, source_bytes = TreeCache.get_tree(filepath)
    except Exception as e:
        return {"error": str(e)}

    references = []
    lines = source_bytes.split(b"\n")

    ast_refs = {}
    def walk(node):
        text = node.text.decode("utf-8", errors="replace")
        symbol_no_sigil = target_symbol.lstrip("$")
        text_no_sigil = text.lstrip("$")
        
        is_leaf_symbol = not node.children and node.type in (
            "identifier", "type_identifier", "property_identifier", "field_identifier", 
            "variable_name", "variable", "name", "class_name", "method_name", "attribute_name",
            "package_identifier", "shorthand_property_identifier"
        )
        
        if is_leaf_symbol and (text == target_symbol or text_no_sigil == symbol_no_sigil):
            ast_refs[node.start_byte] = (node.start_byte, node.end_byte)
        for child in node.children:
            walk(child)

    walk(tree.root_node)

    import re
    clean_symbol = target_symbol.lstrip("$").lstrip(".")
    pattern = re.compile(rb'\b' + re.escape(clean_symbol.encode("utf-8")) + rb'\b')
    exact_pattern = re.compile(re.escape(target_symbol.encode("utf-8")))
    
    seen_bytes = set()
    
    for start_b, end_b in ast_refs.values():
        seen_bytes.add((start_b, end_b))
        
    for match in exact_pattern.finditer(source_bytes):
        start_b, end_b = match.start(), match.end()
        if not any(s <= start_b < e for s, e in seen_bytes):
            seen_bytes.add((start_b, end_b))
            
    for match in pattern.finditer(source_bytes):
        start_b, end_b = match.start(), match.end()
        if start_b > 0 and source_bytes[start_b-1:start_b] in (b"$", b"."):
            start_b -= 1
        if not any(s <= start_b < e for s, e in seen_bytes):
            seen_bytes.add((start_b, end_b))
            
    # Deduplicate overlapping ranges (keep the one that starts earlier or is longer)
    non_overlapping = []
    for start, end in sorted(list(seen_bytes), key=lambda x: (x[0], -x[1])):
        if not non_overlapping:
            non_overlapping.append((start, end))
        else:
            prev_start, prev_end = non_overlapping[-1]
            if start < prev_end:
                continue
            else:
                non_overlapping.append((start, end))

    for start_b, end_b in non_overlapping:
        line_idx = source_bytes[:start_b].count(b"\n")
        ref_item = {
            "line": line_idx + 1,
            "start_byte": start_b,
            "end_byte": end_b
        }
        if include_context:
            context_str = lines[line_idx].decode("utf-8", errors="replace").strip() if line_idx < len(lines) else ""
            ref_item["context"] = context_str
        references.append(ref_item)

    total_count = len(references)
    if offset:
        references = references[offset:]
    if limit is not None:
        has_more = len(references) > limit
        references = references[:limit]
    else:
        has_more = False

    result = {"references": references, "total_count": total_count}
    if offset or limit is not None:
        result["has_more"] = has_more
        result["offset"] = offset
        result["limit"] = limit
    return result


async def get_html_attribute_bytes(filepath: str, tag_name: Optional[str] = None, attribute_name: str = None, target_substring: str = None, workdir: str = None) -> dict:
    """
    Finds the exact byte coordinates of all class or attribute value substrings in HTML/JSX.
    
    Args:
        filepath: HTML/JSX file path.
        tag_name: Optional. The tag element (e.g. 'div', 'button'). If omitted or '*', searches all tags.
        attribute_name: The attribute name (e.g. 'class', 'href').
        target_substring: The target substring value to locate.
        workdir: Optional working directory context.
        
    Returns:
        Coordinates dictionary containing start_byte and end_byte of the substring,
        along with an array of matches for all occurrences.
    """
    if workdir:
        if not _is_safe_path(workdir, filepath):
            return {"found": False, "error": f"Security Error: Access to '{filepath}' is denied. Path is outside the working directory."}
        if not os.path.isabs(filepath):
            filepath = os.path.join(workdir, filepath)
    try:
        tree, source_bytes = TreeCache.get_tree(filepath)
    except Exception as e:
        return {"error": str(e)}

    search_all_tags = not tag_name or tag_name == "*"
    matches = []

    def walk(node):
        if node.type == "attribute":
            parent = node.parent
            tag = None
            if parent:
                for sibling in parent.children:
                    if sibling.type in ("tag_name", "identifier"):
                        tag = sibling.text.decode("utf-8")
                        break
            
            if search_all_tags or tag == tag_name:
                # Find the attribute_name child
                name_node = None
                for child in node.children:
                    if child.type == "attribute_name":
                        name_node = child
                        break
                
                if name_node and name_node.text.decode("utf-8") == attribute_name:
                    # Find the value node
                    val_node = None
                    for child in node.children:
                        if child.type in ("quoted_attribute_value", "attribute_value"):
                            val_node = child
                            break
                    
                    if val_node:
                        # If it's a quoted_attribute_value, look for the nested attribute_value child
                        nested_val = None
                        if val_node.type == "quoted_attribute_value":
                            for child in val_node.children:
                                if child.type == "attribute_value":
                                    nested_val = child
                                    break
                        
                        target_node = nested_val if nested_val else val_node
                        val_text = target_node.text.decode("utf-8", errors="replace")
                        
                        start_idx = 0
                        while True:
                            idx = val_text.find(target_substring, start_idx)
                            if idx == -1:
                                break
                            m_start = target_node.start_byte + len(val_text[:idx].encode("utf-8"))
                            m_end = m_start + len(target_substring.encode("utf-8"))
                            matches.append({
                                "start_byte": m_start,
                                "end_byte": m_end
                            })
                            start_idx = idx + len(target_substring)

        for child in node.children:
            walk(child)

    walk(tree.root_node)

    if attribute_name == "class":
        def scan_style_elements(node):
            if node.type in ("element", "style_element"):
                is_style = (node.type == "style_element")
                if not is_style:
                    for child in node.children:
                        if child.type == "start_tag":
                            for subchild in child.children:
                                if subchild.type == "tag_name" and subchild.text.decode("utf-8") == "style":
                                    is_style = True
                                    break
                if is_style:
                    for child in node.children:
                        if child.type in ("raw_text", "text"):
                            try:
                                css_parser = tslp.get_parser("css")
                                css_tree = css_parser.parse(child.text)
                                def walk_css(css_node):
                                    if css_node.type == "class_name":
                                        css_text = css_node.text.decode("utf-8", errors="replace")
                                        if css_text == target_substring:
                                            m_start = child.start_byte + css_node.start_byte
                                            m_end = child.start_byte + css_node.end_byte
                                            matches.append({
                                                "start_byte": m_start,
                                                "end_byte": m_end
                                            })
                                    for css_child in css_node.children:
                                        walk_css(css_child)
                                walk_css(css_tree.root_node)
                            except Exception:
                                pass
            for child in node.children:
                scan_style_elements(child)
        scan_style_elements(tree.root_node)

    # Deduplicate matches by range
    seen = set()
    dedup_matches = []
    for m in matches:
        coord = (m["start_byte"], m["end_byte"])
        if coord not in seen:
            seen.add(coord)
            dedup_matches.append(m)
    matches = sorted(dedup_matches, key=lambda m: m["start_byte"])

    if matches:
        return {
            "found": True,
            "start_byte": matches[0]["start_byte"],
            "end_byte": matches[0]["end_byte"],
            "matches": matches
        }
    return {
        "found": False,
        "error": f"Attribute '{attribute_name}' or CSS rule with substring '{target_substring}' not found."
    }


async def verify_ast_integrity(filepath: str, workdir: str = None) -> dict:
    """
    Checks if the syntax of the parsed file is valid by searching for ERROR/MISSING nodes.
    
    Args:
        filepath: The path to the code file.
        workdir: Optional working directory context.
        
    Returns:
        JSON summary detailing syntax validity and specific syntax errors.
    """
    if workdir:
        if not _is_safe_path(workdir, filepath):
            return {"syntax_valid": False, "error": f"Security Error: Access to '{filepath}' is denied. Path is outside the working directory."}
        if not os.path.isabs(filepath):
            filepath = os.path.join(workdir, filepath)
    try:
        lang_name = TreeCache.get_language_name(filepath)
        if not lang_name:
            return {"syntax_valid": True, "unsupported": True}
        tree, source_bytes = TreeCache.get_tree(filepath)
    except Exception as e:
        return {"syntax_valid": False, "error": str(e)}

    errors = []

    def walk(node):
        if node.type == "ERROR" or node.is_missing:
            # Extract surrounding context (30 characters before and after)
            start = max(0, node.start_byte - 30)
            end = min(len(source_bytes), node.end_byte + 30)
            near_bytes = source_bytes[start:end]
            near_text = near_bytes.decode("utf-8", errors="replace")
            
            error_type = f"MISSING '{node.type}'" if node.is_missing else "ERROR"
            errors.append({
                "byte_offset": node.start_byte,
                "error_type": error_type,
                "near_text": near_text
            })
            
        for child in node.children:
            walk(child)

    walk(tree.root_node)

    return {
        "syntax_valid": len(errors) == 0,
        "errors": errors
    }


async def batch_ast_query(queries: list[dict], workdir: str = None) -> dict:
    """
    Executes multiple AST/Tree-Sitter queries in a single batch pass to save turns and tokens.
    
    Args:
        queries: A list of query objects, each having:
                 - "action": One of 'get_document_map', 'get_entity_coordinates', 'get_references', 'get_html_attribute_bytes', 'verify_ast_integrity'.
                 - "params": A dictionary of parameters matching that action's arguments.
        workdir: Optional working directory context.
        
    Returns:
        JSON structure with a list of results in the matching order.
    """
    if isinstance(queries, str):
        import ast
        import json
        try:
            queries = ast.literal_eval(queries)
        except Exception:
            try:
                queries = json.loads(queries)
            except Exception:
                pass
                
    if isinstance(queries, list):
        import ast
        import json
        for i in range(len(queries)):
            if isinstance(queries[i], str):
                try:
                    queries[i] = ast.literal_eval(queries[i])
                except Exception:
                    try:
                        queries[i] = json.loads(queries[i])
                    except Exception:
                        pass

    if not isinstance(queries, list):
        return {"success": False, "error": f"The queries parameter must be a list of dictionaries. Failed to parse: {queries}"}

    from agent_engine.tools.ast_grep import ast_grep_run

    results = []
    actions_map = {
        "get_document_map": get_document_map,
        "get_entity_coordinates": get_entity_coordinates,
        "get_references": get_references,
        "get_html_attribute_bytes": get_html_attribute_bytes,
        "verify_ast_integrity": verify_ast_integrity,
        "rename_symbol": rename_symbol,
        "ast_grep_run": ast_grep_run
    }

    for idx, q in enumerate(queries):
        if not isinstance(q, dict):
            results.append({"success": False, "error": f"Query at index {idx} must be a dictionary."})
            continue
        
        action = q.get("action")
        params = q.get("params")
        if not action or not isinstance(params, dict):
            results.append({"success": False, "error": f"Query at index {idx} must contain 'action' and 'params' (dict)."})
            continue

        if action not in actions_map:
            results.append({"success": False, "error": f"Unknown action '{action}' at index {idx}."})
            continue

        func = actions_map[action]
        try:
            # Inject workdir into params
            params_with_workdir = params.copy()
            params_with_workdir["workdir"] = workdir
            
            # Execute asynchronously
            res = await func(**params_with_workdir)
            results.append({"success": True, "result": res})
        except Exception as e:
            results.append({"success": False, "error": f"Error executing '{action}': {str(e)}"})

    return {"results": results}


async def rename_symbol(filepath: str, old_name: str, new_name: str, workdir: str = None) -> dict:
    """
    Atomically renames all occurrences of a symbol in a single file using host-side AST reference discovery.
    
    This tool combines get_references + patch_code_range into a single atomic operation,
    eliminating manual coordinate transcription errors entirely.
    
    Args:
        filepath: The target source file.
        old_name: The current symbol name to rename (variable, function, class, etc.).
        new_name: The new symbol name.
        workdir: Optional working directory context.
        
    Returns:
        Summary of how many occurrences were renamed, or an error message.
    """
    # Step 1: Discover all references using the AST engine
    refs_result = await get_references(filepath, old_name, workdir=workdir, include_context=False)
    
    if "error" in refs_result:
        return refs_result
    
    references = refs_result.get("references", [])
    if not references:
        return {"success": False, "error": f"Symbol '{old_name}' not found in '{filepath}'. No references to rename."}
    
    # Step 2: Build patches from references (bottom-up sorting handled by patch_code_range)
    from .file_ops import patch_code_range
    
    patches = []
    for ref in references:
        patches.append({
            "start_byte": ref["start_byte"],
            "end_byte": ref["end_byte"],
            "replacement": new_name,
            "original_text": old_name
        })
    
    # Step 3: Apply atomically via patch_code_range
    resolved_filepath = filepath
    if workdir and not os.path.isabs(filepath):
        resolved_filepath = filepath  # patch_code_range resolves relative to workdir
    
    result = await patch_code_range(workdir, resolved_filepath, patches=patches)
    
    return {
        "success": not result.startswith("Error"),
        "renamed_count": len(patches),
        "old_name": old_name,
        "new_name": new_name,
        "message": result
    }
