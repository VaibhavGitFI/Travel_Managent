"""
TravelSync Pro — Document Processing Agent
Multi-doc OCR: flight tickets, hotel vouchers, visa documents, train tickets.
Uses Gemini Vision for structured extraction; falls back to Vision API + regex.
"""
import re
import logging
from datetime import datetime
from pathlib import Path

from services.gemini_service import gemini
from services.vision_service import vision

logger = logging.getLogger(__name__)

# Type-specific extraction prompts for Gemini Vision
_DOC_PROMPTS = {
    "flight_ticket": (
        "This is a flight ticket or boarding pass. Extract ALL details and return ONLY JSON with these keys: "
        "airline, flight_number, pnr, from_city, to_city, from_airport_code, to_airport_code, "
        "departure_date (YYYY-MM-DD), departure_time (HH:MM), arrival_date (YYYY-MM-DD), arrival_time (HH:MM), "
        "fare_class, passenger_name, seat_number. Use null for missing fields."
    ),
    "hotel_voucher": (
        "This is a hotel booking voucher or confirmation. Extract ALL details and return ONLY JSON with: "
        "hotel_name, city, address, check_in_date (YYYY-MM-DD), check_out_date (YYYY-MM-DD), "
        "room_type, num_rooms, booking_ref, amount_per_night, total_amount, guest_name. "
        "Use null for missing fields."
    ),
    "visa": (
        "This is a visa document. Extract ALL details and return ONLY JSON with: "
        "country, visa_type, entry_type (single/multiple/transit), "
        "valid_from (YYYY-MM-DD), valid_until (YYYY-MM-DD), visa_number, "
        "passport_number, holder_name, issuing_authority, issued_date (YYYY-MM-DD). "
        "Use null for missing fields."
    ),
    "train_ticket": (
        "This is a train ticket or rail booking. Extract ALL details and return ONLY JSON with: "
        "train_name, train_number, pnr, from_station, to_station, from_city, to_city, "
        "departure_date (YYYY-MM-DD), departure_time (HH:MM), arrival_date (YYYY-MM-DD), arrival_time (HH:MM), "
        "class_type, seat_number, passenger_name, fare. Use null for missing fields."
    ),
    "receipt": (
        "This is an expense receipt or invoice. Extract ALL details and return ONLY JSON with: "
        "vendor_name, amount, currency, date (YYYY-MM-DD), invoice_number, gst_number, "
        "items_summary, payment_method. Use null for missing fields."
    ),
}

_AUTO_DETECT_PROMPT = (
    "Look at this document image. Identify what type of travel document this is and extract all key details. "
    "Return ONLY JSON with two keys: "
    '"doc_type" (one of: flight_ticket, hotel_voucher, visa, train_ticket, receipt, other) and '
    '"extracted" (a dict of all relevant fields you can read from the document, with dates as YYYY-MM-DD). '
    "Include everything visible: names, dates, amounts, reference numbers, locations."
)


def _parse_date(date_str: str) -> str | None:
    """Try to normalize a date string to YYYY-MM-DD."""
    if not date_str or str(date_str).lower() in ("null", "none", "n/a", ""):
        return None
    formats = ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%d %b %Y",
               "%d %B %Y", "%B %d, %Y", "%b %d, %Y", "%Y%m%d"]
    for fmt in formats:
        try:
            return datetime.strptime(str(date_str).strip(), fmt).strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            continue
    return str(date_str).strip() or None


def _check_visa_overlap(extracted: dict, trip_start: str, trip_end: str) -> list[str]:
    """Return warning strings if visa validity overlaps with trip dates."""
    warnings = []
    valid_until = _parse_date(extracted.get("valid_until"))
    valid_from = _parse_date(extracted.get("valid_from"))
    if not valid_until:
        return warnings
    try:
        exp = datetime.strptime(valid_until, "%Y-%m-%d").date()
        if trip_end:
            end = datetime.strptime(trip_end, "%Y-%m-%d").date()
            if exp < end:
                warnings.append(
                    f"VISA EXPIRY WARNING: Visa expires {valid_until} but trip ends {trip_end}. "
                    "Renew visa before departure."
                )
        if trip_start:
            start = datetime.strptime(trip_start, "%Y-%m-%d").date()
            if valid_from:
                vf = datetime.strptime(valid_from, "%Y-%m-%d").date()
                if vf > start:
                    warnings.append(
                        f"VISA NOT YET VALID: Visa is valid from {valid_from} but trip starts {trip_start}."
                    )
    except (ValueError, TypeError):
        pass
    return warnings


