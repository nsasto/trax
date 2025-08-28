# Trax – Personal Finance ETL with Plaid

Trax is a little app I built to help me collect and consolidate my own financial data. If you find it useful, feel free to use or adapt it for your own needs.

Trax lets you connect your UK/EU bank accounts using Plaid, pulls your transactions, and stores everything in a local SQLite database. It’s designed for privacy, extensibility, and tinkering.

At the moment it's simply a data funnel for further analysis.

---

## ✨ What Trax Does

- Connects to your banks via **Plaid Link**
- Handles **OAuth redirects** for UK/EU banks (Amex, Monzo, Virgin Money, Investec, etc.)
- Stores linked accounts and tokens in SQLite (`.tokens.sqlite`)
- Shows your linked banks, institution names, and consent expiry
- Lets you:
  - **Link a new bank**
  - **Relink** (refresh consent)
  - **Delete** (revoke and remove from DB)
- Ready to extend: add `/transactions/sync` to pull transactions into your own analytics DB

---

## 🛠 What You’ll Need

- Python 3.9+
- Virtualenv (`python -m venv .venv`)
- A Plaid account and API keys ([dashboard.plaid.com](https://dashboard.plaid.com))
- For OAuth:
  - A valid **HTTPS redirect URI** (use a self-signed cert for `https://localhost:5000/oauth-return`, or [ngrok](https://ngrok.com/)). you can run `python cert.py` to create them for you.

---

## ⚙️ Setup

Clone the repo and install dependencies:

```bash
git clone https://github.com/you/trax.git
cd trax
python -m venv .venv
.venv\Scripts\activate   # PowerShell on Windows
pip install -r requirements.txt
```

### Environment variables

Copy `.env.example` to `.env` and fill in your Plaid keys:

```env
PLAID_ENV=sandbox               # or development / production
PLAID_CLIENT_ID=your_client_id
PLAID_SECRET=your_secret
PLAID_REDIRECT_URI=https://localhost:5000/oauth-return
```

➡️ Make sure your redirect URI is whitelisted in the Plaid Dashboard (**API → OAuth Redirect URIs**) for your environment.

### SSL certificates (for [https://localhost](https://localhost))

To use OAuth locally, you’ll need HTTPS. You can generate self-signed certs or use ngrok:

```bash
mkdir certs
pip install pyopenssl
python makecert.py  # generates certs/cert.pem and certs/key.pem
```

---

## 🚀 Running Trax

Start the Flask app:

```bash
python app.py
```

Visit:

```
https://localhost:5000/
```

Open that URL in your browser. You’ll need to accept the self-signed certificate warning the first time.

---

## 🖥️ UI Overview

- **Home page** (`/`):
  - Lists your linked banks, consent expiry (color coded), and action buttons:
    - `Link new bank` – connect a new institution
    - `Relink` – refresh login/consent for an existing Item
    - `Delete` – revoke a bank connection
- **OAuth return** (`/oauth-return`):
  - Plaid redirects here for banks that use OAuth. The page resumes Link automatically.

---

## 📦 Database

Trax uses two SQLite databases:

- `.tokens.sqlite` – stores Plaid Items and access tokens (internal use only)
- `finance.db` – (optional) your analytics DB for transactions/accounts

---

## 🔑 Environments

- **Sandbox**: Test with Platypus Bank, Tartan Bank, etc. (canned data)
- **Development**: Connect to real banks with your own accounts (limit: ~100 Items)
- **Production**: Full scale; requires Plaid approval and compliance review

Switch environments by changing `PLAID_ENV` in your `.env` file.

---

## 🧹 Deleting a Link

When you click **Delete** in the UI:

- The Item is removed at Plaid (`/item/remove`)
- The record is deleted from `.tokens.sqlite`

You can also extend this to purge historical transactions from `finance.db` if you want.

---

## 🛣 Next Steps & Ideas

- Add a `/transactions/sync` endpoint to pull and classify transactions
- Extend `finance.db` with `accounts` and `transactions` tables
- Add background jobs for nightly syncs
- Classify spending categories with ML or rules

---

## 📝 License

MIT
