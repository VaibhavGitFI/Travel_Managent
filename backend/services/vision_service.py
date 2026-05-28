"""
TravelSync Pro — Google Cloud Vision OCR Service
Extracts structured data (amount, date, vendor, GST) from expense receipts.
Configure GOOGLE_VISION_API_KEY for live OCR.
https://cloud.google.com/vision/docs/reference/rest
"""
import os
import re
import base64
import logging
from pathlib import Path
from services.http_client import http as requests
from datetime import datetime

logger = logging.getLogger(__name__)


class VisionService:
    ANNOTATE_URL = "https://vision.googleapis.com/v1/images:annotate"

    def __init__(self):
        self.api_key = os.getenv("GOOGLE_VISION_API_KEY") or os.getenv("GOOGLE_MAPS_API_KEY")
        self.configured = bool(self.api_key)

    def extract_receipt_data(self, file_path: str) -> dict:
        """
        Extract structured data from a receipt/invoice image.
        Supports JPG, PNG, JPEG. PDF requires Document AI.
        """
        path = Path(file_path)
        if not path.exists():
            return {"error": "File not found", "source": "error"}

        ext = path.suffix.lower()
        if ext == ".pdf":
            return {
                "raw_text": "",
                "extracted": {},
                "confidence": 0.0,
                "source": "unsupported",
                "note": "PDF OCR requires Google Document AI. Use image format for Vision API.",
            }

        if self.configured:
            try:
                with open(file_path, "rb") as f:
                    image_b64 = base64.b64encode(f.read()).decode("utf-8")

                payload = {
                    "requests": [{
                        "image": {"content": image_b64},
                        "features": [
                            {"type": "DOCUMENT_TEXT_DETECTION", "maxResults": 1},
                        ],
                    }]
                }
                resp = requests.post(
                    f"{self.ANNOTATE_URL}?key={self.api_key}",
                    json=payload,
                    timeout=20
                )
                if resp.status_code == 200:
                    response_data = resp.json()
                    annotation = response_data["responses"][0].get("fullTextAnnotation", {})
                    text = annotation.get("text", "")
                    if text:
                        extracted = self.parse_receipt_text(text)
                        extracted["source"] = "google_vision"
                        return extracted
                else:
                    logger.warning("[Vision] API error %s: %s", resp.status_code, resp.text[:200])
            except Exception as e:
                logger.warning("[Vision] OCR error: %s", e)

        return self._mock_extraction(file_path)

    def parse_receipt_text(self, text: str) -> dict:
        """
        Parse raw OCR text to extract structured receipt fields.
        Handles Indian receipt formats: ₹, Rs., INR, GST, GSTIN.
        """
        result = {
            "raw_text": text,
            "extracted": {},
            "confidence": 0.85,
            "source": "parsed",
        }
        extracted = result["extracted"]
        text_lower = text.lower()

        # ── Total Amount ──────────────────────────────────────────
        amount_patterns = [
            # "Total: ₹12,345.67" or "Grand Total: Rs. 12345"
            r"(?:grand\s*total|net\s*amount|total\s*amount|total\s*payable|total)[:\s*]+(?:rs\.?\s*|inr\s*|₹\s*)([0-9,]+(?:\.[0-9]{1,2})?)",
            r"(?:₹|rs\.?\s*|inr\s*)([0-9,]+(?:\.[0-9]{1,2})?)\s*(?:only|/-|$)",
            r"([0-9,]{4,}(?:\.[0-9]{1,2})?)\s*(?:inr|/-\s*$)",
        ]
        for pattern in amount_patterns:
            match = re.search(pattern, text_lower, re.IGNORECASE)
            if match:
                try:
                    extracted["amount"] = float(match.group(1).replace(",", ""))
                    break
                except ValueError:
                    continue

        # ── Date ──────────────────────────────────────────────────
        date_patterns = [
            r"(?:date|dated|invoice\s*date|bill\s*date)[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
            r"(\d{2}/\d{2}/\d{4})",
            r"(\d{4}-\d{2}-\d{2})",
            r"(\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+\d{4})",
        ]
        for pattern in date_patterns:
            match = re.search(pattern, text_lower, re.IGNORECASE)
            if match:
                extracted["date"] = match.group(1)
                break

        # ── Vendor / Business Name ────────────────────────────────
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        if lines:
            # First non-empty line is usually the business name
            for line in lines[:3]:
                if len(line) > 3 and not re.match(r"^\d", line):
                    extracted["vendor"] = line
                    break

        # ── GST / GSTIN ───────────────────────────────────────────
        gst_match = re.search(
            r"(?:gstin?|gst\s*no|gst\s*number)[:\s]+([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1})",
            text.upper()
        )
        if gst_match:
            extracted["gst_number"] = gst_match.group(1)

        # ── Invoice / Bill Number ─────────────────────────────────
        inv_match = re.search(
            r"(?:invoice\s*(?:no|number|#)|bill\s*(?:no|number|#)|receipt\s*(?:no|#))[:\s]+([A-Z0-9/\-]+)",
            text.upper()
        )
        if inv_match:
            extracted["invoice_number"] = inv_match.group(1)

        # ── Tax Breakdown ─────────────────────────────────────────
        cgst_match = re.search(r"cgst[:\s]+(?:₹|rs\.?\s*)?([0-9,]+(?:\.[0-9]{1,2})?)", text_lower)
        sgst_match = re.search(r"sgst[:\s]+(?:₹|rs\.?\s*)?([0-9,]+(?:\.[0-9]{1,2})?)", text_lower)
        igst_match = re.search(r"igst[:\s]+(?:₹|rs\.?\s*)?([0-9,]+(?:\.[0-9]{1,2})?)", text_lower)

        if cgst_match:
            extracted["cgst"] = float(cgst_match.group(1).replace(",", ""))
        if sgst_match:
            extracted["sgst"] = float(sgst_match.group(1).replace(",", ""))
        if igst_match:
            extracted["igst"] = float(igst_match.group(1).replace(",", ""))

        # ── Payment Method ────────────────────────────────────────
        if any(k in text_lower for k in ["upi", "gpay", "phonepe", "paytm"]):
            extracted["payment_method"] = "UPI"
        elif any(k in text_lower for k in ["credit card", "debit card"]):
            extracted["payment_method"] = "Card"
        elif "cash" in text_lower:
            extracted["payment_method"] = "Cash"
        elif "neft" in text_lower or "rtgs" in text_lower or "bank transfer" in text_lower:
            extracted["payment_method"] = "Bank Transfer"

        # Set confidence based on how many fields were extracted
        n_fields = len([v for v in extracted.values() if v])
        result["confidence"] = min(0.4 + n_fields * 0.1, 0.95)

        return result

    def extract_from_bytes(self, image_bytes: bytes) -> dict:
        """Extract receipt data directly from image bytes (for WhatsApp/Cliq)."""
        if not self.configured:
            return {"raw_text": "", "extracted": {}, "confidence": 0.0, "source": "unconfigured"}
        try:
            image_b64 = base64.b64encode(image_bytes).decode("utf-8")
            payload = {
                "requests": [{
                    "image": {"content": image_b64},
                    "features": [{"type": "DOCUMENT_TEXT_DETECTION", "maxResults": 1}],
                }]
            }
            resp = requests.post(f"{self.ANNOTATE_URL}?key={self.api_key}", json=payload, timeout=20)
            if resp.status_code == 200:
                annotation = resp.json()["responses"][0].get("fullTextAnnotation", {})
                text = annotation.get("text", "")
                if text:
                    result = self.parse_receipt_text(text)
                    result["source"] = "google_vision"
                    return result
            else:
                logger.warning("[Vision] API error %s: %s", resp.status_code, resp.text[:200])
        except Exception as e:
            logger.warning("[Vision] extract_from_bytes error: %s", e)
        return {"raw_text": "", "extracted": {}, "confidence": 0.0, "source": "error"}

    def _mock_extraction(self, file_path: str) -> dict:
        return {
            "raw_text": "",
            "extracted": {},
            "confidence": 0.0,
            "source": "mock",
            "note": "Set GOOGLE_VISION_API_KEY for real OCR extraction from receipts",
        }


vision = VisionService()
