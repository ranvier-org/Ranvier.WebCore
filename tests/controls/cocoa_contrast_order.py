"""Check the complete strict contrast matrices across fresh process orders."""
import argparse
import json
from pathlib import Path


def paired_reports(left, right):
    expected = {(s, p) for s in [False, True] for p in [False, True, None]}
    indexed = []
    for report in [left, right]:
        if report.get('failures') or not report.get('scopedHelper') or report.get('assertions', 0) < 83:
            raise ValueError('Original strict contrast checks did not all pass')
        controls = report.get('unknownCallerControls', [])
        if len(controls) != 2 or {row['forced'] for row in controls} != {0, 1} or any(
                row['original'] not in [0, 1] or row['observed'] != row['original']
                or row['themeCalls'] != 0 or row['platformCalls'] <= 0 for row in controls):
            raise ValueError('Unknown caller did not forward the original preference')
        rows = [row for row in report['rows'] if 'label' in row]
        lookup = {(row['systemMore'], row['pageMore']): row for row in rows}
        if len(rows) != 6 or set(lookup) != expected:
            raise ValueError('Require all six unique page/System rows')
        if any((row['getterCalls'] <= 0 if row['pageMore'] is None else row['getterCalls'] != 0)
               for row in rows):
            raise ValueError('Explicit/System positive attribution control failed')
        indexed.append(lookup)
    comparisons = []
    for key in sorted(expected, key=str):
        first, second = (lookup[key] for lookup in indexed)
        if first['sha256'] != second['sha256']:
            raise ValueError('Fresh-process order changed the same-policy full image: ' + str(key))
        comparisons.append(dict(systemMore=key[0], pageMore=key[1], sha256=first['sha256']))
    return {'rows': comparisons, 'strictChecksUnchanged': True, 'freshProcessOrderEqual': True}



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports", type=Path, nargs=2, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = paired_reports(*(json.loads(p.read_text()) for p in args.reports))
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
