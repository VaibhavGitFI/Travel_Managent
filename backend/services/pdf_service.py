"""
TravelSync Pro — PDF Generation Service
Generates trip reports, expense summaries, and approval letters.
Uses ReportLab for PDF creation.
"""
import io
import logging
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
)

logger = logging.getLogger(__name__)

_styles = getSampleStyleSheet()
_styles.add(ParagraphStyle(name="Brand", fontSize=18, textColor=colors.HexColor("#0d2a5e"),
                           spaceAfter=4, fontName="Helvetica-Bold"))
_styles.add(ParagraphStyle(name="SubBrand", fontSize=9, textColor=colors.HexColor("#6B7280"),
                           spaceAfter=12))
_styles.add(ParagraphStyle(name="SectionHead", fontSize=12, textColor=colors.HexColor("#1E3A5F"),
                           spaceBefore=14, spaceAfter=6, fontName="Helvetica-Bold"))
_styles.add(ParagraphStyle(name="FieldLabel", fontSize=8, textColor=colors.HexColor("#6B7280")))
_styles.add(ParagraphStyle(name="FieldValue", fontSize=10, spaceBefore=1, spaceAfter=6))

_TABLE_STYLE = TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d2a5e")),
    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTSIZE", (0, 0), (-1, 0), 9),
    ("FONTSIZE", (0, 1), (-1, -1), 8),
    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
    ("TOPPADDING", (0, 0), (-1, -1), 5),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ("LEFTPADDING", (0, 0), (-1, -1), 6),
])


def _header(elements):
    elements.append(Paragraph("TravelSync Pro", _styles["Brand"]))
    elements.append(Paragraph(
        f"Generated on {datetime.now().strftime('%d %b %Y at %I:%M %p')}",
        _styles["SubBrand"]
    ))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#E5E7EB")))
    elements.append(Spacer(1, 6))


def _field(elements, label, value):
    elements.append(Paragraph(label, _styles["FieldLabel"]))
    elements.append(Paragraph(str(value or "—"), _styles["FieldValue"]))


def _section(elements, title):
    elements.append(Paragraph(title, _styles["SectionHead"]))


def _format_inr(amount):
    try:
        return f"Rs. {float(amount):,.2f}"
    except (TypeError, ValueError):
        return "Rs. 0.00"


