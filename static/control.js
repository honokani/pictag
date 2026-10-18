// pictag 画面制御
// 表は 画像 × 段落（大kind）の入力欄。入力欄では辞書（使用中の語句）から fzf のように語句を引き出す
'use strict';

const $ = id => document.getElementById(id);

const state = {
    loaded: false,
    projectName: '',
    sections: [],
    rows: [],
    byIndex: new Map(),
    tokenLimit: 507,
    words: [],            // [{section, key, phrase, count}]
    selected: new Set(),  // 行の index
    anchor: null,         // Shift 範囲選択の起点（最後にクリックした行）
    dirty: false,
    editor: null,         // {index, section, td, el}
    suggest: null,        // {el, section, ctx, items, active, moved}
    pending: new Set(),   // 送信中の入力（保存の前に待つ）
};

// ---- 通信 ----

async function getJson(url) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`${url}: ${res.status}`);
    return res.json();
}

async function postJson(url, payload) {
    const res = await fetch(url, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload || {}),
    });
    if (!res.ok) throw new Error(`${url}: ${res.status}`);
    return res.json();
}

function track(promise) {
    state.pending.add(promise);
    promise.finally(() => state.pending.delete(promise));
    return promise;
}

const settled = () => Promise.allSettled([...state.pending]);

// 例外は画面に出す
const guarded = fn => (...args) => fn(...args).catch(e => setStatus(String(e.message || e), 'error'));

// ---- 表示の小物 ----

