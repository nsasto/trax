CREATE TABLE IF NOT EXISTS connections (
  item_id TEXT PRIMARY KEY,
  institution_id TEXT,
  institution_name TEXT,
  consent_expires_utc TEXT, -- optional if you track it from Link callbacks
  created_utc TEXT NOT NULL,
  last_sync_utc TEXT
);

CREATE TABLE IF NOT EXISTS accounts (
  account_id TEXT PRIMARY KEY,
  item_id TEXT NOT NULL,
  name TEXT,
  official_name TEXT,
  type TEXT,
  subtype TEXT,
  currency TEXT,
  FOREIGN KEY(item_id) REFERENCES connections(item_id)
);

CREATE TABLE IF NOT EXISTS transactions (
  transaction_id TEXT PRIMARY KEY,
  account_id TEXT NOT NULL,
  posted_date TEXT NOT NULL,
  description TEXT,
  merchant_name TEXT,
  amount NUMERIC NOT NULL,  -- expenses negative (see ETL)
  currency TEXT,
  mcc TEXT,
  category TEXT,            -- final category after rules
  category_src TEXT,        -- 'rules' | 'plaid' | 'fallback'
  plaid_category TEXT,      -- Plaid personal_finance_category.primary if present
  pending INTEGER DEFAULT 0,
  FOREIGN KEY(account_id) REFERENCES accounts(account_id)
);

CREATE INDEX IF NOT EXISTS idx_txn_account_date ON transactions(account_id, posted_date);
