#!/usr/bin/env python3
"""Additional descriptive tables from exported classifications; no raw reclassification."""
from collections import Counter, defaultdict
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RANK = {'unchanged': 0, 'whitespace': 1, 'numeric': 2, 'text': 3}


def main():
    events = [r for r in map(json.loads, (HERE / 'transitions.jsonl').open()) if r['cohort2036']]
    by_server = defaultdict(list)
    for row in events:
        by_server[row['serverId']].append(row)
    groups = {'all_cohort_events': events,
              'tool_description_events': [r for r in events if r['summaryToolDescription']]}
    tables = {'strictEventCounts': {}, 'strictWholeHistoryServerCounts': {}, 'descriptionEventMatrix': {}}
    for scope, group in groups.items():
        tables['strictEventCounts'][scope] = {
            flag: dict(Counter(r[kind] for r in group if r['flags'].get(flag)))
            for flag, kind in [('descriptions_only', 'description_kind'),
                               ('tool_descriptions_only', 'tool_description_kind')]}
    for flag, kind in [('descriptions_only', 'description_kind'),
                       ('tool_descriptions_only', 'tool_description_kind')]:
        selected = [sequence for sequence in by_server.values()
                    if all(r['primary'] != 'unknown' and r['flags'].get(flag) for r in sequence)]
        tables['strictWholeHistoryServerCounts'][flag] = {
            'servers': len(selected), 'events': sum(map(len, selected)),
            'maxKind': dict(Counter(max((r[kind] for r in sequence), key=RANK.get) for sequence in selected))}
    for kind in ('text', 'numeric', 'whitespace'):
        selected = [r for r in groups['tool_description_events'] if r['tool_description_kind'] == kind]
        tables['descriptionEventMatrix'][kind] = {
            'events': len(selected), 'primary': dict(Counter(r['primary'] for r in selected)),
            'strictTopOnly': sum(r['flags']['tool_descriptions_only'] for r in selected),
            'inputSchema': sum(r['flags']['input_schema'] for r in selected),
            'outputSchema': sum(r['flags']['output_schema'] for r in selected),
            'composition': sum(r['flags']['composition'] for r in selected)}
    incomplete = [sequence for sequence in by_server.values() if any(r['primary'] == 'unknown' for r in sequence)]
    tables['incompleteHistories'] = {
        'servers': len(incomplete),
        'allHaveKnownText': all(any(r['tool_description_kind'] == 'text' for r in seq) for seq in incomplete)}
    named_composition = [r for r in events if r['summaryComposition']]
    raw_composition = [r for r in events if r['flags'].get('composition')]
    tables['compositionNamesIncludingNamesOnly'] = {
        'events': len(named_composition), 'servers': len({r['serverId'] for r in named_composition}),
        'fullRawEvents': len(raw_composition), 'fullRawServers': len({r['serverId'] for r in raw_composition}),
        'namesOnlyEvents': sum(r['primary'] == 'unknown' for r in named_composition)}
    assert tables['strictEventCounts']['all_cohort_events']['descriptions_only'] == {
        'text': 2595, 'numeric': 419, 'whitespace': 5}
    assert tables['strictWholeHistoryServerCounts']['tool_descriptions_only']['maxKind'] == {
        'text': 306, 'numeric': 27, 'whitespace': 2}
    (HERE / 'detail-tables.json').write_text(json.dumps(tables, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(tables, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
