import sys
try:
    import reportlab
    print("reportlab", reportlab.__version__)
except ImportError as e:
    print("no reportlab:", e)
try:
    import fpdf
    print("fpdf", fpdf.__version__)
except ImportError as e:
    print("no fpdf:", e)
try:
    import markdown
    print("markdown", markdown.__version__)
except ImportError as e:
    print("no markdown:", e)
try:
    import weasyprint
    print("weasyprint", weasyprint.__version__)
except ImportError as e:
    print("no weasyprint:", e)
print("python", sys.version)
