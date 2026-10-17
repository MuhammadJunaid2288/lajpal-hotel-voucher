#!/usr/bin/env python3
"""
LAJPAL TRAVEL LARKANA - Hotel / Umrah Voucher Generator
Multi-voucher system matching professional Umrah voucher layout
"""

import streamlit as st
import sqlite3
from datetime import datetime, date, timedelta
from pathlib import Path
import tempfile
import os
import urllib.request
import urllib.parse
from io import BytesIO

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
        HRFlowable, Image as RLImage, KeepTogether
    )
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    REPORTLAB_OK = True
except ImportError:
    REPORTLAB_OK = False

import pandas as pd

def parse_date_flexible(s):
    """Parse DD-MM-YY, DD/MM/YY, DD-MM-YYYY, YYYY-MM-DD etc."""
    if not s or not str(s).strip():
        return None
    s = str(s).strip().replace("/", "-").replace(".", "-")
    for fmt in ("%d-%m-%y", "%d-%m-%Y", "%Y-%m-%d", "%d-%b-%Y", "%d-%b-%y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None

def calc_nights(checkin, checkout):
    d1 = parse_date_flexible(checkin)
    d2 = parse_date_flexible(checkout)
    if d1 and d2 and d2 >= d1:
        return (d2 - d1).days
    return None

def calc_checkout(checkin, nights):
    """Check-in + nights number -> checkout date string DD-MM-YY"""
    d1 = parse_date_flexible(checkin)
    try:
        n = int(float(nights))
    except (TypeError, ValueError):
        return None
    if d1 and n >= 0:
        return (d1 + __import__('datetime').timedelta(days=n)).strftime("%d-%m-%y")
    return None

def sync_acc_dates(row):
    """Auto-fill nights from dates, OR checkout from checkin+nights."""
    r = dict(row)
    ci, co, n = r.get("checkin"), r.get("checkout"), r.get("nights")
    nights_val = None
    try:
        if n is not None and str(n).strip() != "":
            nights_val = int(float(n))
    except (TypeError, ValueError):
        nights_val = None

    # If both dates present -> nights
    calculated = calc_nights(ci, co)
    if calculated is not None:
        r["nights"] = calculated
        return r
    # If checkin + nights number -> checkout
    if parse_date_flexible(ci) and nights_val is not None and not (co and str(co).strip()):
        out = calc_checkout(ci, nights_val)
        if out:
            r["checkout"] = out
            r["nights"] = nights_val
        return r
    # If checkin + nights and checkout empty-ish
    if parse_date_flexible(ci) and nights_val is not None:
        out = calc_checkout(ci, nights_val)
        if out:
            r["checkout"] = out
            r["nights"] = nights_val
    return r


from storage import (
    init_db, get_setting, set_setting, storage_mode, supabase_ok, supabase_error_message,
    next_voucher_no, get_all_vouchers, get_voucher, create_voucher, update_voucher, delete_voucher,
    get_mutamers, set_mutamers, get_accommodations, set_accommodations, get_flights, set_flights,
)

# ==================== PDF ====================

def generate_voucher_pdf(vid, path):
    if not REPORTLAB_OK:
        raise Exception("reportlab required")

    v = get_voucher(vid)
    mutamers = get_mutamers(vid)
    accs = get_accommodations(vid)
    flights = get_flights(vid)
    agency = get_setting("agency_name", "LAJPAL TRAVEL LARKANA")
    agency_sub = get_setting("agency_subtitle", "")

    doc = SimpleDocTemplate(
        path, pagesize=A4,
        rightMargin=10*mm, leftMargin=10*mm,
        topMargin=8*mm, bottomMargin=8*mm
    )
    styles = getSampleStyleSheet()
    small = ParagraphStyle('sm', parent=styles['Normal'], fontSize=7, leading=9)
    tiny = ParagraphStyle('ty', parent=styles['Normal'], fontSize=6.5, leading=8)
    center_bold = ParagraphStyle('cb', parent=styles['Normal'], fontSize=11, alignment=TA_CENTER, fontName='Helvetica-Bold', textColor=colors.HexColor('#1a365d'))
    header_agency = ParagraphStyle('ha', parent=styles['Normal'], fontSize=12, alignment=TA_LEFT, fontName='Helvetica-Bold', textColor=colors.HexColor('#1a365d'))
    right_text = ParagraphStyle('rt', parent=styles['Normal'], fontSize=8, alignment=TA_RIGHT, leading=10)
    title_style = ParagraphStyle('ts', parent=styles['Normal'], fontSize=13, alignment=TA_CENTER, fontName='Helvetica-Bold', textColor=colors.HexColor('#1a365d'))

    elements = []

    # Header: Agency | Agent info
    left_h = [
        Paragraph(f"<b>{agency}</b>", header_agency),
        Paragraph(agency_sub or "", tiny),
        Paragraph(f"Voucher Date: {v['voucher_date'] or ''}", tiny),
        Paragraph(f"Package: {v['package_info'] or ''}", tiny),
        Paragraph(f"PAX: {v['pax_info'] or ''}", tiny),
    ]
    right_h = [
        Paragraph(f"<b>{v['agent_name'] or ''}</b>", right_text),
        Paragraph(v['agent_city'] or "", right_text),
        Paragraph(f"WhatsApp: {v['whatsapp'] or ''}", right_text),
    ]
    left_t = Table([[x] for x in left_h], colWidths=[95*mm])
    right_t = Table([[x] for x in right_h], colWidths=[85*mm])
    header_table = Table([[left_t, right_t]], colWidths=[100*mm, 90*mm])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 3))
    elements.append(HRFlowable(width="100%", thickness=1.2, color=colors.HexColor('#1a365d')))
    elements.append(Paragraph("Hotel Voucher", title_style))
    elements.append(Spacer(1, 3))

    # Family Head | Voucher No | Manual No
    fh = Table([[
        Paragraph(f"<b>Family Head:</b>  {v['family_head'] or ''}", small),
        Paragraph(f"<b>{v['voucher_no'] or ''}</b>", ParagraphStyle('vn', fontSize=9, alignment=TA_CENTER, fontName='Helvetica-Bold')),
        Paragraph(f"<b>Manual No:</b>  {v['manual_no'] or ''}", small),
    ]], colWidths=[80*mm, 50*mm, 60*mm])
    fh.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.6, colors.HexColor('#2b6cb0')),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#ebf8ff')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(fh)
    elements.append(Spacer(1, 5))

    # Mutamers table
    elements.append(Paragraph("<b>Mutamers</b>", ParagraphStyle('sec', fontSize=8, fontName='Helvetica-Bold', textColor=colors.HexColor('#1a365d'))))
    mut_header = ['SNO', 'Passport', 'Mutamer Name', 'G', 'PAX', 'Bed', 'Group No', 'Visa #', 'PNR']
    mut_data = [mut_header]
    for m in mutamers:
        mut_data.append([
            str(m['sno'] or ''),
            str(m['passport'] or '')[:14],
            str(m['name'] or '')[:22],
            str(m['gender'] or ''),
            str(m['pax_type'] or ''),
            str(m['bed'] or ''),
            str(m['group_no'] or '')[:12],
            str(m['visa_no'] or '')[:10],
            str(m['pnr'] or '')[:12],
        ])
    if not mutamers:
        mut_data.append(['—', 'No mutamers', '', '', '', '', '', '', ''])

    mt = Table(mut_data, colWidths=[10*mm, 26*mm, 40*mm, 8*mm, 14*mm, 12*mm, 24*mm, 20*mm, 26*mm])
    mt.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a365d')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 6.5),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('ALIGN', (0, 1), (0, -1), 'CENTER'),
        ('ALIGN', (3, 1), (5, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#a0aec0')),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f7fafc')]),
    ]))
    elements.append(mt)
    elements.append(Spacer(1, 5))

    # Accommodation
    elements.append(Paragraph("<b>Accommodation</b>", ParagraphStyle('sec', fontSize=8, fontName='Helvetica-Bold', textColor=colors.HexColor('#1a365d'))))
    acc_header = ['City', 'Hotel Name', 'View', 'Meal', 'Conf#', 'Room Type', 'Checkin', 'Checkout', 'Nights']
    acc_data = [acc_header]
    total_nights = 0
    for a in accs:
        nights = a['nights'] or 0
        total_nights += nights
        acc_data.append([
            str(a['city'] or ''),
            str(a['hotel_name'] or '')[:22],
            str(a['view_type'] or ''),
            str(a['meal'] or ''),
            str(a['conf_no'] or '')[:12],
            str(a['room_type'] or '')[:14],
            str(a['checkin'] or ''),
            str(a['checkout'] or ''),
            str(nights),
        ])
    if not accs:
        acc_data.append(['—', 'No hotels', '', '', '', '', '', '', ''])
    acc_data.append(['', '', '', '', '', '', '', 'Total Nights:', str(total_nights)])

    at = Table(acc_data, colWidths=[18*mm, 38*mm, 16*mm, 12*mm, 22*mm, 26*mm, 18*mm, 18*mm, 14*mm])
    at.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2b6cb0')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 6.5),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('ALIGN', (8, 1), (8, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -2), 0.3, colors.HexColor('#a0aec0')),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#fefcbf')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('LINEABOVE', (0, -1), (-1, -1), 0.8, colors.HexColor('#1a365d')),
    ]))
    elements.append(at)
    elements.append(Spacer(1, 5))

    # Transport
    elements.append(Paragraph("<b>Transport / Services</b>", ParagraphStyle('sec', fontSize=8, fontName='Helvetica-Bold', textColor=colors.HexColor('#1a365d'))))
    tr = Table([[
        Paragraph(f"<b>Transporter:</b> {v['transport_transporter'] or ''}", tiny),
        Paragraph(f"<b>Type:</b> {v['transport_type'] or ''}", tiny),
        Paragraph(f"<b>Description:</b> {v['transport_desc'] or ''}", tiny),
    ]], colWidths=[55*mm, 50*mm, 85*mm])
    tr.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.4, colors.HexColor('#a0aec0')),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f7fafc')),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
    ]))
    elements.append(tr)
    elements.append(Spacer(1, 4))

    # Flights
    dep_flights = [f for f in flights if (f['direction'] or '').lower().startswith('dep')]
    arr_flights = [f for f in flights if (f['direction'] or '').lower().startswith('arr')]
    # if no direction tags, split half
    if not dep_flights and not arr_flights and flights:
        mid = max(1, len(flights)//2)
        dep_flights = list(flights[:mid])
        arr_flights = list(flights[mid:])

    def flight_table(title, flist):
        data = [[title, '', '', ''],
                ['Flight', 'Sector', 'Departure', 'Arrival']]
        for f in flist:
            data.append([
                str(f['flight_no'] or ''),
                str(f['sector'] or ''),
                str(f['departure'] or ''),
                str(f['arrival'] or ''),
            ])
        if not flist:
            data.append(['—', '', '', ''])
        t = Table(data, colWidths=[22*mm, 28*mm, 32*mm, 28*mm])
        t.setStyle(TableStyle([
            ('SPAN', (0, 0), (-1, 0)),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#276749')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#c6f6d5')),
            ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 6.5),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#a0aec0')),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]))
        return t

    ft = Table([[
        flight_table("Departure (Pakistan to KSA)", dep_flights),
        flight_table("Arrival (KSA to PAK)", arr_flights),
    ]], colWidths=[95*mm, 95*mm])
    ft.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 1),
        ('RIGHTPADDING', (0, 0), (-1, -1), 1),
    ]))
    elements.append(ft)
    elements.append(Spacer(1, 5))

    # Special Instructions + QR
    instr = (v['special_instructions'] or '').replace('\n', '<br/>')
    instr_para = Paragraph(f"<b>Special Instructions:</b><br/>{instr}", tiny)

    base_url = get_setting("app_public_url", "").strip().rstrip("/")
    if base_url:
        qr_link = f"{base_url}?view=voucher&id={vid}"
    else:
        qr_link = f"Voucher: {v['voucher_no']}\nFamily: {v['family_head']}\nAgency: {agency}"
    qr_img = None
    try:
        qr_api = f"https://api.qrserver.com/v1/create-qr-code/?size=100x100&margin=4&data={urllib.parse.quote(qr_link)}"
        with urllib.request.urlopen(qr_api, timeout=8) as resp:
            qr_data = resp.read()
        qr_img = RLImage(BytesIO(qr_data), width=22*mm, height=22*mm)
    except Exception:
        pass

    if qr_img:
        bottom = Table([[instr_para, qr_img]], colWidths=[155*mm, 30*mm])
    else:
        bottom = Table([[instr_para]], colWidths=[185*mm])
    bottom.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOX', (0, 0), (-1, -1), 0.4, colors.HexColor('#a0aec0')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),
    ]))
    elements.append(bottom)

    elements.append(Spacer(1, 4))
    elements.append(Paragraph(
        f"{agency}  |  Generated: {datetime.now().strftime('%d-%b-%Y %H:%M')}  |  {v['voucher_no']}",
        ParagraphStyle('ft', fontSize=6, alignment=TA_CENTER, textColor=colors.HexColor('#718096'))
    ))

    doc.build(elements)

