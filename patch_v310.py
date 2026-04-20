import sys, os

def patch(fp, old, new, label):
    with open(fp) as f: c = f.read()
    if c.count(old) == 0: print(f'SKIP (not found): {label}'); return
    if c.count(old) > 1:  print(f'ERROR (ambiguous): {label}'); sys.exit(1)
    with open(fp, 'w') as f: f.write(c.replace(old, new, 1))
    print(f'OK: {label}')

patch('config.py',
    "    'notify_on_failure':     True,\n}",
    "    'notify_on_failure':     True,\n    'preserve_originals':    False,\n}",
    'config.py — preserve_originals default')

patch('app.py', 'VERSION = "3.0.2"', 'VERSION = "3.1.0"', 'app.py — version bump')

patch('app.py',
    "                        'notify_on_success', 'notify_on_failure'):",
    "                        'notify_on_success', 'notify_on_failure',\n                        'preserve_originals'):",
    'app.py — preserve_originals in POST handler')

patch('pyproject.toml', 'version = "2.8.1"', 'version = "3.1.0"', 'pyproject.toml — version')

patch('processor.py',
    "COMICS_IN  = '/Comics_in'\nCOMICS_OUT = '/Comics_out'",
    "COMICS_IN      = '/Comics_in'\nCOMICS_OUT     = '/Comics_out'\nCOMICS_ARCHIVE = os.path.join(COMICS_IN, '.archive')",
    'processor.py — COMICS_ARCHIVE constant')

patch('processor.py',
    "    for root, _, files in os.walk(COMICS_IN):",
    "    for root, dirs, files in os.walk(COMICS_IN):\n        dirs[:] = [d for d in dirs if not (root == COMICS_IN and d == '.archive')]",
    'processor.py — exclude .archive from scan')

patch('processor.py',
    "            if os.path.exists(filepath):\n                os.remove(filepath)\n                prune_empty_dirs(filepath, in_base)",
    "            if os.path.exists(filepath):\n                if c_type == 'comic' and config.get('preserve_originals', False):\n                    _dest = os.path.join(COMICS_ARCHIVE, os.path.relpath(filepath, COMICS_IN))\n                    os.makedirs(os.path.dirname(_dest), exist_ok=True)\n                    shutil.move(filepath, _dest)\n                else:\n                    os.remove(filepath)\n                prune_empty_dirs(filepath, in_base)",
    'processor.py — archive instead of delete')

patch('processor.py',
    "            if path.endswith('.failed'):\n                return\n            with lock_mutex:",
    "            if path.endswith('.failed'):\n                return\n            if self.c_type == 'comic' and path.startswith(COMICS_ARCHIVE + os.sep):\n                return\n            with lock_mutex:",
    'processor.py — exclude .archive from inotify')

patch('templates/index.html',
    "Increase for slow network drives. Range: 10\u2013300 s.</p>\n            </div>",
    "Increase for slow network drives. Range: 10\u2013300 s.</p>\n                <div class=\"checks\" style=\"margin-top:14px\">\n                    <label class=\"check\">\n                        <input type=\"checkbox\" name=\"preserve_originals\" {% if config.preserve_originals %}checked{% endif %}>\n                        <span>\n                            <div class=\"check-label\">Preserve Originals</div>\n                            <div class=\"check-hint\">Move source comics to <code>Comics_in/.archive</code> after conversion instead of deleting them</div>\n                        </span>\n                    </label>\n                </div>\n            </div>",
    'index.html — preserve_originals checkbox')

patch('CHANGELOG.md',
    "## v3.0.1 \u2014 Bug Fixes & Housekeeping\n\n## [3.0.2] - 2026-04-18\n\n### Fixed\n",
    "## v3.0.2 \u2014 Bug Fixes & Housekeeping\n\n",
    'CHANGELOG.md — fix empty v3.0.1 and reformat v3.0.2')

entry = """## v3.1.0 \u2014 Preserve Originals

- Added: **Preserve Originals** toggle in Bindery Settings \u2014 when enabled, source files in `Comics_in` are moved to `Comics_in/.archive` (mirroring subfolder structure) after a successful conversion instead of being deleted; `.archive` is never scanned or reprocessed
- Fixed: `pyproject.toml` version was out of sync with app version (was `2.8.1`)
- Fixed: `CHANGELOG.md` had an empty `v3.0.1` heading and inconsistent entry format \u2014 standardised to `## vX.Y.Z \u2014 Description` throughout

"""
with open('CHANGELOG.md') as f: cl = f.read()
if '## v3.1.0' not in cl:
    with open('CHANGELOG.md', 'w') as f: f.write(entry + cl)
    print('OK: CHANGELOG.md — v3.1.0 entry prepended')
else:
    print('SKIP: CHANGELOG.md — v3.1.0 already present')

print('\nDone. Run: git diff')
