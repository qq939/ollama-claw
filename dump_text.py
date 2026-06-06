import pypdf
r = pypdf.PdfReader(r"C:\Users\qq939\Downloads\ollama-claw\openclaw-gateway-pairing-notes.pdf")
out = []
for i, p in enumerate(r.pages):
    out.append(f"===== PAGE {i+1} =====")
    out.append(p.extract_text())
open(r"C:\Users\qq939\Downloads\ollama-claw\pdf_text_dump.txt", "w", encoding="utf-8").write("\n".join(out))
print("wrote pdf_text_dump.txt, total pages:", len(r.pages))
