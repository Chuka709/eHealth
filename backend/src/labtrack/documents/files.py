"""What an uploaded file is, checked from its content and made safe to keep (Phase 3.2; docs/04
"Файл: python-magic, хэмжээ, хуудас, PDF JS/embedded хаах").

- The type comes from the bytes (libmagic), never from the name or the client's header.
- PDF: opened with PDFium; refused when encrypted, scripted (document JavaScript), carrying
  attachments, or longer than MAX_PAGES. Kept as uploaded (the original is the record).
- Images (JPEG, PNG, WebP, HEIC): decoded with a pixel cap (decompression bombs), turned
  upright from EXIF, and re-encoded without any metadata (EXIF carries GPS and the phone).
  HEIC becomes JPEG so every later step reads one of a few formats.
Errors carry a code only - never a value from the file (CLAUDE.md rule 3).
"""

import hashlib
import io
import re
import threading
import zlib
from dataclasses import dataclass
from typing import Final

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

register_heif_opener()

MAX_BYTES: Final = 20 * 1024 * 1024
MAX_PAGES: Final = 20
MAX_PIXELS: Final = 30_000_000  # a 12 MP phone photo is ~12M; a bomb is far beyond
TEXT_CHARS: Final = 20  # a few characters on a page: a text layer, not a scan
_IMAGE_FORMATS: Final = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
    "image/heic": "HEIF",
    "image/heif": "HEIF",
}
# PDF names that run or fetch something; looked for in the file and in every stream it packs
# (object streams hide dictionaries). Links (/URI) are allowed: lab PDFs carry them.
_UNSAFE_PDF: Final = re.compile(
    rb"/(JavaScript|JS|Launch|XFA|RichMedia|EmbeddedFiles?|SubmitForm|ImportData|GoToE|GoToR"
    rb"|Movie|Sound|Rendition)\b"
)
# a stream's data runs to the first "endstream" (with or without the end-of-line before it)
_STREAM: Final = re.compile(rb"stream\r?\n(.*?)endstream", re.DOTALL)
_HEX_NAME: Final = re.compile(rb"#([0-9A-Fa-f]{2})")
_INFLATED_MAX: Final = 64 * 1024 * 1024  # a packed stream bigger than this is refused
# PDFium is not thread-safe: one file at a time in this process (security review 3.2)
_PDFIUM: Final = threading.Lock()
# set once for the process: Pillow refuses (DecompressionBombError) at twice this
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


class FileRejectedError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class CheckedFile:
    data: bytes  # what is stored: the PDF as uploaded, an image re-encoded without metadata
    mime_type: str
    sha256: str  # of the uploaded bytes: the same file twice is one document
    page_count: int
    has_text_layer: bool | None


def check(data: bytes) -> CheckedFile:
    if not data:
        raise FileRejectedError("document.empty")
    if len(data) > MAX_BYTES:
        raise FileRejectedError("document.too_large")
    # imported here: libmagic exists in the containers; Windows dev tools (openapi, mypy) that
    # import the app must not load it (python-magic crashed there on a stray DLL)
    import magic  # noqa: PLC0415

    sniffed = magic.from_buffer(data[:8192], mime=True)
    digest = hashlib.sha256(data).hexdigest()
    if sniffed == "application/pdf":
        pages, text = _check_pdf(data)
        return CheckedFile(data, "application/pdf", digest, pages, text)
    if sniffed in _IMAGE_FORMATS:
        cleaned, mime = _clean_image(data, _IMAGE_FORMATS[sniffed])
        return CheckedFile(cleaned, mime, digest, 1, None)
    raise FileRejectedError("document.unsupported_type")


def _names(raw: bytes) -> bytes:
    """PDF names may spell a character as #xx (/Java#53cript is /JavaScript): decoded first."""
    return _HEX_NAME.sub(lambda m: bytes([int(m.group(1), 16)]), raw)


