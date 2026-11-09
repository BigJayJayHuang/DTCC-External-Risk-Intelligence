"""Deterministic provenance/schema checks; no network, API calls, or claim inference.

Passing these checks establishes file binding and output structure, not semantic
support, measured DAS vulnerability, or empirical validation of a risk chain.
"""
from __future__ import annotations

from datetime import date
import hashlib
import json
import math
from pathlib import Path
import re


def _nonempty_string(value):
    return isinstance(value, str) and bool(value.strip())


def _string_list(value):
    return isinstance(value, list) and bool(value) and all(_nonempty_string(x) for x in value)


def _confined_file(root, relative, directory):
    if not _nonempty_string(relative) or Path(relative).is_absolute():
        raise ValueError(f'{directory} file must be a relative path')
    allowed = root / directory
    try:
        candidate = (root / relative).resolve(strict=True)
        candidate.relative_to(allowed)
    except (ValueError, OSError, RuntimeError) as exc:
        raise ValueError(f'File escapes {directory}/ or does not exist: {relative}') from exc
    if not candidate.is_file():
        raise ValueError(f'Not a regular file: {relative}')
    return candidate


def _verified_bytes(path, expected, label):
    if not isinstance(expected, str) or not re.fullmatch(r'[0-9a-f]{64}', expected):
        raise ValueError(f'Missing or invalid SHA-256 for {label}')
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != expected:
        raise ValueError(f'SHA-256 mismatch for {label}')
    return content


def load_bound_sources(root) -> list[dict]:
    """Read retrieved manifest entries only after confining and verifying both files.

    Hashes apply to the exact saved UTF-8 bytes. No universal-newline translation
    or whitespace normalization is permitted before binding the API input.
    Source hashes/paths travel with the content for the immutable request receipt.
    """
    root = Path(root).resolve(strict=True)
    manifest_path = _confined_file(root, 'inputs/source_manifest.json', 'inputs')
    manifest = json.loads(manifest_path.read_bytes().decode('utf-8'))
    if not isinstance(manifest, list):
        raise ValueError('Source manifest must be a list')
    documents, identifiers = [], set()
    for row in manifest:
        if not isinstance(row, dict):
            raise ValueError('Source manifest entries must be objects')
        if row.get('status') != 'retrieved':
            continue
        sid = row.get('source_id')
        if not _nonempty_string(sid) or sid in identifiers:
            raise ValueError('Retrieved sources require unique nonempty source_id values')
        if not _nonempty_string(row.get('url')):
            raise ValueError(f'Missing source URL: {sid}')
        raw = _confined_file(root, row.get('raw_file'), 'evidence')
        text = _confined_file(root, row.get('text_file'), 'inputs')
        _verified_bytes(raw, row.get('raw_sha256'), f'{sid} raw evidence')
        content = _verified_bytes(text, row.get('text_sha256'), f'{sid} extracted text').decode('utf-8')
        if not content.strip():
            raise ValueError(f'Empty extracted text: {sid}')
        identifiers.add(sid)
        documents.append({
            'source_id': sid, 'url': row['url'],
            'publication_date': row.get('publication_date'), 'content': content,
            'raw_file': row['raw_file'], 'text_file': row['text_file'],
            'raw_sha256': row['raw_sha256'], 'text_sha256': row['text_sha256'],
        })
    return documents


FACT_STRINGS = (
    'fact_id', 'source_id', 'category', 'statement_en', 'statement_zh',
    'evidence_quote', 'limitation',
)
CHAIN_STRINGS = (
    'card_id', 'name_en', 'name_zh', 'external_shock',
    'transmission_pathway_en', 'transmission_pathway_zh',
    'mechanism_evidence_quote', 'mechanism_evidence_source_id',
    'proposed_internal_buffer_metric', 'metric_units', 'risk_direction',
    'exact_data_needed', 'public_external_information_to_collect',
    'simulation_limits', 'public_driver_candidate', 'validation_needed',
)


