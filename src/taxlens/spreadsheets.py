"""Writing values that people open in spreadsheet programs."""

# A cell starting with one of these is read as a formula by Excel and LibreOffice.
FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


def spreadsheet_safe(value: object) -> object:
    """Keep spreadsheet programs from running a cell that starts like a formula.

    The cell keeps its text, behind a leading apostrophe; None becomes an empty cell.
    """

    if value is None:
        return ""
    if isinstance(value, str) and value.startswith(FORMULA_STARTS):
        return "'" + value
    return value
