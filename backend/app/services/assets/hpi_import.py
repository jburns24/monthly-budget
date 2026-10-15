"""Parsers for the FHFA quarterly house price index downloads (bytes/text in, rows out; no I/O).

Sources:
- ZIP3: https://www.fhfa.gov/hpi/download/quarterly_datasets/hpi_at_3zip.xlsx
- State: https://www.fhfa.gov/hpi/download/quarterly_datasets/hpi_at_state.csv

Rows with a blank index, and ZIP3 rows whose ZIP cell is not a number (footnotes), are skipped.
Anything else malformed, or a file that yields no rows at all, raises ``ValueError`` so a truncated,
garbled or reformatted download fails the refresh instead of replacing good data with nothing.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from io import BytesIO
from typing import Any
from zipfile import BadZipFile

import openpyxl
from openpyxl.utils.exceptions import InvalidFileException

ZIP3_URL = "https://www.fhfa.gov/hpi/download/quarterly_datasets/hpi_at_3zip.xlsx"
STATE_URL = "https://www.fhfa.gov/hpi/download/quarterly_datasets/hpi_at_state.csv"

_ZIP_HEADER = "Three-Digit ZIP Code"
_HEADER_SCAN_ROWS = 100
_INDEX_QUANTUM = Decimal("0.01")


@dataclass(frozen=True)
class HpiRow:
    series: str  # "zip3" | "state"
    geo_code: str
    year: int
    quarter: int
    index_value: Decimal


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() in ("", "."))


def _index_value(value: Any) -> Decimal:
    try:
        return Decimal(str(value).strip()).quantize(_INDEX_QUANTUM, rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise ValueError(f"invalid index value: {value!r}") from exc


def _int(value: Any, what: str) -> int:
    try:
        number = Decimal(str(value).strip())
    except InvalidOperation as exc:
        raise ValueError(f"invalid {what}: {value!r}") from exc
    if number != number.to_integral_value():
        raise ValueError(f"invalid {what}: {value!r}")
    return int(number)


def _quarter(value: Any) -> int:
    quarter = _int(value, "quarter")
    if not 1 <= quarter <= 4:
        raise ValueError(f"invalid quarter: {value!r}")
    return quarter


def _zip3(value: Any) -> str | None:
    """A ZIP cell as a zero-padded three-digit code, or None when it is not an integer or numeric string."""
    try:
        return str(_int(value, "ZIP code")).zfill(3)
    except ValueError:
        return None


def parse_zip3_xlsx(data: bytes) -> list[HpiRow]:
    """Parse the three-digit ZIP workbook; the header row is located by its first cell, not by position."""
    try:
        workbook = openpyxl.load_workbook(BytesIO(data), read_only=True, data_only=True)
    except (BadZipFile, InvalidFileException, KeyError, OSError) as exc:
        raise ValueError("not a readable xlsx workbook") from exc
    try:
        rows = workbook.worksheets[0].iter_rows(values_only=True)
        columns: dict[str, int] | None = None
        for _, row in zip(range(_HEADER_SCAN_ROWS), rows):
            if row and isinstance(row[0], str) and row[0].strip() == _ZIP_HEADER:
                columns = {str(cell).strip(): i for i, cell in enumerate(row) if cell is not None}
                break
        if columns is None:
            raise ValueError(f"header row starting with {_ZIP_HEADER!r} not found")
        missing = [name for name in ("Year", "Quarter", "Index (NSA)") if name not in columns]
        if missing:
            raise ValueError(f"header is missing column(s): {', '.join(missing)}")

        def cell(row: tuple[Any, ...], name: str) -> Any:
            i = columns[name]
            return row[i] if i < len(row) else None

        parsed: list[HpiRow] = []
        for row in rows:
            zip_cell = row[0] if row else None
            if _blank(zip_cell) or _blank(cell(row, "Index (NSA)")):
                continue
            zip3 = _zip3(zip_cell)
            if zip3 is None:  # footnotes and source lines below the table
                continue
            parsed.append(
                HpiRow(
                    "zip3",
                    zip3,
                    _int(cell(row, "Year"), "year"),
                    _quarter(cell(row, "Quarter")),
                    _index_value(cell(row, "Index (NSA)")),
                )
            )
        if not parsed:
            raise ValueError("no data rows found in the workbook")
        return parsed
    finally:
        workbook.close()


def parse_state_csv(text: str) -> list[HpiRow]:
    """Parse ``ST,YYYY,Q,index[,...]`` lines (no header; a leading header line is tolerated)."""
    parsed: list[HpiRow] = []
    first = True
    for line in text.splitlines():
        if not line.strip():
            continue
        fields = [f.strip() for f in line.split(",")]
        is_first, first = first, False
        if is_first and len(fields) > 1 and not fields[1].isdigit():
            continue
        if len(fields) < 4:
            raise ValueError(f"expected at least 4 columns: {line!r}")
        if _blank(fields[3]):
            continue
        parsed.append(
            HpiRow("state", fields[0].upper(), _int(fields[1], "year"), _quarter(fields[2]), _index_value(fields[3]))
        )
    if not parsed:
        raise ValueError("no data rows found in the state file")
    return parsed
