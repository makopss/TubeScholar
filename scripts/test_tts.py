"""Offline narration regressions: .venv/Scripts/python.exe -B -X utf8 scripts/test_tts.py."""
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
(ROOT / 'build').mkdir(exist_ok=True)
_data = tempfile.TemporaryDirectory(prefix='tts-tests-', dir=ROOT / 'build')
os.environ['TUBESCHOLAR_DATA_DIR'] = _data.name

import storage
import tts


class NarrationCleaningTests(unittest.TestCase):
    def test_notes_keep_definitions_conditions_and_nested_parentheses(self):
        text = ('강화학습(RL). 결과(단, 온도가 일정할 때). '
                '조건（0보다 클 때）. 정의(음향(sound)의 전달). '
                '인용 예시 (웃음). [음악 이론의 배경].')
        cleaned = tts.clean_markdown_for_tts(text)
        for expected in ('(RL)', '(단, 온도가 일정할 때)', '（0보다 클 때）',
                         '(음향(sound)의 전달)', '(웃음)', '음악 이론의 배경'):
            with self.subTest(expected=expected):
                self.assertIn(expected, cleaned)

    def test_subtitles_keep_meaning_even_when_sound_keywords_appear(self):
        examples = [
            '음향(sound)은 파동이다.', '음악(music)의 구조.',
            '(sound waves carry energy)', '[background music theory]',
            '(웃음의 사회적 기능)', '(단, 박수 횟수가 일정할 때)',
            '[설명 [웃음]]', '(설명 (music))', '（조건이 참일 때）',
            '(unclear annotation)', '(unfinished (music)',
        ]
        for text in examples:
            with self.subTest(text=text):
                self.assertEqual(tts.clean_subtitle_line_for_tts(text), text)

    def test_subtitles_remove_only_complete_sound_annotations(self):
        examples = ['(웃음)', '[박수]', '（배경음악）', '［ MUSIC ］',
                    '【拍手】', '(background music)', '[Chuckle]']
        for annotation in examples:
            with self.subTest(annotation=annotation):
                self.assertEqual(tts.clean_subtitle_line_for_tts(annotation), '')
                self.assertEqual(tts.clean_subtitle_line_for_tts(
                    f'{annotation} 실제 대사.'), '실제 대사.')
        self.assertEqual(tts.clean_subtitle_line_for_tts(
            '첫 대사. (웃음) 다음 대사.'), '첫 대사. 다음 대사.')

    def test_long_notes_keep_the_tail_and_paragraph_boundaries(self):
        text = '\n\n'.join(f'{index}번째 문단(중요 조건)을 모두 읽습니다.'
                           for index in range(1200)) + '\n\n마지막 내용 END_MARKER'
        cleaned = tts.clean_markdown_for_tts(text)
        self.assertGreater(len(cleaned), 15000)
        self.assertTrue(cleaned.endswith('마지막 내용 END_MARKER'))
        self.assertIn('\n', cleaned)
        self.assertEqual(cleaned.count('(중요 조건)'), 1200)
        self.assertNotIn('이상으로 주요 요약', cleaned)


class NarrationAudioTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_chunks_cover_the_full_note_and_keep_cumulative_cues(self):
        """Use the installed SDK chunker/offset logic; replace only the network stream."""
        chunks = []

        async def offline_stream(communicate):
            chunk = communicate.state['partial_text']
            chunks.append(chunk)
            audio = b'x' * 6000  # One second at the SDK's 48 kbps CBR rate.
            communicate.state['chunk_audio_bytes'] += len(audio)
            yield {'type': 'audio', 'data': audio}
            metadata = {'Metadata': [{'Type': 'SentenceBoundary', 'Data': {
                'Offset': 0, 'Duration': 10_000_000,
                'text': {'Text': chunk.decode('utf-8')},
            }}]}
            yield communicate._Communicate__parse_metadata(json.dumps(metadata).encode())
            communicate._Communicate__compensate_offset()

        markdown = '\n\n'.join(f'문단 {i}: 강화학습(RL)과 조건(온도 일정)을 설명합니다.'
                               for i in range(700)) + '\n\n마지막 END_MARKER'
        with patch.object(tts.edge_tts.Communicate, '_Communicate__stream', offline_stream):
            result = await tts.generate_note_audio('long_note', markdown)
        self.assertTrue(result['success'], result)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 4096 for chunk in chunks))
        expected = tts.clean_markdown_for_tts(markdown)
        actual = ''.join(cue['text'] for cue in result['cues'])
        self.assertEqual(re.sub(r'\s+', '', actual), re.sub(r'\s+', '', expected))
        self.assertEqual([cue['start'] for cue in result['cues']],
                         list(range(len(chunks))))
        self.assertEqual(result['cues'][-1]['end'], len(chunks))
        self.assertEqual(Path(result['filepath']).stat().st_size, len(chunks) * 6000)
        self.assertIn('END_MARKER', result['cues'][-1]['text'])
        with patch.object(tts, '_stream_tts_with_retry', side_effect=AssertionError('cache missed')):
            cached = await tts.generate_note_audio('long_note', markdown)
        self.assertTrue(cached['cached'])
        self.assertEqual(cached['cues'], result['cues'])
        reopened = tts.find_saved_note_audiobook('long_note', markdown)
        self.assertEqual(reopened['cues'], result['cues'])

    async def test_generation_ignores_old_cache_and_binds_new_temp_audio(self):
        markdown = '의미(중요 조건)를 보존합니다.'
        digest = tts.hashlib.sha1(markdown.encode()).hexdigest()[:8]
        old_filename = f'current_note_injoon_p0_{digest}.mp3'
        old_path = Path(tts.AUDIO_DIR) / old_filename
        old_path.write_bytes(b'x' * 2048)
        old_path.with_suffix('.json').write_text('[{"start": 0, "end": 1, "text": "old"}]')
        self.assertIsNone(tts.bind_temp_note_audio('saved_note', markdown))
        self.assertFalse(tts.has_saved_audiobook_on_disk('current_note'))
        self.assertIsNone(tts.find_saved_note_audiobook(
            'current_note', markdown, saved_meta={'filename': old_filename}))

        async def synthesize(text, voice, speed, filepath):
            Path(filepath).write_bytes(b'y' * 2048)
            return [{'start': 0, 'end': 1, 'text': text}]

        with patch.object(tts, '_stream_tts_with_retry', side_effect=synthesize):
            result = await tts.generate_note_audio('current_note', markdown)
        self.assertFalse(result['cached'])
        self.assertNotEqual(result['filename'], old_filename)
        saved = storage.save_note({'video_id': 'tts_fixture', 'title': 'Fixture'},
                                  markdown, note_id='saved_note')
        self.assertIsNotNone(saved['audiobook'])
        self.assertIn('(중요 조건)', saved['audiobook']['cues'][0]['text'])
        self.assertTrue(tts.has_saved_audiobook_on_disk('saved_note'))
        self.assertTrue(old_path.exists())

    async def test_subtitle_cache_restoration_uses_the_new_cleaning_rules(self):
        subs = [{'text': '(sound waves carry energy)', 'start': 3, 'end': 5}]
        old_filename = 'sub_caption_fixture_orig_injoon_p0_12345678.mp3'
        old_path = Path(tts.AUDIO_DIR) / old_filename
        old_path.write_bytes(b'x' * 2048)
        old_path.with_suffix('.json').write_text('{"cues": [], "sub_cue_map": {}}')
        self.assertIsNone(tts.find_saved_subtitle_audiobook(
            'caption_note', 'caption_fixture', saved_meta={'filename': old_filename}))
        self.assertFalse(tts.has_saved_audiobook_on_disk('caption_note', 'caption_fixture'))

        async def synthesize(text, voice, speed, filepath):
            self.assertIn('(sound waves carry energy)', text)
            Path(filepath).write_bytes(b'y' * 2048)
            return [{'start': 0, 'end': 1, 'text': text}]

        with patch.object(tts, '_stream_tts_with_retry', side_effect=synthesize) as stream:
            result = await tts.generate_subtitles_audio(subs, video_id='caption_fixture', mode='original')
            cached = await tts.generate_subtitles_audio(subs, video_id='caption_fixture', mode='original')
        self.assertTrue(result['success'], result)
        self.assertEqual(stream.call_count, 1)
        self.assertTrue(cached['cached'])
        self.assertEqual(result['cues'][0]['video_start'], 3)
        reopened = tts.find_saved_subtitle_audiobook('caption_note', 'caption_fixture')
        self.assertEqual(reopened['filename'], result['filename'])
        self.assertTrue(old_path.exists())


if __name__ == '__main__':
    try:
        unittest.main()
    finally:
        _data.cleanup()
