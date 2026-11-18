"""The made-up lab report given to app store reviewers (docs/STORE_RELEASE.md §4): a digital PDF
with a text layer, laid out like a central-lab printout, every value inside its range (no
critical banner), marked SAMPLE on every page. No real person, register number or result.

Runs where WeasyPrint is (the API image) and writes the PDF to stdout:
    docker compose -f infra/docker-compose.yml --env-file .env run --rm --no-deps -T api \
        python - < backend/scripts/make_review_sample.py > docs/store/review-sample-lab.pdf
"""

import sys

ROWS = [
    # name, value, range, unit
    ("Креатинин", "92", "62 - 115", "мкмоль/л"),
    ("Мочевин", "6.4", "2.5 - 7.5", "ммоль/л"),
    ("Кали", "4.6", "3.5 - 5.1", "ммоль/л"),
    ("Натри", "140", "135 - 145", "ммоль/л"),
    ("Глюкоз", "5.1", "3.9 - 6.1", "ммоль/л"),
    ("АЛТ", "24", "0 - 40", "U/L"),
    ("АСТ", "22", "0 - 40", "U/L"),
    ("Гемоглобин", "138", "130 - 170", "г/л"),
]

PAGE = """<!doctype html><html lang="mn"><head><meta charset="utf-8"><style>
@page {{ size: A4; margin: 18mm; @top-right {{ content: "ЗОХИОМОЛ ЖИШЭЭ / SAMPLE"; color: #b00;
  font: 9pt 'Noto Sans'; }} }}
body {{ font: 10pt 'Noto Sans', sans-serif; color: #111; }}
h1 {{ font-size: 13pt; margin: 0 0 4mm; }}
.note {{ border: 1px solid #b00; color: #b00; padding: 2mm 3mm; margin: 0 0 5mm; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ text-align: left; padding: 1.4mm 2mm; border-bottom: 1px solid #ccc; }}
.meta td {{ border: 0; padding: 0.6mm 2mm 0.6mm 0; }}
</style></head><body>
<h1>Жишээ лаборатори — Биохими, Гематологи</h1>
<p class="note">Зохиомол жишээ баримт (апп дэлгүүрийн хяналтад). Бодит хүн, бодит хариу биш.<br>
Made-up sample for app store review. Not a real person or result.</p>
<table class="meta">
<tr><td>Нэр:</td><td>Туршилт Хэрэглэгч</td><td>Хүйс:</td><td>Эр</td></tr>
<tr><td>Сорьц:</td><td>Цус</td><td>Огноо:</td><td>{day}</td></tr>
</table>
<br>
<table>
<tr><th>Шинжилгээ</th><th>Хариу</th><th>Лавлах хэмжээ</th><th>Нэгж</th></tr>
{rows}
</table>
</body></html>"""


def main() -> int:
    from weasyprint import HTML  # noqa: PLC0415 - heavy, only in the container

    day = sys.argv[1] if len(sys.argv) > 1 else "2026.11.02"
    rows = "\n".join(
        f"<tr><td>{n}</td><td>{v}</td><td>{r}</td><td>{u}</td></tr>" for n, v, r, u in ROWS
    )
    pdf = HTML(string=PAGE.format(day=day, rows=rows)).write_pdf()
    if pdf is None:
        raise SystemExit("make_review_sample: WeasyPrint wrote no PDF")
    sys.stdout.buffer.write(pdf)
    return 0


if __name__ == "__main__":
    sys.exit(main())
