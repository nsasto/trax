import os, sqlite3, datetime as dt
from dotenv import load_dotenv
import pandas as pd
from plaid.api import plaid_api
from plaid import Configuration, ApiClient
from plaid.model import TransactionsSyncRequest, AccountsGetRequest, ItemGetRequest

load_dotenv()
PLAID_CLIENT_ID = os.getenv("PLAID_CLIENT_ID")
PLAID_SECRET = os.getenv("PLAID_SECRET")
PLAID_ENV = os.getenv("PLAID_ENV", "sandbox")

PLAID_ENV_URLS = {
    "SANDBOX": "https://sandbox.plaid.com",
    "DEVELOPMENT": "https://development.plaid.com",
    "PRODUCTION": "https://production.plaid.com",
}
conf = Configuration(
    host=PLAID_ENV_URLS[os.getenv("PLAID_ENV", "sandbox").upper()],
    api_key={
        "clientId": os.getenv("PLAID_CLIENT_ID"),
        "secret": os.getenv("PLAID_SECRET"),
    },
)
client = plaid_api.PlaidApi(ApiClient(conf))

TOK_DB = ".tokens.sqlite"
tok_conn = sqlite3.connect(TOK_DB)
items = [r[0] for r in tok_conn.execute("SELECT item_id FROM items").fetchall()]
tok_conn.close()

DB = "finance.db"
conn = sqlite3.connect(DB)
conn.executescript(open("db.sql").read())
cur = conn.cursor()

# Keep cursors in a tiny meta table
cur.execute(
    """CREATE TABLE IF NOT EXISTS cursors(
  item_id TEXT PRIMARY KEY,
  cursor TEXT
)"""
)
conn.commit()


def upsert_connection(item_id, institution_id, institution_name):
    cur.execute(
        """
      INSERT INTO connections(item_id,institution_id,institution_name,created_utc,last_sync_utc)
      VALUES(?,?,?,?,?)
      ON CONFLICT(item_id) DO UPDATE SET
        institution_id=excluded.institution_id,
        institution_name=excluded.institution_name,
        last_sync_utc=excluded.last_sync_utc
    """,
        (
            item_id,
            institution_id,
            institution_name,
            dt.datetime.utcnow().isoformat(),
            dt.datetime.utcnow().isoformat(),
        ),
    )


def upsert_accounts(item_id, accounts):
    for a in accounts:
        cur.execute(
            """
          INSERT INTO accounts(account_id,item_id,name,official_name,type,subtype,currency)
          VALUES(?,?,?,?,?,?,?)
          ON CONFLICT(account_id) DO UPDATE SET
            name=excluded.name, official_name=excluded.official_name,
            type=excluded.type, subtype=excluded.subtype, currency=excluded.currency
        """,
            (
                a["account_id"],
                item_id,
                a.get("name"),
                a.get("official_name"),
                a.get("type"),
                a.get("subtype"),
                a.get("iso_currency_code"),
            ),
        )


def categorise(row):
    # Take Plaid primary category when available, else simple rules
    if row.get("personal_finance_category"):
        primary = row["personal_finance_category"].get("primary")
        if primary:
            return primary, "plaid"
    # very light rules example
    desc = (row.get("merchant_name") or row.get("name") or "").upper()
    if "TESCO" in desc:
        return "Groceries", "rules"
    if "AMAZON" in desc:
        return "Shopping", "rules"
    return "Uncategorized", "fallback"


def upsert_transactions(item_id, txs):
    for t in txs:
        # Normalise sign: expenses negative
        amount = -abs(t["amount"]) if t["amount"] > 0 else t["amount"]
        cat, src = categorise(t)
        cur.execute(
            """
          INSERT INTO transactions(
            transaction_id, account_id, posted_date, description, merchant_name,
            amount, currency, mcc, category, category_src, plaid_category, pending
          ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(transaction_id) DO UPDATE SET
            account_id=excluded.account_id,
            posted_date=excluded.posted_date,
            description=excluded.description,
            merchant_name=excluded.merchant_name,
            amount=excluded.amount,
            currency=excluded.currency,
            mcc=excluded.mcc,
            category=excluded.category,
            category_src=excluded.category_src,
            plaid_category=excluded.plaid_category,
            pending=excluded.pending
        """,
            (
                t["transaction_id"],
                t["account_id"],
                t["date"],
                t.get("name"),
                t.get("merchant_name"),
                amount,
                t.get("iso_currency_code"),
                t.get("mcc"),
                cat,
                src,
                (t.get("personal_finance_category") or {}).get("primary"),
                1 if t.get("pending") else 0,
            ),
        )


def sync_item(item_id, access_token):
    # fetch institution info + accounts for mapping
    item = client.item_get(ItemGetRequest(access_token=access_token)).to_dict()
    inst_id = (item.get("item") or {}).get("institution_id")
    accounts = client.accounts_get(
        AccountsGetRequest(access_token=access_token)
    ).to_dict()["accounts"]

    upsert_connection(item_id, inst_id, None)
    upsert_accounts(item_id, accounts)
    conn.commit()

    # cursor-based sync
    row = cur.execute(
        "SELECT cursor FROM cursors WHERE item_id=?", (item_id,)
    ).fetchone()
    cursor_val = row[0] if row else None
    added, modified, removed = [], [], []
    has_more = True

    while has_more:
        req = TransactionsSyncRequest(access_token=access_token, cursor=cursor_val)
        resp = client.transactions_sync(req).to_dict()
        added += resp["added"]
        modified += resp["modified"]
        removed += resp["removed"]
        cursor_val = resp["next_cursor"]
        has_more = resp["has_more"]

    # Apply changes (removed items will just stop appearing; we typically don’t hard-delete)
    upsert_transactions(item_id, added + modified)
    cur.execute(
        "INSERT OR REPLACE INTO cursors(item_id, cursor) VALUES (?,?)",
        (item_id, cursor_val),
    )
    cur.execute(
        "UPDATE connections SET last_sync_utc=? WHERE item_id=?",
        (dt.datetime.utcnow().isoformat(), item_id),
    )
    conn.commit()


def main():
    tok_conn = sqlite3.connect(TOK_DB)
    rows = tok_conn.execute("SELECT item_id, access_token FROM items").fetchall()
    tok_conn.close()
    for item_id, access_token in rows:
        sync_item(item_id, access_token)
    print("Sync complete → finance.db")


if __name__ == "__main__":
    main()
