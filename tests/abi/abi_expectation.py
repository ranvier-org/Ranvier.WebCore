"""Manifest-bound ABI admission; standalone probes retain their historical default."""
import os
import re

ENVIRONMENT = 'RANVIER_ABI_TEST_EXPECTED'


def expected_abi(default=63):
    value=os.environ.get(ENVIRONMENT)
    if value is None:
        return default
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
    expected = 63 if explicit is None else explicit
    if type(expected) is not int or expected not in (63, 64):
        raise ValueError('The producer must explicitly select supported ABI63 or ABI64.')
    source = manifest.get('source', {})
    if (not isinstance(source, dict) or not isinstance(source_commit, str)
            or not re.fullmatch('[0-9a-f]{40}', source_commit)
            or source.get('commit') != source_commit or source.get('dirty') is not False
            or manifest.get('rid') != rid or manifest.get('flavor') != flavor):
        raise ValueError('The probe stage must match the actual clean producer HEAD, RID and flavor.')
    return expected_environment(manifest, expected, {})
