"""Words of a PDF's text layer with their places (pdfplumber), on a PDF made here."""

from labtrack.extraction.text_pdf import read_pages


def _pdf(lines: list[tuple[float, float, str]]) -> bytes:
    """A one-page PDF (Helvetica) with text at (x, y-from-top) points; Latin only."""
    height = 842
    body = "".join(
        f"BT /F1 10 Tf {x} {height - y} Td ({text}) Tj ET\n" for x, y, text in lines
    ).encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R"
        b" /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(body)).encode() + b" >>\nstream\n" + body + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n".encode()
    out += f"startxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def test_words_come_with_their_places_in_reading_order() -> None:
    pages = read_pages(_pdf([(220, 215, "5.37"), (25, 215, "Glucose"), (25, 228, "Urea")]))
    assert len(pages) == 1
    first, second = pages[0].lines
    assert first.text == "Glucose 5.37"
    assert [round(w.x0) for w in first.words] == [25, 220]
    assert second.text == "Urea"
    assert second.top > first.top


def test_a_page_without_text_has_no_lines() -> None:
    assert read_pages(_pdf([]))[0].lines == ()
