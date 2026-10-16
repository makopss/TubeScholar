"""Isolated library/API regressions: python -B -X utf8 scripts/test_library.py."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
(ROOT / 'build').mkdir(exist_ok=True)
_data = tempfile.TemporaryDirectory(prefix='library-tests-', dir=ROOT / 'build')
os.environ['TUBESCHOLAR_DATA_DIR'] = _data.name

import httpx
import app as api
import library_manager as manager
import storage
from note_topics import classify_note, CLASSIFICATION_VERSION


class LibraryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        storage.save_library({'notes': {}})
        manager._text_cache.clear()
        storage.save_note({'video_id': 'lesson', 'title': '벡터 Vector', 'channel': 'Math School'},
                          '# 벡터\n고유벡터 <script>example</script>', note_id='one',
                          lang_meta={'note_target_lang': 'ko'},
                          subtitles=[{'start': 0, 'end': 2, 'text': 'Source dialogue'}])
        storage.save_note({'video_id': 'local_fixture', 'video_type': 'local', 'title': '행렬 Matrix'},
                          '본문의 고유값 설명', note_id='two', lang_meta={'note_target_lang': 'en'})
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=api.app),
                                        base_url='http://127.0.0.1', headers={'x-tubescholar': '1'})

    async def asyncTearDown(self):
        await self.client.aclose()

    async def bulk(self, action, ids=None, **kwargs):
        return await self.client.post('/api/library/notes/bulk',
                                      json={'action': action, 'note_ids': ids or ['one'], **kwargs})

    async def collection(self, name='선형대수', **kwargs):
        response = await self.client.post('/api/library/collections', json={'name': name, **kwargs})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()['id']

    async def query(self, **params):
        response = await self.client.get('/api/library', params=params)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def test_legacy_notes_have_defaults_without_rewriting_files(self):
        before = Path(storage.LIBRARY_FILE).read_bytes()
        result = await self.query()
        self.assertEqual(result['active_count'], 2)
        self.assertEqual(result['collections'], [])
        self.assertEqual(result['notes'][0]['learning_status'], 'unread')
        self.assertEqual(result['notes'][0]['tags'], [])
        self.assertEqual(Path(storage.LIBRARY_FILE).read_bytes(), before)

    async def test_search_title_channel_tags_and_note_text(self):
        await self.bulk('tags_add', tags=['Game Math'])
        for query in ['VECTOR', 'Ｍａｔｈ', 'game', '고유벡터']:
            with self.subTest(query=query):
                result = await self.query(q=query)
                self.assertEqual([m['note_id'] for m in result['notes']], ['one'])
        result = await self.query(q='고유벡터')
        self.assertIn('<script>', result['notes'][0]['snippet'])  # Frontend must escape it.
        self.assertEqual((await self.query(q='없는표현'))['total'], 0)

    async def test_body_search_cache_invalidates_after_edit(self):
        self.assertEqual((await self.query(q='고유벡터'))['total'], 1)
        storage.update_note('one', '새로운 개념: 회전변환')
        self.assertEqual((await self.query(q='고유벡터'))['total'], 0)
        self.assertEqual((await self.query(q='회전변환'))['total'], 1)

    async def test_filters_and_bulk_updates_persist_on_reload(self):
        for action, kwargs in [('tags_add', {'tags': ['수학', '수학', 'MATH']}),
                               ('status', {'status': 'review'}), ('star', {})]:
            self.assertEqual((await self.bulk(action, **kwargs)).status_code, 200)
        storage._lib_cache = None
        result = await self.query(tag='math', status='review', starred='true', source='youtube', language='ko')
        self.assertEqual(result['total'], 1)
        self.assertEqual(result['notes'][0]['tags'], ['수학', 'MATH'])
        await self.bulk('tags_remove', tags=['math'])
        self.assertEqual((await self.query(tag='math'))['total'], 0)

    async def test_collections_share_references_and_preserve_order_and_source(self):
        cid = await self.collection(source={'kind': 'youtube_playlist', 'reference': 'https://youtube.com/playlist?list=fixture'})
        other = await self.collection('복습')
        await self.bulk('collection_add', ['two', 'one'], collection_id=cid)
        await self.bulk('collection_add', collection_id=other)
        result = await self.query(collection_id=cid, sort='collection')
        self.assertEqual([m['note_id'] for m in result['notes']], ['two', 'one'])
        self.assertEqual(result['collections'][0]['source']['kind'], 'youtube_playlist')
        self.assertEqual(len(storage.load_library()['notes']), 2)
        response = await self.client.put(f'/api/library/collections/{cid}/order', json={'note_ids': ['one', 'two']})
        self.assertEqual(response.status_code, 200)
        self.assertEqual((await self.query(collection_id=cid, sort='collection'))['notes'][0]['note_id'], 'one')
        response = await self.client.put(f'/api/library/collections/{cid}/order', json={'note_ids': ['one', 'one']})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(storage.load_library()['collections'][cid]['note_ids'], ['one', 'two'])

    async def test_collection_rename_duplicates_remove_membership_and_delete(self):
        cid = await self.collection('Course')
        response = await self.client.post('/api/library/collections', json={'name': 'course'})
        self.assertEqual(response.status_code, 409)
        await self.bulk('collection_add', collection_id=cid)
        await self.bulk('collection_remove', collection_id=cid)
        self.assertEqual((await self.query(collection_id=cid))['total'], 0)
        await self.client.patch(f'/api/library/collections/{cid}', json={'name': 'Renamed'})
        self.assertEqual(storage.load_library()['collections'][cid]['name'], 'Renamed')
        await self.client.delete(f'/api/library/collections/{cid}')
        self.assertIsNotNone(storage.get_note('one'))
        self.assertEqual((await self.query())['collections'], [])

    async def test_invalid_selection_does_not_partially_change_notes(self):
        response = await self.bulk('tags_add', ['one', 'missing'], tags=['bad'])
        self.assertEqual(response.status_code, 404)
        self.assertNotIn('tags', storage.load_library()['notes']['one'])
        response = await self.bulk('tags_add', tags=['x' * 61])
        self.assertEqual(response.status_code, 400)
        response = await self.bulk('tags_add', tags=['x'] * 31)
        self.assertEqual(response.status_code, 400)
        response = await self.bulk('trash', ['../outside'])
        self.assertEqual(response.status_code, 400)

    async def test_metadata_save_failure_does_not_change_cached_library(self):
        before = deepcopy(storage.load_library())
        with patch.object(storage, 'save_library', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):
                manager.bulk_update(['one'], 'star')
        self.assertEqual(storage.load_library(), before)

    async def test_trash_hides_notes_without_deleting_and_restore_preserves_organization(self):
        cid = await self.collection()
        await self.bulk('collection_add', ['one', 'two'], collection_id=cid)
        await self.bulk('tags_add', tags=['保留'])
        await self.bulk('status', status='learning')
        markdown = (Path(storage.NOTES_DIR) / 'one.md').read_bytes()
        bundle = (Path(storage.SUBTITLES_DIR) / 'one.json').read_bytes()
        response = await self.client.delete('/api/notes/one')
        self.assertEqual(response.status_code, 200)
        self.assertEqual((await self.query())['total'], 1)
        self.assertEqual((await self.query(trash='true'))['total'], 1)
        self.assertEqual((await self.client.get('/api/notes/one')).status_code, 404)
        self.assertEqual(len((await self.client.get('/api/notes')).json()['notes']), 1)
        self.assertEqual((Path(storage.NOTES_DIR) / 'one.md').read_bytes(), markdown)
        self.assertEqual((Path(storage.SUBTITLES_DIR) / 'one.json').read_bytes(), bundle)
        self.assertEqual((await self.bulk('restore')).status_code, 200)
        restored = storage.get_note('one')
        self.assertEqual(restored['metadata']['tags'], ['保留'])
        self.assertEqual(restored['metadata']['learning_status'], 'learning')
        self.assertEqual(storage.load_library()['collections'][cid]['note_ids'], ['one', 'two'])

    async def test_trashed_notes_cannot_be_edited_or_purged_as_active(self):
        self.assertEqual((await self.bulk('purge')).status_code, 409)
        await self.bulk('trash')
        self.assertEqual((await self.client.put('/api/notes/one', json={'markdown': 'overwrite'})).status_code, 404)
        self.assertEqual((await self.bulk('star')).status_code, 409)
        self.assertEqual((await self.bulk('restore', ['two'])).status_code, 409)

    async def test_shared_video_retained_until_last_trashed_reference_is_purged(self):
        video = b'unique library media fixture'
        storage.save_note({'video_id': 'local_fixture', 'video_type': 'local', 'title': 'Sibling'},
                          'Other version', note_id='sibling')
        reference = storage.attach_note_video('two', io.BytesIO(video), 'lesson.mp4')
        storage.attach_note_video('sibling', io.BytesIO(video), 'lesson.mp4')
        cid = await self.collection()
        await self.bulk('collection_add', ['two', 'sibling'], collection_id=cid)
        await self.bulk('trash', ['two', 'sibling'])
        self.assertTrue(storage.local_video_path(reference))
        await self.bulk('purge', ['two'])
        self.assertTrue(storage.local_video_path(reference))
        self.assertEqual(storage.load_library()['collections'][cid]['note_ids'], ['sibling'])
        await self.bulk('restore', ['sibling'])
        self.assertEqual(Path(storage.local_video_path(reference)).read_bytes(), video)
        await self.bulk('trash', ['sibling'])
        await self.bulk('purge', ['sibling'])
        self.assertIsNone(storage.local_video_path(reference))

    async def test_purge_keeps_audio_owned_by_a_note_with_a_longer_id(self):
        storage.save_note({'video_id': 'sibling', 'title': 'Sibling'}, 'Sibling text', note_id='one_extra')
        own_audio = Path(storage.AUDIO_DIR) / 'one_v2_injoon_p0_deadbeef.mp3'
        sibling_audio = Path(storage.AUDIO_DIR) / 'one_extra_v2_injoon_p0_deadbeef.mp3'
        sibling_subs = Path(storage.AUDIO_DIR) / 'sub_one_extra_orig_v2_injoon_p0_deadbeef.mp3'
        for audio in (own_audio, sibling_audio, sibling_subs):
            audio.write_bytes(b'audio fixture')
            audio.with_suffix('.json').write_text('[]', encoding='utf-8')
        await self.bulk('trash')
        await self.bulk('purge')
        self.assertFalse(own_audio.exists())
        self.assertTrue(sibling_audio.exists())
        self.assertTrue(sibling_audio.with_suffix('.json').exists())
        self.assertTrue(sibling_subs.exists())

    async def test_purge_metadata_failure_keeps_cached_notes_and_files(self):
        await self.bulk('trash')
        before = deepcopy(storage.load_library())
        note_path = Path(storage.NOTES_DIR) / 'one.md'
        with patch.object(storage, 'save_library', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):
                manager.bulk_update(['one'], 'purge')
        self.assertEqual(storage.load_library(), before)
        self.assertTrue(note_path.exists())

    async def test_note_edit_and_regeneration_keep_longer_id_audio(self):
        storage.save_note({'video_id': 'sibling', 'title': 'Sibling'}, 'Sibling text', note_id='one_extra')
        audio = Path(storage.AUDIO_DIR) / 'one_extra_v2_injoon_p0_deadbeef.mp3'
        audio.write_bytes(b'audio fixture')
        storage.update_note('one', 'Edited text')
        self.assertTrue(audio.exists())
        storage.save_note({'video_id': 'lesson', 'title': 'Rewritten'}, 'New text', note_id='one')
        self.assertTrue(audio.exists())

    async def test_regeneration_preserves_manager_fields(self):
        await self.bulk('tags_add', tags=['수학'])
        await self.bulk('status', status='completed')
        await self.bulk('star')
        storage.save_note({'video_id': 'lesson', 'title': 'Rewritten'}, 'New text', note_id='one')
        meta = storage.load_library()['notes']['one']
        self.assertEqual(meta['tags'], ['수학'])
        self.assertEqual(meta['learning_status'], 'completed')
        self.assertTrue(meta['starred'])

    async def test_recent_open_is_separate_from_learning_state(self):
        response = await self.client.post('/api/library/notes/one/opened')
        self.assertEqual(response.status_code, 200)
        result = await self.query(sort='opened')
        self.assertEqual(result['notes'][0]['note_id'], 'one')
        self.assertEqual(result['notes'][0]['learning_status'], 'unread')
        await self.bulk('trash')
        self.assertEqual((await self.client.post('/api/library/notes/one/opened')).status_code, 404)

    async def test_audiobook_files_and_cues_survive_trash_and_restore(self):
        import tts
        markdown = storage.get_note('one')['markdown']
        digest = tts.hashlib.sha1(markdown.encode()).hexdigest()[:8]
        name = f'one_v2_injoon_p0_{digest}.mp3'
        audio = Path(storage.AUDIO_DIR) / name
        audio.write_bytes(b'a' * 2048)
        cues = [{'start': 0, 'end': 1, 'text': '벡터'}]
        audio.with_suffix('.json').write_text(json.dumps(cues), encoding='utf-8')
        storage.update_note_audiobook('one', audiobook_info={'filename': name})
        await self.bulk('trash')
        self.assertTrue(audio.exists())
        await self.bulk('restore')
        reopened = storage.get_note('one')
        self.assertEqual(reopened['audiobook']['filename'], name)
        self.assertEqual(reopened['audiobook']['cues'], cues)
        await self.bulk('trash')
        await self.bulk('purge')
        self.assertFalse(audio.exists())
        self.assertFalse(audio.with_suffix('.json').exists())

    async def test_large_library_metadata_page_avoids_body_reads(self):
        lib = deepcopy(storage.load_library())
        for index in range(2000):
            nid = f'large_{index:04}'
            lib['notes'][nid] = {'note_id': nid, 'title': nid, 'video_id': nid,
                                 'created_at': '2026-01-01 00:00:00',
                                 'classification_version': CLASSIFICATION_VERSION, 'auto_tags': []}
        lib['collections'] = {f'group_{i}': {'id': f'group_{i}', 'name': f'Group {i}',
            'note_ids': [f'large_{j:04}' for j in range(i * 50, (i + 1) * 50)]}
            for i in range(40)}
        storage.save_library(lib)
        with patch.object(manager, '_body', side_effect=AssertionError('unneeded body read')):
            result = await self.query(limit=20)
        self.assertEqual(result['total'], 2002)
        self.assertEqual(len(result['notes']), 20)
        self.assertEqual(len(result['collections']), 40)
        self.assertTrue(all(group['count'] == 50 for group in result['collections']))

    async def test_pagination_has_no_overlap_or_missing_notes(self):
        lib = deepcopy(storage.load_library())
        for index in range(65):
            nid = f'page_{index:03}'
            lib['notes'][nid] = {'note_id': nid, 'title': nid, 'video_id': nid,
                                 'created_at': '2026-01-01 00:00:00'}
        storage.save_library(lib)
        ids = []
        for offset in range(0, 67, 20):
            result = await self.query(offset=offset, limit=20)
            self.assertEqual(result['total'], 67)
            ids.extend(note['note_id'] for note in result['notes'])
        self.assertEqual(len(set(ids)), 67)

    async def test_zip_exports_selected_notes_subtitles_and_memberships_only(self):
        cid = await self.collection()
        await self.bulk('collection_add', ['one', 'two'], collection_id=cid)
        response = await self.client.post('/api/library/export', json={'note_ids': ['one']})
        self.assertEqual(response.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            self.assertEqual(set(archive.namelist()), {'notes/one.md', 'subtitles/one.json', 'manifest.json'})
            self.assertIn('고유벡터', archive.read('notes/one.md').decode())
            self.assertEqual(json.loads(archive.read('subtitles/one.json'))['subtitles'][0]['text'], 'Source dialogue')
            manifest = json.loads(archive.read('manifest.json'))
            self.assertEqual(manifest['collections'][0]['note_ids'], ['one'])
            self.assertNotIn('note_path', manifest['notes'][0])
        await self.bulk('trash')
        self.assertEqual((await self.client.post('/api/library/export', json={'note_ids': ['one']})).status_code, 409)

    async def test_concurrent_metadata_changes_are_not_lost(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(manager.bulk_update, ['one'], 'tags_add', tags=[tag]) for tag in ['A', 'B']]
            for future in futures:
                future.result(timeout=5)
        self.assertEqual(set(storage.load_library()['notes']['one']['tags']), {'A', 'B'})

    async def test_request_validation_and_csrf(self):
        self.assertEqual((await self.client.get('/api/library', params={'offset': -1})).status_code, 422)
        self.assertEqual((await self.client.get('/api/library', params={'limit': 101})).status_code, 422)
        self.assertEqual((await self.client.get('/api/library', params={'sort': 'unknown'})).status_code, 422)
        self.assertEqual((await self.client.post('/api/library/notes/bulk', json={'note_ids': [], 'action': 'trash'})).status_code, 422)
        response = await self.client.post('/api/library/collections', headers={'x-tubescholar': ''}, json={'name': 'blocked'})
        self.assertEqual(response.status_code, 403)

    async def test_auto_topics_group_related_languages_and_keep_manual_groups(self):
        cid = await self.collection('My course')
        await self.bulk('collection_add', collection_id=cid)
        await self.bulk('tags_add', tags=['수동 태그'])
        result = await self.query(topic='math')
        self.assertEqual({m['note_id'] for m in result['notes']}, {'one', 'two'})
        self.assertEqual(result['smart_groups'], [{'id': 'math', 'count': 2}])
        self.assertEqual((await self.query(collection_id=cid, topic='math'))['total'], 1)
        storage.update_note('one', '# Python programming\nCoding in Python.')
        meta = storage.load_library()['notes']['one']
        self.assertIn('programming', meta['auto_tags'])
        self.assertEqual(meta['tags'], ['수동 태그'])
        self.assertEqual(storage.load_library()['collections'][cid]['note_ids'], ['one'])

    async def test_legacy_classification_runs_once_without_changing_note_files(self):
        cid = await self.collection()
        await self.bulk('collection_add', collection_id=cid)
        lib = deepcopy(storage.load_library())
        for meta in lib['notes'].values():
            for field in ('auto_tags', 'auto_keywords', 'classification_version'):
                meta.pop(field, None)
        storage.save_library(lib)
        markdown = (Path(storage.NOTES_DIR) / 'one.md').read_bytes()
        result = await self.query(topic='math')
        self.assertEqual(result['total'], 2)
        self.assertEqual((Path(storage.NOTES_DIR) / 'one.md').read_bytes(), markdown)
        self.assertEqual(storage.load_library()['collections'][cid]['note_ids'], ['one'])
        with patch.object(manager, 'classify_note', side_effect=AssertionError('classified twice')):
            self.assertEqual((await self.query())['total'], 2)

    async def test_classification_failure_keeps_cached_library_unchanged(self):
        lib = deepcopy(storage.load_library())
        lib['notes']['one'].pop('classification_version')
        storage.save_library(lib)
        before = deepcopy(storage.load_library())
        with patch.object(storage, 'save_library', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):
                manager.query_library()
        self.assertEqual(storage.load_library(), before)

    async def test_unknown_topic_and_trash_counts(self):
        storage.save_note({'video_id': 'misc', 'title': '이름 없는 기록'}, '평범한 하루', note_id='misc')
        self.assertEqual((await self.query(topic='other'))['total'], 1)
        await self.bulk('trash')
        counts = {g['id']: g['count'] for g in (await self.query())['smart_groups']}
        self.assertEqual(counts['math'], 1)
        await self.bulk('restore')
        self.assertEqual((await self.query(topic='math'))['total'], 2)
        self.assertEqual((await self.client.get('/api/library', params={'topic':'bad'})).status_code, 400)


class TopicTests(unittest.TestCase):
    def test_titles_outweigh_incidental_prose_and_fullwidth_words(self):
        tags = classify_note('Ｐｙｔｈｏｎ Programming', 'Music was used once as an example.')['auto_tags']
        self.assertEqual(tags, ['programming'])

    def test_code_blocks_and_substrings_are_not_topics(self):
        self.assertEqual(classify_note('A daily journal', '```python\npython programming\n```')['auto_tags'], [])
        self.assertEqual(classify_note('A chair painted red', 'plain text')['auto_tags'], [])

    def test_keywords_are_bounded_and_generic_headings_ignored(self):
        result = classify_note('벡터와 행렬 핵심 강의', '# 개요\n## 요약\n## 고유값')
        self.assertEqual(result['auto_tags'], ['math'])
        self.assertNotIn('개요', result['auto_keywords'])
        self.assertLessEqual(len(result['auto_keywords']), 5)


if __name__ == '__main__':
    try:
        unittest.main()
    finally:
        _data.cleanup()
