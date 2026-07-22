-- ============================================================================
-- Phase 5 — Extended CIB seed: realistic volumes + new domain tables.
-- Idempotent: safe to re-run via `\i 03_seed_extended.sql` on existing DB.
-- ============================================================================
-- Adds:
--   * 7 new tables: country_ref, industry_ref, rm_user, client_contact,
--                   fx_rate, transaction, daily_balance, covenant, collateral,
--                   rating_history
--   * +180 clients (CIF0000021..0000200) with realistic distributions
--   * +570 accounts, +275 exposures
--   * 730 days of fx_rate per currency, 50k+ daily_balance rows,
--     ~10k transactions, 80 covenants, 60 collateral records,
--     50 rating-history rows.
--
-- Designed to exercise: time series, FX conversion, PII guardrails,
-- multi-table joins, SCD2 lookups, regulatory reporting.
-- ============================================================================

SET client_min_messages = WARNING;

-- ---------------------------------------------------------------------------
-- 1. Reference tables
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS country_ref (
    country_iso  char(2)      PRIMARY KEY,
    country_name varchar(80)  NOT NULL,
    region       varchar(32)  NOT NULL,         -- APAC / EMEA / NAM / LATAM
    risk_tier    varchar(8)   NOT NULL,         -- LOW / MED / HIGH / SANCT
    is_fatf_grey boolean      NOT NULL DEFAULT false
);

INSERT INTO country_ref VALUES
  ('US','United States',   'NAM','LOW',  false),
  ('CA','Canada',           'NAM','LOW',  false),
  ('GB','United Kingdom',   'EMEA','LOW', false),
  ('DE','Germany',          'EMEA','LOW', false),
  ('FR','France',           'EMEA','LOW', false),
  ('CH','Switzerland',      'EMEA','LOW', false),
  ('IT','Italy',            'EMEA','LOW', false),
  ('NO','Norway',           'EMEA','LOW', false),
  ('IS','Iceland',          'EMEA','LOW', false),
  ('EG','Egypt',            'EMEA','HIGH',true),
  ('JP','Japan',            'APAC','LOW', false),
  ('HK','Hong Kong SAR',    'APAC','LOW', false),
  ('SG','Singapore',        'APAC','LOW', false),
  ('CN','China',            'APAC','MED', false),
  ('IN','India',            'APAC','MED', false),
  ('AU','Australia',        'APAC','LOW', false),
  ('MY','Malaysia',         'APAC','MED', false),
  ('ID','Indonesia',        'APAC','MED', false),
  ('TH','Thailand',         'APAC','MED', false),
  ('VN','Vietnam',          'APAC','MED', false),
  ('KR','South Korea',      'APAC','LOW', false),
  ('PH','Philippines',      'APAC','HIGH',true),
  ('MN','Mongolia',         'APAC','HIGH',false),
  ('NZ','New Zealand',      'APAC','LOW', false),
  ('BR','Brazil',           'LATAM','MED',false),
  ('MX','Mexico',           'LATAM','MED',false),
  ('AR','Argentina',        'LATAM','HIGH',false),
  ('CL','Chile',            'LATAM','LOW',false),
  ('CO','Colombia',         'LATAM','MED',false),
  ('AE','United Arab Emirates','EMEA','LOW',false)
ON CONFLICT (country_iso) DO NOTHING;

CREATE TABLE IF NOT EXISTS industry_ref (
    industry      varchar(64)  PRIMARY KEY,
    sector        varchar(32)  NOT NULL,        -- Cyclical / Defensive / Tech / Financial
    naics_top     varchar(8),
    is_esg_focus  boolean      NOT NULL DEFAULT false
);

INSERT INTO industry_ref VALUES
  ('Manufacturing','Cyclical','31',  false),
  ('Energy',       'Cyclical','21',  true),
  ('Transport',    'Cyclical','48',  false),
  ('Consumer',     'Defensive','44', false),
  ('Healthcare',   'Defensive','62', false),
  ('Aerospace',    'Cyclical','33',  false),
  ('Mining',       'Cyclical','21',  true),
  ('Automotive',   'Cyclical','33',  true),
  ('Technology',   'Tech',    '54',  false),
  ('Telecom',      'Tech',    '51',  false),
  ('Forestry',     'Cyclical','11',  true),
  ('Financials',   'Financial','52', false),
  ('Travel',       'Cyclical','72',  false),
  ('Hotels',       'Cyclical','72',  false),
  ('Retail',       'Cyclical','44',  false),
  ('Insurance',    'Financial','52', false),
  ('Utilities',    'Defensive','22', true),
  ('RealEstate',   'Cyclical','53',  false),
  ('Agriculture',  'Defensive','11', true),
  ('Chemicals',    'Cyclical','32',  true)
