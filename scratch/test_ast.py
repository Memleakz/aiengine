import sys
import os
sys.path.insert(0, "/home/tobias/dev/Repo/aiengine/src")
import tree_sitter_language_pack as tslp

html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Polyglot Challenge</title>
    <style>
        .old-button { padding: 10px 20px; color: #fff; background: #007bff; }
    </style>
</head>
<body>
    <button class="old-button" id="submitBtn">Submit</button>
    <div class="contact-card">
        <h3>Contact Support</h3>
        <p>Email: support@dailygrind.com</p>
    </div>
</body>
</html>"""

parser = tslp.get_parser("html")
tree = parser.parse(html.encode("utf-8"))

def walk(node, depth=0):
    indent = "  " * depth
    text_preview = node.text.decode("utf-8")[:30].replace("\n", "\\n")
    print(f"{indent}{node.type} [{node.start_byte}-{node.end_byte}]: {text_preview}")
    for child in node.children:
        walk(child, depth + 1)

print("HTML AST:")
walk(tree.root_node)

print("\n--- Testing style content ---")
# Find style element
style_element = None
def find_style(node):
    global style_element
    if node.type == "style_element":
        style_element = node
        return
    for child in node.children:
        find_style(child)

find_style(tree.root_node)
if style_element:
    print("Found style element!")
    for child in style_element.children:
        print(f"Child: {child.type} [{child.start_byte}-{child.end_byte}]: {child.text.decode('utf-8')[:30].replace('\n', '\\n')}")
        if child.type in ("raw_text", "text"):
            print("Parsing with CSS parser:")
            css_parser = tslp.get_parser("css")
            css_tree = css_parser.parse(child.text)
            def walk_css(css_node, css_depth=0):
                css_indent = "  " * css_depth
                print(f"{css_indent}{css_node.type} [{css_node.start_byte}-{css_node.end_byte}]: {css_node.text.decode('utf-8')[:30].replace('\n', '\\n')}")
                for css_child in css_node.children:
                    walk_css(css_child, css_depth + 1)
            walk_css(css_tree.root_node)
else:
    print("Style element not found!")