def generate_trip_report_pdf(request_data: dict, expenses: list = None,
                              approvals: list = None) -> bytes:
    """Generate a PDF trip report. Returns PDF bytes."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=20*mm, bottomMargin=15*mm,
                            leftMargin=18*mm, rightMargin=18*mm)
    elements = []

    _header(elements)
    elements.append(Paragraph("Trip Report", ParagraphStyle(
        name="Title", fontSize=16, fontName="Helvetica-Bold", spaceAfter=10,
        textColor=colors.HexColor("#111827"))))

    # Trip details
    _section(elements, "Trip Details")
    r = request_data
    details = [
        ("Request ID", r.get("request_id", "—")),
        ("Destination", r.get("destination", "—")),
        ("Origin", r.get("origin", "—")),
        ("Purpose", r.get("purpose", "—")),
        ("Dates", f"{r.get('start_date', '—')} to {r.get('end_date', '—')}"),
        ("Duration", f"{r.get('duration_days', 0)} days"),
        ("Travelers", str(r.get("num_travelers", 1))),
        ("Flight Class", (r.get("flight_class") or "economy").title()),
        ("Status", (r.get("status") or "draft").replace("_", " ").title()),
        ("Estimated Budget", _format_inr(r.get("estimated_total"))),
    ]
    for label, value in details:
        _field(elements, label, value)

    # Approvals
    if approvals:
        _section(elements, "Approval History")
        table_data = [["Approver", "Status", "Comments", "Date"]]
        for a in approvals:
            table_data.append([
                a.get("approver_name", "—"),
                (a.get("status") or "—").title(),
                (a.get("comments") or "—")[:60],
                str(a.get("decided_at") or a.get("created_at") or "—")[:10],
            ])
        t = Table(table_data, colWidths=[100, 70, 200, 80])
        t.setStyle(_TABLE_STYLE)
        elements.append(t)

    # Expenses
    if expenses:
        _section(elements, "Expenses")
        table_data = [["Category", "Description", "Amount", "Status"]]
        total = 0.0
        for e in expenses:
            try:
                amt = float(e.get("invoice_amount") or e.get("amount") or 0)
            except (ValueError, TypeError):
                amt = 0.0
            total += amt
            table_data.append([
                (e.get("category") or "misc").title(),
                (e.get("description") or "—")[:40],
                _format_inr(amt),
                (e.get("verification_status") or "pending").title(),
            ])
        table_data.append(["", "Total", _format_inr(total), ""])
        t = Table(table_data, colWidths=[90, 180, 90, 80])
        style = TableStyle([
            *_TABLE_STYLE.getCommands(),
            ("FONTNAME", (-3, -1), (-1, -1), "Helvetica-Bold"),
            ("LINEABOVE", (0, -1), (-1, -1), 1, colors.HexColor("#0d2a5e")),
        ])
        t.setStyle(style)
        elements.append(t)

    # Footer
    elements.append(Spacer(1, 20))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#E5E7EB")))
    elements.append(Paragraph(
        "This report was auto-generated by TravelSync Pro. For queries, contact your admin.",
        ParagraphStyle(name="Footer", fontSize=7, textColor=colors.HexColor("#9CA3AF"), spaceBefore=6)
    ))

    doc.build(elements)
    return buf.getvalue()


def generate_expense_summary_pdf(expenses: list, user_name: str = "",
                                  trip_id: str = "") -> bytes:
    """Generate a PDF expense summary. Returns PDF bytes."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=20*mm, bottomMargin=15*mm,
                            leftMargin=18*mm, rightMargin=18*mm)
    elements = []

    _header(elements)
    elements.append(Paragraph("Expense Summary", ParagraphStyle(
        name="Title", fontSize=16, fontName="Helvetica-Bold", spaceAfter=4,
        textColor=colors.HexColor("#111827"))))
    if user_name:
        _field(elements, "Employee", user_name)
    if trip_id:
        _field(elements, "Trip ID", trip_id)

    _section(elements, "Expenses")
    table_data = [["#", "Date", "Category", "Description", "Amount", "Currency", "Status"]]
    total = 0.0
    for i, e in enumerate(expenses, 1):
        try:
            amt = float(e.get("invoice_amount") or e.get("amount") or 0)
        except (ValueError, TypeError):
            amt = 0.0
        total += amt
        table_data.append([
            str(i),
            str(e.get("date") or "—")[:10],
            (e.get("category") or "misc").title(),
            (e.get("description") or "—")[:30],
            _format_inr(amt),
            e.get("currency_code", "INR"),
            (e.get("verification_status") or e.get("approval_status") or "pending").title(),
        ])
    table_data.append(["", "", "", "Grand Total", _format_inr(total), "", ""])
    t = Table(table_data, colWidths=[25, 60, 65, 120, 70, 40, 60])
    style = TableStyle([
        *_TABLE_STYLE.getCommands(),
        ("FONTNAME", (-4, -1), (-1, -1), "Helvetica-Bold"),
        ("LINEABOVE", (0, -1), (-1, -1), 1, colors.HexColor("#0d2a5e")),
    ])
    t.setStyle(style)
    elements.append(t)

    # Category breakdown
    if expenses:
        _section(elements, "Category Breakdown")
        by_cat = {}
        for e in expenses:
            cat = (e.get("category") or "misc").title()
            by_cat[cat] = by_cat.get(cat, 0) + float(e.get("invoice_amount") or e.get("amount") or 0)
        cat_data = [["Category", "Amount", "% of Total"]]
        for cat, amt in sorted(by_cat.items(), key=lambda x: -x[1]):
            pct = (amt / total * 100) if total else 0
            cat_data.append([cat, _format_inr(amt), f"{pct:.1f}%"])
        t = Table(cat_data, colWidths=[150, 120, 80])
        t.setStyle(_TABLE_STYLE)
        elements.append(t)

    elements.append(Spacer(1, 20))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#E5E7EB")))
    elements.append(Paragraph(
        "This report was auto-generated by TravelSync Pro.",
        ParagraphStyle(name="Footer", fontSize=7, textColor=colors.HexColor("#9CA3AF"), spaceBefore=6)
    ))

    doc.build(elements)
    return buf.getvalue()