ON CONFLICT (industry) DO NOTHING;

-- ---------------------------------------------------------------------------
-- 2. Relationship Manager master (PII: email + phone + employee_id)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rm_user (
    rm_email      varchar(80)  PRIMARY KEY,
    full_name     varchar(120) NOT NULL,
    phone         varchar(32)  NOT NULL,
    employee_id   varchar(16)  NOT NULL UNIQUE,
    business_unit varchar(32)  NOT NULL,        -- CIB-APAC / CIB-EMEA / CIB-NAM
    cost_center   varchar(16)  NOT NULL,
    hired_at      date         NOT NULL,
    is_active     boolean      NOT NULL DEFAULT true
);

INSERT INTO rm_user VALUES
  ('alice@bank',  'Alice Wong',     '+852-2345-6789','EMP00012','CIB-APAC','CC-AP-01','2017-03-01',true),
  ('bob@bank',    'Bob Schmidt',    '+44-20-7946-0123','EMP00018','CIB-EMEA','CC-EM-04','2016-08-15',true),
  ('carol@bank',  'Carol Martinez', '+1-212-555-0188','EMP00027','CIB-NAM','CC-NA-02','2018-11-20',true),
  ('dan@bank',    'Dan Chen',       '+65-6789-0123','EMP00041','CIB-APAC','CC-AP-02','2020-02-10',true),
  ('eva@bank',    'Eva Petrova',    '+41-44-678-9012','EMP00055','CIB-EMEA','CC-EM-01','2019-06-05',true),
  ('frank@bank',  'Frank Tanaka',   '+81-3-5678-9012','EMP00063','CIB-APAC','CC-AP-03','2021-04-12',true),
  ('grace@bank',  'Grace Mueller',  '+49-69-1234-5678','EMP00072','CIB-EMEA','CC-EM-02','2015-09-30',true),
  ('henry@bank',  'Henry Park',     '+82-2-3456-7890','EMP00081','CIB-APAC','CC-AP-04','2022-01-17',true),
  ('iris@bank',   'Iris Dubois',    '+33-1-4567-8901','EMP00094','CIB-EMEA','CC-EM-03','2014-12-01',true),
  ('jack@bank',   'Jack Wilson',    '+1-415-555-0234','EMP00103','CIB-NAM','CC-NA-01','2023-03-22',true)
ON CONFLICT (rm_email) DO NOTHING;

-- ---------------------------------------------------------------------------
-- 3. Bulk-extend CLIENT to ~200 rows.
--    Uses generate_series + deterministic hash so re-runs are idempotent.
-- ---------------------------------------------------------------------------
WITH industries AS (SELECT industry FROM industry_ref),
     countries  AS (SELECT country_iso FROM country_ref),
     rms        AS (SELECT rm_email FROM rm_user WHERE is_active),
     gen AS (
       SELECT n,
              'CIF' || LPAD(n::text, 7, '0') AS cif_id,
              -- Deterministic pseudo-random picks
              (n * 7919) % (SELECT COUNT(*) FROM industries) AS ind_idx,
              (n * 6491) % (SELECT COUNT(*) FROM countries)  AS ctry_idx,
              (n * 4339) % (SELECT COUNT(*) FROM rms)        AS rm_idx,
              (n * 1009) AS aum_seed,
              (n * 251)  AS rating_seed,
              (n * 113)  AS days_seed
       FROM generate_series(21, 200) AS n
     )
INSERT INTO client (cif_id, legal_name, country_iso, industry, rm_owner,
                    aum_usd, risk_rating, onboarded_at, is_active)
