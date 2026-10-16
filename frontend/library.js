// Search, thumbnail notes and folders, independent of player state.
(() => {
  const state = { q: '', collection_id: '', topic: '', trash: false, sort: 'newest', offset: 0, limit: 20 };
  let data = { notes: [], collections: [], smart_groups: [], total: 0 };
  const selected = new Set(), dragType = 'application/x-tubescholar-notes';
  let requestNumber = 0, controller, busy = false, searchTimer, dragIds = [];
  let menuNoteId = '', menuAnchor, dragNotice = '';
  let openingNote = null;
  const el = id => document.getElementById(id);
  const tr = (key, params) => t(`lib_${key}`, params);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
  const paths = {
    close: '<path d="m6 6 12 12M18 6 6 18"/>',
    folder: '<path d="M3 7V5h6l2 2h10v13H3Z"/>',
    folderPlus: '<path d="M3 7V5h6l2 2h10v13H3Z M12 10v7m-3-3.5h6"/>',
    folderMinus: '<path d="M3 7V5h6l2 2h10v13H3Z M9 14h6"/>',
    check: '<path d="m5 12 4 4L19 6"/>', home: '<path d="m3 11 9-8 9 8M5 10v11h14V10M9 21v-7h6v7"/>',
    trash: '<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7"/>',
    restore: '<path d="M4 10a8 8 0 1 1 0 5M4 4v6h6"/>', erase: '<path d="m3 15 10-12 8 7-10 12H8Z M9 8l8 7M14 22h8"/>',
    left: '<path d="m15 5-7 7 7 7"/>', right: '<path d="m9 5 7 7-7 7"/>',
    spark: '<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z"/>',
    video: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="m10 8 6 4-6 4Z"/>',
    more: '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
  };
  const icon = name => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.folder}</svg>`;
  const button = (name, label, attrs = '') => `<button class="library-icon" type="button" title="${esc(label)}" aria-label="${esc(label)}" ${attrs}>${icon(name)}</button>`;

  async function api(url, method = 'GET', body, signal) {
    const response = await fetch(url, { method, signal,
      ...(body ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {}) });
    if (!response.ok) {
      const failure = await response.json().catch(() => ({}));
      const error = new Error(typeof failure.detail === 'string' ? failure.detail : tr('request_error'));
      error.status = response.status; throw error;
    }
    return response;
  }
  function feedback(message = '', error = false) {
    el('library-feedback').textContent = message;
    el('library-feedback').classList.toggle('is-error', error);
  }
  function groupsOpen(open) {
    el('library-folders').classList.toggle('hidden', !open);
    el('library-groups-toggle').setAttribute('aria-expanded', String(open));
    el('library-groups-toggle').classList.toggle('is-active', open);
  }
  function closeToolbarMenu() {
    el('library-toolbar-menu').classList.add('hidden');
    el('library-more-btn').setAttribute('aria-expanded', 'false');
  }
  function positionMenu(menu, anchor) {
    const drawer = el('library-drawer').getBoundingClientRect(), trigger = anchor.getBoundingClientRect();
    menu.style.top = `${Math.max(8, Math.min(trigger.bottom - drawer.top + 4, drawer.height - menu.offsetHeight - 8))}px`;
    menu.querySelectorAll('[role="menuitem"]')[0]?.focus();
  }
  async function refresh(notice = '') {
    const serial = ++requestNumber;
    controller?.abort(); controller = new AbortController();
    try {
      const response = await api(`/api/library?${new URLSearchParams(state)}`, 'GET', null, controller.signal);
      const result = await response.json();
      if (serial !== requestNumber) return;
      if (state.offset >= result.total && state.offset > 0) {
        state.offset = Math.max(0, Math.floor((result.total - 1) / state.limit) * state.limit);
        return refresh(notice);
      }
      data = result; render(); feedback(notice);
    } catch (error) {
      if (serial !== requestNumber || error.name === 'AbortError') return;
      if (error.status === 404 && state.collection_id) {
        state.collection_id = ''; state.offset = 0; selected.clear();
        return refresh(tr('collection_missing'));
      }
      feedback(error.message, true);
    }
  }
  function render() {
    closeNoteMenu(); closeToolbarMenu();
    el('library-count-badge').textContent = data.active_count;
    el('drawer-count').textContent = data.active_count;
    const chip = (name, count, active, attrs, hint = '') => {
      count = Math.max(0, Number(count) || 0);
      const label = tr('group_count', { name, count });
      return `<button type="button" class="library-group-chip ${active ? 'is-active' : ''}" aria-pressed="${active}" aria-label="${esc(label)}" title="${esc(hint ? `${label} · ${hint}` : label)}" ${attrs}><span class="library-group-name">${esc(name)}</span><span class="library-group-count">${count}</span></button>`;
    };
    el('library-group-shortcuts').innerHTML = chip(tr('all'), data.active_count, !state.collection_id && !state.topic && !state.trash, 'data-library-view="all"') +
      data.collections.map(group => chip(group.name, group.count, state.collection_id === group.id,
        `data-library-collection="${esc(group.id)}" data-library-drop="${esc(group.id)}"`, `${group.name} · ${tr('drop_hint')}`)).join('') +
      (data.smart_groups || []).map(group => chip(tr(`topic_${group.id}`), group.count, state.topic === group.id,
        `data-library-topic="${esc(group.id)}"`, `${tr(`topic_${group.id}`)} · ${tr('auto_hint')}`)).join('') +
      (state.trash ? chip(tr('trash'), data.trash_count, true, 'data-library-view="trash"') : '');
    el('library-views').innerHTML = `<button class="library-folder ${!state.collection_id && !state.topic && !state.trash ? 'is-active' : ''}" data-library-view="all">${icon('home')}<span>${esc(tr('all'))}</span><small>${data.active_count}</small></button>`;
    el('library-collections').innerHTML = data.collections.map(group => `<div class="library-folder-row">
      <button class="library-folder ${state.collection_id === group.id ? 'is-active' : ''}" data-library-collection="${esc(group.id)}" data-library-drop="${esc(group.id)}" title="${esc(tr('drop_hint'))}">${icon('folder')}<span>${esc(group.name)}</span><small>${group.count}</small></button>
      ${button('trash', tr('delete_named_group', { name: group.name }), `data-library-delete-group="${esc(group.id)}"`)}</div>`).join('');
    el('library-smart-groups').innerHTML = (data.smart_groups || []).length ?
      `<div class="library-auto-label">${icon('spark')}<span>${esc(tr('auto_groups'))}</span></div>` + data.smart_groups.map(group =>
        `<button class="library-folder library-auto-folder ${state.topic === group.id ? 'is-active' : ''}" data-library-topic="${esc(group.id)}" title="${esc(tr('auto_hint'))}">${icon('spark')}<span>${esc(tr(`topic_${group.id}`))}</span><small>${group.count}</small></button>`).join('') : '';
    el('library-destination-menu').innerHTML = data.collections.length ? data.collections.map(group =>
      `<button class="library-folder" data-library-destination="${esc(group.id)}">${icon('folder')}<span>${esc(group.name)}</span></button>`).join('') : `<span class="library-empty-hint">${esc(tr('create_group_first'))}</span>`;
    el('library-list').innerHTML = data.notes.length ? data.notes.map(card).join('') : `<div class="library-empty">${esc(tr('empty_results'))}</div>`;
    el('library-page-label').textContent = data.total ? tr('page_range', {
      start: state.offset + 1, end: state.offset + data.notes.length, total: data.total
    }) : tr('zero_results');
    el('library-prev').disabled = busy || state.offset === 0;
    el('library-next').disabled = busy || state.offset + state.limit >= data.total;
    updateSelection();
  }
  function card(note) {
    const id = esc(note.note_id), title = esc(note.title), videoId = String(note.video_id || '');
    let thumbnail = note.thumbnail || (note.video_type !== 'local' && /^[\w-]{11}$/.test(videoId) ? `https://i.ytimg.com/vi/${videoId}/hqdefault.jpg` : '');
    if (!/^https?:\/\//i.test(thumbnail)) thumbnail = '';
    const tags = [...new Set([...(note.auto_tags || []).map(topic => tr(`topic_${topic}`)), ...(note.auto_keywords || []), ...(note.tags || [])])];
    return `<article class="library-note ${selected.has(note.note_id) ? 'is-selected' : ''}" data-library-note="${id}" draggable="${!state.trash}">
      <label class="library-note-select"><input type="checkbox" data-library-select="${id}" ${selected.has(note.note_id) ? 'checked' : ''} aria-label="${esc(tr('select_named', { title: note.title }))}"></label>
      <div class="library-thumb-wrap"><button class="library-thumb" data-library-open="${id}" aria-label="${title}" ${state.trash ? 'disabled' : ''}>${thumbnail ? `<img src="${esc(thumbnail)}" alt="" loading="lazy" draggable="false">` : icon('video')}</button></div>
      <button class="library-note-body" data-library-open="${id}" ${state.trash ? 'disabled' : ''}>
        <span class="library-note-title">${title}</span><span class="library-note-meta">${esc(note.channel || tr(note.video_type === 'local' ? 'local' : 'youtube'))}${note.has_audiobook ? ' · 🎧' : ''}</span>
        <span class="library-note-tags" title="${esc(tags.join(' · '))}">${tags.slice(0, 3).map(tag => `<span>#${esc(tag)}</span>`).join('')}</span>
        ${note.snippet ? `<span class="library-snippet">${esc(note.snippet)}</span>` : ''}
      </button>${button('more', tr('note_menu', { title: note.title }), `data-library-menu="${id}" aria-haspopup="menu" aria-expanded="false"`)}</article>`;
  }
  function closeNoteMenu() {
    menuAnchor?.setAttribute('aria-expanded', 'false'); menuNoteId = ''; menuAnchor = null;
    el('library-note-menu').classList.add('hidden');
  }
  function showNoteMenu(id, anchor, destinations = false) {
    const note = data.notes.find(item => item.note_id === id); if (!note || busy) return;
    closeNoteMenu(); closeToolbarMenu(); menuNoteId = id; menuAnchor = anchor; anchor.setAttribute('aria-expanded', 'true');
    const menu = el('library-note-menu');
    const item = (symbol, label, attrs) => `<button class="library-menu-item" role="menuitem" ${attrs}>${icon(symbol)}<span>${esc(label)}</span></button>`;
    const attrs = `data-library-note-id="${esc(id)}"`;
    if (destinations) {
      menu.innerHTML = data.collections.length ? data.collections.map(group => item('folder', group.name,
        `data-library-destination="${esc(group.id)}" ${attrs}`)).join('') : `<span class="library-empty-hint">${esc(tr('create_group_first'))}</span>`;
    } else if (state.trash) {
      menu.innerHTML = item('restore', tr('restore'), `data-library-note-action="restore" ${attrs}`) +
        item('erase', tr('purge'), `data-library-note-action="purge" ${attrs}`);
    } else {
      menu.innerHTML = item('video', tr('open_note'), `data-library-open="${esc(id)}"`) +
        item('folderPlus', tr('note_add_group'), `data-library-choose-group="${esc(id)}"`) +
        (state.collection_id ? item('folderMinus', tr('remove_from_collection'), `data-library-note-action="collection_remove" ${attrs}`) : '') +
        item('trash', tr('move_trash'), `data-library-note-action="trash" ${attrs}`);
    }
    menu.classList.remove('hidden');
    positionMenu(menu, anchor);
  }
  function updateSelection() {
    el('library-selection-bar').classList.toggle('hidden', !selected.size);
    el('library-selection-count').textContent = tr('selected', { count: selected.size });
    for (const [id, show] of [['library-add-group-btn', !state.trash], ['library-remove-group-btn', !!state.collection_id && !state.trash],
      ['library-trash-selected', !state.trash], ['library-restore-selected', state.trash], ['library-purge-selected', state.trash]]) el(id).classList.toggle('hidden', !show);
    const onPage = data.notes.filter(note => selected.has(note.note_id)).length;
    el('library-select-page').checked = !!data.notes.length && onPage === data.notes.length;
    el('library-select-page').indeterminate = onPage > 0 && onPage < data.notes.length;
    el('library-select-page').disabled = busy || !data.notes.length;
    el('library-list').querySelectorAll('[data-library-select]').forEach(input => {
      input.checked = selected.has(input.dataset.librarySelect);
      input.closest('.library-note').classList.toggle('is-selected', input.checked);
    });
  }
  async function mutate(operation, notice = tr('saved')) {
    if (busy) return;
    closeNoteMenu(); closeToolbarMenu();
    busy = true; ++requestNumber; controller?.abort(); clearTimeout(searchTimer);
    el('library-drawer').querySelectorAll('input, button').forEach(input => { input.disabled = true; });
    feedback(tr('working'));
    try {
      await operation(); selected.clear(); el('library-destination-menu').classList.add('hidden'); await refresh(notice);
    } catch (error) { feedback(error.message, true); }
    finally {
      busy = false;
      el('library-drawer').querySelectorAll('input, button').forEach(input => { input.disabled = false; }); render();
    }
  }
  function bulk(action, ids = Array.from(selected), collectionId = '') {
    if (!ids.length || busy) return;
    if (ids.length > 500) return feedback(tr('selection_limit'), true);
    if (action === 'purge' && !confirm(tr('confirm_purge', { count: ids.length }))) return;
    if (action === 'trash' && !confirm(tr('confirm_trash', { count: ids.length }))) return;
    if (action === 'collection_remove') collectionId = state.collection_id;
    if (action.startsWith('collection_') && !data.collections.some(group => group.id === collectionId)) return feedback(tr('choose_collection'), true);
    return mutate(async () => {
      await api('/api/library/notes/bulk', 'POST', { note_ids: ids, action, ...(collectionId ? { collection_id: collectionId } : {}) });
      if ((action === 'trash' || action === 'purge') && ids.includes(currentNoteId)) resetTtsPlayerState();
    }, tr(action === 'collection_add' ? 'group_added' : 'saved'));
  }
  function selectView(view, id = '') {
    closeNoteMenu(); closeToolbarMenu();
    Object.assign(state, { collection_id: view === 'collection' ? id : '', topic: view === 'topic' ? id : '',
      trash: view === 'trash', offset: 0, sort: view === 'collection' ? 'collection' : 'newest' });
    selected.clear(); el('library-destination-menu').classList.add('hidden'); refresh();
  }
  async function openNote(id) {
    if (busy || state.trash) return;
    closeNoteMenu(); closeToolbarMenu();
    if (openingNote?.id === id) return openingNote.promise;
    if (!openingNote && currentNoteId === id) return;
    const request = { id }; openingNote = request;
    request.promise = (async () => {
      try {
        await loadSingleSavedNote(id);
        if (openingNote === request && currentNoteId === id) {
          api(`/api/library/notes/${encodeURIComponent(id)}/opened`, 'POST').catch(() => {});
        }
      } catch (error) {
        if (openingNote === request) feedback(error.message, true);
      } finally {
        if (openingNote === request) openingNote = null;
      }
    })();
    return request.promise;
  }
  function dragAllowed(event) { return !busy && (dragIds.length > 0 || Array.from(event.dataTransfer?.types || []).includes(dragType)); }
  function init() {
    const root = el('library-drawer'); if (!root) return;
    root.querySelectorAll('[data-library-icon]').forEach(node => { node.innerHTML = icon(node.dataset.libraryIcon); });
    const localizeIcons = () => root.querySelectorAll('button[data-i18n-title]').forEach(node => {
      node.setAttribute('aria-label', t(node.dataset.i18nTitle)); node.title = t(node.dataset.i18nTitle);
    });
    localizeIcons();
    el('library-more-btn').addEventListener('click', () => {
      const menu = el('library-toolbar-menu'), opening = menu.classList.contains('hidden');
      closeNoteMenu(); closeToolbarMenu();
      if (opening) {
        menu.classList.remove('hidden'); el('library-more-btn').setAttribute('aria-expanded', 'true');
        positionMenu(menu, el('library-more-btn'));
      }
    });
    el('library-groups-toggle').addEventListener('click', () => {
      const opening = el('library-folders').classList.contains('hidden');
      closeToolbarMenu(); groupsOpen(opening);
      el(opening ? 'library-close-groups' : 'library-more-btn').focus();
    });
    el('library-close-groups').addEventListener('click', () => {
      groupsOpen(false); el('library-more-btn').focus();
    });
    el('library-new-group-btn').addEventListener('click', () => {
      closeToolbarMenu();
      el('library-create-form').classList.remove('hidden'); el('library-new-name').focus();
    });
    el('library-cancel-create').addEventListener('click', () => {
      el('library-create-form').classList.add('hidden'); el('library-more-btn').focus();
    });
    el('library-search').addEventListener('input', event => {
      closeNoteMenu(); closeToolbarMenu();
      state.q = event.target.value; state.offset = 0; selected.clear(); updateSelection();
      ++requestNumber; controller?.abort(); clearTimeout(searchTimer); searchTimer = setTimeout(() => refresh(), 250);
    });
    el('library-select-page').addEventListener('change', event => {
      for (const note of data.notes) event.target.checked ? selected.add(note.note_id) : selected.delete(note.note_id);
      updateSelection();
    });
    el('library-clear-selection').addEventListener('click', () => { selected.clear(); updateSelection(); el('library-destination-menu').classList.add('hidden'); });
    el('library-add-group-btn').addEventListener('click', () => el('library-destination-menu').classList.toggle('hidden'));
    el('library-prev').addEventListener('click', () => { state.offset = Math.max(0, state.offset - state.limit); refresh(); });
    el('library-next').addEventListener('click', () => { state.offset += state.limit; refresh(); });
    el('library-create-form').addEventListener('submit', event => {
      event.preventDefault(); if (busy) return;
      const input = el('library-new-name'), name = input.value.trim(); if (!name) return;
      mutate(async () => {
        await api('/api/library/collections', 'POST', { name });
        input.value = '';
      }).then(() => {
        if (!el('library-create-form').classList.contains('hidden')) input.focus();
      });
    });
    root.addEventListener('change', event => {
      if (!busy && event.target.dataset.librarySelect) {
        const id = event.target.dataset.librarySelect;
        event.target.checked ? selected.add(id) : selected.delete(id); updateSelection();
      }
    });
    root.addEventListener('click', async event => {
      const target = event.target.closest('button'); if (!target || busy) return;
      const attrs = target.dataset;
      if (attrs.libraryMenu) {
        if (menuNoteId === attrs.libraryMenu) closeNoteMenu(); else showNoteMenu(attrs.libraryMenu, target);
        return;
      }
      if (attrs.libraryChooseGroup) { showNoteMenu(attrs.libraryChooseGroup, menuAnchor, true); return; }
      if (attrs.libraryNoteAction) bulk(attrs.libraryNoteAction, [attrs.libraryNoteId]);
      if (attrs.libraryView) selectView(attrs.libraryView);
      if (attrs.libraryCollection) selectView('collection', attrs.libraryCollection);
      if (attrs.libraryTopic) selectView('topic', attrs.libraryTopic);
      if (attrs.libraryAction) bulk(attrs.libraryAction);
      if (attrs.libraryDestination) bulk('collection_add', attrs.libraryNoteId ? [attrs.libraryNoteId] : Array.from(selected), attrs.libraryDestination);
      if (attrs.libraryDeleteGroup && confirm(tr('confirm_delete_collection'))) mutate(async () => {
        await api(`/api/library/collections/${encodeURIComponent(attrs.libraryDeleteGroup)}`, 'DELETE');
        if (state.collection_id === attrs.libraryDeleteGroup) { state.collection_id = ''; state.sort = 'newest'; state.offset = 0; }
      });
      if (attrs.libraryOpen && (event.detail || 0) < 2) openNote(attrs.libraryOpen);
    });
    root.addEventListener('dblclick', event => {
      const target = event.target.closest('[data-library-open]');
      if (!target?.dataset.libraryOpen || busy || state.trash) return;
      event.preventDefault(); openNote(target.dataset.libraryOpen); toggleDrawer(false);
    });
    root.addEventListener('dragstart', event => {
      const note = event.target.closest('[data-library-note]');
      if (!note || busy || state.trash || !event.dataTransfer) { event.preventDefault(); return; }
      closeNoteMenu(); closeToolbarMenu();
      const id = note.dataset.libraryNote;
      if (!selected.has(id)) { selected.clear(); selected.add(id); }
      dragIds = Array.from(selected);
      if (dragIds.length > 500) { event.preventDefault(); feedback(tr('selection_limit'), true); return; }
      event.dataTransfer.setData(dragType, JSON.stringify({ note_ids: dragIds }));
      event.dataTransfer.effectAllowed = 'copy';
      // Let the browser capture the dragged row before folders/toolbars change its layout.
      setTimeout(() => {
        if (!dragIds.length) return;
        updateSelection(); dragNotice = tr('drag_hint', { count: dragIds.length }); feedback(dragNotice);
      }, 0);
    });
    const allowDrop = event => {
      const folder = event.target.closest('[data-library-drop]'); if (!folder || !dragAllowed(event)) return;
      event.preventDefault(); event.dataTransfer.dropEffect = 'copy'; folder.classList.add('is-drop-target');
    };
    root.addEventListener('dragenter', allowDrop);
    root.addEventListener('dragover', allowDrop);
    root.addEventListener('dragleave', event => {
      const folder = event.target.closest('[data-library-drop]');
      if (folder && !folder.contains(event.relatedTarget)) folder.classList.remove('is-drop-target');
    });
    root.addEventListener('drop', event => {
      const folder = event.target.closest('[data-library-drop]'); if (!folder || !dragAllowed(event)) return;
      event.preventDefault(); folder.classList.remove('is-drop-target');
      try {
        const raw = event.dataTransfer.getData(dragType), ids = raw ? JSON.parse(raw).note_ids : dragIds;
        if (!Array.isArray(ids) || !ids.length || ids.length > 500 || ids.some(id => typeof id !== 'string' || !/^[A-Za-z0-9_-]{1,120}$/.test(id))) throw new Error(tr('invalid_drop'));
        bulk('collection_add', [...new Set(ids)], folder.dataset.libraryDrop);
      } catch (error) { feedback(error.message || tr('invalid_drop'), true); }
      dragIds = [];
    });
    root.addEventListener('dragend', () => {
      dragIds = []; root.querySelectorAll('.is-drop-target').forEach(node => node.classList.remove('is-drop-target'));
      if (dragNotice && el('library-feedback').textContent === dragNotice) feedback();
      dragNotice = '';
    });
    el('library-list').addEventListener('scroll', closeNoteMenu);
    document.addEventListener('click', event => {
      const path = event.composedPath();
      // Submenu rendering detaches the clicked item; the original event path still identifies it.
      if (menuNoteId && !path.some(node => node.id === 'library-note-menu' || node.dataset?.libraryMenu)) closeNoteMenu();
      if (!path.some(node => ['library-toolbar-menu', 'library-more-btn'].includes(node.id))) closeToolbarMenu();
      if (root.getAttribute('aria-hidden') === 'false' && !path.some(node => ['library-drawer', 'library-toggle-btn'].includes(node.id))) {
        toggleDrawer(false, { restoreFocus: false });
      }
    });
    root.addEventListener('keydown', event => {
      const toolbarOpen = !el('library-toolbar-menu').classList.contains('hidden');
      if ((menuNoteId || toolbarOpen) && ['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
        event.preventDefault();
        const items = Array.from(el(menuNoteId ? 'library-note-menu' : 'library-toolbar-menu').querySelectorAll('[role="menuitem"]'));
        const index = items.indexOf(document.activeElement);
        const next = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1 :
          (index + (event.key === 'ArrowUp' ? -1 : 1) + items.length) % items.length;
        items[next]?.focus();
      }
      if (event.key === 'Escape') {
        if (menuNoteId) { const anchor = menuAnchor; closeNoteMenu(); anchor?.focus(); }
        else if (toolbarOpen) { closeToolbarMenu(); el('library-more-btn').focus(); }
      }
    });
    window.addEventListener('tubescholar:lang_change', () => { localizeIcons(); render(); });
  }
  window.StudyLibrary = { refresh };
  document.addEventListener('DOMContentLoaded', init);
})();
