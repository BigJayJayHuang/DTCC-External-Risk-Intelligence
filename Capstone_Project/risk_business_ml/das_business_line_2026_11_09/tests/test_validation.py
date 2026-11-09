"""Offline negative controls for evidence binding and DAS API output validation."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / 'src/validate_outputs.py'
SPEC = importlib.util.spec_from_file_location('das_validate_outputs', MODULE)
V = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(V)


def valid_result():
    fact = {key: 'description' for key in V.FACT_STRINGS}
    fact.update(fact_id='F01', source_id='one', evidence_quote='Exact source quotation.',
                date=None, measured_metric=None, measured_value=None, unit=None)
    chains = []
    for i in range(1, 6):
        chain = {key: 'description' for key in V.CHAIN_STRINGS}
        chain.update(card_id=f'DAS-{i:02d}', mechanism_source_ids=['one'],
                     mechanism_evidence_source_id='one', mechanism_evidence_quote='Exact source quotation.',
                     real_v_available=False, simulation_suitable=True)
        chains.append(chain)
    return dict(scope=dict(business_name_en='DAS', business_name_zh='数字资产服务',
                           included=['included'], excluded=['excluded'], date_limitations=['limited history']),
                facts=[fact], chains=chains, recommended_next_steps_en=['review'],
                recommended_next_steps_zh=['复核'], cannot_empirically_validate_yet=['No measured V.'])


DOCS = [dict(source_id='one', content='Exact source quotation. Other text.'),
        dict(source_id='two', content='A different source without that quotation.')]


class SourceBindingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'inputs').mkdir()
        (self.root / 'evidence').mkdir()
        self.raw = b'<p>Exact source quotation.</p>'
        self.text = 'Exact source quotation.\r\nOther text.\n'.encode()
        (self.root / 'evidence/one.html').write_bytes(self.raw)
        (self.root / 'inputs/one.txt').write_bytes(self.text)
        self.rows = [dict(source_id='one', status='retrieved', url='https://example.test/one',
                          publication_date=None, raw_file='evidence/one.html', text_file='inputs/one.txt',
                          raw_sha256=hashlib.sha256(self.raw).hexdigest(),
                          text_sha256=hashlib.sha256(self.text).hexdigest()),
                     dict(source_id='unavailable', status='unavailable')]
        self.save_manifest()

    def save_manifest(self):
        (self.root / 'inputs/source_manifest.json').write_text(json.dumps(self.rows))

    def test_valid_binding_preserves_exact_bytes_and_metadata(self):
        docs = V.load_bound_sources(self.root)
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0]['content'].encode(), self.text)
        self.assertEqual(docs[0]['raw_sha256'], self.rows[0]['raw_sha256'])

    def test_stale_text_hash_rejected(self):
        (self.root / 'inputs/one.txt').write_bytes(b'Replaced text')
        with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
            V.load_bound_sources(self.root)

    def test_stale_raw_hash_rejected(self):
        (self.root / 'evidence/one.html').write_bytes(b'Replaced raw')
        with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
            V.load_bound_sources(self.root)

    def test_path_outside_inputs_rejected(self):
        (self.root / 'outside.txt').write_bytes(self.text)
        self.rows[0]['text_file'] = 'inputs/../outside.txt'
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, 'escapes inputs'):
            V.load_bound_sources(self.root)

    def test_absolute_path_rejected(self):
        self.rows[0]['text_file'] = str(self.root / 'inputs/one.txt')
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, 'relative path'):
            V.load_bound_sources(self.root)

    def test_symlink_escape_rejected(self):
        (self.root / 'outside.txt').write_bytes(self.text)
        (self.root / 'inputs/link.txt').symlink_to(self.root / 'outside.txt')
        self.rows[0]['text_file'] = 'inputs/link.txt'
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, 'escapes inputs'):
            V.load_bound_sources(self.root)

    def test_missing_hash_rejected(self):
        self.rows[0].pop('raw_sha256')
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, 'Missing or invalid SHA-256'):
            V.load_bound_sources(self.root)

    def test_duplicate_bound_source_id_rejected(self):
        self.rows.append(copy.deepcopy(self.rows[0]))
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, 'unique nonempty source_id'):
            V.load_bound_sources(self.root)


class OutputValidationTests(unittest.TestCase):
    def test_valid_five_card_result(self):
        self.assertEqual(V.validate_understanding(valid_result(), DOCS), [])

    def test_duplicate_card_rejected(self):
        result = valid_result()
        result['chains'][1]['card_id'] = 'DAS-01'
        self.assertTrue(any('Duplicate card_id' in e for e in V.validate_understanding(result, DOCS)))

    def test_empty_chains_rejected(self):
        result = valid_result()
        result['chains'] = []
        self.assertTrue(any('5–6 chains' in e for e in V.validate_understanding(result, DOCS)))

    def test_wrong_source_quote_rejected(self):
        result = valid_result()
        result['facts'][0]['source_id'] = 'two'
        self.assertTrue(any('verbatim in its bound source' in e for e in V.validate_understanding(result, DOCS)))

    def test_chain_quote_requires_its_own_source(self):
        result = valid_result()
        result['chains'][0]['mechanism_evidence_source_id'] = 'two'
        result['chains'][0]['mechanism_source_ids'] = ['two']
        self.assertTrue(any('verbatim in its bound source' in e for e in V.validate_understanding(result, DOCS)))

    def test_quoted_source_must_be_listed(self):
        result = valid_result()
        result['chains'][0]['mechanism_source_ids'] = ['two']
        self.assertTrue(any('included in mechanism_source_ids' in e for e in V.validate_understanding(result, DOCS)))

    def test_duplicate_fact_rejected(self):
        result = valid_result()
        result['facts'].append(copy.deepcopy(result['facts'][0]))
        self.assertTrue(any('Duplicate fact_id' in e for e in V.validate_understanding(result, DOCS)))

    def test_empty_facts_rejected(self):
        result = valid_result()
        result['facts'] = []
        self.assertTrue(any('1–12 facts' in e for e in V.validate_understanding(result, DOCS)))

    def test_string_boolean_and_real_v_claim_rejected(self):
        result = valid_result()
        result['chains'][0]['simulation_suitable'] = 'true'
        result['chains'][0]['real_v_available'] = True
        errors = V.validate_understanding(result, DOCS)
        self.assertTrue(any('simulation_suitable must be a boolean' in e for e in errors))
        self.assertTrue(any('real_v_available must be false' in e for e in errors))

    def test_missing_required_field_rejected(self):
        result = valid_result()
        result['chains'][0].pop('exact_data_needed')
        self.assertTrue(any('exact_data_needed' in e for e in V.validate_understanding(result, DOCS)))

    def test_numeric_bool_and_nonfinite_values_rejected(self):
        for value in (True, float('nan'), float('inf')):
            with self.subTest(value=value):
                result = valid_result()
                result['facts'][0].update(measured_value=value, measured_metric='count', unit='number')
                self.assertTrue(any('finite number' in e for e in V.validate_understanding(result, DOCS)))

    def test_invalid_date_rejected(self):
        result = valid_result()
        result['facts'][0]['date'] = '2026-02-30'
        self.assertTrue(any('ISO calendar date' in e for e in V.validate_understanding(result, DOCS)))

    def test_invented_source_rejected(self):
        result = valid_result()
        result['chains'][0]['mechanism_source_ids'] = ['one', 'invented']
        self.assertTrue(any('known source IDs' in e for e in V.validate_understanding(result, DOCS)))

    def test_unknown_card_id_rejected(self):
        result = valid_result()
        result['chains'][0]['card_id'] = 'FICC-GSD-01'
        self.assertTrue(any('DAS-01 through DAS-06' in e for e in V.validate_understanding(result, DOCS)))

    def test_malformed_result_returns_errors_not_exception(self):
        self.assertTrue(V.validate_understanding([], DOCS))
        result = valid_result()
        result['chains'] = [None] * 5
        self.assertTrue(V.validate_understanding(result, DOCS))


if __name__ == '__main__':
    unittest.main()