def _unsafe_pdf(data: bytes) -> bool:
    """Unsafe names in the PDF's structure: the file outside its streams, and the inside of
    object streams (/ObjStm), which pack dictionaries. Other streams (page content, images,
    fonts) are data - a name there means nothing and would refuse real lab PDFs."""
    if _UNSAFE_PDF.search(_names(_STREAM.sub(b"stream endstream", data))):
        return True
    budget = _INFLATED_MAX
    for match in _STREAM.finditer(data):
        # this stream's own dictionary: from its "obj" keyword, however long it is
        header = _names(data[data.rfind(b"obj", 0, match.start()) : match.start()])
        if b"/ObjStm" not in header:
            continue
        inflater = zlib.decompressobj()
        try:
            chunk = inflater.decompress(match.group(1), budget + 1)
        except zlib.error:
            return True  # an object stream that cannot be read is not accepted
        budget -= len(chunk)
        if budget < 0:
            return True  # a zip bomb of a PDF
        if _UNSAFE_PDF.search(_names(chunk)):
            return True
    return False


def _check_pdf(data: bytes) -> tuple[int, bool]:
    if _unsafe_pdf(data):
        raise FileRejectedError("document.pdf_unsafe")
    with _PDFIUM:
        return _read_pdf(data)


def _read_pdf(data: bytes) -> tuple[int, bool]:
    try:
        pdf = pdfium.PdfDocument(data)
    except pdfium.PdfiumError as exc:
        # a password-protected file cannot be read without it
        raise FileRejectedError(
            "document.pdf_encrypted" if "password" in str(exc).lower() else "document.unreadable"
        ) from exc
    try:
        # a count PDFium cannot give (-1) is refused too
        if pdfium_c.FPDFDoc_GetJavaScriptActionCount(pdf.raw) != 0:
            raise FileRejectedError("document.pdf_unsafe")
        if pdfium_c.FPDFDoc_GetAttachmentCount(pdf.raw) != 0:
            raise FileRejectedError("document.pdf_unsafe")
        pages = len(pdf)
        if pages < 1:
            raise FileRejectedError("document.unreadable")
        if pages > MAX_PAGES:
            raise FileRejectedError("document.too_many_pages")
        text = False
        for index in range(min(pages, 3)):
            page = pdf[index]
            textpage = page.get_textpage()
            try:
                if textpage.count_chars() > TEXT_CHARS:
                    text = True
                    break
            finally:
                textpage.close()
                page.close()
        return pages, text
    finally:
        pdf.close()


def _clean_image(data: bytes, fmt: str) -> tuple[bytes, str]:
    try:
        # only the format libmagic saw: no other Pillow plugin parses the bytes
        opened = Image.open(io.BytesIO(data), formats=[fmt])
    except Image.DecompressionBombError as exc:  # a header far beyond the pixel cap
        raise FileRejectedError("document.too_large") from exc
    except (OSError, ValueError, SyntaxError) as exc:
        raise FileRejectedError("document.unreadable") from exc
    with opened:
        width, height = opened.size
        if width * height > MAX_PIXELS:  # before any pixel is decoded
            raise FileRejectedError("document.too_large")
        upright = _decode(opened)
    out = io.BytesIO()
    if fmt == "PNG":
        # a fresh image (a palette turned into colours first): no text chunks, no EXIF
        source = upright.convert(
            "RGBA" if "A" in upright.getbands() or "transparency" in upright.info else "RGB"
        )
        clean = Image.new(source.mode, source.size)
        clean.paste(source)
        clean.save(out, format="PNG", optimize=True)
        return out.getvalue(), "image/png"
    upright.convert("RGB").save(out, format="JPEG", quality=90, optimize=True)  # no EXIF kept
    return out.getvalue(), "image/jpeg"


def _decode(opened: Image.Image) -> Image.Image:
    try:
        opened.load()
        return ImageOps.exif_transpose(opened)
    except Image.DecompressionBombError as exc:
        raise FileRejectedError("document.too_large") from exc
    except (OSError, ValueError, SyntaxError) as exc:
        raise FileRejectedError("document.unreadable") from exc
