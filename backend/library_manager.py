"""Library organization without moving or duplicating notes and their media."""
from collections import Counter, OrderedDict, defaultdict
from copy import deepcopy
from pathlib import Path
import io
import json
import time
import unicodedata
import uuid
import zipfile

from fastapi import HTTPException
import storage
from note_topics import classify_note, CLASSIFICATION_VERSION, TOPICS

STATUSES = {'unread', 'learning', 'completed', 'review'}
_text_cache = OrderedDict()


def _key(value):
    return unicodedata.normalize('NFKC', str(value or '')).casefold()


def _label(value, limit=60):
    if not isinstance(value, str):
        raise HTTPException(400, '이름은 문자열이어야 합니다.')
    value = ' '.join(value.split())
    if not value or len(value) > limit:
        raise HTTPException(400, f'이름은 1~{limit}자로 입력해 주세요.')
    return value


def _tags(values):
    if not isinstance(values, list) or len(values) > 30:
        raise HTTPException(400, '태그는 최대 30개까지 지정할 수 있습니다.')
    result, seen = [], set()
    for value in values:
        label = _label(value)
        if _key(label) not in seen:
            seen.add(_key(label))
            result.append(label)
    return result


def _body(note_id):
    if not storage.is_safe_note_id(note_id):
        return ''
    path = Path(storage.NOTES_DIR) / f'{note_id}.md'
    try:
        stamp = path.stat()
        signature = (stamp.st_mtime_ns, stamp.st_size)
        cached = _text_cache.get(note_id)
        if cached and cached[0] == signature:
            _text_cache.move_to_end(note_id)
            return cached[1]
        text = storage.strip_frontmatter(path.read_text(encoding='utf-8'))
        _text_cache[note_id] = (signature, text)
        while len(_text_cache) > 512:
            _text_cache.popitem(last=False)
        return text
    except (OSError, UnicodeError):
        return ''


def _entry(meta):
    entry = {k: v for k, v in meta.items() if k not in ('subtitles', 'translations', 'note_path', 'local_video')}
    entry.update(tags=list(meta.get('tags') or []),
                 learning_status=meta.get('learning_status') or 'unread',
                 starred=bool(meta.get('starred')))
    entry['has_audiobook'] = bool(meta.get('audiobook') or meta.get('subtitle_audiobook'))
    return entry


def _classified_library():
    lib = storage.load_library()
    pending = [nid for nid, meta in lib.get('notes', {}).items()
               if meta.get('classification_version') != CLASSIFICATION_VERSION]
    if pending:
        lib = deepcopy(lib)
        for nid in pending:
            meta = lib['notes'][nid]
            meta.update(classify_note(meta.get('title', ''), _body(nid)))
        storage.save_library(lib)
    return lib


