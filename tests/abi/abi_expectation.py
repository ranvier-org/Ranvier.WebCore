"""Manifest-bound ABI admission; an unspecified expectation is the ABI declared by the checkout's host source."""
import os
from pathlib import Path
import re

ENVIRONMENT = 'RANVIER_ABI_TEST_EXPECTED'
SOURCE = Path(__file__).resolve().parents[2] / 'host/RanvierWebCoreAbi.cpp'


def current_abi():
    """The value returned by rv_abi_version in the checkout's host source."""
    return int(re.search(r'rv_abi_version\(void\)\s*\{\s*return\s+(\d+);', SOURCE.read_text(encoding='utf-8')).group(1))


def expected_abi(default=None):
    value=os.environ.get(ENVIRONMENT)
    if value is None:
        return current_abi() if default is None else default
    if not re.fullmatch(r'[1-9][0-9]{0,8}',value):
        raise ValueError('The explicit expected ABI must be a positive decimal version.')
    return int(value)


def expected_environment(manifest, explicit, environment):
    result=dict(environment)
    if explicit is None:
        return result
    if (type(explicit) is not int or not 1 <= explicit <= 999999999
            or type(manifest.get('abi')) is not int or explicit!=manifest['abi']):
        raise ValueError('The explicit expected ABI must match the staged manifest.')
    result[ENVIRONMENT]=str(explicit)
    return result


def producer_environment(manifest, explicit, source_commit, rid, flavor):
    expected = current_abi() if explicit is None else explicit
    if type(expected) is not int or not 1 <= expected <= 999999999:
        raise ValueError('The producer must select a positive decimal ABI version.')
    source = manifest.get('source', {})
    if (not isinstance(source, dict) or not isinstance(source_commit, str)
            or not re.fullmatch('[0-9a-f]{40}', source_commit)
            or source.get('commit') != source_commit or source.get('dirty') is not False
            or manifest.get('rid') != rid or manifest.get('flavor') != flavor):
        raise ValueError('The probe stage must match the actual clean producer HEAD, RID and flavor.')
    return expected_environment(manifest, expected, {})
