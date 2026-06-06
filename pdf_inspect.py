import pdfplumber
with pdfplumber.open(r"C:\Users\qq939\Downloads\ollama-claw\openclaw-gateway-pairing-notes.pdf") as pdf:
    for i, page in enumerate(pdf.pages):
        chars = page.chars
        print(f"page {i+1}: {len(chars)} chars, {len(set(c['fontname'] for c in chars))} fonts")
        fonts = {}
        for c in chars:
            fn = c["fontname"]
            fonts.setdefault(fn, []).append(c["text"])
        for fn, ts in fonts.items():
            sample = "".join(ts[:5])
            print(f"  font={fn!r}  total={len(ts)}  sample={sample!r}")