@storage._locked
def query_library(q='', collection_id='', tag='', status='', source='', language='',
                  starred=False, trash=False, sort='newest', offset=0, limit=40, topic=''):
    if topic and topic not in {*TOPICS, 'other'}:
        raise HTTPException(400, '잘못된 자동 분류입니다.')
    lib = _classified_library()
    groups = lib.get('collections', {})
    if collection_id and collection_id not in groups:
        raise HTTPException(404, '학습 묶음을 찾을 수 없습니다.')
    notes = [m for m in lib.get('notes', {}).values() if isinstance(m, dict)]
    active = [m for m in notes if not m.get('trashed_at')]
    tag_counts = Counter(t for m in active for t in (m.get('tags') or []))
    versions = Counter(m.get('video_id') for m in active)
    memberships = defaultdict(list)
    for cid, group in groups.items():
        for nid in group.get('note_ids', []):
            memberships[nid].append(cid)
    selected = groups.get(collection_id, {})
    members = selected.get('note_ids', [])
    member_set = set(members)
    terms = _key(q).split()
    rows = []
    for meta in notes:
        if bool(meta.get('trashed_at')) != trash:
            continue
        nid = meta['note_id']
        if collection_id and nid not in member_set:
            continue
        if topic and topic not in (meta.get('auto_tags') or ['other']):
            continue
        if tag and _key(tag) not in {_key(t) for t in meta.get('tags', [])}:
            continue
        if status and (meta.get('learning_status') or 'unread') != status:
            continue
        if source and meta.get('video_type', 'youtube') != source:
            continue
        if language and meta.get('note_target_lang') != language:
            continue
        if starred and not meta.get('starred'):
            continue
        haystack = _key(' '.join([str(meta.get('title', '')), str(meta.get('channel', '')),
                                 ' '.join(meta.get('tags') or []),
                                 ' '.join(meta.get('auto_keywords') or [])]))
        snippet = ''
        if terms and not all(term in haystack for term in terms):
            body = _body(nid)
            combined = haystack + '\n' + _key(body)
            if not all(term in combined for term in terms):
                continue
            # Display source text, never HTML supplied by the note.
            lines = [line.strip() for line in body.splitlines() if line.strip()]
            snippet = next((line[:240] for line in lines if any(term in _key(line) for term in terms)), '')
        row = _entry(meta)
        row['snippet'] = snippet
        row['version_count'] = versions[meta.get('video_id')]
        row['collection_ids'] = memberships[nid]
        rows.append(row)
    order = {nid: index for index, nid in enumerate(members)}
    if sort == 'title':
        rows.sort(key=lambda m: (_key(m.get('title')), m['note_id']))
    elif sort == 'collection' and collection_id:
        rows.sort(key=lambda m: order.get(m['note_id'], len(order)))
    else:
        field = {'newest': 'created_at', 'updated': 'updated_at', 'opened': 'last_opened_at'}.get(sort, 'created_at')
        rows.sort(key=lambda m: (m.get(field) or '', m['note_id']), reverse=True)
    collections = []
    active_ids = {m['note_id'] for m in active}
    for cid, group in groups.items():
        collections.append(dict(group, id=cid,
                                count=sum(nid in active_ids for nid in group.get('note_ids', []))))
    smart_counts = Counter(topic for meta in active for topic in (meta.get('auto_tags') or ['other']))
    return {'notes': rows[offset:offset + limit], 'total': len(rows), 'offset': offset,
            'active_count': len(active), 'trash_count': len(notes) - len(active),
            'smart_groups': [{'id': topic, 'count': count} for topic, count in sorted(smart_counts.items())],
            'collections': collections, 'tags': [{'name': name, 'count': count} for name, count in sorted(tag_counts.items(), key=lambda x: _key(x[0]))],
            'languages': sorted({m['note_target_lang'] for m in active if m.get('note_target_lang')})}


@storage._locked
def create_collection(name, source=None):
    name = _label(name, 100)
    lib = deepcopy(storage.load_library())
    groups = lib.setdefault('collections', {})
    if any(_key(group['name']) == _key(name) for group in groups.values()):
        raise HTTPException(409, '같은 이름의 학습 묶음이 있습니다.')
    cid = uuid.uuid4().hex
    group = {'id': cid, 'name': name, 'note_ids': [],
             'source': source or {'kind': 'manual', 'reference': ''},
             'created_at': time.strftime('%Y-%m-%d %H:%M:%S')}
    groups[cid] = group
    storage.save_library(lib)
    return group


@storage._locked
def edit_collection(collection_id, name=None, note_ids=None, delete=False):
    lib = deepcopy(storage.load_library())
    groups = lib.get('collections', {})
    if collection_id not in groups:
        raise HTTPException(404, '학습 묶음을 찾을 수 없습니다.')
    if delete:
        del groups[collection_id]
    else:
        group = groups[collection_id]
        if name is not None:
            name = _label(name, 100)
            if any(cid != collection_id and _key(other['name']) == _key(name) for cid, other in groups.items()):
                raise HTTPException(409, '같은 이름의 학습 묶음이 있습니다.')
            group['name'] = name
        if note_ids is not None:
            previous = group.get('note_ids', [])
            if len(note_ids) != len(previous) or set(note_ids) != set(previous):
                raise HTTPException(400, '묶음에 포함된 노트를 각각 한 번씩 지정해야 합니다.')
            group['note_ids'] = list(note_ids)
    storage.save_library(lib)
    return {'success': True}


