import hashlib
from pathlib import Path
import pypdf
import docx


def parse_pdf(file_bytes: bytes) -> str:
    import io
    reader = pypdf.PdfReader(io.BytesIO(file_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def parse_docx(file_bytes: bytes) -> str:
    import io
    doc = docx.Document(io.BytesIO(file_bytes))
    return "\n".join(para.text for para in doc.paragraphs if para.text.strip())


def parse_txt(file_bytes: bytes) -> str:
    return file_bytes.decode("utf-8", errors="replace")


def parse_html(content: str) -> str:
    import html2text
    h = html2text.HTML2Text()
    h.ignore_links = False
    return h.handle(content)


def parse_document(filename: str, file_bytes: bytes) -> str:
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        return parse_pdf(file_bytes)
    elif ext == ".docx":
        return parse_docx(file_bytes)
    elif ext in (".html", ".htm"):
        return parse_html(file_bytes.decode("utf-8", errors="replace"))
    else:
        return parse_txt(file_bytes)


def hash_content(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]
