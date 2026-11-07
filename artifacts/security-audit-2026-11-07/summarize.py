"""Assemble audit receipts without merging overlapping test/advisory counts."""
import datetime
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def read(relative):
    return json.loads((HERE / relative).read_text())


def concise_scan(scan):
    return {key: scan[key] for key in (
        'manifest_count', 'package_versions', 'versions_by_ecosystem',
        'affected_package_versions', 'raw_advisory_ids', 'parse_error_count',
        'matching_error_count') if key in scan}


python = read('python/summary.json')
npm = read('npm/summary.json')
vulnetix = read('vulnetix/summary.json')
other = read('rust-go-dart/summary.json')
rust = read('rust-unlocked/remediation-summary.json')
datasets = read('osv-download-provenance.json')
datasets += python['source_coverage']['datasets']
initial_user_changes = {
    'pingblip/memeforge/public/dex/caramel-bust.webp',
    'pingblip/memeforge/public/dex/rendered-from.json',
    'pingblip/memeforge/public/models/caramel-bust.glb',
    'pingblip/memeforge/scripts/blender/generate_chrome_sugar.py',
    'pingblip/memeforge/scripts/check-seated.mjs',
    'pingblip/memeforge/src/data/model-versions.json',
    'pingblip/web/src/data/model-versions.json',
    'pingblip/world/public/dex/caramel-bust.webp',
    'pingblip/world/public/dex/og/caramel-bust.jpg',
}
changed = set(subprocess.check_output(['git', 'diff', '--name-only', '-z'], cwd=ROOT)
              .decode().strip('\0').split('\0')) - initial_user_changes
new = subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard', '-z'], cwd=ROOT)
for relative in new.decode().strip('\0').split('\0'):
    if relative.startswith(('security/vendor-rust/glib/',
                            'packaging/templates/tauri_desktop/src-tauri/vendor/glib/')) \
            or relative == 'helios/tests/test_publication_control.py':
        changed.add(relative)
files = [{'path': relative, 'sha256': hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()}
         for relative in sorted(changed) if relative and (ROOT / relative).is_file()]
(HERE / 'changed-files.json').write_text(json.dumps(files, indent=2) + '\n')
result = {
    'date': '2026-11-07',
    'assembled_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'scope_ru': 'Локальные исходники alexar76 в aicom, закреплённые зависимости, '
                'изолированно разрешённые графы и целевые регрессии. Production не проверялся и не изменялся.',
    'databases': {
        'osv': 'https://osv.dev/',
        'osv_ecosystems': ['npm', 'PyPI', 'crates.io', 'Go', 'Pub'],
        'osv_download_provenance': datasets,
        'vulnetix': vulnetix['database'],
        'npm_registry': 'https://registry.npmjs.org/-/npm/v1/security/advisories/bulk',
    },
    'results': {
        'vulnetix': vulnetix['coverage'],
        'npm_registry': npm['npm_registry'],
        'npm_lock_consistency': npm['lock_consistency'],
        'python_exact_pins': concise_scan(python['source_coverage']),
        'python_after_documented_manual_disposition': python['registry_matches_after_manual_disposition'],
        'python_edited_declarations': python['fixed_declarations'],
        'python_edited_manifests': python['modified_manifest_files'],
        'python_refreshed_locks': python['refreshed_lockfiles'],
        'rust_go_dart_existing_locks': concise_scan(other),
        'rust_unlocked_remediation': rust,
    },
    'fixes_ru': [
        'HELIOS: снятие видео с публикации сохраняется при автоодобрении, гонках и перезапусках; '
        'старые снятия восстанавливаются по журналу; неполная история приостанавливает автоодобрение.',
        'Оба dependency scanner теперь читают requirements*.lock signer/deployer, включая хешированные транзитивные зависимости.',
        'Восстановлены отсутствовавшие bundled-метаданные трёх npm lockfiles без замены существующих версий.',
        'В VS Code tooling заменён устаревший vsce и закреплён исправленный minimatch; '
        'проверен набор инструментов без неразрешённого GitHub SDK.',
        'Уточнены проверенные Python-ограничения и обновлены согласованные uv.lock.',
        'Rust: обновлён git2 и применён проверяемый совместимый upstream-backport glib для Tauri.',
    ],
    'validation': {
        'scanner': {'passed': 110, 'log': 'scanner-regressions.log'},
        'vulnetix_source_families': vulnetix['validation'],
        'python': python['tests'],
        'npm': 'npm/summary.json',
        'rust': 'rust-unlocked/remediation-summary.json',
        'test_counts_overlap': True,
        'diff_check': 'passed',
    },
    'remaining_limits_ru': [
        'Не проверены актуальные процессы серверов, установленные пакеты хостов и OS-слои контейнеров; '
        'локальное исправление ещё не развёрнуто.',
        'Не все допустимые диапазоны и транзитивные комбинации безопасны: остаточные старые версии '
        'и причины сохранены в python/summary.json; текущие проверенные графы учитываются отдельно.',
        'VS Code extension остаётся прототипом без полного разрешённого SDK-графа/tsconfig; '
        'полная сборка расширения не заявляется.',
        'Исторический ignored distribution-снимок с HIGH не переписывался; это не текущий source lockfile.',
        'GLib-backport сохраняет upstream-версию и может давать сырое version-only срабатывание; '
        'доказательства исправления и maintenance notices сохранены отдельно.',
        'Android/JVM, native CocoaPods/Flutter engine, системные библиотеки, toolchain и неизвестные дефекты '
        'не покрываются полностью этими пятью экосистемами OSV.',
    ],
    'evidence': {
        'python': 'python/summary.json', 'npm': 'npm/summary.json',
        'vulnetix': 'vulnetix/summary.json', 'rust_go_dart': 'rust-go-dart/summary.json',
        'rust_unlocked': 'rust-unlocked/remediation-summary.json',
        'changed_files_and_sha256': 'changed-files.json',
        'platform_coverage_limits': 'platform-coverage-limits.json',
    },
    'github_writes': False, 'deployments': False, 'remote_youtube_changes': False,
}
(HERE / 'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'changed_source_files': len(files), 'summary': str(HERE / 'summary.json')}, ensure_ascii=False))