@storage._locked
def bulk_update(note_ids, action, tags=None, collection_id=None, status=None):
    # Validate the entire selection before changing any record.
    ids = list(dict.fromkeys(note_ids))
    lib = deepcopy(storage.load_library())
    notes = lib.get('notes', {})
    if not ids or len(ids) > 500 or any(not storage.is_safe_note_id(nid) for nid in ids):
        raise HTTPException(400, '노트를 1~500개 선택해 주세요.')
    if any(nid not in notes for nid in ids):
        raise HTTPException(404, '선택한 노트 중 일부를 찾을 수 없습니다. 목록을 새로고침해 주세요.')
    selected = [notes[nid] for nid in ids]
    if action not in {'tags_add', 'tags_remove', 'collection_add', 'collection_remove', 'status', 'star', 'unstar', 'trash', 'restore', 'purge'}:
        raise HTTPException(400, '지원하지 않는 보관함 작업입니다.')
    if action in {'restore', 'purge'}:
        if any(not meta.get('trashed_at') for meta in selected):
            raise HTTPException(409, '휴지통의 노트만 복원하거나 영구 삭제할 수 있습니다.')
    elif any(meta.get('trashed_at') for meta in selected):
        raise HTTPException(409, '먼저 휴지통에서 노트를 복원해 주세요.')
    if action.startswith('tags_'):
        tags = _tags(tags)
    if action.startswith('collection_'):
        group = lib.get('collections', {}).get(collection_id)
        if not group:
            raise HTTPException(404, '학습 묶음을 찾을 수 없습니다.')
        members = group.setdefault('note_ids', [])
        group['note_ids'] = list(dict.fromkeys(members + ids)) if action == 'collection_add' else [nid for nid in members if nid not in ids]
    if action == 'status' and status not in STATUSES:
        raise HTTPException(400, '잘못된 학습 상태입니다.')
    now = time.strftime('%Y-%m-%d %H:%M:%S')
    for meta in selected:
        if action == 'tags_add':
            meta['tags'] = _tags(list(meta.get('tags') or []) + tags)
        elif action == 'tags_remove':
            remove = {_key(tag) for tag in tags}
            meta['tags'] = [tag for tag in meta.get('tags', []) if _key(tag) not in remove]
        elif action == 'status':
            meta['learning_status'] = status
        elif action in {'star', 'unstar'}:
            meta['starred'] = action == 'star'
        elif action == 'trash':
            meta['trashed_at'] = now
        elif action == 'restore':
            meta.pop('trashed_at', None)
    if action == 'purge':
        for nid in ids:
            storage.delete_note(nid)
            _text_cache.pop(nid, None)
    else:
        storage.save_library(lib)
    return {'success': True, 'updated': len(ids)}


@storage._locked
def record_opened(note_id):
    lib = deepcopy(storage.load_library())
    meta = lib.get('notes', {}).get(note_id)
    if not meta or meta.get('trashed_at'):
        raise HTTPException(404, '노트를 찾을 수 없습니다.')
    meta['last_opened_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
    storage.save_library(lib)
    return {'success': True}


@storage._locked
def export_notes(note_ids):
    ids = list(dict.fromkeys(note_ids))
    lib = storage.load_library()
    notes = lib.get('notes', {})
    if not ids or len(ids) > 500 or any(not storage.is_safe_note_id(nid) or nid not in notes for nid in ids):
        raise HTTPException(400, '내보낼 노트를 1~500개 선택해 주세요.')
    if any(notes[nid].get('trashed_at') for nid in ids):
        raise HTTPException(409, '휴지통의 노트는 먼저 복원해 주세요.')
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for nid in ids:
            try:
                text = (Path(storage.NOTES_DIR) / f'{nid}.md').read_text(encoding='utf-8')
            except (OSError, UnicodeError) as exc:
                raise HTTPException(409, '일부 노트 파일을 읽을 수 없습니다.') from exc
            archive.writestr(f'notes/{nid}.md', text)
            bundle = storage._load_note_subtitles_bundle(nid)
            archive.writestr(f'subtitles/{nid}.json', json.dumps(bundle, ensure_ascii=False))
        manifest = {'notes': [_entry(notes[nid]) for nid in ids], 'collections': [
            dict(group, note_ids=[nid for nid in group.get('note_ids', []) if nid in ids])
            for group in lib.get('collections', {}).values() if set(group.get('note_ids', [])) & set(ids)]}
        archive.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2))
    output.seek(0)
    return output
