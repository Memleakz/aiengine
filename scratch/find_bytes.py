with open("demosite/index.html", "rb") as f:
    content = f.read()

idx = 0
while True:
    idx = content.find(b"Vanilla Latte", idx)
    if idx == -1:
        break
    print(f"Found 'Vanilla Latte' at byte offset: {idx} to {idx + 13}")
    idx += 13