def validate_understanding(result, docs) -> list[str]:
    """Return review-blocking structural/provenance errors without modifying data."""
    errors = []
    if not isinstance(result, dict):
        return ['Understanding output must be an object']
    texts = {}
    for doc in docs:
        if not isinstance(doc, dict) or not _nonempty_string(doc.get('source_id')) or not _nonempty_string(doc.get('content')):
            errors.append('Bound documents require nonempty source_id and content')
            continue
        if doc['source_id'] in texts:
            errors.append('Duplicate bound source_id: ' + doc['source_id'])
        texts[doc['source_id']] = doc['content']
    if not texts:
        errors.append('No bound source documents')

    def strings(obj, keys, label):
        for key in keys:
            if not _nonempty_string(obj.get(key)):
                errors.append(f'{label}.{key} must be a nonempty string')

    def quote(obj, sid_key, quote_key, label):
        sid, value = obj.get(sid_key), obj.get(quote_key)
        if not isinstance(sid, str) or sid not in texts:
            errors.append(f'{label}: unknown quote source_id')
        elif not _nonempty_string(value) or value not in texts[sid]:
            errors.append(f'{label}: quote does not occur verbatim in its bound source')
        if isinstance(value, str) and len(value.split()) > 20:
            errors.append(f'{label}: quote exceeds 20 words')

    scope = result.get('scope')
    if not isinstance(scope, dict):
        errors.append('scope must be an object')
    else:
        strings(scope, ('business_name_en', 'business_name_zh'), 'scope')
        for key in ('included', 'excluded', 'date_limitations'):
            if not _string_list(scope.get(key)):
                errors.append(f'scope.{key} must be a nonempty list of nonempty strings')

    facts = result.get('facts')
    if not isinstance(facts, list):
        errors.append('facts must be a list containing 1–12 facts')
        facts = []
    if not 1 <= len(facts) <= 12:
        errors.append('facts must contain 1–12 facts')
    seen = set()
    for i, fact in enumerate(facts):
        label = f'facts[{i}]'
        if not isinstance(fact, dict):
            errors.append(f'{label} must be an object')
            continue
        strings(fact, FACT_STRINGS, label)
        fid = fact.get('fact_id')
        if _nonempty_string(fid):
            if fid in seen:
                errors.append(f'Duplicate fact_id: {fid}')
            seen.add(fid)
        quote(fact, 'source_id', 'evidence_quote', label)
        for key in ('date', 'measured_metric', 'measured_value', 'unit'):
            if key not in fact:
                errors.append(f'{label}.{key} is required (null allowed)')
        value = fact.get('date')
        if value is not None:
            try:
                if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
                    raise ValueError
                date.fromisoformat(value)
            except ValueError:
                errors.append(f'{label}.date must be an ISO calendar date or null')
        for key in ('measured_metric', 'unit'):
            if fact.get(key) is not None and not _nonempty_string(fact[key]):
                errors.append(f'{label}.{key} must be a nonempty string or null')
        value = fact.get('measured_value')
        if value is not None:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or (isinstance(value, float) and not math.isfinite(value)):
                errors.append(f'{label}.measured_value must be a finite number or null')
            if not _nonempty_string(fact.get('measured_metric')) or not _nonempty_string(fact.get('unit')):
                errors.append(f'{label}: measured_value requires a metric and unit')

    chains = result.get('chains')
    if not isinstance(chains, list):
        errors.append('chains must be a list containing 5–6 chains')
        chains = []
    if not 5 <= len(chains) <= 6:
        errors.append('chains must contain 5–6 chains')
    seen = set()
    for i, chain in enumerate(chains):
        label = f'chains[{i}]'
        if not isinstance(chain, dict):
            errors.append(f'{label} must be an object')
            continue
        strings(chain, CHAIN_STRINGS, label)
        cid = chain.get('card_id')
        if _nonempty_string(cid):
            if not re.fullmatch(r'DAS-0[1-6]', cid):
                errors.append(f'{label}.card_id must use DAS-01 through DAS-06')
            if cid in seen:
                errors.append(f'Duplicate card_id: {cid}')
            seen.add(cid)
        ids = chain.get('mechanism_source_ids')
        if not _string_list(ids):
            errors.append(f'{label}.mechanism_source_ids must be a nonempty list of source IDs')
        else:
            if len(ids) != len(set(ids)) or any(sid not in texts for sid in ids):
                errors.append(f'{label}.mechanism_source_ids must be unique known source IDs')
            if chain.get('mechanism_evidence_source_id') not in ids:
                errors.append(f'{label}: quoted source must be included in mechanism_source_ids')
        quote(chain, 'mechanism_evidence_source_id', 'mechanism_evidence_quote', label)
        for key in ('real_v_available', 'simulation_suitable'):
            if not isinstance(chain.get(key), bool):
                errors.append(f'{label}.{key} must be a boolean')
        if chain.get('real_v_available') is not False:
            errors.append(f'{label}: observed V unavailable; real_v_available must be false')
    if 5 <= len(chains) <= 6 and seen != {f'DAS-{i:02d}' for i in range(1, len(chains) + 1)}:
        errors.append('card_id values must form a consecutive unique DAS-01 onward sequence')

    for key in ('recommended_next_steps_en', 'recommended_next_steps_zh', 'cannot_empirically_validate_yet'):
        value = result.get(key)
        if not (_nonempty_string(value) or _string_list(value)):
            errors.append(f'{key} must be a nonempty string or list of nonempty strings')
    return errors
