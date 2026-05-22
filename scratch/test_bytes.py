with open("demosite/index.html", "rb") as f:
    lines = f.readlines()

def get_byte_offset(row, col):
    return sum(len(lines[i]) for i in range(row)) + col

# Opening hours div:
# Start: row 28, column 8
# End: row 32, column 14

start_byte = get_byte_offset(28, 8)
end_byte = get_byte_offset(32, 14)

print(f"Calculated: start_byte={start_byte}, end_byte={end_byte}")

with open("demosite/index.html", "rb") as f:
    content = f.read()

print("Extracted content:")
print(repr(content[start_byte:end_byte].decode("utf-8")))