# ==================== STREAMLIT UI ====================
st.set_page_config(page_title="Lajpal Travel — Hotel Voucher", page_icon="🏨", layout="wide")
init_db()

# ========== PUBLIC VOUCHER VIEW (QR scan opens this) ==========
qp = st.query_params
if qp.get("view") == "voucher":
    try:
        pub_id = int(qp.get("id", 0))
    except (TypeError, ValueError):
        pub_id = 0
    pub_v = get_voucher(pub_id) if pub_id else None
    if not pub_v:
        st.error("Voucher not found.")
        st.stop()

    agency = get_setting("agency_name", "LAJPAL TRAVEL LARKANA")
    mutamers = get_mutamers(pub_id)
    accs = get_accommodations(pub_id)
    flights = get_flights(pub_id)

    st.markdown("""
    <style>
        [data-testid="stSidebar"] { display: none; }
        #MainMenu, footer { visibility: hidden; }
        @media print { .no-print { display: none !important; } }
    </style>
    """, unsafe_allow_html=True)

    st.markdown(f"### {agency}")
    st.markdown(f"**Hotel Voucher** — `{pub_v['voucher_no']}`")
    st.write(f"**Family Head:** {pub_v['family_head']}  |  **Date:** {pub_v['voucher_date']}  |  **Agent:** {pub_v['agent_name']} ({pub_v['agent_city']})")
    st.write(f"**Package:** {pub_v['package_info']}  |  **PAX:** {pub_v['pax_info']}")
    st.divider()

    st.subheader("Mutamers")
    if mutamers:
        st.dataframe(pd.DataFrame([{
            "SNO": m["sno"], "Passport": m["passport"], "Name": m["name"],
            "G": m["gender"], "PAX": m["pax_type"], "Bed": m["bed"],
            "Group No": m["group_no"], "Visa": m["visa_no"], "PNR": m["pnr"],
        } for m in mutamers]), use_container_width=True, hide_index=True)
    else:
        st.info("No mutamers")

    st.subheader("Accommodation")
    if accs:
        total_n = sum((a["nights"] or 0) for a in accs)
        st.dataframe(pd.DataFrame([{
            "City": a["city"], "Hotel": a["hotel_name"], "View": a["view_type"],
            "Meal": a["meal"], "Conf#": a["conf_no"], "Room": a["room_type"],
            "Checkin": a["checkin"], "Checkout": a["checkout"], "Nights": a["nights"],
        } for a in accs]), use_container_width=True, hide_index=True)
        st.markdown(f"**Total Nights: {total_n}**")
    else:
        st.info("No hotels")

    st.subheader("Transport")
    st.write(f"{pub_v['transport_transporter']} | {pub_v['transport_type']} | {pub_v['transport_desc']}")

    st.subheader("Flights")
    if flights:
        st.dataframe(pd.DataFrame([{
            "Direction": f["direction"], "Flight": f["flight_no"],
            "Sector": f["sector"], "Departure": f["departure"], "Arrival": f["arrival"],
        } for f in flights]), use_container_width=True, hide_index=True)

    if pub_v["special_instructions"]:
        st.subheader("Special Instructions")
        st.write(pub_v["special_instructions"])

    st.caption(f"Generated online | {datetime.now().strftime('%d-%b-%Y %H:%M')}")

    st.markdown('<div class="no-print">', unsafe_allow_html=True)
    st.info("Print: Ctrl+P (Windows) / Cmd+P (Mac)")
    if REPORTLAB_OK:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            generate_voucher_pdf(pub_id, tmp.name)
            with open(tmp.name, "rb") as f:
                st.download_button("📄 Download PDF", f.read(),
                                   file_name=f"Voucher_{pub_v['voucher_no']}.pdf",
                                   mime="application/pdf")
            try:
                os.unlink(tmp.name)
            except Exception:
                pass
    st.markdown('</div>', unsafe_allow_html=True)
    st.stop()

