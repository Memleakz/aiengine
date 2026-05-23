# Ultimate Host-Side AST & Coords Precision Development Protocol
This protocol defines reference standards for executing precise, zero-regression code modifications using our host-side, token-optimized Tree-Sitter Extraction Engine. Prioritize the AST and structural pipeline at all times.

## 1. Exposed Core Agent Tools

### `get_document_map` — Blueprint
Get a structural overview of a file (classes, functions, imports) without loading code into context.
Input: `{ "filepath": "src/main.py" }`

### `get_entity_coordinates` — Surgeon's Scalpel
Fetch exact byte coordinates + source text of any class, function, or HTML element block.
Input: `{ "filepath": "src/main.py", "entity_name": "calculate_tax" }`
*Output includes `start_byte`, `end_byte`, `original_text_guard`, and `version_token` (SHA-256 fingerprint).*
*Set `"include_content": false` to optimize token weight when you only need raw coordinates.*

### `get_references` — Blast Radius
Find every byte coordinate where a symbol is used or defined.
Input: `{ "filepath": "src/main.py", "target_symbol": "calculate_tax" }`
*Set `"include_context": false` to omit line context strings when you only need raw coordinates.*

### `get_html_attribute_bytes` — DOM & CSS Manipulator
Target HTML/JSX attribute values (class names, hrefs, etc.) by substring without guessing offsets.
Input: `{ "filepath": "index.html", "attribute_name": "class", "target_substring": "old-button" }`
*When `attribute_name == "class"`, the engine also parses inline `<style>` blocks to match and rename CSS selectors simultaneously.*

### `patch_code_range` — Precision Scalpel
Apply surgical byte-range replacements. Pass `patches: [...]` for atomic multi-edit transactions.
* ⚠️ **CRITICAL REQUIREMENT**: You MUST ALWAYS pass `"filepath"` (e.g. `"index.html"`) at the top level of the tool call, even when using `patches`!
* **Call Structure Example**:
  ```json
  {
    "filepath": "index.html",
    "patches": [
      {
        "start_byte": 126,
        "end_byte": 136,
        "text": "btn-primary",
        "patch_type": "replace"
      }
    ],
    "version_token": "18f0bd7e304c3933"
  }
  ```

### `batch_ast_query` — Turn Collapser
Execute multiple AST queries or structural actions (including `rename_symbol` and `ast_grep_run`) in a single tool call.
```json
{"queries": [
  {"action": "ast_grep_run", "params": {"filepath_glob": "server.py", "action": "search", "pattern": "class $SERVICE:"}},
  {"action": "rename_symbol", "params": {"filepath": "server.py", "old_name": "UserService", "new_name": "UserSvc"}}
]}
```

### `rename_symbol` — One-Shot Atomic Rename
Renames every occurrence of a symbol across a file in a single atomic transaction.
Input: `{ "filepath": "server.py", "old_name": "auth_key", "new_name": "api_token" }`
*Preferred over manual `get_references` + `patch_code_range` for all pure rename tasks.*

### `ast_grep_run` — Workspace-Wide Structural Search & Rewrite
Executes the high-performance `ast-grep` tool on the codebase for structural queries and declarative multi-file refactors using metavariables.
Input: `{ "action": "search", "pattern": "calculate_tax($AMT, $RATE)" }`
Input: `{ "action": "rewrite", "pattern": "$A.map($B)", "rewrite": "Array.from($A, $B)", "dry_run": true }`

---
## 2. Immutable Laws of Surgical Code Editing

1. **AST-First Directive:** Always prioritize `rename_symbol` for renames, `get_entity_coordinates` for functions/HTML, and `get_references` for refactoring. Never guess byte coordinates or manually edit broad textual blocks.
2. **Concise Planning & High Speed:** Limit your planning/reasoning content to a maximum of 2-3 sentences per turn. Immediately execute your tool calls. Do not write long explanations, checklists, or summaries.
3. **Turn-1 Batch Discovery:** Open every refactor task with a single `batch_ast_query` bundling all discovery queries (document maps, coordinates, references). Collapsing queries to 1 turn cuts token costs by 70%.
4. **Atomic Batch Patches:** When editing multiple locations in one file, pass all edits as a single `patches` list in `patch_code_range` to apply them bottom-up in one atomic transaction.
5. **Original Coords & Tokens:** Always pass the `version_token` from `get_entity_coordinates` to `patch_code_range`. If you receive a stale-coordinates error, immediately re-query the coordinates to refresh the token and offsets.
6. **Complex Refactor Rule:** If you are performing a complex file-wide structural refactor (such as replacing InMemoryRepository with SQLiteRepository, or implementing a rate limiter or transaction context manager from scratch), DO NOT use patch_code_range or coordinate tools. Immediately use read_file followed by file_write or file_edit to write the complete implementation. This prevents byte coordinate mismatch errors and guarantees success on local models.
7. **No Placeholders:** Copy and apply all symbol names EXACTLY as specified in instructions. NEVER use placeholders (e.g. `...` or comments) inside replacement text—write the complete, syntactically-valid functional code block.
8. **HTML & CSS Node Lookup:** In HTML files, all tag containers are of tree-sitter node type `"element"`. Set `entity_type` to `"element"` when calling `get_entity_coordinates` on HTML classes or IDs to ensure precise containment matches.
9. **Self-Verification & Test Loop:** You are highly encouraged to run the test suite using `pytest scratch/test_real_life_app.py` in a `bash` tool call after editing files. If any tests fail, inspect the tracebacks, surgically edit the code to fix any typos or logic errors, and rerun the tests until everything passes perfectly before exiting.
