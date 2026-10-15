from decimal import Decimal
from io import BytesIO

import openpyxl
import pytest

from app.services.assets.hpi_import import HpiRow, parse_state_csv, parse_zip3_xlsx

HEADER = ("Three-Digit ZIP Code", "Year", "Quarter", "Index (NSA)", "Index Type")


def build_xlsx(data_rows, *, header=HEADER, preamble_rows=4) -> bytes:
    """A tiny workbook shaped like FHFA's: title and notes rows, then the header, then data."""
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    notes = ["FHFA HPI for Three-Digit ZIP Codes", None, "* developmental indexes", "Not Seasonally Adjusted (NSA) "]
    for i in range(preamble_rows):
        ws.append([notes[i] if i < len(notes) else None])
    if header is not None:
        ws.append(list(header))
    for row in data_rows:
        ws.append(list(row))
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


class TestZip3Xlsx:
    def test_parses_rows_below_the_header(self):
        data = build_xlsx(
            [
                (10, 1995, 1, 100, "Native 3-Digit ZIP index"),
                (10, 1995, 2, 101.38, "Native 3-Digit ZIP index"),
                (275, 2026, 2, 312.456, "Native 3-Digit ZIP index"),
            ]
        )
        assert parse_zip3_xlsx(data) == [
            HpiRow("zip3", "010", 1995, 1, Decimal("100.00")),
            HpiRow("zip3", "010", 1995, 2, Decimal("101.38")),
            HpiRow("zip3", "275", 2026, 2, Decimal("312.46")),
        ]

    def test_zip_is_zero_padded_to_three_digits(self):
        rows = parse_zip3_xlsx(build_xlsx([(5, 2000, 1, 100, "x"), ("019", 2000, 1, 100, "x")]))
        assert [r.geo_code for r in rows] == ["005", "019"]

    def test_rows_without_an_index_are_skipped(self):
        data = build_xlsx(
            [(10, 1995, 1, 100, "x"), (10, 1995, 2, None, "x"), (10, 1995, 3, "", "x"), (10, 1995, 4, 103.62, "x")]
        )
        assert [(r.quarter, r.index_value) for r in parse_zip3_xlsx(data)] == [
            (1, Decimal("100.00")),
            (4, Decimal("103.62")),
        ]

    def test_blank_trailing_rows_are_skipped(self):
        data = build_xlsx([(10, 1995, 1, 100, "x"), (None, None, None, None, None)])
        assert len(parse_zip3_xlsx(data)) == 1

    def test_rows_whose_zip_is_not_numeric_are_skipped(self):
        data = build_xlsx(
            [
                (10, 1995, 1, 100, "x"),
                ("Source: FHFA, all rights reserved", 2026, 1, 100, "x"),
                ("see note 3", None, None, None, None),
                ("019.5", 2000, 1, 100, "x"),
                (276.0, 2000, 1, 100, "x"),
            ]
        )
        assert [r.geo_code for r in parse_zip3_xlsx(data)] == ["010", "276"]

    def test_a_workbook_with_no_data_rows_raises(self):
        with pytest.raises(ValueError, match="no data rows"):
            parse_zip3_xlsx(build_xlsx([(None, None, None, None, None), (10, 1995, 1, None, "x")]))

    def test_header_is_found_wherever_it_sits(self):
        data = build_xlsx([(10, 1995, 1, 100, "x")], preamble_rows=7)
        assert len(parse_zip3_xlsx(data)) == 1

    def test_columns_are_located_by_header_name(self):
        header = ("Three-Digit ZIP Code", "Index Type", "Year", "Quarter", "Index (NSA)")
        data = build_xlsx([(10, "Native", 1995, 3, 103.64)], header=header)
        assert parse_zip3_xlsx(data) == [HpiRow("zip3", "010", 1995, 3, Decimal("103.64"))]

    def test_missing_header_raises(self):
        with pytest.raises(ValueError, match="header"):
            parse_zip3_xlsx(build_xlsx([(10, 1995, 1, 100, "x")], header=None))

    def test_header_without_required_columns_raises(self):
        with pytest.raises(ValueError, match="Index"):
            parse_zip3_xlsx(build_xlsx([], header=("Three-Digit ZIP Code", "Year", "Quarter")))

    def test_quarter_out_of_range_raises(self):
        with pytest.raises(ValueError, match="quarter"):
            parse_zip3_xlsx(build_xlsx([(10, 1995, 5, 100, "x")]))

    def test_non_xlsx_bytes_raise(self):
        with pytest.raises(ValueError):
            parse_zip3_xlsx(b"<html>rate limited</html>")


class TestStateCsv:
    def test_parses_headerless_rows(self):
        text = "AK,1975,1,100.00\nAK,1975,2,101.54\nNC,2026,2,455.1\n"
        assert parse_state_csv(text) == [
            HpiRow("state", "AK", 1975, 1, Decimal("100.00")),
            HpiRow("state", "AK", 1975, 2, Decimal("101.54")),
            HpiRow("state", "NC", 2026, 2, Decimal("455.10")),
        ]

    def test_blank_lines_and_missing_index_are_skipped(self):
        text = "\nAK,1975,1,100.00\nAK,1975,2,\nAK,1975,3,.\r\n\r\nAK,1975,4,102\n"
        assert [r.quarter for r in parse_state_csv(text)] == [1, 4]

    def test_extra_trailing_columns_are_ignored(self):
        assert parse_state_csv("AK,1975,1,100.00,99.5\n") == [HpiRow("state", "AK", 1975, 1, Decimal("100.00"))]

    def test_state_code_is_uppercased_and_trimmed(self):
        assert parse_state_csv(" nc , 2026 , 2 , 455.10 \n")[0].geo_code == "NC"

    def test_leading_header_line_is_tolerated(self):
        assert len(parse_state_csv("state,yr,qtr,index_nsa\nAK,1975,1,100.00\n")) == 1

    @pytest.mark.parametrize("text", ["", "\n\n", "state,yr,qtr,index_nsa\n", "AK,1975,1,\n"])
    def test_text_with_no_data_rows_raises(self, text):
        with pytest.raises(ValueError, match="no data rows"):
            parse_state_csv(text)

    @pytest.mark.parametrize("line", ["AK,1975,1", "AK,abc,1,100", "AK,1975,9,100", "AK,1975,1,not-a-number"])
    def test_malformed_rows_raise(self, line):
        with pytest.raises(ValueError):
            parse_state_csv(f"NC,2026,2,455.10\n{line}\n")
