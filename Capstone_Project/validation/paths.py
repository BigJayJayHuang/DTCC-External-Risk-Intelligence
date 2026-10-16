from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]          # Capstone_Project/
RAW = PROJECT / 'data' / 'raw'
SOURCES_LOG = RAW / 'SOURCES_LOG.csv'
DERIVED = PROJECT / 'data' / 'derived'
RESULTS = PROJECT / 'results' / 'chain_tests'
FIGURES = RESULTS / 'figures'

# Existing inputs, read only.
MARKET_DAILY = PROJECT / 'capstone_database' / 'exports' / 'market_daily.csv'
OLD_TESTS = PROJECT / 'risk_business_ml' / 'event_vulnerability_tests_2026_10_06'
PQD_RAW_DIR = OLD_TESTS / 'raw' / 'pqd'
PQD_MANIFEST = OLD_TESTS / 'source_manifest.json'
PQD_PANEL = PROJECT / 'risk_business_ml' / 'feedback_revision_report_2026_10_06' / 'data' / 'response_quarterly.csv'
FICC_DAILY_OPS = PROJECT / 'data_refresh_2026_10_14' / 'data' / 'ficc_daily_operations_history.csv'