SELECT
    gen.cif_id,
    -- Synthetic but plausible legal names
    CASE (n % 12)
      WHEN 0 THEN 'Aurum '   WHEN 1 THEN 'Vector '  WHEN 2  THEN 'Nimbus '
      WHEN 3 THEN 'Orion '   WHEN 4 THEN 'Helix '   WHEN 5  THEN 'Zenith '
      WHEN 6 THEN 'Polaris ' WHEN 7 THEN 'Crescent ' WHEN 8 THEN 'Meridian '
      WHEN 9 THEN 'Vanguard ' WHEN 10 THEN 'Beacon ' ELSE 'Summit ' END
    ||
    CASE ((n / 12) % 10)
      WHEN 0 THEN 'Capital'  WHEN 1 THEN 'Holdings' WHEN 2 THEN 'Industries'
      WHEN 3 THEN 'Group'    WHEN 4 THEN 'Partners' WHEN 5 THEN 'Logistics'
      WHEN 6 THEN 'Resources' WHEN 7 THEN 'Trading' WHEN 8 THEN 'Solutions'
      ELSE 'International' END
    ||
    CASE (n % 5)
      WHEN 0 THEN ' Ltd' WHEN 1 THEN ' SA' WHEN 2 THEN ' GmbH'
      WHEN 3 THEN ' Inc' ELSE ' Plc' END,
    (SELECT country_iso FROM countries ORDER BY country_iso OFFSET ctry_idx LIMIT 1),
    (SELECT industry    FROM industries ORDER BY industry  OFFSET ind_idx  LIMIT 1),
    (SELECT rm_email    FROM rms        ORDER BY rm_email  OFFSET rm_idx   LIMIT 1),
    -- Power-law-ish AUM distribution: 5M..5B USD
    (5000000::bigint + (aum_seed % 5000)::bigint * 1000000::bigint)::numeric(18,2),
    -- Rating distribution roughly biased to BBB/A
    CASE (rating_seed % 100)
      WHEN  0 THEN 'AAA' WHEN  1 THEN 'AAA'
      WHEN  2 THEN 'AA'  WHEN  3 THEN 'AA'  WHEN 4 THEN 'AA' WHEN 5 THEN 'AA'
      WHEN  6 THEN 'A'   WHEN  7 THEN 'A'   WHEN 8 THEN 'A'  WHEN 9 THEN 'A'
      WHEN 10 THEN 'A'   WHEN 11 THEN 'A'
      WHEN 12 THEN 'BBB' WHEN 13 THEN 'BBB' WHEN 14 THEN 'BBB' WHEN 15 THEN 'BBB'
      WHEN 16 THEN 'BBB' WHEN 17 THEN 'BBB' WHEN 18 THEN 'BBB' WHEN 19 THEN 'BBB'
      ELSE
        CASE ((rating_seed / 100) % 5)
          WHEN 0 THEN 'BB' WHEN 1 THEN 'BB' WHEN 2 THEN 'B' WHEN 3 THEN 'B' ELSE 'CCC'
        END
    END,
    (DATE '2014-01-01' + (days_seed % 4000) * INTERVAL '1 day')::date,
    (n % 23) <> 0     -- ~4% inactive
