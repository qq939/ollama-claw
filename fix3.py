with open('./control/app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the indentation issue
old = '''def send_openclaw_message(container, message):
        import base64
        labels = ((getattr(container, "attrs", {}) or {}).get("Config", {}) or {}).get("Labels", {}) or (getattr(container, "labels", {}) or {})'''

new = '''def send_openclaw_message(container, message):
    import base64
    labels = ((getattr(container, "attrs", {}) or {}).get("Config", {}) or {}).get("Labels", {}) or (getattr(container, "labels", {}) or {})'''

if old in content:
    content = content.replace(old, new)
    print("Fixed indentation")
else:
    print("Pattern not found")

# Also fix subsequent lines that need 4 spaces instead of 8
# The function body should start with 4 spaces, not 8
import re
# Pattern to find the entire function and fix it
pattern = r'(def send_openclaw_message\(container, message\):\n    import base64\n    labels = ((getattr\(container, "attrs", \{\}\) or \{\}\)\.get\("Config", \{\}\) or \{\}\)\.get\("Labels", \{\}\) or \{\}\))'

with open('./control/app.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done")