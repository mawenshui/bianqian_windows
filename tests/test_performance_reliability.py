"""Performance helpers must not hang or leave partial JSON writes."""

import json
import threading

from features.performance import AsyncFileWorker, LazyLoader, NoteDataCache


def test_cache_stats_finishes_and_reports_hits_and_misses():
    cache = NoteDataCache(max_size=2)
    cache.put(1, {'title': 'one'})
    assert cache.get(1)['title'] == 'one'
    assert cache.get(2) is None
    finished = threading.Event()
    values = []
    def read_stats():
        values.append(cache.stats())
        finished.set()
    thread = threading.Thread(target=read_stats, daemon=True)
    thread.start()
    assert finished.wait(1), 'cache.stats() deadlocked'
    assert values[0]['hits'] == 1 and values[0]['misses'] == 1
    assert values[0]['hit_rate'] == 0.5


def test_cache_eviction_and_lazy_initialization():
    cache = NoteDataCache(max_size=2)
    cache.put(1, {'a': 1})
    cache.put(2, {'a': 2})
    cache.get(1)
    cache.put(3, {'a': 3})
    assert cache.get(2) is None and cache.size == 2
    calls = []
    loader = LazyLoader(lambda: calls.append('made') or {'ready': True})
    assert not loader.is_loaded()
    assert loader.instance is loader.instance
    assert calls == ['made']
    loader.reset()
    assert loader.instance == {'ready': True} and calls == ['made', 'made']


def test_failed_async_write_keeps_prior_json_and_removes_temporary(tmp_path, monkeypatch):
    path = tmp_path / 'note.json'
    path.write_text('{"title":"old"}', encoding='utf-8')
    failures = []
    worker = AsyncFileWorker('write', str(path), {'title': 'new'})
    worker.write_failed.connect(lambda _path, error: failures.append(error))
    def fail_replace(*_args):
        raise OSError('injected failure')
    monkeypatch.setattr('features.performance.os.replace', fail_replace)
    worker.run()
    assert failures and json.loads(path.read_text(encoding='utf-8'))['title'] == 'old'
    assert not list(tmp_path.glob('*.tmp'))
