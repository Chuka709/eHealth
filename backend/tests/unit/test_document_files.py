"""What an upload is, from its bytes (Phase 3.2; documents/files.py). Runs where libmagic is
(the test container)."""

import io

import pypdfium2 as pdfium
import pytest
from PIL import Image

from labtrack.documents.files import MAX_BYTES, MAX_PAGES, FileRejectedError, check


def _pdf(pages: int = 1) -> bytes:
    doc = pdfium.PdfDocument.new()
    for _ in range(pages):
        doc.new_page(595, 842)
    out = io.BytesIO()
    doc.save(out)
    doc.close()
    return out.getvalue()


def _raw_pdf(objects: list[str]) -> bytes:
    """A PDF from object bodies (1-based), with a correct xref table."""
    out = b"%PDF-1.7\n"
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return out


def _scripted_pdf() -> bytes:
    return _raw_pdf(
        [
            "<< /Type /Catalog /Pages 2 0 R /Names << /JavaScript 4 0 R >> >>",
            "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] >>",
            "<< /Names [(run) 5 0 R] >>",
            "<< /S /JavaScript /JS (app.alert\\('x'\\)) >>",
        ]
    )


def _truncated_png() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (64, 64), "white").save(out, format="PNG")
    return out.getvalue()[:60]  # the header says PNG; the image data is cut off


def _jpeg_with_location() -> bytes:
    image = Image.new("RGB", (40, 20), "white")
    exif = Image.Exif()
    exif[0x0112] = 6  # orientation: rotate 90 to be upright
    exif[0x010F] = "PhoneMaker"
    gps = exif.get_ifd(0x8825)
    gps[2] = (47.0, 55.0, 0.0)  # latitude
    out = io.BytesIO()
    image.save(out, format="JPEG", exif=exif)
    return out.getvalue()


def test_a_pdf_is_kept_as_uploaded_with_its_pages() -> None:
    data = _pdf(3)
    checked = check(data)
    assert (checked.mime_type, checked.page_count, checked.data) == ("application/pdf", 3, data)
    assert checked.has_text_layer is False  # blank pages: a scan, not text
    assert len(checked.sha256) == 64


def test_a_scripted_pdf_is_refused() -> None:
    with pytest.raises(FileRejectedError) as err:
        check(_scripted_pdf())
    assert err.value.code == "document.pdf_unsafe"


def test_too_many_pages_are_refused() -> None:
    with pytest.raises(FileRejectedError) as err:
        check(_pdf(MAX_PAGES + 1))
    assert err.value.code == "document.too_many_pages"


def test_a_photo_loses_its_metadata_and_stands_upright() -> None:
    checked = check(_jpeg_with_location())
    assert checked.mime_type == "image/jpeg"
    with Image.open(io.BytesIO(checked.data)) as cleaned:
        assert cleaned.size == (20, 40)  # turned by its EXIF orientation
        assert not cleaned.getexif()  # no GPS, no maker, nothing


def test_a_png_keeps_its_format_without_text_chunks() -> None:
    image = Image.new("RGBA", (10, 10))
    out = io.BytesIO()
    from PIL import PngImagePlugin  # noqa: PLC0415

    info = PngImagePlugin.PngInfo()
    info.add_text("Comment", "patient name")
    image.save(out, format="PNG", pnginfo=info)
    checked = check(out.getvalue())
    assert checked.mime_type == "image/png"
    with Image.open(io.BytesIO(checked.data)) as cleaned:
        assert "Comment" not in cleaned.info


@pytest.mark.parametrize(
    ("data", "code"),
    [
        (b"", "document.empty"),
        (b"<html><script>x</script></html>", "document.unsupported_type"),
        (b"%PDF-1.7\nnot really", "document.unreadable"),
        (_truncated_png(), "document.unreadable"),
        (b"%PDF" + b"\x00" * MAX_BYTES, "document.too_large"),
    ],
)
def test_odd_files_are_refused_with_a_code(data: bytes, code: str) -> None:
    with pytest.raises(FileRejectedError) as err:
        check(data)
    assert err.value.code == code


