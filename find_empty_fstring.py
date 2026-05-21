import re

with open('./control/app.py', 'r', encoding='utf-8') as f:
    content = f.read()

lines = content.split('\n')
for i, line in enumerate(lines, 1):
    if 'f"' in line or "f'" in line:
        matches = re.findall(r'\{[^}]*\}', line)
        for m in matches:
            if m == '{}' or m == '{ }':
                print(f"Line {i}: {line.strip()}")
                break