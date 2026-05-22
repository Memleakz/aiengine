# Budget Coords & AST Protocol
Follow these 4 laws strictly using minimal context and action-oriented tool calls:

1. **Law of Scoped Block-Replacement:** Instead of renaming variables or patching lines one-by-one (which takes 6+ turns and times out), always target the **entire method block** (from `def method_name` to the final line of its return). Query the method's `start_byte` and `end_byte` boundaries, read it, perform all edits in a single turn, and replace the entire method body at once using `patch_code_range`.
2. **Law of Scoped Class-End Injection:** To insert a sibling method at the end of a class, query the `end_byte` of the parent class definition node from the AST structure. Then call `patch_code_range` with `start_byte = class_end_byte`, `end_byte = class_end_byte`, and `override_base_indent = 4`.
3. **Law of Multi-Turn Coordinate Transition:** Never cache or reuse coordinates across different *edit operations*. However, since the engine executes one tool call per turn, you must query coordinates in Turn N and immediately execute `patch_code_range` in Turn N+1 using those exact coordinates.
4. **Action-First Protocol:** Keep text thinking/reasoning extremely brief (1 sentence max) and output the tool call immediately.
