"""
Dual storage: SQLite (local) + Supabase (online permanent)
"""
import sqlite3
import json
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent / "vouchers.db"

def _use_supabase():
    """Return True only if Supabase secrets are properly set."""
    try:
        import streamlit as st
        secrets = getattr(st, "secrets", None)
        if secrets is None:
            return False
        try:
            url = secrets["SUPABASE_URL"]
            key = secrets["SUPABASE_KEY"]
        except Exception:
            return False
        url = str(url or "").strip()
        key = str(key or "").strip()
        return len(url) > 0 and len(key) > 0
    except Exception:
        return False

def _supabase():
    from supabase import create_client
    import streamlit as st
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

# ---------- SQLite ----------
def _sql_conn():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    if _use_supabase():
        # Tables must exist on Supabase (user runs SQL once) — just verify connection
        try:
            sb = _supabase()
            sb.table("settings").select("key").limit(1).execute()
        except Exception:
            pass
        _ensure_supabase_defaults()
        return

    conn = _sql_conn()
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)""")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS vouchers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            voucher_no TEXT UNIQUE, manual_no TEXT, voucher_date TEXT,
            agent_name TEXT, agent_city TEXT, whatsapp TEXT,
            package_info TEXT, pax_info TEXT, family_head TEXT,
            transport_transporter TEXT, transport_type TEXT, transport_desc TEXT,
            special_instructions TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS mutamers (
            id INTEGER PRIMARY KEY AUTOINCREMENT, voucher_id INTEGER, sno INTEGER,
            passport TEXT, name TEXT, gender TEXT, pax_type TEXT, bed TEXT,
            group_no TEXT, visa_no TEXT, pnr TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS accommodations (
            id INTEGER PRIMARY KEY AUTOINCREMENT, voucher_id INTEGER,
            city TEXT, hotel_name TEXT, view_type TEXT, meal TEXT, conf_no TEXT,
            room_type TEXT, checkin TEXT, checkout TEXT, nights INTEGER
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS flights (
            id INTEGER PRIMARY KEY AUTOINCREMENT, voucher_id INTEGER,
            direction TEXT, flight_no TEXT, sector TEXT, departure TEXT, arrival TEXT
        )
    """)
    defaults = {
        "agency_name": "LAJPAL TRAVEL LARKANA",
        "agency_subtitle": "",
        "default_agent": "",
        "default_city": "Larkana",
        "default_whatsapp": "",
        "default_instructions": (
            "- آپ ہوٹل اور ٹرانسپورٹ کی ہدایات پر عمل کریں۔\n"
            "- چیک اِن / چیک آؤٹ اوقات کا خیال رکھیں۔\n"
            "- پاسپورٹ اور ضروری دستاویزات ساتھ رکھیں۔\n"
            "- کسی مسئلے کی صورت میں فوری ایجنسی سے رابطہ کریں۔"
        ),
        "app_public_url": "",
    }
    for k, v in defaults.items():
        cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
    conn.commit()
    conn.close()

def _ensure_supabase_defaults():
    defaults = {
        "agency_name": "LAJPAL TRAVEL LARKANA",
        "agency_subtitle": "",
        "default_agent": "",
        "default_city": "Larkana",
        "default_whatsapp": "",
        "default_instructions": (
            "- آپ ہوٹل اور ٹرانسپورٹ کی ہدایات پر عمل کریں۔\n"
            "- چیک اِن / چیک آؤٹ اوقات کا خیال رکھیں۔\n"
            "- پاسپورٹ اور ضروری دستاویزات ساتھ رکھیں۔"
        ),
        "app_public_url": "",
    }
    try:
        sb = _supabase()
        existing = {r["key"] for r in (sb.table("settings").select("key").execute().data or [])}
        for k, v in defaults.items():
            if k not in existing:
                sb.table("settings").insert({"key": k, "value": v}).execute()
    except Exception:
        pass

def storage_mode():
    try:
        return "supabase" if _use_supabase() else "sqlite"
    except Exception:
        return "sqlite"

def get_setting(key, default=""):
    if _use_supabase():
        try:
            r = _supabase().table("settings").select("value").eq("key", key).limit(1).execute()
            if r.data:
                return r.data[0]["value"]
        except Exception:
            pass
        return default
    conn = _sql_conn()
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = cur.fetchone()
    conn.close()
    return row["value"] if row else default