def _build_prefill(doc_type: str, extracted: dict) -> dict:
    """Map extracted fields to travel_requests form fields."""
    prefill = {}

    if doc_type in ("flight_ticket", "train_ticket"):
        for key in ("from_city", "from_station"):
            if extracted.get(key) and str(extracted[key]).lower() not in ("null", "none"):
                prefill["origin"] = str(extracted[key])
                prefill["from_city"] = str(extracted[key])
                break
        for key in ("to_city", "to_station"):
            if extracted.get(key) and str(extracted[key]).lower() not in ("null", "none"):
                prefill["destination"] = str(extracted[key])
                prefill["to_city"] = str(extracted[key])
                break
        dep_date = _parse_date(extracted.get("departure_date"))
        arr_date = _parse_date(extracted.get("arrival_date"))
        if dep_date:
            prefill["start_date"] = dep_date
            prefill["travel_date"] = dep_date
        if arr_date:
            prefill["end_date"] = arr_date
            prefill["return_date"] = arr_date
        if extracted.get("pnr"):
            prefill["notes"] = f"PNR: {extracted['pnr']}"
        if doc_type == "flight_ticket" and extracted.get("fare_class"):
            fc = str(extracted["fare_class"]).lower()
            if "business" in fc:
                prefill["flight_class"] = "business"
            elif "first" in fc:
                prefill["flight_class"] = "first"
            else:
                prefill["flight_class"] = "economy"

    elif doc_type == "hotel_voucher":
        if extracted.get("city") and str(extracted["city"]).lower() not in ("null", "none"):
            prefill["destination"] = str(extracted["city"])
            prefill["to_city"] = str(extracted["city"])
        check_in = _parse_date(extracted.get("check_in_date"))
        check_out = _parse_date(extracted.get("check_out_date"))
        if check_in:
            prefill["start_date"] = check_in
            prefill["travel_date"] = check_in
        if check_out:
            prefill["end_date"] = check_out
            prefill["return_date"] = check_out
        if extracted.get("amount_per_night"):
            try:
                prefill["hotel_budget_per_night"] = float(str(extracted["amount_per_night"]).replace(",", ""))
            except (ValueError, TypeError):
                pass
        if extracted.get("booking_ref"):
            prefill["notes"] = f"Hotel booking ref: {extracted['booking_ref']}"

    elif doc_type == "visa":
        country = extracted.get("country")
        if country and str(country).lower() not in ("null", "none"):
            prefill["destination"] = str(country)
            prefill["to_city"] = str(country)
            prefill["trip_type"] = "international"
        valid_until = _parse_date(extracted.get("valid_until"))
        if valid_until:
            notes = f"Visa valid until: {valid_until}"
            if extracted.get("visa_number"):
                notes += f" | Visa #: {extracted['visa_number']}"
            prefill["notes"] = notes

    return prefill


