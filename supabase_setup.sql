-- Run this once in Supabase → SQL Editor → New query → Run

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT
);

CREATE TABLE IF NOT EXISTS vouchers (
  id BIGSERIAL PRIMARY KEY,
  voucher_no TEXT UNIQUE,
  manual_no TEXT,
  voucher_date TEXT,
  agent_name TEXT,
  agent_city TEXT,
  whatsapp TEXT,
  package_info TEXT,
  pax_info TEXT,
  family_head TEXT,
  transport_transporter TEXT,
  transport_type TEXT,
  transport_desc TEXT,
  special_instructions TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS mutamers (
  id BIGSERIAL PRIMARY KEY,
  voucher_id BIGINT REFERENCES vouchers(id) ON DELETE CASCADE,
  sno INT,
  passport TEXT,
  name TEXT,
  gender TEXT,
  pax_type TEXT,
  bed TEXT,
  group_no TEXT,
  visa_no TEXT,
  pnr TEXT
);

CREATE TABLE IF NOT EXISTS accommodations (
  id BIGSERIAL PRIMARY KEY,
  voucher_id BIGINT REFERENCES vouchers(id) ON DELETE CASCADE,
  city TEXT,
  hotel_name TEXT,
  view_type TEXT,
  meal TEXT,
  conf_no TEXT,
  room_type TEXT,
  checkin TEXT,
  checkout TEXT,
  nights INT
);

CREATE TABLE IF NOT EXISTS flights (
  id BIGSERIAL PRIMARY KEY,
  voucher_id BIGINT REFERENCES vouchers(id) ON DELETE CASCADE,
  direction TEXT,
  flight_no TEXT,
  sector TEXT,
  departure TEXT,
  arrival TEXT
);

-- Allow public access for app (simple setup)
ALTER TABLE settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE vouchers ENABLE ROW LEVEL SECURITY;
ALTER TABLE mutamers ENABLE ROW LEVEL SECURITY;
ALTER TABLE accommodations ENABLE ROW LEVEL SECURITY;
ALTER TABLE flights ENABLE ROW LEVEL SECURITY;

CREATE POLICY "allow_all_settings" ON settings FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "allow_all_vouchers" ON vouchers FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "allow_all_mutamers" ON mutamers FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "allow_all_accommodations" ON accommodations FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "allow_all_flights" ON flights FOR ALL USING (true) WITH CHECK (true);