# ========== ADMIN GATE (public users only see voucher via QR) ==========
def _admin_password():
    # Prefer Streamlit secrets, else settings, else default
    try:
        import streamlit as st
        if "ADMIN_PASSWORD" in st.secrets:
            return str(st.secrets["ADMIN_PASSWORD"])
    except Exception:
        pass
    return get_setting("admin_password", "lajpal123")

if "is_admin" not in st.session_state:
    st.session_state.is_admin = False

if not st.session_state.is_admin:
    st.markdown("""
    <style>
        [data-testid="stSidebar"] { display: none; }
        #MainMenu, footer { visibility: hidden; }
    </style>
    """, unsafe_allow_html=True)
    agency = get_setting("agency_name", "LAJPAL TRAVEL LARKANA")
    st.markdown(f"## {agency}")
    st.markdown("### Hotel / Umrah Voucher")
    st.info(
        "Customer ho? Apne **voucher PDF** ka **QR code** scan karein — "
        "sirf aapka voucher khulega.\n\n"
        "Staff ho? Neeche login karein."
    )
    with st.expander("🔐 Staff Login", expanded=False):
        pw = st.text_input("Password", type="password", key="admin_pw_input")
        if st.button("Login", type="primary"):
            if pw == _admin_password():
                st.session_state.is_admin = True
                st.success("Login OK")
                st.rerun()
            else:
                st.error("Galat password")
    st.caption("Public users can only open a voucher via QR link.")
    st.stop()

