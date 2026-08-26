# -*- coding: utf-8 -*-
"""从 artifacts/releases/vX.Y.Z 创建 GitHub Release 并上传正式资产。"""

import argparse
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request


DEFAULT_REPO = 'mawenshui/bianqian_windows'
PROJECT_ROOT = Path(__file__).resolve().parents[2]
VERSION_PATTERN = re.compile(r'^\d+\.\d+\.\d+$')


def configure_utf8_stdio():
    """强制发布工具控制台使用 UTF-8，避免中文输出经过系统 ANSI 编码。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, 'reconfigure', None)
        if reconfigure:
            reconfigure(encoding='utf-8')


def api(method, url, token, data=None, content_type=None):
    """调用 GitHub API，所有 JSON 和返回文本均显式使用 UTF-8。"""
    headers = {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'StickyNote-ReleaseTool',
    }
    if content_type:
        headers['Content-Type'] = content_type

    if isinstance(data, bytes):
        body = data
    elif data is not None:
        headers['Content-Type'] = 'application/json; charset=utf-8'
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
    else:
        body = None

    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request) as response:
            payload = response.read()
            return json.loads(payload.decode('utf-8')) if payload else {}
    except urllib.error.HTTPError as error:
        message = error.read().decode('utf-8', errors='replace')
        raise RuntimeError(f'GitHub API HTTP {error.code}: {message}') from error


def release_files(version):
    """返回发布目录、说明文件及必须上传的正式资产。"""
    release_dir = PROJECT_ROOT / 'artifacts' / 'releases' / f'v{version}'
    notes_file = release_dir / 'RELEASE_NOTES.md'
    assets = [
        release_dir / f'StickyNote-{version}-win64.msi',
        release_dir / f'StickyNote_v{version}_Portable.zip',
        release_dir / 'SHA256SUMS.txt',
    ]
    return release_dir, notes_file, assets


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description='创建 StickyNote GitHub Release')
    parser.add_argument('version', help='不带 v 前缀的语义版本，例如 1.7.8')
    parser.add_argument('--repo', default=DEFAULT_REPO, help='GitHub owner/repo')
    return parser.parse_args(argv)


def main(argv=None):
    configure_utf8_stdio()
    args = parse_args(argv)
    version = args.version.strip()
    if not VERSION_PATTERN.fullmatch(version):
        raise SystemExit('版本号必须使用 X.Y.Z 格式且不带 v 前缀。')

    release_dir, notes_file, assets = release_files(version)
    required_files = [notes_file, *assets]
    missing = [str(path) for path in required_files if not path.is_file()]
    if missing:
        raise SystemExit('发布文件不完整:\n- ' + '\n- '.join(missing))

    token = os.environ.get('GTIHUB_TOKEN', '').strip()
    if not token:
        raise SystemExit('缺少系统环境变量 GTIHUB_TOKEN，停止发布。')

    tag = f'v{version}'
    notes = notes_file.read_text(encoding='utf-8')
    release = api(
        'POST',
        f'https://api.github.com/repos/{args.repo}/releases',
        token,
        {
            'tag_name': tag,
            'name': f'StickyNote {tag}',
            'body': notes,
            'draft': False,
            'prerelease': False,
        },
    )
    upload_url = release['upload_url'].split('{?')[0]

    for asset in assets:
        query = urllib.parse.urlencode({'name': asset.name})
        api(
            'POST',
            f'{upload_url}?{query}',
            token,
            data=asset.read_bytes(),
            content_type='application/octet-stream',
        )
        print(f'已上传: {asset.name}')

    print(f'发布完成: {release["html_url"]}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
