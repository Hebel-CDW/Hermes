"""Secure document intake: validation, governance metadata, encrypted storage and text extraction.

Malware scanning is an adapter: the default reports ``not_scanned`` honestly (no scanner is wired in
this prototype). OCR is not performed; image-only PDFs are reported as ``needs_ocr``.
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import zipfile
import zlib
from pathlib import Path
from typing import Optional, Protocol, Tuple

from hoi.crypto import cipher
from shared.errors import HermesError

MAX_BYTES = 10 * 1024 * 1024
MAX_UNZIPPED = 50 * 1024 * 1024
MAX_STREAM_INFLATE = 20 * 1024 * 1024   # one PDF stream may not inflate beyond this
MAX_PDF_INFLATE = 40 * 1024 * 1024      # nor all streams of one PDF together
MAX_TEXT_CHARS = 2_000_000              # extracted text beyond this is refused, not truncated silently
DOC_TYPES = ("rfp", "sow", "jd")
EXTENSIONS = (".pdf", ".docx", ".txt")
MIME = {".pdf": "application/pdf", ".txt": "text/plain",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
_BAD_MAGIC = (b"MZ", b"\x7fELF", b"#!", b"\xca\xfe\xba\xbe", b"\xcf\xfa\xed\xfe")
_PDF_ACTIVE = (b"/JavaScript", b"/JS ", b"/Launch", b"/EmbeddedFile", b"/RichMedia")


class DocumentRejected(HermesError):
    code = "document_rejected"
    http_status = 422


class MalwareScanner(Protocol):
    def scan(self, data: bytes) -> str: ...


class NotConfiguredScanner:
    """Honest placeholder: enterprise AV/DLP integration is pending."""

    def scan(self, data: bytes) -> str:
        return "not_scanned"


_scanner: MalwareScanner = NotConfiguredScanner()


def set_scanner(scanner: MalwareScanner) -> None:
    global _scanner
    _scanner = scanner


def scan(data: bytes) -> str:
    return _scanner.scan(data)


def safe_filename(name: str) -> str:
    base = os.path.basename(name.replace("\\", "/")).strip()
    base = re.sub(r"[^A-Za-z0-9._ -]", "_", base)[:120]
    if not base or base.startswith("."):
        raise DocumentRejected("filename is not acceptable")
    return base


def validate_upload(filename: str, data: bytes, doc_type: str) -> Tuple[str, str]:
    """Return (safe_filename, extension) or raise DocumentRejected."""
    if doc_type not in DOC_TYPES:
        raise DocumentRejected(f"doc_type must be one of {list(DOC_TYPES)}")
    name = safe_filename(filename)
    ext = os.path.splitext(name)[1].lower()
    if ext not in EXTENSIONS:
        raise DocumentRejected(f"unsupported file type; allowed: {list(EXTENSIONS)}")
    if not data:
        raise DocumentRejected("file is empty")
    if len(data) > MAX_BYTES:
        raise DocumentRejected(f"file exceeds {MAX_BYTES // (1024 * 1024)} MB")
    if data.startswith(_BAD_MAGIC):
        raise DocumentRejected("file content does not match an allowed document type")
    if ext == ".pdf":
        if not data.startswith(b"%PDF-"):
            raise DocumentRejected("file content is not a PDF")
        if any(tok in data for tok in _PDF_ACTIVE):
            raise DocumentRejected("PDF contains active or embedded content")
    elif ext == ".docx":
        _check_docx(data)
    else:
        if b"\x00" in data[:4096]:
            raise DocumentRejected("text file contains binary content")
    return name, ext


def _check_docx(data: bytes) -> None:
    if not data.startswith(b"PK\x03\x04"):
        raise DocumentRejected("file content is not a DOCX")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = z.namelist()
            if "word/document.xml" not in names:
                raise DocumentRejected("DOCX has no document body")
            if any("vbaProject" in n or n.lower().endswith((".exe", ".dll", ".bin")) and "embeddings" in n for n in names):
                raise DocumentRejected("DOCX contains macros or embedded binaries")
            if sum(i.file_size for i in z.infolist()) > MAX_UNZIPPED:
                raise DocumentRejected("DOCX expands beyond the allowed size")
    except zipfile.BadZipFile as exc:
        raise DocumentRejected("DOCX is corrupt") from exc


def storage_root() -> Path:
    root = Path(os.getenv("HOI_STORAGE_DIR") or Path(__file__).resolve().parents[2] / "data" / "hoi_storage")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root


def checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def store_encrypted(opportunity_id: str, document_id: str, data: bytes) -> str:
    d = storage_root() / opportunity_id
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = d / f"{document_id}.enc"
    path.write_bytes(cipher("doc").encrypt(data))
    os.chmod(path, 0o600)
    return f"hoi-store://{opportunity_id}/{document_id}.enc"


def load_decrypted(uri: str) -> bytes:
    if not uri.startswith("hoi-store://"):
        raise DocumentRejected("unknown storage reference")
    rel = uri[len("hoi-store://"):]
    path = (storage_root() / rel).resolve()
    if storage_root().resolve() not in path.parents:
        raise DocumentRejected("storage reference escapes the store")
    return cipher("doc").decrypt(path.read_bytes())


# ------------------------------------------------------------------ text extraction
def extract_text(ext: str, data: bytes) -> Tuple[str, str]:
    """Return (text, status) with status ok | needs_ocr | empty."""
    if ext == ".txt":
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("cp1252", errors="replace")
    elif ext == ".docx":
        text = _docx_text(data)
    else:
        text = _pdf_text(data)
        if len(text.strip()) < 20:
            return "", "needs_ocr"
    if len(text) > MAX_TEXT_CHARS:
        raise DocumentRejected(f"document text exceeds {MAX_TEXT_CHARS:,} characters")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return (text, "ok") if text.strip() else ("", "empty")


def _unescape_xml(s: str) -> str:
    return (s.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
            .replace("&apos;", "'").replace("&amp;", "&"))


def _docx_text(data: bytes) -> str:
    # Regex, not an XML parser: untrusted XML never reaches an entity-expanding parser.
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        xml = z.read("word/document.xml").decode("utf-8", errors="replace")
    out = []
    for para in re.findall(r"<w:p[ >].*?</w:p>", xml, flags=re.S):
        para = re.sub(r"</w:tc>", " | ", para)
        para = re.sub(r"<w:(?:tab|br)\s*/>", " ", para)
        runs = re.findall(r"<w:t(?: [^>]*)?>(.*?)</w:t>|( \| )", para, flags=re.S)
        out.append(_unescape_xml("".join(a or b for a, b in runs)).strip(" |"))
    return "\n".join(out)


def _pdf_text(data: bytes) -> str:
    try:  # preferred when installed
        from pypdf import PdfReader  # type: ignore

        return "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages)
    except ImportError:
        pass
    except Exception:  # noqa: BLE001 - corrupt PDF: fall through to best effort
        return ""
    chunks = []
    budget = MAX_PDF_INFLATE
    for m in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, flags=re.S):
        raw = m.group(1)
        raw, budget = _inflate_bounded(raw, budget)
        for t in re.finditer(rb"\((.*?)(?<!\\)\)\s*Tj|\[(.*?)\]\s*TJ", raw, flags=re.S):
            if t.group(1) is not None:
                chunks.append(_pdf_unescape(t.group(1)))
            else:
                chunks.append("".join(_pdf_unescape(s) for s in re.findall(rb"\((.*?)(?<!\\)\)", t.group(2), flags=re.S)))
        chunks.append("\n")
    return "\n".join(c for c in "".join(c if c.endswith("\n") else c + "\n" for c in chunks).split("\n") if c.strip())


def _inflate_bounded(raw: bytes, budget: int):
    """Inflate one PDF stream with hard limits (a few-KB 'zip bomb' PDF must never expand into memory unbounded).
    Streams that are not zlib data are returned as-is. Returns (data, remaining_budget)."""
    d = zlib.decompressobj()
    cap = min(MAX_STREAM_INFLATE, budget)
    try:
        out = d.decompress(raw, cap + 1)
    except zlib.error:
        return raw, budget
    if len(out) > cap or d.unconsumed_tail:
        raise DocumentRejected("PDF expands beyond the allowed size")
    return out, budget - len(out)


def _pdf_unescape(b: bytes) -> str:
    s = b.decode("latin-1")
    s = re.sub(r"\\([nrt()\\])", lambda m: {"n": "\n", "r": "\r", "t": "\t"}.get(m.group(1), m.group(1)), s)
    return s
