# -*- coding: utf-8 -*-
"""
更新 GitHub Release v1.5.5 的资源文件
用法: python _update_release.py <GITHUB_TOKEN>
"""
import sys
import os
import urllib.request
import json

REPO = 'mawenshui/bianqian_windows'
TAG = 'v1.5.5'

DIST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dist')
FILES = [
    'StickyNote-1.5.5-win64.msi',
    'StickyNote-v1.5.5-portable.zip',
]

def get_token():
    if len(sys.argv) > 1:
        return sys.argv[1]
    token = os.environ.get('GITHUB_TOKEN', '')
    if token:
        return token
    print('请提供 GitHub Token:')
    print('  方式1: python _update_release.py <TOKEN>')
    print('  方式2: set GITHUB_TOKEN=<TOKEN> && python _update_release.py')
    sys.exit(1)

def api_request(method, url, token, data=None, content_type=None):
    headers = {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'StickyNote-Release-Updater',
    }
    if content_type:
        headers['Content-Type'] = content_type
    body = None
    if data is not None:
        body = data if isinstance(data, bytes) else json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        err = json.loads(e.read())
        print(f'  HTTP {e.code}: {err.get("message", str(e))}')
        raise

def main():
    token = get_token()
    
    # 1. 获取 release
    print(f'获取 Release {TAG}...')
    release = api_request('GET', f'https://api.github.com/repos/{REPO}/releases/tags/{TAG}', token)
    release_id = release['id']
    print(f'  Release ID: {release_id}')
    
    # 2. 删除旧资源
    print('\n删除旧资源...')
    for asset in release.get('assets', []):
        print(f'  删除 {asset["name"]} (id={asset["id"]})...')
        api_request('DELETE', asset['url'], token)
    print('  旧资源已删除')
    
    # 3. 上传新资源
    upload_url = release['upload_url'].split('{?')[0]
    print('\n上传新资源...')
    for filename in FILES:
        filepath = os.path.join(DIST_DIR, filename)
        if not os.path.exists(filepath):
            print(f'  [SKIP] {filename} - 文件不存在: {filepath}')
            continue
        size_mb = os.path.getsize(filepath) / 1024 / 1024
        print(f'  上传 {filename} ({size_mb:.1f} MB)...')
        with open(filepath, 'rb') as f:
            data = f.read()
        url = f'{upload_url}?name={filename}'
        api_request('POST', url, token, data=data, content_type='application/octet-stream')
        print(f'  [OK] {filename}')
    
    print(f'\n✅ Release {TAG} 更新完成!')
    print(f'   {release["html_url"]}')

if __name__ == '__main__':
    main()