def test_the_name_never_decides_the_type() -> None:
    """A text file called scan.pdf is text: only the content counts."""
    with pytest.raises(FileRejectedError):
        check(b"plain text pretending to be a pdf")


def _catalog_pdf(extra: str) -> bytes:
    return _raw_pdf(
        [
            f"<< /Type /Catalog /Pages 2 0 R {extra} >>",
            "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] >>",
        ]
    )


@pytest.mark.parametrize(
    "extra",
    [
        r"/OpenAction << /S /JavaScript /JS (app.alert\(1\)) >>",
        "/OpenAction << /S /Launch /F (calc.exe) >>",
        "/AcroForm << /XFA [] >>",
        "/AA << /WC << /S /SubmitForm /F (https://example.invalid) >> >>",
    ],
)
def test_actions_outside_the_names_tree_are_refused(extra: str) -> None:
    with pytest.raises(FileRejectedError) as err:
        check(_catalog_pdf(extra))
    assert err.value.code == "document.pdf_unsafe"


def test_a_script_packed_in_a_compressed_stream_is_found() -> None:
    import zlib  # noqa: PLC0415

    packed = zlib.compress(b"<< /S /JavaScript /JS (app.alert(1)) >>")
    data = _raw_pdf(
        [
            "<< /Type /Catalog /Pages 2 0 R >>",
            "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] >>",
            f"<< /Type /ObjStm /N 1 /First 0 /Length {len(packed)} /Filter /FlateDecode >>"
            "\nstream\n" + packed.decode("latin-1") + "\nendstream",
        ]
    )
    with pytest.raises(FileRejectedError) as err:
        check(data)
    assert err.value.code == "document.pdf_unsafe"


def test_a_link_alone_is_allowed() -> None:
    """Lab PDFs carry web links: /URI is not refused."""
    assert (
        check(_catalog_pdf("/OpenAction << /S /URI /URI (https://lab.example) >>")).page_count == 1
    )


def test_unsafe_bytes_inside_image_data_are_not_a_pdf_name() -> None:
    """A real lab PDF's compressed image happened to contain the bytes "/JS" (3.2)."""
    data = _raw_pdf(
        [
            "<< /Type /Catalog /Pages 2 0 R >>",
            "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] >>",
            "<< /Type /XObject /Subtype /Image /Length 8 /Filter /DCTDecode >>\nstream\n"
            "\xff\xd8/JS.\x00\xff\nendstream",
        ]
    )
    assert check(data).page_count == 1


@pytest.mark.parametrize(
    "extra",
    [
        r"/OpenAction << /S /Java#53cript /J#53 (app.alert\(1\)) >>",
        "/OpenAction << /S /L#61unch /F (calc.exe) >>",
    ],
)
def test_names_spelled_with_hex_escapes_are_found(extra: str) -> None:
    with pytest.raises(FileRejectedError) as err:
        check(_catalog_pdf(extra))
    assert err.value.code == "document.pdf_unsafe"


def test_an_image_whose_header_claims_a_huge_size_is_too_large() -> None:
    import struct  # noqa: PLC0415
    import zlib  # noqa: PLC0415

    def chunk(kind: bytes, body: bytes) -> bytes:
        return (
            struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
        )

    header = struct.pack(">IIBBBBB", 20000, 20000, 8, 2, 0, 0, 0)  # 400 MP claimed
    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IEND", b"")
    with pytest.raises(FileRejectedError) as err:
        check(data)
    assert err.value.code == "document.too_large"


@pytest.mark.parametrize(
    "extra",
    [
        "/OpenAction << /S /URI /URI (file:///etc/passwd) >>",
        "/Names << /Collection << /D (x) >> >>",
    ],
)
def test_local_links_and_portfolios_are_refused(extra: str) -> None:
    with pytest.raises(FileRejectedError) as err:
        check(_catalog_pdf(extra))
    assert err.value.code == "document.pdf_unsafe"
