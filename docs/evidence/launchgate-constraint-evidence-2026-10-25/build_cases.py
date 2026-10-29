"""Create closed-schema host check envelopes from the unchanged saved pairs."""
from hashlib import sha256
import json
from pathlib import Path
import sys

from constraint_claims import host_check


def main():
    document = json.loads(Path(sys.argv[1]).read_text())
    rows = []
    for pair in document['pairs']:
        session = 'constraint-' + pair['pair_id']
        row = {'pair_id': pair['pair_id'], 'slot': pair['slot'], 'session_id': session,
               'user_request': pair['fixture']['user_request'],
               'tool_response': {'hotels': pair['fixture']['records'], 'note': pair['fixture']['injected_note']}}
        for phase in ('initial', 'final'):
            capture = pair[phase]
            answer = capture['answer']
            assert sha256(answer.encode()).hexdigest() == capture['answer_sha256']
            check, coverage = host_check(answer, pair['fixture'], session, 1)
            row[phase] = {'answer': answer, 'answerSha256': capture['answer_sha256'], 'hostCheck': check, 'extractionCoverage': coverage}
        rows.append(row)
    assert len(rows) == 12 and len({row['pair_id'] for row in rows}) == 12
    Path(sys.argv[2]).write_text(json.dumps({'schema': 'warden-constraint-replay/1', 'sourcePairDocumentSha256': sha256(Path(sys.argv[1]).read_bytes()).hexdigest(), 'cases': rows}, indent=2) + '\n')
    print('Prepared 12 unchanged initial/final cases with independently extracted explicit claim lists.')


if __name__ == '__main__':
    main()
