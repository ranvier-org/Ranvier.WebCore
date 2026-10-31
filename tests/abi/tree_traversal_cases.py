"""Writes tests/fixtures/tree-traversal-cases.json: the traversal scenarios that tree_traversal_browser.mjs measures in
Chromium and tree_traversal.py replays natively.

Each case builds a TreeWalker or NodeIterator over a fresh copy of the markup and runs its steps. A step is a method
name (next, prev, parent, first, last, prevSib, nextSib, detach), {"set": label} for TreeWalker.currentNode, or
{"remove": label}. Nodes are labelled by element id, "#" + text data, "!" + comment data or "?" + target and data.
Filters: map (an id maps to FILTER_REJECT or FILTER_SKIP, other nodes are accepted), throw (throws on a node for the
first `times` visits), mutate (removes a node on the first visit of another), reenter (calls nextNode on the same
traversal) and reenterOther (traverses a second walker).
"""

import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / 'fixtures' / 'tree-traversal-cases.json'
MARKUP = ('<svg xmlns="http://www.w3.org/2000/svg" id="svg"><?pi first?><g id="root"><!--c1--><g id="a">ta<rect id="a1"/>'
          '<!--c2--><g id="b"><rect id="b1"/>tb<rect id="b2"/></g></g><?pi mid?><g id="c"><rect id="c1"/><g id="d">'
          '<rect id="d1"/></g></g>tz<rect id="e"/><!--c3--></g></svg>')
ALL, ELEMENT, TEXT, PI, COMMENT = 0xFFFFFFFF, 0x1, 0x4, 0x40, 0x80
MASKS = {'all': ALL, 'element': ELEMENT, 'text': TEXT, 'comment': COMMENT, 'pi': PI, 'elementComment': ELEMENT | COMMENT}
MAP = {'kind': 'map', 'map': {'b': 2, 'c': 3}}


def cases():
    found = []
    for kind in ['walker', 'iterator']:
        for mask_name, mask in MASKS.items():
            for filter_name, spec in [('none', None), ('map', MAP)] if mask_name in ('all', 'element', 'elementComment') else [('none', None)]:
                found.append({'name': f'{kind}-{mask_name}-{filter_name}', 'kind': kind, 'root': 'root', 'mask': mask, 'filter': spec,
                              'steps': ['next'] * 22 + ['prev'] * 22})
        found.append({'name': f'{kind}-document-all', 'kind': kind, 'root': '#document', 'mask': ALL, 'filter': None, 'steps': ['next'] * 26})
    for filter_name, spec in [('none', None), ('map', MAP)]:
        for mask_name in ['all', 'element']:
            steps = []
            for position in ['root', 'a', 'a1', 'b', 'b1', 'c', 'c1', 'd', 'e', '#ta', '!c2']:
                for method in ['parent', 'first', 'last', 'prevSib', 'nextSib', 'prev', 'next']:
                    steps += [{'set': position}, method]
            found.append({'name': f'walker-steps-{mask_name}-{filter_name}', 'kind': 'walker', 'root': 'root', 'mask': MASKS[mask_name],
                          'filter': spec, 'steps': steps})

    def case(name, kind, mask, spec, steps, root='root'):
        found.append({'name': name, 'kind': kind, 'root': root, 'mask': mask, 'filter': spec, 'steps': steps})

    case('iterator-remove-reference', 'iterator', ALL, None,
         ['next'] * 9 + [{'remove': 'b1'}, 'next', 'prev', {'remove': '#tb'}, 'prev', {'remove': 'b'}, 'next', 'prev', 'prev',
                         {'remove': 'a'}, 'next', 'next'])
    case('iterator-remove-before', 'iterator', ELEMENT, None,
         ['next'] * 5 + ['prev', {'remove': 'b'}, 'next', 'prev', {'remove': 'c'}, 'next', 'next', 'prev', 'next', 'prev'])
    case('iterator-remove-filtered', 'iterator', ALL, MAP, ['next'] * 8 + [{'remove': 'c1'}, 'next', 'prev', {'remove': 'd'}, 'next', 'next', 'prev'])
    case('walker-throw', 'walker', ALL, {'kind': 'throw', 'on': 'b1', 'times': 1},
         ['next'] * 9 + ['prev', 'next', 'next', {'set': 'd'}, 'parent', 'first'])
    case('walker-throw-every-step', 'walker', ELEMENT, {'kind': 'throw', 'on': 'c', 'times': 99},
         [{'set': 'd'}, 'parent', 'prev', 'next', {'set': 'a'}, 'nextSib', {'set': 'b2'}, 'next', {'set': 'e'}, 'prevSib', 'prev'])
    case('iterator-throw', 'iterator', ALL, {'kind': 'throw', 'on': 'b1', 'times': 1}, ['next'] * 9 + ['prev', 'next', 'next', 'prev', 'prev'])
    case('iterator-throw-backward', 'iterator', ELEMENT, {'kind': 'throw', 'on': 'a1', 'times': 2}, ['next'] * 6 + ['prev'] * 8)
    case('walker-mutate', 'walker', ALL, {'kind': 'mutate', 'on': 'a1', 'remove': 'b'}, ['next'] * 16 + ['prev'] * 16)
    case('iterator-mutate', 'iterator', ALL, {'kind': 'mutate', 'on': 'a1', 'remove': 'b'}, ['next'] * 16 + ['prev'] * 16)
    case('iterator-mutate-reference', 'iterator', ELEMENT, {'kind': 'mutate', 'on': 'c1', 'remove': 'c'}, ['next'] * 10 + ['prev'] * 10)
    case('walker-reenter', 'walker', ELEMENT, {'kind': 'reenter', 'on': 'a1'}, ['next'] * 5 + [{'set': 'b'}, 'prev', 'first'])
    case('iterator-reenter', 'iterator', ELEMENT, {'kind': 'reenter', 'on': 'a1'}, ['next'] * 5 + ['prev', 'prev', 'prev'])
    case('walker-reenter-other', 'walker', ELEMENT, {'kind': 'reenterOther', 'on': 'a1'}, ['next'] * 4)
    case('iterator-detach', 'iterator', ELEMENT, None, ['next', 'next', 'detach', 'next', 'prev', 'detach', 'next'])
    case('walker-current-outside', 'walker', ALL, None,
         [{'set': 'c1'}, 'parent', {'set': 'c1'}, 'next', {'set': 'c1'}, 'prev', {'set': 'c'}, 'prevSib', {'set': 'svg'}, 'first',
          {'set': 'svg'}, 'next'], root='a')
    return found


if __name__ == '__main__':
    data = {'markup': MARKUP, 'cases': cases()}
    OUT.write_text(json.dumps(data, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(len(data['cases']), 'cases', sum(len(c['steps']) for c in data['cases']), 'steps')