FROM gen
ON CONFLICT (cif_id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- 4. Client contacts (PII playground — should be blocked by pii_guard)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS client_contact (
    contact_id    serial      PRIMARY KEY,
    cif_id        varchar(16) NOT NULL REFERENCES client(cif_id),
    full_name     varchar(120) NOT NULL,        -- PII
    email         varchar(120) NOT NULL,        -- PII
    phone         varchar(32)  NOT NULL,        -- PII
    role_title    varchar(64)  NOT NULL,
    is_primary    boolean      NOT NULL DEFAULT false,
    created_at    timestamp    NOT NULL DEFAULT now()
);

INSERT INTO client_contact (cif_id, full_name, email, phone, role_title, is_primary)
SELECT
  c.cif_id,
  CASE (row_number() OVER (PARTITION BY c.cif_id ORDER BY i)) % 8
    WHEN 0 THEN 'James Anderson'  WHEN 1 THEN 'Mary Robinson'
    WHEN 2 THEN 'Wei Chen'        WHEN 3 THEN 'Priya Patel'
    WHEN 4 THEN 'Hans Bauer'      WHEN 5 THEN 'Sofia Rossi'
    WHEN 6 THEN 'Kenji Yamada'    ELSE 'Olivia Martin' END
  || ' #' || c.cif_id,
  'contact' || (row_number() OVER (PARTITION BY c.cif_id ORDER BY i))
    || '.' || lower(c.cif_id) || '@example.com',
  '+1-555-' || LPAD((abs(hashtext(c.cif_id || i::text)) % 10000)::text, 4, '0'),
  CASE i WHEN 1 THEN 'CFO' WHEN 2 THEN 'Treasurer' ELSE 'Operations' END,
  i = 1
FROM client c
CROSS JOIN generate_series(1, 2) AS i
WHERE NOT EXISTS (SELECT 1 FROM client_contact cc WHERE cc.cif_id = c.cif_id);

-- ---------------------------------------------------------------------------
-- 5. FX rates: daily snapshot per currency for last 730 days.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fx_rate (
    rate_date     date         NOT NULL,
    currency      char(3)      NOT NULL,
    usd_per_unit  numeric(18,8) NOT NULL,       -- 1 unit of currency = X USD
    PRIMARY KEY (rate_date, currency)
);

WITH ccys(currency, base) AS (VALUES
   ('USD',1.00000000),('EUR',1.08000000),('GBP',1.26000000),('JPY',0.00650000),
   ('CHF',1.12000000),('CAD',0.74000000),('HKD',0.12800000),('CNY',0.13800000),
   ('SGD',0.74500000),('AUD',0.66000000),('NZD',0.61000000),('NOK',0.09200000),
   ('SEK',0.09500000),('DKK',0.14500000),('INR',0.01200000),('MYR',0.21000000),
   ('IDR',0.00006300),('THB',0.02750000),('PHP',0.01750000),('KRW',0.00074000),
   ('BRL',0.20000000),('MXN',0.05800000),('ARS',0.00110000),('CLP',0.00105000),
   ('AED',0.27200000),('EGP',0.02050000),('ISK',0.00720000)
),
days AS (SELECT generate_series(CURRENT_DATE - 730, CURRENT_DATE, INTERVAL '1 day')::date AS d)
INSERT INTO fx_rate (rate_date, currency, usd_per_unit)
SELECT d, currency,
       -- ±5% sinusoidal walk so time-series queries find a real signal
       (base * (1 + 0.05 * sin( (extract(doy from d)::int + ascii(currency)) / 30.0 )))::numeric(18,8)
FROM days CROSS JOIN ccys
ON CONFLICT (rate_date, currency) DO NOTHING;

-- ---------------------------------------------------------------------------
-- 6. Bulk-extend ACCOUNT to ~600 rows
-- ---------------------------------------------------------------------------
WITH ccys AS (SELECT DISTINCT currency FROM fx_rate),
     types(t) AS (VALUES ('LOAN'),('DEPOSIT'),('FX'),('DERIV'))
INSERT INTO account (account_id, cif_id, account_type, currency, balance_usd, opened_at, is_closed)
SELECT
  'ACC' || LPAD((10000 + ROW_NUMBER() OVER ())::text, 6, '0'),
  c.cif_id,
  (SELECT t FROM types ORDER BY t OFFSET (abs(hashtext(c.cif_id || g::text)) % 4) LIMIT 1),
  (SELECT currency FROM ccys ORDER BY currency OFFSET (abs(hashtext(c.cif_id||g::text||'c')) % (SELECT COUNT(*) FROM ccys)) LIMIT 1),
  ((abs(hashtext(c.cif_id||g::text||'b'))::bigint % 50000 + 1000) * 10000::bigint)::numeric(18,2),
  (c.onboarded_at + (abs(hashtext(c.cif_id||g::text||'d')) % 1500) * INTERVAL '1 day')::date,
  (abs(hashtext(c.cif_id||g::text||'cl')) % 40) = 0
FROM client c
CROSS JOIN generate_series(1, 3) AS g
WHERE c.cif_id NOT IN (SELECT DISTINCT cif_id FROM account);

-- ---------------------------------------------------------------------------
-- 7. Bulk-extend EXPOSURE to ~300 rows
-- ---------------------------------------------------------------------------
WITH products(p) AS (VALUES ('TERM_LOAN'),('RCF'),('TRADE_FIN'),('IRS'))
INSERT INTO exposure (exposure_id, cif_id, product, notional_usd, drawn_usd, pd_bps, booked_at, matures_at)
SELECT
  'EXP' || LPAD((20000 + ROW_NUMBER() OVER ())::text, 6, '0'),
  c.cif_id,
  (SELECT p FROM products ORDER BY p OFFSET (abs(hashtext(c.cif_id||g::text||'p')) % 4) LIMIT 1),
  notional,
  (notional * (0.4 + (abs(hashtext(c.cif_id||g::text||'u')) % 60) / 100.0))::numeric(18,2),
  CASE c.risk_rating
    WHEN 'AAA' THEN 5  + (abs(hashtext(c.cif_id||g::text||'pd')) % 10)
    WHEN 'AA'  THEN 15 + (abs(hashtext(c.cif_id||g::text||'pd')) % 15)
    WHEN 'A'   THEN 30 + (abs(hashtext(c.cif_id||g::text||'pd')) % 30)
    WHEN 'BBB' THEN 80 + (abs(hashtext(c.cif_id||g::text||'pd')) % 60)
    WHEN 'BB'  THEN 200+ (abs(hashtext(c.cif_id||g::text||'pd')) % 80)
    WHEN 'B'   THEN 350+ (abs(hashtext(c.cif_id||g::text||'pd')) % 150)
    ELSE             550+ (abs(hashtext(c.cif_id||g::text||'pd')) % 300)
  END,
  (c.onboarded_at + (abs(hashtext(c.cif_id||g::text||'b')) % 1200) * INTERVAL '1 day')::date,
  (c.onboarded_at + ((abs(hashtext(c.cif_id||g::text||'b')) % 1200) + 1095 + (abs(hashtext(c.cif_id||g::text||'m')) % 1825)) * INTERVAL '1 day')::date
FROM client c
CROSS JOIN generate_series(1, 2) AS g,
LATERAL (SELECT (5000000::bigint + (abs(hashtext(c.cif_id||g::text||'n'))::bigint % 200) * 1000000::bigint)::numeric(18,2) AS notional) n
WHERE c.cif_id NOT IN (SELECT DISTINCT cif_id FROM exposure WHERE exposure_id LIKE 'EXP02%' OR exposure_id LIKE 'EXP03%')
  AND c.is_active;

-- ---------------------------------------------------------------------------
-- 8. Covenants (per exposure, financial maintenance)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS covenant (
    covenant_id   serial      PRIMARY KEY,
    exposure_id   varchar(20) NOT NULL REFERENCES exposure(exposure_id),
    covenant_type varchar(32) NOT NULL,    -- DSCR / LEVERAGE / MIN_EBITDA / NWC
    threshold     numeric(18,4) NOT NULL,
    test_freq     varchar(16) NOT NULL,    -- QUARTERLY / SEMIANNUAL / ANNUAL
    last_tested   date,
    last_status   varchar(16) NOT NULL DEFAULT 'PASS' -- PASS / WAIVED / BREACH
);

INSERT INTO covenant (exposure_id, covenant_type, threshold, test_freq, last_tested, last_status)
SELECT
  e.exposure_id,
  CASE (abs(hashtext(e.exposure_id)) % 4)
    WHEN 0 THEN 'DSCR' WHEN 1 THEN 'LEVERAGE' WHEN 2 THEN 'MIN_EBITDA' ELSE 'NWC' END,
  CASE (abs(hashtext(e.exposure_id)) % 4)
    WHEN 0 THEN 1.20 WHEN 1 THEN 4.00 WHEN 2 THEN 50000000.00 ELSE 10000000.00 END,
  CASE (abs(hashtext(e.exposure_id||'f')) % 3)
    WHEN 0 THEN 'QUARTERLY' WHEN 1 THEN 'SEMIANNUAL' ELSE 'ANNUAL' END,
  CURRENT_DATE - (abs(hashtext(e.exposure_id||'t')) % 180),
  CASE (abs(hashtext(e.exposure_id||'s')) % 20)
    WHEN 0 THEN 'BREACH' WHEN 1 THEN 'BREACH' WHEN 2 THEN 'WAIVED' ELSE 'PASS' END
FROM exposure e
WHERE e.product IN ('TERM_LOAN','RCF')
  AND NOT EXISTS (SELECT 1 FROM covenant cv WHERE cv.exposure_id = e.exposure_id)
LIMIT 100;

-- ---------------------------------------------------------------------------
-- 9. Collateral (per exposure)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS collateral (
    collateral_id  serial      PRIMARY KEY,
    exposure_id    varchar(20) NOT NULL REFERENCES exposure(exposure_id),
    collateral_type varchar(32) NOT NULL,  -- CASH / EQUITY / PROPERTY / RECEIVABLES / GUARANTEE
    market_value_usd numeric(18,2) NOT NULL,
    haircut_pct    numeric(5,2) NOT NULL,
    valuation_date date         NOT NULL
);

INSERT INTO collateral (exposure_id, collateral_type, market_value_usd, haircut_pct, valuation_date)
SELECT
  e.exposure_id,
  CASE (abs(hashtext(e.exposure_id||'col')) % 5)
    WHEN 0 THEN 'CASH' WHEN 1 THEN 'EQUITY' WHEN 2 THEN 'PROPERTY'
    WHEN 3 THEN 'RECEIVABLES' ELSE 'GUARANTEE' END,
  (e.notional_usd * (0.5 + (abs(hashtext(e.exposure_id||'mv')) % 80)/100.0))::numeric(18,2),
  (5 + (abs(hashtext(e.exposure_id||'h')) % 30))::numeric(5,2),
  CURRENT_DATE - (abs(hashtext(e.exposure_id||'vd')) % 90)
FROM exposure e
WHERE e.product = 'TERM_LOAN'
  AND NOT EXISTS (SELECT 1 FROM collateral cl WHERE cl.exposure_id = e.exposure_id);

-- ---------------------------------------------------------------------------
-- 10. Risk rating history (SCD2)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rating_history (
    history_id    serial      PRIMARY KEY,
    cif_id        varchar(16) NOT NULL REFERENCES client(cif_id),
    rating        varchar(8)  NOT NULL,
    effective_from date       NOT NULL,
    effective_to  date,                         -- NULL = current
    change_reason varchar(64) NOT NULL          -- INITIAL / ANNUAL_REVIEW / DOWNGRADE / UPGRADE / WATCHLIST
);

INSERT INTO rating_history (cif_id, rating, effective_from, effective_to, change_reason)
SELECT c.cif_id, c.risk_rating, c.onboarded_at, NULL, 'INITIAL'
FROM client c
WHERE NOT EXISTS (SELECT 1 FROM rating_history h WHERE h.cif_id = c.cif_id);

-- Add ~50 historical changes to a subset (downgrades + upgrades)
INSERT INTO rating_history (cif_id, rating, effective_from, effective_to, change_reason)
SELECT c.cif_id,
       CASE WHEN (abs(hashtext(c.cif_id||'r')) % 2) = 0
            THEN CASE c.risk_rating
                   WHEN 'AAA' THEN 'AA' WHEN 'AA' THEN 'A' WHEN 'A' THEN 'BBB'
                   WHEN 'BBB' THEN 'BB' WHEN 'BB' THEN 'B' ELSE 'CCC' END
            ELSE c.risk_rating
       END,
       (CURRENT_DATE - (180 + (abs(hashtext(c.cif_id||'rd')) % 365)))::date,
       (CURRENT_DATE - (abs(hashtext(c.cif_id||'rd')) % 180))::date,
       CASE (abs(hashtext(c.cif_id||'rs')) % 4)
         WHEN 0 THEN 'DOWNGRADE' WHEN 1 THEN 'UPGRADE'
         WHEN 2 THEN 'ANNUAL_REVIEW' ELSE 'WATCHLIST' END
FROM client c
WHERE c.cif_id IN (SELECT cif_id FROM client ORDER BY cif_id LIMIT 50)
  AND NOT EXISTS (SELECT 1 FROM rating_history h
                  WHERE h.cif_id = c.cif_id AND h.change_reason <> 'INITIAL');

-- ---------------------------------------------------------------------------
-- 11. TRANSACTION fact table — payment / drawdown / repayment events
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS transaction (
    txn_id        bigserial   PRIMARY KEY,
    account_id    varchar(20) NOT NULL REFERENCES account(account_id),
    txn_type      varchar(16) NOT NULL,         -- PAYMENT / DRAWDOWN / REPAYMENT / FEE / INTEREST
    amount_native numeric(18,2) NOT NULL,
    currency      char(3)     NOT NULL,
    txn_date      date        NOT NULL,
    description   varchar(120),
    counterparty  varchar(80)
);

CREATE INDEX IF NOT EXISTS transaction_date_idx ON transaction(txn_date);
CREATE INDEX IF NOT EXISTS transaction_account_idx ON transaction(account_id);

-- ~10000 transactions over last 720 days; 5 per active account on average.
INSERT INTO transaction (account_id, txn_type, amount_native, currency, txn_date, description, counterparty)
SELECT
  a.account_id,
  CASE (abs(hashtext(a.account_id||g::text||'t')) % 8)
    WHEN 0 THEN 'DRAWDOWN' WHEN 1 THEN 'REPAYMENT' WHEN 2 THEN 'INTEREST' WHEN 3 THEN 'FEE'
    ELSE 'PAYMENT' END,
  ((abs(hashtext(a.account_id||g::text||'a'))::bigint % 1000 + 10) * 10000::bigint)::numeric(18,2),
  a.currency,
  (CURRENT_DATE - (abs(hashtext(a.account_id||g::text||'d')) % 720))::date,
  'Auto-generated tx',
  CASE (abs(hashtext(a.account_id||g::text||'cp')) % 5)
    WHEN 0 THEN 'JPMorgan'  WHEN 1 THEN 'HSBC'   WHEN 2 THEN 'BNP Paribas'
    WHEN 3 THEN 'Citi'      ELSE 'Standard Chartered' END
FROM account a
CROSS JOIN generate_series(1, 5) AS g
WHERE NOT a.is_closed
  AND NOT EXISTS (SELECT 1 FROM transaction tx WHERE tx.account_id = a.account_id);

-- ---------------------------------------------------------------------------
-- 12. DAILY_BALANCE snapshot — last 90 days for every open account
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS daily_balance (
    balance_date  date        NOT NULL,
    account_id    varchar(20) NOT NULL REFERENCES account(account_id),
    balance_native numeric(18,2) NOT NULL,
    balance_usd   numeric(18,2) NOT NULL,
    PRIMARY KEY (balance_date, account_id)
);

CREATE INDEX IF NOT EXISTS daily_balance_date_idx ON daily_balance(balance_date);

INSERT INTO daily_balance (balance_date, account_id, balance_native, balance_usd)
SELECT
  d.balance_date,
  a.account_id,
  -- Random walk around opening balance ±5%
  (a.balance_usd * (1 + 0.05 * sin((d.balance_date - a.opened_at)::int / 7.0)))::numeric(18,2),
  (a.balance_usd * (1 + 0.05 * sin((d.balance_date - a.opened_at)::int / 7.0))
                 * COALESCE((SELECT usd_per_unit FROM fx_rate fx
                             WHERE fx.rate_date = d.balance_date AND fx.currency = a.currency
                             LIMIT 1), 1.0))::numeric(18,2)
FROM account a
CROSS JOIN (SELECT generate_series(CURRENT_DATE - 89, CURRENT_DATE, INTERVAL '1 day')::date AS balance_date) d
WHERE NOT a.is_closed
  AND NOT EXISTS (SELECT 1 FROM daily_balance db
                  WHERE db.account_id = a.account_id AND db.balance_date = d.balance_date)
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- 13. Helpful views (so Cube + Trino get a clean denormalized layer)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_client_enriched AS
SELECT c.cif_id, c.legal_name, c.country_iso, cr.country_name, cr.region, cr.risk_tier,
       c.industry, ir.sector, ir.is_esg_focus,
       c.rm_owner, ru.full_name AS rm_name, ru.business_unit,
       c.aum_usd, c.risk_rating, c.onboarded_at, c.is_active
FROM client c
LEFT JOIN country_ref  cr ON cr.country_iso = c.country_iso
LEFT JOIN industry_ref ir ON ir.industry    = c.industry
LEFT JOIN rm_user      ru ON ru.rm_email    = c.rm_owner;

CREATE OR REPLACE VIEW v_exposure_with_collateral AS
SELECT e.*,
       COALESCE(SUM(cl.market_value_usd * (1 - cl.haircut_pct/100.0)), 0)::numeric(18,2)
         AS collateral_value_haircut_usd,
       (e.drawn_usd - COALESCE(SUM(cl.market_value_usd * (1 - cl.haircut_pct/100.0)), 0))::numeric(18,2)
         AS unsecured_drawn_usd
FROM exposure e
LEFT JOIN collateral cl ON cl.exposure_id = e.exposure_id
GROUP BY e.exposure_id;

-- ---------------------------------------------------------------------------
-- 14. Stats refresh (so query planner knows the new row counts)
-- ---------------------------------------------------------------------------
ANALYZE client;
ANALYZE account;
ANALYZE exposure;
ANALYZE transaction;
ANALYZE daily_balance;
ANALYZE fx_rate;
