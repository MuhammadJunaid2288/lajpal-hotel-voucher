import os
import json
import sqlite3
import pandas as pd
from datetime import datetime

# Global storage mode indicator
storage_mode = "SQLite (Local)"

class StorageManager:
    def __init__(self, secrets=None):
        global storage_mode
        self.use_supabase = False
        self.supabase = None
        
        url = None
        key = None
        
        # Streamlit Secrets check
        try:
            import streamlit as st
            if hasattr(st, "secrets"):
                url = st.secrets.get("SUPABASE_URL")
                key = st.secrets.get("SUPABASE_KEY")
        except Exception:
            pass

        if not url and secrets:
            url = secrets.get("SUPABASE_URL")
            key = secrets.get("SUPABASE_KEY")

        if url and key:
            try:
                from supabase import create_client
                self.supabase = create_client(url, key)
                self.supabase.table("vouchers").select("count", count="exact").execute()
                self.use_supabase = True
                storage_mode = "Supabase (Cloud Online)"
            except Exception as e:
                print(f"Supabase connection error: {e}")
                self.use_supabase = False
                storage_mode = "SQLite (Fallback)"

        if not self.use_supabase:
            self._init_sqlite()

    def _init_sqlite(self):
        self.conn = sqlite3.connect("vouchers.db", check_same_thread=False)
        self._create_tables()

    def _create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS vouchers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                voucher_no TEXT UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                data JSON
            )
        ''')
        self.conn.commit()

# Singleton instance setup
def _get_inst():
    if not hasattr(_get_inst, "_instance"):
        _get_inst._instance = StorageManager()
    return _get_inst._instance

def init_db():
    _get_inst()

def get_setting(key, default=""):
    st_inst = _get_inst()
    if st_inst.use_supabase:
        try:
            res = st_inst.supabase.table("settings").select("value").eq("key", key).execute()
            if res.data and len(res.data) > 0:
                return res.data[0]["value"]
        except Exception:
            pass
        return default
    else:
        cursor = st_inst.conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row[0] if row else default

def set_setting(key, value):
    st_inst = _get_inst()
    if st_inst.use_supabase:
        try:
            st_inst.supabase.table("settings").upsert({"key": key, "value": value}).execute()
            return True
        except Exception as e:
            print(f"Error setting {key}: {e}")
            return False
    else:
        cursor = st_inst.conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        st_inst.conn.commit()
        return True

def next_voucher_no():
    vouchers = get_all_vouchers()
    if not vouchers:
        return "LV-1001"
    try:
        nums = [int(v.get("voucher_no", "1000").split("-")[-1]) for v in vouchers if "-" in str(v.get("voucher_no", ""))]
        return f"LV-{max(nums) + 1}" if nums else "LV-1001"
    except Exception:
        return f"LV-{len(vouchers) + 1001}"

def get_all_vouchers():
    st_inst = _get_inst()
    if st_inst.use_supabase:
        try:
            res = st_inst.supabase.table("vouchers").select("*").order("created_at", desc=True).execute()
            v_list = []
            for row in res.data:
                d = row.get("data", {})
                if isinstance(d, str):
                    d = json.loads(d)
                d["voucher_no"] = row.get("voucher_no")
                d["id"] = row.get("id")
                v_list.append(d)
            return v_list
        except Exception:
            return []
    else:
        cursor = st_inst.conn.cursor()
        cursor.execute("SELECT id, voucher_no, data FROM vouchers ORDER BY id DESC")
        rows = cursor.fetchall()
        v_list = []
        for r in rows:
            d = json.loads(r[2]) if r[2] else {}
            d["id"] = r[0]
            d["voucher_no"] = r[1]
            v_list.append(d)
        return v_list

def get_voucher(voucher_no_or_id):
    st_inst = _get_inst()
    v_str = str(voucher_no_or_id)
    if st_inst.use_supabase:
        try:
            res = st_inst.supabase.table("vouchers").select("data").eq("voucher_no", v_str).execute()
            if res.data and len(res.data) > 0:
                d = res.data[0]["data"]
                return json.loads(d) if isinstance(d, str) else d
        except Exception:
            pass
        return {}
    else:
        cursor = st_inst.conn.cursor()
        cursor.execute("SELECT data FROM vouchers WHERE voucher_no = ?", (v_str,))
        row = cursor.fetchone()
        return json.loads(row[0]) if row else {}

def create_voucher(v_data):
    st_inst = _get_inst()
    v_no = v_data.get("voucher_no") or next_voucher_no()
    v_data["voucher_no"] = v_no
    if st_inst.use_supabase:
        try:
            st_inst.supabase.table("vouchers").upsert({"voucher_no": v_no, "data": v_data}, on_conflict="voucher_no").execute()
            return v_no
        except Exception as e:
            print(f"Error creating voucher: {e}")
            return None
    else:
        cursor = st_inst.conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO vouchers (voucher_no, data) VALUES (?, ?)", (v_no, json.dumps(v_data)))
        st_inst.conn.commit()
        return v_no

def update_voucher(v_no, v_data):
    return create_voucher(v_data)

def delete_voucher(v_no):
    st_inst = _get_inst()
    if st_inst.use_supabase:
        try:
            st_inst.supabase.table("vouchers").delete().eq("voucher_no", str(v_no)).execute()
            return True
        except Exception:
            return False
    else:
        cursor = st_inst.conn.cursor()
        cursor.execute("DELETE FROM vouchers WHERE voucher_no = ?", (str(v_no),))
        st_inst.conn.commit()
        return True

def get_mutamers(v_no):
    v = get_voucher(v_no)
    return v.get("mutamers", [])

def set_mutamers(v_no, mutamers):
    v = get_voucher(v_no) or {}
    v["mutamers"] = mutamers
    return update_voucher(v_no, v)

def get_accommodations(v_no):
    v = get_voucher(v_no)
    return v.get("accommodations", [])

def set_accommodations(v_no, accs):
    v = get_voucher(v_no) or {}
    v["accommodations"] = accs
    return update_voucher(v_no, v)

def get_flights(v_no):
    v = get_voucher(v_no)
    return v.get("flights", [])

def set_flights(v_no, flights):
    v = get_voucher(v_no) or {}
    v["flights"] = flights
    return update_voucher(v_no, v)

# Class Aliases
StorageManager = StorageManager
Storage = StorageManager
def get_storage(secrets=None):
    return StorageManager(secrets)
