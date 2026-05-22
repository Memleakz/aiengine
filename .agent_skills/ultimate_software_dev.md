# Ultimate Host-Side AST & Coords Precision Development Protocol
This protocol defines the absolute reference standards for executing 100% precise, zero-regression code modifications using our host-side, token-optimized Tree-Sitter Extraction Engine.

## 1. Exposed Core Agent Tools

### `get_document_map` — Blueprint
Get a structural overview of a file (classes, functions, imports) without loading code into context.
Input: `{ "filepath": "src/main.py" }`

### `get_entity_coordinates` — Surgeon's Scalpel
Fetch exact byte coordinates + source text of any class, function, or HTML element block.
Input: `{ "filepath": "src/main.py", "entity_name": "calculate_tax" }`
Output includes `start_byte`, `end_byte`, `original_text_guard` (the exact current source), and `version_token` (SHA-256 file fingerprint — pass back to `patch_code_range` to guard against stale coordinates).
*`entity_type` is optional. HTML class/ID names return the full container element block.*
*Token Optimization: Set `"include_content": false` if you only need the coordinates and do not need the full body content yet.*

### `get_references` — Blast Radius
Find every byte coordinate where a symbol is used or defined.
Input: `{ "filepath": "src/main.py", "target_symbol": "calculate_tax" }`
Output: `references[]` with `line`, `start_byte`, `end_byte`, `context`, plus `total_count`.
*Pagination: use `limit` and `offset` to avoid flooding context on high-reference symbols.*
*Token Optimization: Set `"include_context": false` to omit line context strings when you only need raw coordinates.*

### `get_html_attribute_bytes` — DOM & CSS Manipulator
Target HTML/JSX attribute values (class names, hrefs, etc.) by substring without guessing offsets.
Input: `{ "filepath": "index.html", "attribute_name": "class", "target_substring": "old-button" }`
*`tag_name` is optional — omit or pass `*` to scan all tags.*
*When `attribute_name == "class"`, the engine also parses inline `<style>` blocks via a dedicated CSS tree-sitter parser, returning exact byte coordinates of matching CSS class-name selectors (e.g. `.old-button { ... }`). A single call therefore renames a class in both HTML attributes and CSS rules simultaneously.*

### `patch_code_range` — Precision Scalpel
Apply surgical byte-range replacements. Pass `patches: [...]` for atomic multi-edit transactions (engine sorts bottom-up automatically). Pass `version_token` to get hard rejection on stale coordinates.

### `batch_ast_query` — Turn Collapser
Execute multiple AST queries in a single tool call.
```json
{"queries": [
  {"action": "get_entity_coordinates", "params": {"filepath": "server.py", "entity_name": "UserManager"}},
  {"action": "get_references", "params": {"filepath": "server.py", "target_symbol": "auth_key"}}
]}
```
---
## 2. Immutable Laws of Surgical Code Editing

1. **Never Guess Coordinates:** Always use `get_entity_coordinates` for functions/classes/HTML blocks and `get_references` for variables/properties/identifiers. `patch_code_range` is mathematically strict and rejects invalid boundaries.

2. **Atomic Batch Patches:** When editing multiple locations in one file, pass all edits as a single `patches` list — the engine applies them bottom-up in one transaction, keeping all offsets stable. Never chain sequential single-byte edits across turns on the same file.

3. **No Manual Syntax Checks:** `patch_code_range` auto-validates syntax after every edit. If it introduces an error, the response includes a loud `WARNING`. No need to call `verify_ast_integrity` manually.

4. **Never Call `read_file` on Source Code:** Use `original_text_guard` from `get_entity_coordinates` — it contains the exact target text surgically. Loading an entire source file wastes >90% of your context budget on irrelevant code. ⚙️ *Engine-enforced: `read_file` appends a `⚠️ TOOL_USAGE_WARNING` when called on source files without a line range.*

5. **Always Pass `version_token`:** Take the `version_token` from `get_entity_coordinates` and pass it to `patch_code_range`. If the file changed between query and patch, the engine rejects immediately with a clear stale-coordinates error. ⚙️ *Engine-enforced.*

6. **Mandatory Turn-1 Batch Discovery:** Open every multi-entity refactor task with a single `batch_ast_query` bundling all `get_document_map`, `get_references`, and `get_entity_coordinates` calls. Chaining them sequentially causes quadratic prompt-history bloat — collapsing to 1 turn cuts token cost by 60–70%.

7. **Structured Checklist Persistence:** For multi-stage tasks, maintain a strict mental checklist and process sub-tasks sequentially. Never declare completion after only the first sub-task.

8. **Ultra-Brief Reasoning & Immediate Action:** Keep reasoning to 1–2 sentences max. Never write long explanations. Always output the tool call in the same turn as the reasoning.

9. **Coordinate-Only Scanning:** When performing global symbol renames, always call `get_references` with `"include_context": false` and `get_entity_coordinates` with `"include_content": false` during discovery turns. You only need raw coordinates to apply your batch patches, and suppressing the body/context strings saves thousands of tokens.