st.markdown("""
<style>
.main-title { font-size: 1.5rem; font-weight: 700; color: #1a365d; }
.sub { color: #718096; font-size: 0.9rem; }
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### 🏨 Hotel Voucher")
    st.caption(get_setting("agency_name", "LAJPAL TRAVEL LARKANA"))
    try:
        mode = storage_mode()
    except Exception:
        mode = "sqlite"
    if mode == "supabase":
        if supabase_ok():
            st.success("Online DB — connected")
        else:
            st.error("Supabase connect fail — URL/key check karein")
    else:
        st.info("Local SQLite mode")
    st.divider()
    page = st.radio("Menu", [
        "📋 All Vouchers",
        "➕ New Voucher",
        "✏️ Edit Voucher",
        "⚙️ Agency Settings",
    ], label_visibility="collapsed")
    st.divider()
    if st.button("Logout"):
        st.session_state.is_admin = False
        st.rerun()

# ==================== ALL VOUCHERS ====================
if page == "📋 All Vouchers":
    st.markdown('<p class="main-title">All Hotel Vouchers</p>', unsafe_allow_html=True)
    st.markdown(f'<p class="sub">{get_setting("agency_name")}</p>', unsafe_allow_html=True)
    st.divider()

    vouchers = get_all_vouchers()
    if storage_mode() == "supabase" and not supabase_ok():
        st.warning(
            "Supabase connect nahi ho raha — abhi temporary local mode.\n\n"
            "**Fix:** Supabase → Project Settings → API → **Project URL** copy karo "
            "(sirf `https://xxxxx.supabase.co`, `/rest/v1` mat lagao) aur Secrets mein Save + Reboot."
        )
    if not vouchers:
        st.info("Abhi koi voucher nahi. **➕ New Voucher** se pehla voucher banayein.")
    else:
        rows = []
        for v in vouchers:
            muts = get_mutamers(v["id"])
            rows.append({
                "ID": v["id"],
                "Voucher No": v["voucher_no"],
                "Date": v["voucher_date"],
                "Family Head": v["family_head"],
                "Agent": v["agent_name"],
                "Mutamers": len(muts),
                "Package": v["package_info"],
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        # Excel backup
        try:
            import io
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                pd.DataFrame(rows).to_excel(writer, sheet_name="Vouchers", index=False)
                all_mut, all_acc, all_fl = [], [], []
                for v in vouchers:
                    for m in get_mutamers(v["id"]):
                        all_mut.append({**dict(m), "voucher_no": v["voucher_no"]})
                    for a in get_accommodations(v["id"]):
                        all_acc.append({**dict(a), "voucher_no": v["voucher_no"]})
                    for f in get_flights(v["id"]):
                        all_fl.append({**dict(f), "voucher_no": v["voucher_no"]})
                if all_mut:
                    pd.DataFrame(all_mut).to_excel(writer, sheet_name="Mutamers", index=False)
                if all_acc:
                    pd.DataFrame(all_acc).to_excel(writer, sheet_name="Hotels", index=False)
                if all_fl:
                    pd.DataFrame(all_fl).to_excel(writer, sheet_name="Flights", index=False)
            st.download_button("📥 Backup Excel (sab data)", buf.getvalue(),
                               file_name=f"vouchers_backup_{datetime.now().strftime('%Y%m%d')}.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        except Exception as e:
            st.caption(f"Excel backup: {e}")

        st.subheader("Download / Delete")
        c1, c2 = st.columns(2)
        with c1:
            vid = st.number_input("Voucher ID (PDF)", min_value=1, step=1, key="pdf_id")
            if st.button("📄 Download PDF", use_container_width=True):
                if not REPORTLAB_OK:
                    st.error("pip install reportlab")
                else:
                    try:
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                            generate_voucher_pdf(int(vid), tmp.name)
                            v = get_voucher(int(vid))
                            with open(tmp.name, "rb") as f:
                                st.download_button(
                                    "⬇️ Click to save PDF",
                                    f.read(),
                                    file_name=f"Voucher_{v['voucher_no'] if v else vid}.pdf",
                                    mime="application/pdf",
                                    use_container_width=True,
                                )
                            try:
                                os.unlink(tmp.name)
                            except Exception:
                                pass
                    except Exception as e:
                        st.error(str(e))
        with c2:
            del_id = st.number_input("Voucher ID (Delete)", min_value=1, step=1, key="del_id")
            if st.button("🗑️ Delete Voucher", use_container_width=True):
                delete_voucher(int(del_id))
                st.success("Deleted")
                st.rerun()

# ==================== NEW / EDIT VOUCHER ====================
elif page in ("➕ New Voucher", "✏️ Edit Voucher"):
    is_edit = page == "✏️ Edit Voucher"
    st.markdown(f'<p class="main-title">{"Edit" if is_edit else "New"} Hotel Voucher</p>', unsafe_allow_html=True)
    st.divider()

    edit_vid = None
    existing = None
    if is_edit:
        vouchers = get_all_vouchers()
        if not vouchers:
            st.warning("Pehle koi voucher banao.")
            st.stop()
        opts = {f"{v['voucher_no']} — {v['family_head']}": v["id"] for v in vouchers}
        chosen = st.selectbox("Select voucher to edit", list(opts.keys()))
        edit_vid = opts[chosen]
        existing = get_voucher(edit_vid)

    # --- Header fields ---
    st.subheader("1. Header / Agent")
    c1, c2, c3 = st.columns(3)
    with c1:
        voucher_no = st.text_input("Voucher No *", value=(existing["voucher_no"] if existing else next_voucher_no()))
        voucher_date = st.text_input("Voucher Date", value=(existing["voucher_date"] if existing else datetime.now().strftime("%d/%m/%y")))
        family_head = st.text_input("Family Head *", value=(existing["family_head"] if existing else ""))
    with c2:
        agent_name = st.text_input("Agent Name (editable)", value=(existing["agent_name"] if existing else get_setting("default_agent")))
        agent_city = st.text_input("Agent City", value=(existing["agent_city"] if existing else get_setting("default_city", "Larkana")))
        whatsapp = st.text_input("WhatsApp", value=(existing["whatsapp"] if existing else get_setting("default_whatsapp")))
    with c3:
        manual_no = st.text_input("Manual No", value=(existing["manual_no"] if existing else ""))
        package_info = st.text_input("Package (e.g. 20 Standard)", value=(existing["package_info"] if existing else ""))
        pax_info = st.text_input("PAX (e.g. 7 (A:6,C:1,I:0),Beds=7)", value=(existing["pax_info"] if existing else ""))

    # --- Mutamers ---
    st.subheader("2. Mutamers (Passengers)")
    if is_edit and edit_vid:
        existing_muts = [dict(m) for m in get_mutamers(edit_vid)]
    else:
        existing_muts = []
    if not existing_muts:
        existing_muts = [{"passport": "", "name": "", "gender": "M", "pax_type": "Adult", "bed": "Yes", "group_no": "", "visa_no": "", "pnr": ""}]

    mut_df = pd.DataFrame(existing_muts)
    for col in ["passport", "name", "gender", "pax_type", "bed", "group_no", "visa_no", "pnr"]:
        if col not in mut_df.columns:
            mut_df[col] = ""
    mut_df = mut_df[["passport", "name", "gender", "pax_type", "bed", "group_no", "visa_no", "pnr"]]
    edited_muts = st.data_editor(
        mut_df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "gender": st.column_config.SelectboxColumn("G", options=["M", "F"], required=True),
            "pax_type": st.column_config.SelectboxColumn("PAX", options=["Adult", "Child", "Infant"], required=True),
            "bed": st.column_config.SelectboxColumn("Bed", options=["Yes", "No"], required=True),
            "passport": st.column_config.TextColumn("Passport"),
            "name": st.column_config.TextColumn("Mutamer Name"),
            "group_no": st.column_config.TextColumn("Group No"),
            "visa_no": st.column_config.TextColumn("Visa #"),
            "pnr": st.column_config.TextColumn("PNR"),
        },
        key="mut_editor",
    )

    # --- Accommodation ---
    st.subheader("3. Accommodation (Hotels)")
    st.caption("Option A: Check-in + Check-out → nights auto.  |  Option B: Check-in + Nights number → checkout auto. Format: 08-10-26")
    if is_edit and edit_vid:
        existing_acc = [dict(a) for a in get_accommodations(edit_vid)]
    else:
        existing_acc = []
    if not existing_acc:
        existing_acc = [
            {"city": "Makkah", "hotel_name": "", "view_type": "Standard", "meal": "RO", "conf_no": "", "room_type": "Sharing (Family)", "checkin": "", "checkout": "", "nights": 0},
            {"city": "Medina", "hotel_name": "", "view_type": "Standard", "meal": "RO", "conf_no": "", "room_type": "Sharing (Family)", "checkin": "", "checkout": "", "nights": 0},
        ]
    acc_df = pd.DataFrame(existing_acc)
    for col in ["city", "hotel_name", "view_type", "meal", "conf_no", "room_type", "checkin", "checkout", "nights"]:
        if col not in acc_df.columns:
            acc_df[col] = "" if col != "nights" else 0
    acc_df = acc_df[["city", "hotel_name", "view_type", "meal", "conf_no", "room_type", "checkin", "checkout", "nights"]]
    edited_acc = st.data_editor(
        acc_df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "city": st.column_config.SelectboxColumn("City", options=["Makkah", "Medina", "Jeddah", "Other"]),
            "meal": st.column_config.SelectboxColumn("Meal", options=["RO", "BB", "HB", "FB", "AI"]),
            "view_type": st.column_config.TextColumn("View"),
            "hotel_name": st.column_config.TextColumn("Hotel Name"),
            "conf_no": st.column_config.TextColumn("Conf#"),
            "room_type": st.column_config.TextColumn("Room Type"),
            "checkin": st.column_config.TextColumn("Checkin"),
            "checkout": st.column_config.TextColumn("Checkout"),
            "nights": st.column_config.NumberColumn("Nights", min_value=0, step=1),
        },
        key="acc_editor",
    )
    # Live auto preview (nights OR checkout)
    try:
        _preview = []
        for _, row in edited_acc.iterrows():
            city = str(row.get("city", "") or "")
            hotel = str(row.get("hotel_name", "") or "")
            label = city or hotel or "Hotel"
            synced = sync_acc_dates(row)
            n = calc_nights(row.get("checkin"), row.get("checkout"))
            if n is not None:
                _preview.append(f"**{label}**: {n} nights (dates se)")
            else:
                co = calc_checkout(row.get("checkin"), row.get("nights"))
                if co:
                    _preview.append(f"**{label}**: checkout auto → {co}")
        if _preview:
            st.info("Auto:  " + "  |  ".join(_preview))
    except Exception:
        pass

    # --- Transport ---
    st.subheader("4. Transport / Services")
    c1, c2, c3 = st.columns(3)
    with c1:
        transport_transporter = st.text_input("Transporter", value=(existing["transport_transporter"] if existing else "Company Transport"))
    with c2:
        transport_type = st.text_input("Type", value=(existing["transport_type"] if existing else "Economy By Bus"))
    with c3:
        transport_desc = st.text_input("Description", value=(existing["transport_desc"] if existing else "Round Trip (Jed-Mak-Med-Mak-Jed)"))

    # --- Flights ---
    st.subheader("5. Flights")
    if is_edit and edit_vid:
        existing_fl = [dict(f) for f in get_flights(edit_vid)]
    else:
        existing_fl = []
    if not existing_fl:
        existing_fl = [
            {"direction": "Departure", "flight_no": "", "sector": "", "departure": "", "arrival": ""},
            {"direction": "Arrival", "flight_no": "", "sector": "", "departure": "", "arrival": ""},
        ]
    fl_df = pd.DataFrame(existing_fl)
    for col in ["direction", "flight_no", "sector", "departure", "arrival"]:
        if col not in fl_df.columns:
            fl_df[col] = ""
    fl_df = fl_df[["direction", "flight_no", "sector", "departure", "arrival"]]
    edited_fl = st.data_editor(
        fl_df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "direction": st.column_config.SelectboxColumn("Direction", options=["Departure", "Arrival"]),
            "flight_no": st.column_config.TextColumn("Flight"),
            "sector": st.column_config.TextColumn("Sector"),
            "departure": st.column_config.TextColumn("Departure"),
            "arrival": st.column_config.TextColumn("Arrival"),
        },
        key="fl_editor",
    )

    # --- Instructions ---
    st.subheader("6. Special Instructions (Urdu / English)")
    special_instructions = st.text_area(
        "Instructions",
        value=(existing["special_instructions"] if existing else get_setting("default_instructions")),
        height=120,
    )

    # --- Save ---
    st.divider()
    if st.button("💾 Save Voucher", type="primary", use_container_width=True):
        if not voucher_no.strip() or not family_head.strip():
            st.error("Voucher No aur Family Head zaroori hain.")
        else:
            data = {
                "voucher_no": voucher_no.strip(),
                "manual_no": manual_no.strip(),
                "voucher_date": voucher_date.strip(),
                "agent_name": agent_name.strip(),
                "agent_city": agent_city.strip(),
                "whatsapp": whatsapp.strip(),
                "package_info": package_info.strip(),
                "pax_info": pax_info.strip(),
                "family_head": family_head.strip(),
                "transport_transporter": transport_transporter.strip(),
                "transport_type": transport_type.strip(),
                "transport_desc": transport_desc.strip(),
                "special_instructions": special_instructions.strip(),
            }
            try:
                if is_edit and edit_vid:
                    update_voucher(edit_vid, data)
                    vid = edit_vid
                else:
                    vid = create_voucher(data)

                mut_rows = edited_muts.to_dict("records")
                mut_rows = [r for r in mut_rows if str(r.get("name", "")).strip() or str(r.get("passport", "")).strip()]
                set_mutamers(vid, mut_rows)

                acc_rows = edited_acc.to_dict("records")
                acc_rows = [r for r in acc_rows if str(r.get("hotel_name", "")).strip() or str(r.get("city", "")).strip()]
                # Auto: dates->nights OR checkin+nights->checkout
                acc_rows = [sync_acc_dates(r) for r in acc_rows]
                set_accommodations(vid, acc_rows)

                fl_rows = edited_fl.to_dict("records")
                fl_rows = [r for r in fl_rows if str(r.get("flight_no", "")).strip() or str(r.get("sector", "")).strip()]
                set_flights(vid, fl_rows)

                st.success(f"Voucher saved: {voucher_no}")
                st.balloons()
            except sqlite3.IntegrityError:
                st.error("Yeh Voucher No pehle se maujood hai. Alag number use karein.")
            except Exception as e:
                st.error(str(e))

# ==================== SETTINGS ====================
elif page == "⚙️ Agency Settings":
    st.markdown('<p class="main-title">Agency Settings</p>', unsafe_allow_html=True)
    st.caption("Yahan se agency name aur defaults edit ho sakte hain — har voucher pe apply hote hain.")
    st.divider()

    st.subheader("🔗 App Public URL (QR ke liye zaroori)")
    st.caption("Streamlit Cloud ka link yahan paste karein. Example: https://lajpal-hotel-voucher-xxxx.streamlit.app")
    cur_url = get_setting("app_public_url", "")
    new_url = st.text_input("Public App URL", value=cur_url, placeholder="https://your-app.streamlit.app")
    if st.button("💾 Save App URL"):
        set_setting("app_public_url", new_url.strip().rstrip("/"))
        st.success("URL saved! Ab naya PDF banayein — QR scan pe sirf voucher open hoga.")
        st.rerun()
    if cur_url:
        st.info(f"Current: {cur_url}")
        st.code(f"{cur_url.rstrip('/')}?view=voucher&id=1", language=None)
        st.caption("QR isi format ki link use karta hai — public user ko sirf voucher dikhega, admin nahi.")
    else:
        st.warning("URL save kiye baghair QR mein sirf text hoga, link nahi.")

    st.subheader("🔐 Staff Login Password")
    st.caption("Public app pe staff login isi password se hoga. Default: lajpal123")
    cur_pw = get_setting("admin_password", "lajpal123")
    new_pw = st.text_input("Admin Password", value=cur_pw, type="password")
    if st.button("💾 Save Password"):
        set_setting("admin_password", new_pw.strip() or "lajpal123")
        st.success("Password saved")
        st.rerun()

    st.divider()

    with st.form("settings_form"):
        agency_name = st.text_input("Agency Name *", value=get_setting("agency_name", "LAJPAL TRAVEL LARKANA"))
        agency_subtitle = st.text_input("Subtitle (e.g. PVT LTD)", value=get_setting("agency_subtitle", ""))
        default_agent = st.text_input("Default Agent Name", value=get_setting("default_agent", ""))
        default_city = st.text_input("Default City", value=get_setting("default_city", "Larkana"))
        default_whatsapp = st.text_input("Default WhatsApp", value=get_setting("default_whatsapp", ""))
        default_instructions = st.text_area("Default Special Instructions", value=get_setting("default_instructions", ""), height=150)
        if st.form_submit_button("💾 Save Settings", use_container_width=True):
            set_setting("agency_name", agency_name.strip() or "LAJPAL TRAVEL LARKANA")
            set_setting("agency_subtitle", agency_subtitle.strip())
            set_setting("default_agent", default_agent.strip())
            set_setting("default_city", default_city.strip())
            set_setting("default_whatsapp", default_whatsapp.strip())
            set_setting("default_instructions", default_instructions.strip())
            st.success("Settings saved!")
            st.rerun()

st.markdown("---")
st.caption(f"{get_setting('agency_name', 'LAJPAL TRAVEL LARKANA')} — Hotel / Umrah Voucher System")
