"""A real PDF containing an invisible NUL glyph must remain portable to Postgres."""
import hashlib
import io
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
from app.parsers import extract, extract_isolated


def test_real_pdf_nul_glyph_is_removed_only_from_extracted_text():
    writer=PdfWriter()
    page=writer.add_blank_page(width=400,height=400)
    font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),
        NameObject('/BaseFont'):NameObject('/Helvetica')})
    page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):font})})
    stream=DecodedStreamObject()
    stream.set_data(b'BT /F1 12 Tf 20 200 Td (Public\\000 notice: application materials must be submitted before the official deadline.) Tj ET')
    page[NameObject('/Contents')]=writer._add_object(stream)
    out=io.BytesIO();writer.write(out);raw=out.getvalue();digest=hashlib.sha256(raw).hexdigest()
    assert '\x00' in PdfReader(io.BytesIO(raw)).pages[0].extract_text()
    for parsed in [extract(raw,'pdf'),extract_isolated(raw,'pdf')]:
        assert '\x00' not in parsed.text
        assert 'Public notice: application materials' in parsed.text
    assert hashlib.sha256(raw).hexdigest()==digest
