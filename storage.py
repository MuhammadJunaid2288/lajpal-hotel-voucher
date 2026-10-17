import os
import sqlite3
import pandas as pd
import json
from datetime import datetime

class StorageManager:
    def __init__(self, secrets=None):
        self.use_supabase = False
        self.supabase = None
        
        url = None
        key = None
        if secrets:
            url = secrets.get("SUPABASE_URL")
            key = secrets.get("SUPABASE_KEY")
        
        if url and key:
            try:
                from supabase import create_client
                self.supabase = create_client(url, key)
                # Test call with timeout safety
                self.supabase.table("vouchers").select("count", count="exact").execute()
                self.use_supabase = True
            except Exception as e:
                print(f"Supabase connection bypassed due to error: {e}")
                self.use_supabase = False
                
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

    def get_setting(self, key, default=""):
        if self.use_supabase:
            try:
                res = self.supabase.table("settings").select("value").eq("key", key).execute()
                if res.data and len(res.data) > 0:
                    return res.data[0]["value"]
            except Exception:
                pass
            return default
        else:
            cursor = self.conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row[0] if row else default

    def set_setting(self, key, value):
        if self.use_supabase:
            try:
                self.supabase.table("settings").upsert({"key": key, "value": value}).execute()
                return True
            except Exception as e:
                print(f"Error setting {key}: {e}")
                return False
        else:
            cursor = self.conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
            self.conn.commit()
            return True

    def save_voucher(self, voucher_no, data_dict):
        if self.use_supabase:
            try:
                self.supabase.table("vouchers").upsert({
                    "voucher_no": voucher_no,
                    "data": data_dict
                }, on_conflict="voucher_no").execute()
                return True
            except Exception as e:
                print(f"Error saving voucher: {e}")
                return False
        else:
            cursor = self.conn.cursor()
            json_str = json.dumps(data_dict)
            cursor.execute("INSERT OR REPLACE INTO vouchers (voucher_no, data) VALUES (?, ?)", (voucher_no, json_str))
            self.conn.commit()
            return True

    def get_voucher(self, voucher_no):
        if self.use_supabase:
            try:
                res = self.supabase.table("vouchers").select("data").eq("voucher_no", voucher_no).execute()
                if res.data and len(res.data) > 0:
                    return res.data[0]["data"]
            except Exception:
                pass
            return None
        else:
            cursor = self.conn.cursor()
            cursor.execute("SELECT data FROM vouchers WHERE voucher_no = ?", (voucher_no,))
            row = cursor.fetchone()
            return json.loads(row[0]) if row else None

    def list_vouchers(self):
        if self.use_supabase:
            try:
                res = self.supabase.table("vouchers").select("voucher_no, created_at, data").order("created_at", desc=True).execute()
                records = []
                for row in res.data:
                    d = row.get("data", {})
                    records.append({
                        "Voucher No": row.get("voucher_no"),
                        "Created At": row.get("created_at"),
                        "Guest Name": d.get("passenger_name", ""),
                        "Hotel": d.get("hotel_name", ""),
                        "City": d.get("city", "")
                    })
                return pd.DataFrame(records)
            except Exception:
                return pd.DataFrame()
        else:
            cursor = self.conn.cursor()
            cursor.execute("SELECT voucher_no, created_at, data FROM vouchers ORDER BY id DESC")
            rows = cursor.fetchall()
            records = []
            for r in rows:
                d = json.loads(r[2]) if r[2] else {}
                records.append({
                    "Voucher No": r[0],
                    "Created At": r[1],
                    "Guest Name": d.get("passenger_name", ""),
                    "Hotel": d.get("hotel_name", ""),
                    "City": d.get("city", "")
                })
            return pd.DataFrame(records)

# Aliases for app.py
Storage = StorageManager

def get_storage(secrets=None):
    return StorageManager(secrets)
