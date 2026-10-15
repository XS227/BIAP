import io
import zipfile

from global_markets.sector_reference import deutsche_boerse_entry
from global_markets.sector_reference_sync import parse_deutsche_boerse_xlsx

_M = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _workbook(rows):
    strings = []

    def sid(text):
        if text not in strings:
            strings.append(text)
        return strings.index(text)

    body = ""
    for number, row in enumerate(rows, 1):
        cells = "".join(f'<c r="{col}{number}" t="s"><v>{sid(v)}</v></c>' for col, v in row.items())
        body += f'<row r="{number}">{cells}</row>'
    sheet = f'<worksheet xmlns="{_M}"><sheetData>{body}</sheetData></worksheet>'
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("xl/workbook.xml", f'<workbook xmlns="{_M}" xmlns:r="{_R}"><sheets><sheet name="Prime Standard" sheetId="1" r:id="rId1"/><sheet name="Cover" sheetId="2" r:id="rId2"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Target="worksheets/sheet2.xml"/></Relationships>')
        z.writestr("xl/sharedStrings.xml", f'<sst xmlns="{_M}">' + "".join(f"<si><t>{t}</t></si>" for t in strings) + "</sst>")
        z.writestr("xl/worksheets/sheet1.xml", sheet)
        z.writestr("xl/worksheets/sheet2.xml", f'<worksheet xmlns="{_M}"><sheetData/></worksheet>')
    return buffer.getvalue()


def test_parse_reads_isin_keyed_rows_only_from_segment_sheets():
    content = _workbook([
        {"A": "ISIN", "D": "Sector", "E": "Subsector"},
        {"A": "DE0007164600", "B": "SAP", "D": "Software ", "E": "Software"},
        {"A": "Number of instruments:", "D": "x"},
    ])
    assert parse_deutsche_boerse_xlsx(content) == {"DE0007164600": ("Software", "Software", "Prime Standard")}


def test_mapping_is_conservative_and_traceable():
    def sector(a, b):
        entry = deutsche_boerse_entry(a, b, "Prime Standard", url="u", retrieved_at="t")
        return entry and (entry["sector"], entry["kind"])

    assert sector("Software", "Software") == ("Technology", "operating")
    assert sector("Insurance", "Re-Insurance") == ("Financials", "insurance")
    assert sector("Banks", "Credit Banks") == ("Financials", "bank")
    assert sector("Financial Services", "Real Estate") == ("Real Estate", "operating")
    assert sector("Retail", "Retail, Food & Drug") == ("Consumer Staples", "operating")
    # pooled/holding vehicles and self-contradicting labels are never guessed
    assert sector("Financial Services", "Private Equity & Venture Capital") is None
    assert sector("Industrial", "Internet") is None
    assert sector("Media", "Real Estate") is None
    assert sector("Consumer", "Chemicals, Specialty") is None
    assert sector("-", "-") is None
    entry = deutsche_boerse_entry("Insurance", "Insurance", "Prime Standard", url="u", retrieved_at="t")
    assert entry["source"] == "deutsche-boerse-listed-companies" and entry["url"] == "u" and entry["segment"] == "Prime Standard"
