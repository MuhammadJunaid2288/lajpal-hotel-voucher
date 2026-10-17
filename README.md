# LAJPAL TRAVEL — Hotel Voucher (Local + Online Permanent)

## Local (computer pe)
```bash
pip install -r requirements.txt
streamlit run app.py
```
Data `vouchers.db` mein save rehti hai — permanent.

## Online permanent (Streamlit Cloud + Supabase free)

### 1) Supabase account
1. https://supabase.com → free account
2. New project banao
3. SQL Editor mein `supabase_setup.sql` poora paste karke **Run**
4. Settings → API:
   - Project URL copy
   - `anon` `public` key copy

### 2) Streamlit Cloud secrets
App → Settings → Secrets → yeh paste karo:

```toml
SUPABASE_URL = "https://xxxx.supabase.co"
SUPABASE_KEY = "eyJhbGciOi..."
```

Save → Reboot app.

Sidebar mein **Online DB — data permanent** dikhega.

### 3) App Public URL
Agency Settings mein Streamlit app URL save karo taake QR scan pe voucher open ho.

## Features
- Check-in + Checkout → nights auto
- Check-in + Nights number → checkout auto
- Multi vouchers, PDF, QR, Excel backup
- Agency/agent names editable
