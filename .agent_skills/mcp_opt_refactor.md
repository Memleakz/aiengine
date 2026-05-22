<tree_sitter_refactoring_protocol>
  <objective>
    Execute 100% precise, zero-regression code modifications utilizing AST S-expression queries and compile-guarded byte-level patching. Never guess or approximate coordinates.
  </objective>

  <immutable_laws>
    1. NEVER BREAK RULES TO SUCCEED: Task failure is ACCEPTABLE if tools fail. Bypassing tools using `sed`, `awk`, `perl`, or `echo` file rewrites is a FATAL ERROR.
    2. NEVER GUESS COORDINATES: LLMs are notoriously bad at counting characters. If an assertion fails, your coordinates are wrong. Stop and recalculate mechanically.
    3. STRICT TOOL SCHEMA: If a tool throws "unexpected keyword argument", read its schema and fix your JSON payload. Do not panic.
    4. TARGET ENTIRE STRUCTURAL BLOCKS: When rewriting or replacing an entire multi-line block or HTML tag element (e.g. <div class="opening-hours">...</div>), you MUST target the entire element node from the start tag to the closing tag inclusive. Do NOT target a substring or single line inside it, as that will leak original tags and duplicate nested items.
       - INDENTATION TIP: The replacement block must have consistent indentation relative to its first line. If the first line starts at the left margin (0 spaces), all nested lines must be indented relative to that first line (e.g. 4 spaces). Do NOT mix an unindented first line with heavily pre-indented nested lines (like 12 spaces), as the tool will shift the entire structure and cause double-indentation.
    5. NO CHARACTERS OUTSIDE THE QUERY: A Tree-sitter query string must start directly with `(` (or the node pattern). Never prefix it with `=`, `query=`, or wrap it in extra outer quotes.
    6. STRIP JSON ESCAPES: When searching for patterns using `coords` or `find_text`, never include JSON escaping backslashes like `\"` or `\\` in your search query unless the actual source file literally contains backslashes. Standard double quotes in HTML are just `"` in the search query. E.g. search for `class="menu-item1"`, NOT `class=\"menu-item1\"`.
    7. PREVENT CSS VS HTML CONFUSION: When targeting a block matching a class name (e.g. `.opening-hours` or `class="opening-hours"`), verify whether you are matching the CSS rule in the `<style>` block (which starts with a dot: `.opening-hours`) or the actual HTML tag element (which matches `class="opening-hours"` or `<div class="opening-hours">`). Never confuse them, and verify the surrounding context lines using the `read` action before patching!
    8. MANDATORY PATCH_CODE_RANGE PARAMETERS: You MUST ALWAYS include the `"start_byte"`, `"end_byte"`, `"filepath"`, and `"replacement"` parameters when calling `patch_code_range`. Omitting `start_byte` is a fatal tool invocation failure. Always check that all 4 properties are present in your JSON payload before sending.
    9. TRUST COORDS LINE NUMBERS: When `coords` returns `LINE: <line_number>`, this is the absolute ground-truth line number of where that pattern resides in the file. You MUST use this exact `LINE` number as the parameter for any subsequent `read` action. Never guess or estimate line numbers!
    10. NO BATCH COORDINATES: NEVER query coordinates for multiple occurrences or future steps up front before applying the current patch. Since every patch modifies the file and shifts all subsequent byte offsets, all pre-calculated coordinates will instantly become invalid. You must query coordinates, verify original text, and apply the patch for EXACTLY ONE occurrence at a time. Only query the next occurrence AFTER the previous patch has been fully committed!
  </immutable_laws>

  <advanced_query_syntax>
    Maximize query precision using Tree-Sitter operators:
    - Alternation `[]`: Match one of multiple types. E.g., `[(identifier) (member_expression)] @target`
    - Predicates `#eq?` / `#match?`: Exact string or regex match. E.g., `(#eq? @target "timeout")`
  </advanced_query_syntax>

  <few_shot_examples>
    <example>
      <intent>Find the 'src' attribute value of an HTML 'img' tag</intent>
      <correct_tool_call_payload>
        {
          "project": ".",
          "query": "(element (start_tag (tag_name) @tag (#eq? @tag \"img\") (attribute (attribute_name) @attr (#eq? @attr \"src\") (quoted_attribute_value) @target)))"
        }
      </correct_tool_call_payload>
      <note>Note how inner double quotes inside predicates are escaped as \\" in the JSON string.</note>
    </example>
    <example>
      <intent>Find the ENTIRE 'opening-hours' div tag element structurally in HTML (from start tag to end tag inclusive)</intent>
      <correct_tool_call_payload>
        {
          "project": ".",
          "query": "(element (start_tag (tag_name) @tag (#eq? @tag \"div\") (attribute (attribute_name) @attr (#eq? @attr \"class\") (quoted_attribute_value) @class_val (#eq? @class_val \"\\\"opening-hours\\\"\")))) @target"
        }
      </correct_tool_call_payload>
      <note>Note how double quotes for class values are double-escaped as \\\"opening-hours\\\" inside the query string's JSON representation.</note>
    </example>
  </few_shot_examples>

  <fallback_coordinate_calculator>
    If S-expression queries fail or are not available, DO NOT GUESS OR ESTIMATE bytes. Use the native `coords` action in the `bash` tool.
    
    HOW TO TARGET A SINGLE-LINE SUBSTRING:
    Invoke the `bash` tool with:
    {
      "action": "coords",
      "filepath": "<FILEPATH>",
      "start_line": <LINE_NUMBER>,
      "command": "<PATTERN>"
    }
    This returns: `START: <start_byte>, END: <end_byte>, LINE: <line_number>`. Use this `LINE` number for subsequent `read` actions and calculations.

    HOW TO TARGET A MULTI-LINE STRUCTURAL BLOCK (e.g. <div class="opening-hours">...</div>):
    Since `coords` operates line-by-line, passing a multi-line pattern to `coords` will ALWAYS fail. Instead, compute the start and end of the block separately:
    1. Get the START byte and exact START LINE of the start tag:
       Call `coords` with `start_line` set to a search start line (e.g. `1`), and `command` set to the exact start tag text (e.g. `"<div class=\"class_name\">"`). This returns `START: <start_byte>, END: ..., LINE: <start_line>`. Save this `<start_byte>` as your block's `start_byte` and `<start_line>` as your block's `start_line`.
    2. Get the END byte and exact END LINE of the closing tag:
       Call `coords` with `start_line` set to `<start_line>` (your block's start line), and `command` set to the exact closing tag text (e.g. `"</div>"`). This returns `START: <close_tag_start>, END: ..., LINE: <end_line>`.
       Since `coords` matches the start of `"</div>"`, the block's `end_byte` is `<close_tag_start>` + the byte-length of the closing tag (e.g. 6 bytes for `"</div>"`).
    3. Read the exact text within the verified block boundaries:
       Call the `read` action on the `bash` tool from `<start_line>` to `<end_line>` to verify the `original_text`.
    4. Set `start_byte` and `end_byte` in `patch_code_range` to these exact calculated values.
  </fallback_coordinate_calculator>

  <coordinate_translation_via_coords>
    Tree-Sitter queries return 0-based `row` and `column` coordinates (e.g. `start: {row: 19, column: 8}, end: {row: 23, column: 14}`).
    To translate these to absolute bytes without executing Python, use the native `coords` action in the `bash` tool:
    
    1. Translate the 0-based `row` to a 1-indexed line number: `line_number = row + 1` (e.g. `19 + 1 = 20`).
    2. Get the START byte offset and exact line:
       Call `coords` with `start_line` set to `row + 1` (e.g. `20`), and `command` set to the exact start tag/text at that line (e.g. `"<div class=\"class_name\">"`). This returns `START: <start_byte>, END: ..., LINE: <start_line>`. Save this as your `start_byte` and `start_line`.
    3. Get the END byte offset and exact line:
       Call `coords` with `start_line` set to `end.row + 1` (e.g. `24`), and `command` set to the exact closing tag/text at that line (e.g. `"</div>"`). This returns `START: <close_tag_start>, END: ..., LINE: <end_line>`.
       The block's `end_byte` is `<close_tag_start>` + the byte-length of the closing pattern (e.g. 6 bytes for `"</div>"`).
  </coordinate_translation_via_coords>

  <retrieve_original_text_via_read>
    Before calling `patch_code_range`, you MUST verify the exact text inside the target block to set as `original_text`.
    To read the exact block content natively without running Python:
    Call the `bash` tool with:
    {
      "action": "read",
      "filepath": "<FILEPATH>",
      "start_line": <START_LINE>,
      "end_line": <END_LINE>
    }
    This will print the exact lines. Set this printed string as the `original_text` parameter of your `patch_code_range` tool call. This guarantees a perfect match, preventing any Range Verification errors!
  </retrieve_original_text_via_read>

  <workflow>
    <step num="1" name="ISOLATE">
      Attempt to use an S-expression query to capture (`@target`) the exact element block or leaf node.
      - CRITICAL: If the query fails with a syntax error (e.g. invalid syntax at row 0, column 0), immediately abandon Tree-sitter queries and use the `<fallback_coordinate_calculator>`'s native `coords` action in the `bash` tool to locate the coordinates!
      - If targeting a substring inside a larger string (like HTML classes or attribute values), immediately use the `<fallback_coordinate_calculator>`.
    </step>
    
    <step num="2" name="CALCULATE_ABSOLUTE_BYTES">
      Obtain the exact absolute byte range for the target element using only native internal tools:
      - If using `coords` action in the `bash` tool: Use the returned START and END directly.
      - If using Tree-sitter `run_query` or `get_ast`: Get the 0-based `row`/`column` coordinates, and then use the steps in `<coordinate_translation_via_coords>` with the `coords` action to translate them to the exact absolute `start_byte` and `end_byte`.
      - CRITICAL: Never guess or estimate the byte range! Always compute it using the `coords` action.
    </step>

    <step num="3" name="VERIFY_AND_EXECUTE_PATCH">
      Read the exact content at the calculated byte range to use as the `original_text` parameter:
      - Call the `bash` tool with action `read` as outlined in `<retrieve_original_text_via_read>` to print the exact content at the line numbers.
      - Call `patch_code_range` using the calculated absolute byte offsets from step 2.
      - ALWAYS set `original_text` to the exact content printed by the `read` action. This acts as an active validation guard.
      - Set `start_byte` and `end_byte` to the exact calculated byte offsets.
    </step>

    <step num="4" name="ITERATE">
      For global replacements or multi-step edits, you must repeat Steps 1-3 for EACH occurrence.
      - IMPORTANT: Each patch changes the file length, causing all subsequent absolute byte offsets to shift.
      - CRITICAL REVERSE-ORDER OPTIMIZATION: To prevent byte shifts from invalidating subsequent coordinates, you can query and calculate all coordinates up front, and then apply the patches in REVERSE ORDER (from the bottom of the file to the top of the file). Because modifying a line at the bottom does not affect the byte offsets of lines above it, all pre-calculated coordinates for preceding lines remain 100% stable, accurate, and valid!
      - If not using reverse-order patching, you MUST re-query the coordinates (Step 2) and re-verify the original text (Step 3) for every single occurrence AFTER each edit. Never reuse coordinates calculated prior to a file modification!
      - EFFICIENCY OPTIMIZATION: Do NOT call `find_text` or search tools repeatedly to verify that a pattern is gone if you have already patched all occurrences found in your initial search. Trust your work and proceed directly to the next task to conserve conversational iterations.
    </step>
  </workflow>
</tree_sitter_refactoring_protocol>