def set_setting(key, value):
    if _use_supabase():
        sb = _supabase()
        existing = sb.table("settings").select("key").eq("key", key).execute()
        if existing.data:
            sb.table("settings").update({"value": value}).eq("key", key).execute()
        else:
            sb.table("settings").insert({"key": key, "value": value}).execute()
        return
    conn = _sql_conn()
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

def next_voucher_no():
    rows = get_all_vouchers()
    if rows:
        last = rows[0].get("voucher_no") or ""
        parts = last.rsplit("-", 1)
        if len(parts) == 2 and parts[1].isdigit():
            return f"{parts[0]}-{int(parts[1])+1:06d}"
    return f"UB-{datetime.now().strftime('%y')}0001"

def get_all_vouchers():
    if _use_supabase():
        r = _supabase().table("vouchers").select("*").order("id", desc=True).execute()
        return r.data or []
    conn = _sql_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM vouchers ORDER BY id DESC")
    rows = [dict(x) for x in cur.fetchall()]
    conn.close()
    return rows

def get_voucher(vid):
    if _use_supabase():
        r = _supabase().table("vouchers").select("*").eq("id", vid).limit(1).execute()
        return r.data[0] if r.data else None
    conn = _sql_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM vouchers WHERE id=?", (vid,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def create_voucher(data):
    payload = {
        "voucher_no": data["voucher_no"], "manual_no": data.get("manual_no", ""),
        "voucher_date": data["voucher_date"], "agent_name": data["agent_name"],
        "agent_city": data["agent_city"], "whatsapp": data.get("whatsapp", ""),
        "package_info": data.get("package_info", ""), "pax_info": data.get("pax_info", ""),
        "family_head": data["family_head"],
        "transport_transporter": data.get("transport_transporter", ""),
        "transport_type": data.get("transport_type", ""),
        "transport_desc": data.get("transport_desc", ""),
        "special_instructions": data.get("special_instructions", ""),
    }
    if _use_supabase():
        r = _supabase().table("vouchers").insert(payload).execute()
        return r.data[0]["id"]
    conn = _sql_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO vouchers (
            voucher_no, manual_no, voucher_date, agent_name, agent_city, whatsapp,
            package_info, pax_info, family_head, transport_transporter, transport_type,
            transport_desc, special_instructions
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, tuple(payload.values()))
    vid = cur.lastrowid
    conn.commit()
    conn.close()
    return vid

def update_voucher(vid, data):
    payload = {
        "voucher_no": data["voucher_no"], "manual_no": data.get("manual_no", ""),
        "voucher_date": data["voucher_date"], "agent_name": data["agent_name"],
        "agent_city": data["agent_city"], "whatsapp": data.get("whatsapp", ""),
        "package_info": data.get("package_info", ""), "pax_info": data.get("pax_info", ""),
        "family_head": data["family_head"],
        "transport_transporter": data.get("transport_transporter", ""),
        "transport_type": data.get("transport_type", ""),
        "transport_desc": data.get("transport_desc", ""),
        "special_instructions": data.get("special_instructions", ""),
    }
    if _use_supabase():
        _supabase().table("vouchers").update(payload).eq("id", vid).execute()
        return
    conn = _sql_conn()
    cur = conn.cursor()
    cur.execute("""
        UPDATE vouchers SET
            voucher_no=?, manual_no=?, voucher_date=?, agent_name=?, agent_city=?, whatsapp=?,
            package_info=?, pax_info=?, family_head=?, transport_transporter=?, transport_type=?,
            transport_desc=?, special_instructions=? WHERE id=?
    """, (*payload.values(), vid))
    conn.commit()
    conn.close()

def delete_voucher(vid):
    if _use_supabase():
        sb = _supabase()
        sb.table("mutamers").delete().eq("voucher_id", vid).execute()
        sb.table("accommodations").delete().eq("voucher_id", vid).execute()
        sb.table("flights").delete().eq("voucher_id", vid).execute()
        sb.table("vouchers").delete().eq("id", vid).execute()
        return
    conn = _sql_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM mutamers WHERE voucher_id=?", (vid,))
    cur.execute("DELETE FROM accommodations WHERE voucher_id=?", (vid,))
    cur.execute("DELETE FROM flights WHERE voucher_id=?", (vid,))
    cur.execute("DELETE FROM vouchers WHERE id=?", (vid,))
    conn.commit()
    conn.close()

