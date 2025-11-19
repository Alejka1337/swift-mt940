import csv
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation
import calendar

def _fmt_amount(amount: Decimal) -> str:
    """Format Decimal as '1234,56' (comma decimal sep, two decimals)."""
    q = amount.quantize(Decimal("0.01"))
    s = f"{q:.2f}"
    return s.replace(".", ",")

def _split_text_chunks(text: str, chunk_len: int = 35):
    text = text.replace("\r", " ").replace("\n", " ").strip()
    return [text[i:i+chunk_len] for i in range(0, len(text), chunk_len)] if text else []

def revolut_to_mt940(csv_content: str, iban: str) -> str:
    """
    Convert Revolut CSV text to MT940 text.
    - csv_content: raw CSV text (as read from file)
    - iban: target account IBAN (string) — will be normalized (spaces removed)
    """
    reader = csv.DictReader(io.StringIO(csv_content))
    rows = list(reader)

    if not rows:
        raise ValueError("CSV пустой или имеет неверный формат")

    # Normalize IBAN (no spaces)
    iban_norm = iban.replace(" ", "")

    # Currency from first (most recent) row's Payment currency
    currency = (rows[0].get("Payment currency") or rows[-1].get("Payment currency") or "EUR").strip().upper()

    # Helper to parse decimal safely
    def parse_decimal(v):
        if v is None or v == "":
            return Decimal("0")
        try:
            return Decimal(str(v).replace(",", "."))
        except InvalidOperation:
            return Decimal("0")

    # Determine opening (start-of-period) and closing balances/dates
    # According to your note: second row = last payment (most recent), last row = first payment (earliest)
    # We'll take opening (start) from last row, closing (end) from first row
    first_row = rows[-1]   # earliest transaction (first payment of period)
    last_row = rows[0]     # latest transaction (last payment of period)

    # Dates
    def fmt_yyMMdd(date_str):
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%y%m%d")
    def fmt_MMDD(date_str):
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%m%d")

    opening_date = fmt_yyMMdd(first_row["Date completed (UTC)"])
    opening_balance = parse_decimal(first_row.get("Balance", "0"))

    closing_date = fmt_yyMMdd(last_row["Date completed (UTC)"])
    closing_balance = parse_decimal(last_row.get("Balance", "0"))

    # available date = last day of month of opening_date
    od = datetime.strptime(first_row["Date completed (UTC)"], "%Y-%m-%d")
    last_day = calendar.monthrange(od.year, od.month)[1]
    available_dt = od.replace(day=last_day)
    available_date = available_dt.strftime("%y%m%d")

    lines = []
    lines.append(":20:MT940")
    lines.append(f":25:/{iban_norm}")
    lines.append(":28C:1")
    lines.append(f":60F:C{opening_date}{currency}{_fmt_amount(opening_balance)}")

    # Process transactions in order from earliest -> latest? Banks usually include transactions in chronological order.
    # But your CSV seems to be sorted descending (latest first). To match examples, iterate rows in reverse (earliest first).
    for tx in reversed(rows):
        # Dates
        date_completed = tx.get("Date completed (UTC)") or tx.get("Date started (UTC)")
        if not date_completed:
            # fallback to opening_date
            date_completed = first_row["Date completed (UTC)"]
        val_date = fmt_yyMMdd(date_completed)
        entry_md = fmt_MMDD(date_completed)  # MMDD part

        # ID full no hyphens
        tx_id = (tx.get("ID") or "").replace("-", "").strip()

        # Amount: use 'Amount' field if present, otherwise 'Orig amount'
        amount = parse_decimal(tx.get("Amount") or tx.get("Orig amount") or "0")
        # direction
        direction = "D" if amount < 0 else "C"
        amount_abs = abs(amount)
        amount_str = _fmt_amount(amount_abs)

        # Determine operation code number (default 119, fee -> 49)
        tx_type = (tx.get("Type") or "").upper()
        if "FEE" in tx_type:
            code_num = "49"
        else:
            code_num = "119"

        # Build :61: line -> :61:YYMMDDMMDDD/CamountN{code}NONREF//{tx_id}
        # note: code prefixed with 'N' in :61:
        lines.append(f":61:{val_date}{entry_md}{direction}{amount_str}N{code_num}NONREF//{tx_id}")
        # add the separate numeric code line like "119 0"
        lines.append(f"{code_num} 0")

        # Build :86: block
        lines.append(f":86:020~00{code_num}")

        # ~20 = Reference (if any)
        reference = (tx.get("Reference") or "").strip()
        if reference:
            lines.append(f"~20{reference}")

        # Description split into ~32/~33...
        description = (tx.get("Description") or "").strip()
        desc_chunks = _split_text_chunks(description, 35)
        if desc_chunks:
            # put first chunk in ~32, second in ~33, further into ~3x lines or concatenated to ~38 if empty
            if len(desc_chunks) >= 1:
                lines.append(f"~32{desc_chunks[0]}")
            if len(desc_chunks) >= 2:
                lines.append(f"~33{desc_chunks[1]}")
            if len(desc_chunks) > 2:
                # remaining appended into ~38 (or further lines). We'll append as single concatenation.
                rem = "".join(desc_chunks[2:])
                lines.append(f"~38{rem}")
        else:
            # if no description, keep placeholders as in example (use euro symbol for EUR or currency code)
            pass

        # Beneficiary IBAN
        ben_iban = (tx.get("Beneficiary IBAN") or "").strip()
        if ben_iban:
            ben_iban_norm = ben_iban.replace(" ", "")
            lines.append(f"~38{ben_iban_norm}")

        # ~60 / ~63 — use € for EUR else currency code
        symbol = "€" if currency == "EUR" else currency
        lines.append(f"~60{symbol}")
        lines.append(f"~63{symbol}")

    # Footer balances
    lines.append(f":62F:C{closing_date}{currency}{_fmt_amount(closing_balance)}")
    lines.append(f":64:C{available_date}{currency}{_fmt_amount(closing_balance)}")
    lines.append("-")

    return "\n".join(lines)
