#!/usr/bin/env python3
"""Render standalone plain-Markdown guides for /clients/pipeline-guide/{language}.

Only public repository docs/evidence are read. Include the case inline so a hosted
agent does not depend on unpublished GitHub files or broken relative links.
"""
import argparse
import json
import re
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    docs = Path(__file__).resolve().parents[1] / 'aimarket-hub/docs'
    args.output.mkdir(parents=True, exist_ok=True)
    for lang in ('en', 'ru', 'es', 'fr', 'zh'):
        suffix = '' if lang == 'en' else '.' + lang
        guide = (docs / f'one-call-pipelines{suffix}.md').read_text()
        case = (docs / f'case-study-codex-one-call{suffix}.md').read_text()
        text = guide + '\n---\n\n' + case
        def link(match):
            label, target = match.groups()
            if target.startswith(('https://', 'http://', '#')):
                return match.group(0)
            for stem in ('one-call-pipelines', 'case-study-codex-one-call'):
                if target.startswith(stem):
                    found = re.fullmatch(stem + r'(?:\.(ru|es|fr|zh))?\.md', target)
                    if found:
                        return f'[{label}](https://modelmarket.dev/clients/pipeline-guide/{found.group(1) or "en"})'
            if target.startswith('evidence/'):
                # Evidence is embedded below; no public link to a missing GitHub revision.
                return f'{label}: `{Path(target).name}`'
            raise ValueError(f'unresolved public guide reference: {target}')
        text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', link, text)
        # Detailed payment proof is public, never an SDK recovery file.
        for name in ('codex-one-call-2026-09-30-blueprint.json', 'agent-rails-2026-09-30.json', 'seller-operations-2026-09-30.json', 'independent-seller-mainnet-2026-09-30.json', 'native-price-oracle-2026-09-30.json', 'witness-prepaid-mainnet-2026-09-30.json', 'gas-sponsorship-mainnet-2026-09-30.json', 'provider-recovery-mainnet-2026-09-30.json', 'refund-mainnet-2026-09-30.json', 'ethereum-profile-2026-09-30.json'):
            evidence = json.loads((docs/'evidence'/name).read_text())
            text += '\n### '+name+'\n\n```json\n'+json.dumps(evidence,ensure_ascii=False,indent=2)+'\n```\n'
        (args.output/(lang+'.md')).write_text(text)


if __name__ == '__main__':
    main()
