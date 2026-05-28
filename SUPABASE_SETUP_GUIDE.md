# How to Find Your Supabase Credentials

## Step 1: Sign Up / Log In to Supabase

1. Go to **https://supabase.com**
2. Click "Start your project" or "Sign In"
3. Sign up with GitHub, Google, or email (all free)

---

## Step 2: Create a New Project (if needed)

1. Click **"New Project"**
2. Choose:
   - **Organization:** (default is fine)
   - **Project name:** "trading-bot" (or any name)
   - **Database password:** Create a strong password (save this!)
   - **Region:** Choose closest to you
   - **Pricing plan:** Free tier is perfect
3. Click **"Create new project"**
4. Wait 2-3 minutes for project to initialize

---

## Step 3: Get Your Credentials

Once your project is ready:

1. In the left sidebar, click **"Settings"** (gear icon)
2. Click **"API"** in the Settings menu
3. You'll see two important values:

### **Project URL**
```
https://[your-project-id].supabase.co
```
This is your `SUPABASE_URL`

### **API Keys**
You'll see two keys:

#### **anon public** (NOT what you need)
- Safe for frontend
- Has limited permissions
- DON'T use this for backend

#### **service_role secret** (THIS IS WHAT YOU NEED)
- Full database access
- For backend only
- **⚠️ NEVER expose this publicly!**
- This is your `SUPABASE_SERVICE_ROLE_KEY`

---

## Step 4: Add to Your .env File

Open your backend `.env` file and add:

```bash
# Supabase Configuration
SUPABASE_URL=https://abcdefghijklmnop.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# Note: Replace the values above with your actual values from Supabase dashboard
```

### Example .env file:
```bash
# Required - Market Data
TWELVEDATA_API_KEY=your_twelvedata_key_here

# Required - Supabase Database
SUPABASE_URL=https://xyzabc123.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFz...

# Optional - Capital.com Auto Trading
CAPITAL_API_KEY=your_capital_key
CAPITAL_PASSWORD=your_capital_password
CAPITAL_IDENTIFIER=your_capital_identifier
CAPITAL_ENV=demo

# Optional - Logging
LOG_LEVEL=INFO
```

---

## Security Best Practices

### ✅ DO:
- Use **service_role key** for backend only
- Store credentials in `.env` file
- Add `.env` to `.gitignore`
- Rotate keys if exposed

### ❌ DON'T:
- Never commit `.env` file to Git
- Never use service_role key in frontend
- Never share keys publicly
- Never expose keys in browser console

---

## Verify Your Setup

After adding credentials to `.env`, test the connection:

```bash
# From your backend directory
python -c "from modules import database_supabase as db; db.init_db(); print('✅ Supabase connected!')"
```

If successful, you'll see:
```
✅ Supabase connected!
Supabase client initialized
```

---

## Troubleshooting

### Error: "Invalid API key"
- Double-check you copied the **service_role** key (not anon key)
- Ensure no extra spaces or line breaks

### Error: "Project not found"
- Check your `SUPABASE_URL` is correct
- Make sure project isn't paused (free tier projects pause after 7 days inactive)

### Error: "Connection refused"
- Check your internet connection
- Verify Supabase project is running (not paused)
- Try clicking "Resume project" in Supabase dashboard

---

## Visual Guide

### Where to Find in Dashboard:

```
Supabase Dashboard
├── Left Sidebar
│   └── Settings ⚙️
│       └── API
│           ├── Project URL
│           │   └── https://xyz.supabase.co  ← Copy this
│           │
│           └── Project API keys
│               ├── anon public ← Don't use
│               └── service_role secret ← Copy this
```

---

## Quick Checklist

Before proceeding, ensure you have:

- [ ] Created Supabase account
- [ ] Created new project (or using existing)
- [ ] Copied **Project URL** → `SUPABASE_URL`
- [ ] Copied **service_role key** → `SUPABASE_SERVICE_ROLE_KEY`
- [ ] Added both to `.env` file
- [ ] Verified connection works

---

## Your Existing .env File

I see you already have these variables in your `.env`:

```bash
VITE_SUPABASE_URL=https://0ec90b57d6e95fcbda19832f.supabase.co
VITE_SUPABASE_SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Note:** These are for the **frontend** (VITE_ prefix):
- `VITE_SUPABASE_URL` — Frontend can access Supabase directly
- `VITE_SUPABASE_ANON_KEY` — Safe public key for frontend

**For backend, you need different keys:**
- `SUPABASE_URL` — Same URL
- `SUPABASE_SERVICE_ROLE_KEY` — Secret key for backend

### Update your .env like this:

```bash
# Frontend (already have)
VITE_SUPABASE_URL=https://0ec90b57d6e95fcbda19832f.supabase.co
VITE_SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# Backend (add these)
SUPABASE_URL=https://0ec90b57d6e95fcbda19832f.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<get from Supabase dashboard>
```

Both URLs are the same, but you need the **service_role key** from the dashboard.

---

## Need Help?

1. **Supabase docs:** https://supabase.com/docs
2. **Dashboard:** https://supabase.com/dashboard
3. **Community:** https://github.com/supabase/supabase/discussions

---

## Summary

1. Go to https://supabase.com/dashboard
2. Open your project
3. Settings → API
4. Copy:
   - **Project URL**
   - **service_role key** (NOT anon key)
5. Add to `.env`:
   - `SUPABASE_URL=<project-url>`
   - `SUPABASE_SERVICE_ROLE_KEY=<service-role-key>`

That's it! 🎉
