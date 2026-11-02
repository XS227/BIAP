-- AI Accounting store. Amounts are integer ore (1/100 NOK): no float rounding.
-- Every business table carries company_id, and child rows reference their parent
-- through (company_id, id) composite keys so a row can never point into another company.
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS companies (
  id          INTEGER PRIMARY KEY,
  org_number  TEXT NOT NULL UNIQUE,
  name        TEXT NOT NULL,
  is_test     INTEGER NOT NULL DEFAULT 0,
  created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS company_users (
  company_id  INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  user_id     TEXT NOT NULL,
  role        TEXT NOT NULL CHECK (role IN ('owner','accountant','viewer')),
  PRIMARY KEY (company_id, user_id)
);

CREATE TABLE IF NOT EXISTS accounts (
  company_id         INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  account_id         TEXT NOT NULL,
  description        TEXT NOT NULL,
  grouping_category  TEXT NOT NULL,
  grouping_code      TEXT NOT NULL,
  opening_ore        INTEGER NOT NULL DEFAULT 0,   -- debit positive, credit negative
  PRIMARY KEY (company_id, account_id)
);

CREATE TABLE IF NOT EXISTS tax_codes (
  company_id         INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  tax_code           TEXT NOT NULL,
  description        TEXT NOT NULL,
  standard_tax_code  TEXT NOT NULL CHECK (standard_tax_code GLOB '[0-9a-zA-Z]*' AND length(standard_tax_code) BETWEEN 1 AND 2),
  PRIMARY KEY (company_id, tax_code)
);

CREATE TABLE IF NOT EXISTS entries (
  company_id        INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  id                INTEGER NOT NULL,
  transaction_id    TEXT NOT NULL,
  period            TEXT NOT NULL,
  period_year       TEXT NOT NULL,
  transaction_date  TEXT NOT NULL,
  description       TEXT NOT NULL,
  system_entry_date TEXT NOT NULL,
  gl_posting_date   TEXT NOT NULL,
  source            TEXT NOT NULL CHECK (source IN ('manual','file')),
  PRIMARY KEY (company_id, id),
  UNIQUE (company_id, transaction_id)
);

CREATE TABLE IF NOT EXISTS lines (
  company_id   INTEGER NOT NULL,
  entry_id     INTEGER NOT NULL,
  record_id    TEXT NOT NULL,
  account_id   TEXT NOT NULL,
  description  TEXT NOT NULL,
  amount_ore   INTEGER NOT NULL CHECK (amount_ore <> 0),  -- debit positive, credit negative
  tax_code     TEXT,
  PRIMARY KEY (company_id, entry_id, record_id),
  FOREIGN KEY (company_id, entry_id)   REFERENCES entries(company_id, id)  ON DELETE CASCADE,
  FOREIGN KEY (company_id, account_id) REFERENCES accounts(company_id, account_id),
  FOREIGN KEY (company_id, tax_code)   REFERENCES tax_codes(company_id, tax_code)
);

-- Posted entries are append-only: no edits, corrections are new entries.
CREATE TRIGGER IF NOT EXISTS entries_no_update BEFORE UPDATE ON entries
BEGIN SELECT RAISE(ABORT, 'posted entries are immutable'); END;
CREATE TRIGGER IF NOT EXISTS lines_no_update BEFORE UPDATE ON lines
BEGIN SELECT RAISE(ABORT, 'posted lines are immutable'); END;