def _regex_fallback(raw_text: str) -> dict:
    """Extract basic travel fields from OCR raw text via regex."""
    extracted = {}
    # PNR
    pnr = re.search(r"\bPNR[:\s]*([A-Z0-9]{6,10})\b", raw_text, re.IGNORECASE)
    if pnr:
        extracted["pnr"] = pnr.group(1).upper()
    # Dates YYYY-MM-DD
    dates = re.findall(r"\b(\d{4}-\d{2}-\d{2})\b", raw_text)
    if dates:
        extracted["departure_date"] = dates[0]
        if len(dates) > 1:
            extracted["arrival_date"] = dates[-1]
    # Dates DD/MM/YYYY
    if not dates:
        alt_dates = re.findall(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b", raw_text)
        if alt_dates:
            extracted["departure_date"] = _parse_date(alt_dates[0]) or alt_dates[0]
    # Amount
    amount_m = re.search(r"(?:₹|Rs\.?\s*|INR\s*)([0-9,]+(?:\.[0-9]{1,2})?)", raw_text, re.IGNORECASE)
    if amount_m:
        extracted["amount"] = amount_m.group(1).replace(",", "")
    # Cities (common patterns)
    from_m = re.search(r"(?:From|Origin|Departure)[:\s]+([A-Za-z\s]+?)(?:\n|to|→)", raw_text, re.IGNORECASE)
    to_m = re.search(r"(?:To|Destination|Arrival)[:\s]+([A-Za-z\s]+?)(?:\n|$)", raw_text, re.IGNORECASE)
    if from_m:
        extracted["from_city"] = from_m.group(1).strip().title()
    if to_m:
        extracted["to_city"] = to_m.group(1).strip().title()
    return extracted


def parse_document(
    file_path: str,
    doc_type: str = "auto",
    trip_start: str = None,
    trip_end: str = None,
) -> dict:
    """
    Parse a travel document and extract structured fields.

    Returns:
        {
          success: bool,
          doc_type: str,
          extracted: dict,
          prefill_fields: dict,  # maps to travel_requests form fields
          warnings: list[str],   # visa expiry, etc.
          source: str,
        }
    """
    path = Path(file_path)
    if not path.exists():
        return {"success": False, "error": "File not found"}

    ext = path.suffix.lower()
    if ext not in {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".webp"}:
        return {"success": False, "error": f"Unsupported file type: {ext}. Use JPG/PNG/PDF."}

    extracted = {}
    detected_type = doc_type if doc_type != "auto" else None
    source = "fallback"

    # 1. Try Gemini Vision
    if gemini.is_available and ext != ".pdf":
        try:
            if doc_type == "auto":
                raw = gemini.analyze_image(file_path, _AUTO_DETECT_PROMPT)
                if raw:
                    import json, re as _re
                    clean = _re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=_re.MULTILINE)
                    parsed = json.loads(clean)
                    detected_type = parsed.get("doc_type", "other")
                    extracted = parsed.get("extracted", {})
                    source = "gemini_vision"
            else:
                prompt = _DOC_PROMPTS.get(doc_type, _DOC_PROMPTS["receipt"])
                raw = gemini.analyze_image(file_path, prompt)
                if raw:
                    import json, re as _re
                    clean = _re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=_re.MULTILINE)
                    extracted = json.loads(clean)
                    detected_type = doc_type
                    source = "gemini_vision"
        except Exception as exc:
            logger.warning("[DocumentAgent] Gemini Vision error: %s", exc)

    # 2. Fall back to Vision API OCR + regex
    if not extracted and ext != ".pdf":
        try:
            ocr_result = vision.extract_receipt_data(file_path)
            raw_text = ocr_result.get("raw_text", "")
            if raw_text:
                extracted = _regex_fallback(raw_text)
                if not detected_type:
                    detected_type = _auto_detect_from_text(raw_text)
                source = "vision_ocr_regex"
            elif ocr_result.get("extracted"):
                extracted = ocr_result["extracted"]
                detected_type = detected_type or "receipt"
                source = "vision_ocr"
        except Exception as exc:
            logger.warning("[DocumentAgent] Vision API fallback error: %s", exc)

    if not detected_type:
        detected_type = "other"

    # 3. Normalize extracted date fields
    for date_field in ("departure_date", "arrival_date", "check_in_date", "check_out_date",
                        "valid_from", "valid_until", "date", "issued_date"):
        if extracted.get(date_field):
            extracted[date_field] = _parse_date(extracted[date_field]) or extracted[date_field]

    # 4. Build prefill fields for travel_requests form
    prefill = _build_prefill(detected_type, extracted)

    # 5. Check visa overlap warnings
    warnings = []
    if detected_type == "visa" and (trip_start or trip_end):
        warnings = _check_visa_overlap(extracted, trip_start, trip_end)

    return {
        "success": True,
        "doc_type": detected_type,
        "extracted": extracted,
        "prefill_fields": prefill,
        "warnings": warnings,
        "source": source,
        "file": path.name,
    }


def _auto_detect_from_text(text: str) -> str:
    """Heuristic doc type detection from raw OCR text."""
    t = text.upper()
    if any(w in t for w in ["BOARDING PASS", "AIRLINE", "FLIGHT NO", "PNR", "AIRCRAFT"]):
        return "flight_ticket"
    if any(w in t for w in ["HOTEL", "CHECK-IN", "CHECK IN", "CHECKOUT", "ROOM", "VOUCHER"]):
        return "hotel_voucher"
    if any(w in t for w in ["VISA", "VALIDITY", "ENTRY TYPE", "IMMIGRATION"]):
        return "visa"
    if any(w in t for w in ["TRAIN", "PNR", "RAILWAY", "IRCTC", "BERTH", "COACH"]):
        return "train_ticket"
    return "receipt"
