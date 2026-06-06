import pypdf
r = pypdf.PdfReader(r"C:\Users\qq939\Downloads\ollama-claw\openclaw-gateway-pairing-notes.pdf")
print("Pages:", len(r.pages))
for i, p in enumerate(r.pages):
    print(f"--- page {i+1} ---")
    fonts = p.get("/Resources", {}).get("/Font", {})
    if hasattr(fonts, "keys"):
        for fk in fonts.keys():
            f = fonts[fk]
            print(f"  font: {fk} -> {dict(f) if hasattr(f, '__getitem__') else f}")