function escapeHtml(text) {
    return String(text).replace(/[&<>"']/g, ch => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[ch]));
}

function setStatus(message, kind = '') {
    $('status').textContent = message;
    $('status').className = kind;
}

function setDirty(dirty) {
    state.dirty = dirty;
    $('saveButton').textContent = dirty ? '保存 *' : '保存';
    $('saveButton').disabled = !state.loaded;
}

function autosize(el) {
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight + 2}px`;
}

// ---- 入力の解釈（caption_format.py / words.py と同じ規則） ----

function splitPhrases(text) {
    return [...new Set(text.split(',').map(p => p.trim()).filter(Boolean))];
}

function parseLine(line) {
    const body = line.trim().replace(/^-+/, '').trim();
    const colon = body.indexOf(':');
    const key = colon >= 0 ? body.slice(0, colon).trim() : '';
    if (colon >= 0 && key && !key.includes(',')) return {key, phrases: splitPhrases(body.slice(colon + 1))};
    return {key: '', phrases: splitPhrases(body)};
}

const renderInputLine = (key, phrases) => (key ? `${key}: ${phrases.join(', ')}` : phrases.join(', '));

function addPhrase(text, key, phrase) {
    const trimmed = text.replace(/\s+$/, '');
    const lines = trimmed ? trimmed.split('\n') : [];
    const parsed = lines.map(parseLine);
    if (parsed.some(p => p.key === key && p.phrases.includes(phrase))) return text;
    const at = key ? parsed.findIndex(p => p.key === key) : -1;
    if (at < 0) return [...lines, renderInputLine(key, [phrase])].join('\n');
    return [...lines.slice(0, at), renderInputLine(key, [...parsed[at].phrases, phrase]), ...lines.slice(at + 1)].join('\n');
}

// 行末のカンマ・空白と末尾の空行を落とす（候補の確定で付く ", " の後始末）
const tidyInput = text => text.split('\n').map(line => line.replace(/[\s,]+$/, '')).join('\n').replace(/\n+$/, '');

// ---- あいまい検索（打った文字が順に含まれる語句を拾う。連続・語頭の一致を高く） ----

function fuzzyScore(query, text) {
    const q = query.toLowerCase().replace(/\s+/g, '');
    const t = text.toLowerCase();
    if (!q) return 0;
    let score = t.startsWith(query.toLowerCase()) ? 10 : 0;
    let from = 0;
    let prev = -2;
    for (const ch of q) {
        const at = t.indexOf(ch, from);
        if (at < 0) return null;
        const wordStart = at === 0 || /[\s\-_/:,]/.test(t[at - 1]);
        score += 1 + (at === prev + 1 ? 4 : 0) + (wordStart ? 3 : 0);
        prev = at;
        from = at + 1;
    }
    return score - t.length * 0.02;
}

// 入力欄のカーソル位置の文脈（今の行のキー、打ちかけの語句）
function contextOf(el) {
    const value = el.value;
    const caret = el.selectionStart;
    const lineStart = value.lastIndexOf('\n', caret - 1) + 1;
    const lineEndAt = value.indexOf('\n', caret);
    const lineEnd = lineEndAt < 0 ? value.length : lineEndAt;
    const before = value.slice(lineStart, caret);
    const colon = before.indexOf(':');
    const keyPart = colon >= 0 ? before.slice(0, colon).replace(/^\s*-*\s*/, '').trim() : '';
    const hasKey = colon >= 0 && keyPart !== '' && !keyPart.includes(',');
    const segment = Math.max(before.lastIndexOf(','), hasKey ? colon : -1) + 1;
    const raw = before.slice(segment);
    const query = raw.trimStart();
    return {
        key: hasKey ? keyPart : null,
        query,
        queryStart: lineStart + segment + (raw.length - query.length),
        caret,
        restEmpty: value.slice(caret, lineEnd).trim() === '',
        current: parseLine(value.slice(lineStart, lineEnd)).phrases,
    };
}

function keepBest(items) {
    const best = new Map();
    for (const item of items) {
        const prev = best.get(item.label);
        if (!prev || prev.bonus < item.bonus) best.set(item.label, item);
    }
    return [...best.values()];
}

const wordBonus = (w, section) => (w.section === section ? 3 : 0) + Math.log1p(w.count);

// キーのある行: そのキーで使われた語句（打っていなくても使用回数の多い順に出す）
function phraseCandidates(section, ctx) {
    return keepBest(state.words
        .filter(w => w.key === ctx.key && !ctx.current.includes(w.phrase))
        .map(w => ({kind: 'phrase', label: w.phrase, match: w.phrase, phrase: w.phrase, count: w.count, bonus: wordBonus(w, section)})));
}

// 行頭: キー、キー付きの語句、キーなしの文（1文字以上打ったときだけ）
function lineStartCandidates(section, ctx) {
    if (!ctx.query) return [];
    return keepBest(state.words.flatMap(w => {
        const bonus = wordBonus(w, section);
        if (!w.key) return [{kind: 'line', label: w.phrase, match: w.phrase, phrase: w.phrase, count: w.count, bonus}];
        return [
            {kind: 'key', label: `${w.key}:`, match: w.key, key: w.key, count: 0, bonus: bonus + 1},
            {kind: 'keyed', label: `${w.key}: ${w.phrase}`, match: w.phrase, key: w.key, phrase: w.phrase, count: w.count, bonus},
        ];
    }));
}

function candidates(section, ctx) {
    const pool = ctx.key !== null ? phraseCandidates(section, ctx) : lineStartCandidates(section, ctx);
    return pool
        .map(item => ({...item, score: fuzzyScore(ctx.query, item.match)}))
        .filter(item => item.score !== null)
        .sort((a, b) => (b.score + b.bonus) - (a.score + a.bonus))
        .slice(0, 8);
}

function showSuggestions(el, section) {
    const ctx = contextOf(el);
    const items = candidates(section, ctx);
    if (!items.length) {
        hideSuggestions();
        return;
    }
    state.suggest = {el, section, ctx, items, active: 0, moved: false};
    const list = $('suggestions');
    list.innerHTML = items.map((item, i) =>
        `<li role="option" data-i="${i}"${i === 0 ? ' class="active"' : ''}>${escapeHtml(item.label)}` +
        `${item.count ? `<span class="count">${item.count}</span>` : ''}</li>`).join('');
    list.hidden = false;
    const rect = el.getBoundingClientRect();
    const below = rect.bottom + list.offsetHeight <= window.innerHeight;
    list.style.left = `${rect.left}px`;
    list.style.top = `${below ? rect.bottom : Math.max(0, rect.top - list.offsetHeight)}px`;
}

function hideSuggestions() {
    state.suggest = null;
    $('suggestions').hidden = true;
}

function moveActive(step) {
    const s = state.suggest;
    s.active = (s.active + step + s.items.length) % s.items.length;
    s.moved = true;
    [...$('suggestions').children].forEach((li, i) => li.classList.toggle('active', i === s.active));
    $('suggestions').children[s.active].scrollIntoView({block: 'nearest'});
}

function accept(item) {
    const {el, ctx} = state.suggest;
    if (item.kind === 'keyed' && el.tagName === 'TEXTAREA') {
        // 打ちかけの文字を消し、同じキーの行へ足す（無ければ行を足す）
        const without = el.value.slice(0, ctx.queryStart) + el.value.slice(ctx.caret);
        el.value = addPhrase(without.split('\n').filter(line => line.trim()).join('\n'), item.key, item.phrase);
        el.setSelectionRange(el.value.length, el.value.length);
    } else if (item.kind === 'keyed') {
        el.value = `${item.key}: ${item.phrase}`;  // 一括入力は1行
    } else {
        const text = item.kind === 'key' ? `${item.key}: ` : item.phrase + (item.kind === 'phrase' && ctx.restEmpty ? ', ' : '');
        el.setRangeText(text, ctx.queryStart, ctx.caret, 'end');
    }
    el.dispatchEvent(new Event('input'));
}

// 候補が出ているときのキー操作。Enter は打ちかけがあるか ↑↓ で選んだときだけ確定（改行を邪魔しない）
function handleSuggestKey(event) {
    const s = state.suggest;
    if (!s || s.el !== event.target) return false;
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        moveActive(event.key === 'ArrowDown' ? 1 : -1);
    } else if (event.key === 'Tab' || (event.key === 'Enter' && !event.shiftKey && (s.ctx.query || s.moved))) {
        accept(s.items[s.active]);
    } else if (event.key === 'Escape') {
        hideSuggestions();
    } else {
        return false;
    }
    event.preventDefault();
    return true;
}

function refreshWords() {
    clearTimeout(refreshWords.timer);
    refreshWords.timer = setTimeout(() => {
        getJson('/get_dictionary')
            .then(body => { state.words = body.words; })
            .catch(e => console.warn('辞書を読めません', e));
    }, 100);
}

// ---- 表 ----

function headHtml() {
    return [
        '<th>サムネイル</th>',
        '<th>画像 / トークン</th>',
        ...state.sections.map(s =>
            `<th data-section="${escapeHtml(s)}"><span class="section-name" title="ダブルクリックで改名">${escapeHtml(s)}</span>` +
            `<button type="button" class="remove-section" title="この段落を表から外す" aria-label="${escapeHtml(s)} を外す">×</button></th>`),
    ].join('');
}

function metaHtml(row) {
    const known = row.tokens !== null && row.tokens !== undefined;
    const over = known && row.tokens > state.tokenLimit;
    return `<div class="name">${escapeHtml(row['サムネイル'])}</div>` +
        `<div class="tokens${over ? ' over' : ''}" title="${escapeHtml(row.caption || '（空）')}">${known ? row.tokens : '—'} / ${state.tokenLimit}</div>`;
}

const cellHtml = text => `<div class="text">${escapeHtml(text)}</div>`;

function rowHtml(row) {
    const name = row['サムネイル'];
    const classes = [row.is_dead ? 'dead' : '', state.selected.has(row.index) ? 'selected' : ''].filter(Boolean).join(' ');
    const cells = state.sections.map(s => `<td class="cell" data-section="${escapeHtml(s)}">${cellHtml(row.texts[s] || '')}</td>`).join('');
    return `<tr data-index="${row.index}" data-name="${escapeHtml(name)}" class="${classes}">` +
        `<td class="thumb"><img loading="lazy" src="/thumbnail/${encodeURIComponent(name)}" alt=""></td>` +
        `<td class="meta">${metaHtml(row)}</td>${cells}</tr>`;
}

const rowElement = index => $('gridBody').querySelector(`tr[data-index="${index}"]`);

function renderTable() {
    $('gridHead').innerHTML = headHtml();
    $('gridBody').innerHTML = state.rows.map(rowHtml).join('');
    const bulkSection = $('bulkSection').value;  // 描き直しても一括入力の段落は選んだままにする
    $('bulkSection').innerHTML = state.sections.map(s => `<option value="${escapeHtml(s)}">${escapeHtml(s)}</option>`).join('');
    if (state.sections.includes(bulkSection)) $('bulkSection').value = bulkSection;
    $('emptyNote').hidden = state.loaded;
    $('tools').hidden = !state.loaded;
    setDirty(state.dirty);
    updateSelectionInfo();
}

function replaceRow(row) {
    state.byIndex.set(row.index, row);
    state.rows = state.rows.map(r => (r.index === row.index ? row : r));
    const tr = rowElement(row.index);
    if (tr) tr.outerHTML = rowHtml(row);
}

async function refreshTable() {
    commitEdit();
    const body = await getJson('/get_table_data');
    state.sections = body.sections;
    state.rows = body.data;
    state.byIndex = new Map(body.data.map(r => [r.index, r]));
    state.tokenLimit = body.token_limit;
    state.selected = new Set([...state.selected].filter(i => state.byIndex.has(i)));
    if (!state.byIndex.has(state.anchor)) state.anchor = null;
    state.loaded = true;
    renderTable();
    refreshWords();
}

// ---- 入力欄 ----

function startEdit(td) {
    if (state.editor && state.editor.td === td) return;
    commitEdit();
    const index = Number(td.closest('tr').dataset.index);
    const section = td.dataset.section;
    const el = document.createElement('textarea');
    el.value = state.byIndex.get(index).texts[section] || '';
    td.replaceChildren(el);
    state.editor = {index, section, td, el};
    el.addEventListener('input', () => { autosize(el); showSuggestions(el, section); });
    el.addEventListener('keydown', event => {
        if (handleSuggestKey(event)) return;
        if (event.key === 'Escape' || (event.key === 'Enter' && event.ctrlKey)) {
            event.preventDefault();
            commitEdit();
        }
    });
    el.addEventListener('keyup', event => {
        if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) showSuggestions(el, section);
    });
    el.addEventListener('click', () => showSuggestions(el, section));
    el.addEventListener('blur', () => commitEdit());
    autosize(el);
    el.focus();
    el.setSelectionRange(el.value.length, el.value.length);
}

function commitEdit() {
    const editor = state.editor;
    if (!editor) return;
    state.editor = null;
    hideSuggestions();
    const row = state.byIndex.get(editor.index);
    const text = tidyInput(editor.el.value);
    const changed = text !== (row.texts[editor.section] || '');
    row.texts[editor.section] = text;
    editor.td.innerHTML = cellHtml(text);
    if (changed) track(sendText(row, editor.section, text)).catch(e => setStatus(String(e.message || e), 'error'));
}

async function sendText(row, section, text) {
    const res = await postJson('/update_text', {row_index: row.index, section, text});
    if (!res.success) {
        setStatus(`${row['サムネイル']} の入力を反映できませんでした`, 'error');
        return;
    }
    row.caption = res.caption;
    row.tokens = res.tokens;
    const tr = rowElement(row.index);
    if (tr) tr.querySelector('td.meta').innerHTML = metaHtml(row);
    setDirty(true);
    refreshWords();
}

// ---- 行の選択（クリック: その行だけ / Ctrl: 足し引き / Shift: 最後にクリックした行からの範囲） ----

function visibleIndexes() {
    const showDead = $('showDead').checked;
    return state.rows.filter(r => showDead || !r.is_dead).map(r => r.index);
}

function selectRow(index, event) {
    const additive = event.ctrlKey || event.metaKey;
    if (event.shiftKey && state.anchor !== null) {
        const order = visibleIndexes();
        const from = order.indexOf(state.anchor);
        const to = order.indexOf(index);
        const range = from < 0 || to < 0 ? [index] : order.slice(Math.min(from, to), Math.max(from, to) + 1);
        state.selected = new Set(additive ? [...state.selected, ...range] : range);
    } else if (additive) {
        if (state.selected.has(index)) state.selected.delete(index);
        else state.selected.add(index);
        state.anchor = index;
    } else {
        const onlyThis = state.selected.size === 1 && state.selected.has(index);
        state.selected = new Set(onlyThis ? [] : [index]);
        state.anchor = index;
    }
    paintSelection();
}

function paintSelection() {
    for (const tr of $('gridBody').rows) tr.classList.toggle('selected', state.selected.has(Number(tr.dataset.index)));
    updateSelectionInfo();
}

function updateSelectionInfo() {
    $('selectionInfo').textContent = `選択 ${state.selected.size} 行`;
}

// ---- 操作 ----

async function bulkEdit(op) {
    commitEdit();
    const rows = visibleIndexes().filter(i => state.selected.has(i));
    const text = $('bulkText').value.trim();
    if (!rows.length) return setStatus('行を選んでください', 'error');
    if (!text) return setStatus('語句を入力してください', 'error');
    await settled();
    const res = await postJson(op === 'add' ? '/add_phrase' : '/remove_phrase', {rows, section: $('bulkSection').value, text});
    if (!res.success) return setStatus(res.message || '一括入力できませんでした', 'error');
    res.rows.forEach(replaceRow);
    $('bulkText').value = '';
    hideSuggestions();
    setDirty(true);
    refreshWords();
    setStatus(`${rows.length} 行${op === 'add' ? 'に追加' : 'から削除'}しました`, 'ok');
}

async function addSection() {
    const name = $('sectionName').value.trim();
    if (!name) return;
    const res = await postJson('/add_section', {name});
    if (!res.success) return setStatus(res.message, 'error');
    $('sectionName').value = '';
    setDirty(true);
    await refreshTable();
}

async function renameSection(old) {
    const name = window.prompt('新しい段落名', old);
    if (name === null || name.trim() === old) return;
    await settled();
    const res = await postJson('/rename_section', {old, new: name});
    if (!res.success) return setStatus(res.message, 'error');
    setDirty(true);
    await refreshTable();
}

async function removeSection(name) {
    const message = `段落「${name}」を表から外しますか？\nこの段落の入力も消えます（保存しなければ、プロジェクトを開き直すと戻ります）。`;
    if (!window.confirm(message)) return;
    await settled();
    const res = await postJson('/remove_section', {name});
    if (!res.success) return setStatus(res.message, 'error');
    setDirty(true);
    await refreshTable();
}

async function refreshProjects() {
    const body = await getJson('/get_existing_projects');
    const options = body.projects
        .sort((a, b) => a.name.localeCompare(b.name))
        .map(p => `<option value="${escapeHtml(p.name)}" title="${escapeHtml(p.image_path)}">${escapeHtml(p.name)}</option>`);
    $('projectSelect').innerHTML = ['<option value="">選んでください</option>', ...options].join('');
    $('projectSelect').value = state.projectName;
}

const confirmDiscard = () => !state.dirty || window.confirm('保存していない変更があります。破棄して続けますか？');

async function opened(name) {
    state.projectName = name;
    state.selected = new Set();
    state.anchor = null;
    state.dirty = false;
    await refreshTable();
    await refreshProjects();
    setStatus(`「${name}」を開きました（${state.rows.length} 枚）`, 'ok');
}

async function openProject() {
    const name = $('projectSelect').value;
    if (!name) return;
    commitEdit();
    if (!confirmDiscard()) {
        $('projectSelect').value = state.projectName;
        return;
    }
    await settled();
    const res = await postJson('/load_existing_project', {project_name: name});
    if (!res.success) {
        $('projectSelect').value = state.projectName;
        return setStatus(res.message, 'error');
    }
    $('imageDir').value = res.image_dir;
    await opened(name);
}

async function loadDirectory() {
    const dir = $('imageDir').value.trim();
    if (!dir) return setStatus('画像フォルダのパスを入力してください', 'error');
    commitEdit();
    if (!confirmDiscard()) return;
    await settled();
    const res = await postJson('/load_directory', {image_dir: dir});
    if (!res.success) return setStatus(res.message, 'error');
    await opened(dir.replace(/["']/g, '').replace(/[\\/]+$/, '').split(/[\\/]/).pop());
}

async function save() {
    if (!state.loaded) return;
    commitEdit();
    await settled();
    const res = await postJson('/save_data');
    if (!res.success) return setStatus(res.message, 'error');
    state.dirty = false;
    await refreshTable();
    await refreshProjects();
    setStatus('保存しました', 'ok');
}

async function removeDead() {
    if (!window.confirm('削除済み画像の行を完全に削除しますか？（あわせて保存します）')) return;
    commitEdit();
    await settled();
    const res = await postJson('/remove_all_dead');
    if (!res.success) return setStatus(res.message, 'error');
    state.dirty = false;
    await refreshTable();
    setStatus(res.message, 'ok');
}

function toggleDead() {
    const show = $('showDead').checked;
    $('grid').classList.toggle('hide-dead', !show);
    if (!show) {
        const visible = new Set(visibleIndexes());
        state.selected = new Set([...state.selected].filter(i => visible.has(i)));
        paintSelection();
    }
}

function openImage(name) {
    $('imageTitle').textContent = name;
    $('imageFull').src = `/image/${encodeURIComponent(name)}`;
    $('imageDialog').showModal();
}

// ---- つなぎ込み ----

function wire() {
    $('loadButton').addEventListener('click', guarded(loadDirectory));
    $('imageDir').addEventListener('keydown', event => {
        if (event.key === 'Enter') guarded(loadDirectory)();
    });
    $('projectSelect').addEventListener('change', guarded(openProject));
    $('saveButton').addEventListener('click', guarded(save));
    $('removeDeadButton').addEventListener('click', guarded(removeDead));
    $('showDead').addEventListener('change', toggleDead);
    $('sectionForm').addEventListener('submit', event => {
        event.preventDefault();
        guarded(addSection)();
    });
    $('bulkForm').addEventListener('submit', event => {
        event.preventDefault();
        guarded(bulkEdit)(event.submitter ? event.submitter.value : 'add');
    });
    $('bulkText').addEventListener('input', () => showSuggestions($('bulkText'), $('bulkSection').value));
    $('bulkText').addEventListener('keydown', handleSuggestKey);
    $('bulkText').addEventListener('blur', hideSuggestions);

    $('gridBody').addEventListener('click', event => {
        const td = event.target.closest('td');
        if (!td) return;
        const index = Number(td.closest('tr').dataset.index);
        if (td.classList.contains('thumb')) {
            if (event.target.tagName === 'IMG') openImage(td.closest('tr').dataset.name);
        } else if (td.classList.contains('meta')) {
            selectRow(index, event);
        } else if (td.classList.contains('cell') && !td.querySelector('textarea')) {
            startEdit(td);
        }
    });
    $('gridHead').addEventListener('click', event => {
        const button = event.target.closest('.remove-section');
        if (button) guarded(removeSection)(button.closest('th').dataset.section);
    });
    $('gridHead').addEventListener('dblclick', event => {
        const name = event.target.closest('.section-name');
        if (name) guarded(renameSection)(name.closest('th').dataset.section);
    });

    // 候補をクリックしても入力欄のフォーカスを外さない
    $('suggestions').addEventListener('mousedown', event => event.preventDefault());
    $('suggestions').addEventListener('click', event => {
        const li = event.target.closest('li');
        if (li && state.suggest) accept(state.suggest.items[Number(li.dataset.i)]);
    });

    $('imageDialog').addEventListener('click', event => {
        if (event.target === $('imageDialog')) $('imageDialog').close();
    });
    document.addEventListener('keydown', event => {
        if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
            event.preventDefault();
            guarded(save)();
        }
    });
    window.addEventListener('beforeunload', event => {
        if (state.dirty) {
            event.preventDefault();
            event.returnValue = '';
        }
    });
}

wire();
toggleDead();
guarded(refreshProjects)();