def get_mutamers(vid):
    if _use_supabase():
        r = _supabase().table("mutamers").select("*").eq("voucher_id", vid).order("sno").execute()
        return r.data or []
    conn = _sql_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM mutamers WHERE voucher_id=? ORDER BY sno, id", (vid,))
    rows = [dict(x) for x in cur.fetchall()]
    conn.close()
    return rows

def set_mutamers(vid, rows):
    if _use_supabase():
        sb = _supabase()
        sb.table("mutamers").delete().eq("voucher_id", vid).execute()
        if rows:
            payload = []
            for i, r in enumerate(rows, 1):
                payload.append({
                    "voucher_id": vid, "sno": i,
                    "passport": r.get("passport", ""), "name": r.get("name", ""),
                    "gender": r.get("gender", "M"), "pax_type": r.get("pax_type", "Adult"),
                    "bed": r.get("bed", "Yes"), "group_no": r.get("group_no", ""),
                    "visa_no": r.get("visa_no", ""), "pnr": r.get("pnr", ""),
                })
            sb.table("mutamers").insert(payload).execute()
        return
    conn = _sql_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM mutamers WHERE voucher_id=?", (vid,))
    for i, r in enumerate(rows, 1):
        cur.execute("""
            INSERT INTO mutamers (voucher_id, sno, passport, name, gender, pax_type, bed, group_no, visa_no, pnr)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (vid, i, r.get("passport",""), r.get("name",""), r.get("gender","M"),
              r.get("pax_type","Adult"), r.get("bed","Yes"), r.get("group_no",""),
              r.get("visa_no",""), r.get("pnr","")))
    conn.commit()
    conn.close()

def get_accommodations(vid):
    if _use_supabase():
        r = _supabase().table("accommodations").select("*").eq("voucher_id", vid).order("id").execute()
        return r.data or []
    conn = _sql_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM accommodations WHERE voucher_id=? ORDER BY id", (vid,))
    rows = [dict(x) for x in cur.fetchall()]
    conn.close()
    return rows

def set_accommodations(vid, rows):
    if _use_supabase():
        sb = _supabase()
        sb.table("accommodations").delete().eq("voucher_id", vid).execute()
        if rows:
            payload = [{
                "voucher_id": vid, "city": r.get("city",""), "hotel_name": r.get("hotel_name",""),
                "view_type": r.get("view_type","Standard"), "meal": r.get("meal","RO"),
                "conf_no": r.get("conf_no",""), "room_type": r.get("room_type",""),
                "checkin": r.get("checkin",""), "checkout": r.get("checkout",""),
                "nights": int(r.get("nights") or 0),
            } for r in rows]
            sb.table("accommodations").insert(payload).execute()
        return
    conn = _sql_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM accommodations WHERE voucher_id=?", (vid,))
    for r in rows:
        cur.execute("""
            INSERT INTO accommodations (voucher_id, city, hotel_name, view_type, meal, conf_no, room_type, checkin, checkout, nights)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (vid, r.get("city",""), r.get("hotel_name",""), r.get("view_type","Standard"),
              r.get("meal","RO"), r.get("conf_no",""), r.get("room_type",""),
              r.get("checkin",""), r.get("checkout",""), int(r.get("nights") or 0)))
    conn.commit()
    conn.close()

def get_flights(vid):
    if _use_supabase():
        r = _supabase().table("flights").select("*").eq("voucher_id", vid).order("id").execute()
        return r.data or []
    conn = _sql_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM flights WHERE voucher_id=? ORDER BY id", (vid,))
    rows = [dict(x) for x in cur.fetchall()]
    conn.close()
    return rows

def set_flights(vid, rows):
    if _use_supabase():
        sb = _supabase()
        sb.table("flights").delete().eq("voucher_id", vid).execute()
        if rows:
            payload = [{
                "voucher_id": vid, "direction": r.get("direction",""),
                "flight_no": r.get("flight_no",""), "sector": r.get("sector",""),
                "departure": r.get("departure",""), "arrival": r.get("arrival",""),
            } for r in rows]
            sb.table("flights").insert(payload).execute()
        return
    conn = _sql_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM flights WHERE voucher_id=?", (vid,))
    for r in rows:
        cur.execute("""
            INSERT INTO flights (voucher_id, direction, flight_no, sector, departure, arrival)
            VALUES (?,?,?,?,?,?)
        """, (vid, r.get("direction",""), r.get("flight_no",""), r.get("sector",""),
              r.get("departure",""), r.get("arrival","")))
    conn.commit()
    conn.close()
