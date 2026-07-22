-- Phase 1 walking skeleton seed data
-- Single table: client (CIB customer master), 20 synthetic rows, no PII.

CREATE SCHEMA IF NOT EXISTS public;

CREATE TABLE IF NOT EXISTS client (
    cif_id           varchar(16)  PRIMARY KEY,
    legal_name       varchar(200) NOT NULL,
    country_iso      char(2)      NOT NULL,
    industry         varchar(64)  NOT NULL,
    rm_owner         varchar(64)  NOT NULL,
    aum_usd          numeric(18,2) NOT NULL,
    risk_rating      varchar(8)   NOT NULL,   -- AAA/AA/A/BBB/BB/B/CCC
    onboarded_at     date         NOT NULL,
    is_active        boolean      NOT NULL DEFAULT true
);

INSERT INTO client (cif_id, legal_name, country_iso, industry, rm_owner, aum_usd, risk_rating, onboarded_at, is_active) VALUES
  ('CIF0000001','Acme Industrial Holdings','US','Manufacturing','alice@bank',  250000000.00,'AA','2019-03-12',true),
  ('CIF0000002','Borealis Energy Corp',     'CA','Energy',       'alice@bank',  180000000.00,'A', '2020-06-04',true),
  ('CIF0000003','Cathay Logistics Ltd',     'HK','Transport',    'bob@bank',    420000000.00,'AA','2018-01-22',true),
  ('CIF0000004','Daiwa Foods K.K.',         'JP','Consumer',     'alice@bank',   95000000.00,'BBB','2021-09-15',true),
  ('CIF0000005','Eden Pharma SA',           'CH','Healthcare',   'carol@bank', 1100000000.00,'AAA','2017-11-30',true),
  ('CIF0000006','Falcon Aerospace Ltd',     'GB','Aerospace',    'bob@bank',    640000000.00,'A', '2016-05-18',true),
  ('CIF0000007','Gobi Mining JSC',          'MN','Mining',       'carol@bank',   45000000.00,'BB','2022-02-09',true),
  ('CIF0000008','Helios Solar GmbH',        'DE','Energy',       'alice@bank',  210000000.00,'A', '2019-10-01',true),
  ('CIF0000009','Indus Steel Pvt Ltd',      'IN','Manufacturing','bob@bank',     75000000.00,'BBB','2020-12-20',true),
  ('CIF0000010','Jaguar Auto Group',        'GB','Automotive',   'carol@bank',  330000000.00,'A', '2018-08-08',true),
  ('CIF0000011','Kepler Robotics Inc',      'US','Technology',   'alice@bank',  580000000.00,'AA','2021-03-03',true),
  ('CIF0000012','Lumen Telecom Sdn Bhd',    'MY','Telecom',      'bob@bank',    120000000.00,'BBB','2019-07-25',true),
  ('CIF0000013','Maple Forestry Co',        'CA','Forestry',     'carol@bank',   38000000.00,'BB','2022-11-11',false),
  ('CIF0000014','Nordic Bank AS',           'NO','Financials',   'alice@bank', 2100000000.00,'AAA','2015-04-17',true),
  ('CIF0000015','Orinoco Petrochem',        'BR','Energy',       'bob@bank',    155000000.00,'BB','2020-03-29',true),
  ('CIF0000016','Pyrenees Wines SA',        'FR','Consumer',     'carol@bank',   22000000.00,'B', '2023-01-10',true),
  ('CIF0000017','Quokka Tourism Ltd',       'AU','Travel',       'alice@bank',   18000000.00,'B', '2022-06-30',false),
  ('CIF0000018','Riviera Hospitality',      'IT','Hotels',       'bob@bank',     65000000.00,'BBB','2021-12-12',true),
  ('CIF0000019','Sahara Renewables',        'EG','Energy',       'carol@bank',   88000000.00,'BB','2023-04-04',true),
  ('CIF0000020','Tundra Cargo Lines',       'IS','Transport',    'alice@bank',   29000000.00,'B', '2022-08-19',true);
