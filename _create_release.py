# -*- coding: utf-8 -*-
"""创建 GitHub Release v1.6.1 并上传资源"""
import os, sys, json, urllib.request

REPO = 'mawenshui/bianqian_windows'
TAG = 'v1.6.1'
DIST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dist')
FILES = ['StickyNote-1.6.1-win64.msi', 'StickyNote-v1.6.1-portable.zip']

BODY = """## v1.6.1 更新日志

### 修复
- 修复 window_positions.json 重复 key 问题（加载校验 + 原子写入 + 损坏备份）
- 修复 UndoRedoManager 历史记录索引越界 bug
- 修复自动更新相关测试（适配 _match_asset 新签名）
- 修正 updater 模块单元测试（18 测试全通过）
"""

def api(method, url, token, data=None, ct=None):
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json', 'User-Agent': 'StickyNote'}
    if ct: headers['Content-Type'] = ct
    body = data if isinstance(data, bytes) else (json.dumps(data).encode() if data else None)
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            b = resp.read()
            return json.loads(b) if b else {}
    except urllib.error.HTTPError as e:
        err = json.loads(e.read())
        print(f'HTTP {e.code}: {err.get("message", str(e))}')
        raise

token = os.environ.get('GITHUB_TOKEN', '')
if not token:
    print('GITHUB_TOKEN not set'); sys.exit(1)

# Create release
print(f'Creating release {TAG}...')
release = api('POST', f'https://api.github.com/repos/{REPO}/releases', token, {
    'tag_name': TAG, 'name': f'StickyNote v{TAG}',
    'body': BODY, 'draft': False, 'prerelease': False
})
print(f'  Release ID: {release["id"]}')
upload_url = release['upload_url'].split('{?')[0]

# Upload assets
print('\nUploading assets...')
for fn in FILES:
    fp = os.path.join(DIST_DIR, fn)
    if not os.path.exists(fp):
        print(f'  [SKIP] {fn}'); continue
    sz = os.path.getsize(fp) / 1024 / 1024
    print(f'  Uploading {fn} ({sz:.1f} MB)...')
    with open(fp, 'rb') as f:
        data = f.read()
    api('POST', f'{upload_url}?name={fn}', token, data=data, ct='application/octet-stream')
    print(f'  [OK] {fn}')

print(f'\nDone! {release["html_url"]}')
