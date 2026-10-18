let currentData = [];
let selectedRows = new Set(); // 選択された行のインデックスを管理

function showStatus(message, isError = false) {
    const statusDiv = document.getElementById('statusMessage');
    statusDiv.className = `alert ${isError ? 'alert-danger' : 'alert-success'}`;
    statusDiv.textContent = message;
    statusDiv.style.display = 'block';
    
    setTimeout(() => {
        statusDiv.style.display = 'none';
    }, 3000);
}

// 画像URL（サムネイル列の値は画像ファイル名）
function thumbnailUrl(imageName) {
    return `/thumbnail/${encodeURIComponent(imageName)}`;
}

function imageUrl(imageName) {
    return `/image/${encodeURIComponent(imageName)}`;
}

function showImageModal(imageName) {
    document.getElementById('modalImage').src = imageUrl(imageName);
    document.getElementById('imageModalTitle').textContent = imageName;
    
    const modal = new bootstrap.Modal(document.getElementById('imageModal'));
    modal.show();
}

function toggleRowSelection(rowIndex, event) {
    if (event.ctrlKey || event.metaKey) {
        // Ctrl/Cmd + クリック: 単一行の選択状態を切り替え
        if (selectedRows.has(rowIndex)) {
            selectedRows.delete(rowIndex);
        } else {
            selectedRows.add(rowIndex);
        }
    } else if (event.shiftKey && selectedRows.size > 0) {
        // Shift + クリック: 範囲選択
        const lastSelected = Math.max(...selectedRows);
        const start = Math.min(rowIndex, lastSelected);
        const end = Math.max(rowIndex, lastSelected);
        
        selectedRows.clear();
        for (let i = start; i <= end; i++) {
            selectedRows.add(i);
        }
    } else {
        // 通常クリック: 単一選択（前の選択をクリア）
        selectedRows.clear();
        selectedRows.add(rowIndex);
    }
    
    updateRowVisualState();
    updateStatusMessage();
}

function updateRowVisualState() {
    const tbody = document.getElementById('tableBody');
    const rows = tbody.querySelectorAll('tr');
    
    rows.forEach((row, index) => {
        if (selectedRows.has(index)) {
            row.classList.add('selected-row');
        } else {
            row.classList.remove('selected-row');
        }
    });
}

function updateStatusMessage() {
    if (selectedRows.size > 1) {
        showStatus(`${selectedRows.size}行選択中`);
    }
}

function handleCheckboxChange(rowIndex, columnName, checked, event) {
    // イベント伝播を停止（行選択を防ぐ）
    event.stopPropagation();
    
    if (selectedRows.size > 1 && selectedRows.has(rowIndex)) {
        // 複数選択時: 選択されている全行を同じ値に変更
        selectedRows.forEach(selectedRowIndex => {
            updateCell(selectedRowIndex, columnName, checked);
            // UIも更新 - 畳まれた列を考慮して正確なカラム位置を特定
            const tbody = document.getElementById('tableBody');
            const rows = tbody.querySelectorAll('tr');
            const targetRow = rows[selectedRowIndex];
            const checkboxes = targetRow.querySelectorAll('input[type="checkbox"]');
            
            // 表示されているカラムのみを対象にして正確な位置を計算
            const visibleColumns = getVisibleColumns();
            const columnIndex = visibleColumns.indexOf(columnName);
            
            if (columnIndex !== -1 && checkboxes[columnIndex]) {
                checkboxes[columnIndex].checked = checked;
            }
        });
        showStatus(`${selectedRows.size}行のカラム「${columnName}」を${checked ? 'True' : 'False'}に変更`);
    } else {
        // 単一行の変更
        updateCell(rowIndex, columnName, checked);
    }
}

function getVisibleColumns() {
    // 現在表示されているカラムの一覧を取得（畳まれた列を除外）
    const visibleColumns = [];
    
    if (window.currentColumnsByKind) {
        const columnsByKind = window.currentColumnsByKind;
        Object.keys(columnsByKind).forEach(kind => {
            if (!hiddenKinds.has(kind)) {
                // 表示されているkindのカラムを追加
                columnsByKind[kind].forEach(col => {
                    visibleColumns.push(col);
                });
            }
        });
    }
    
    return visibleColumns;
}

async function updateTaskUI() {
    const taskSelect = document.getElementById('taskSelect');
    const kindSelect = document.getElementById('kindSelect');
    const kindText = document.getElementById('kindText');
    const captionSelect = document.getElementById('captionSelect');
    const captionText = document.getElementById('captionText');
    const defaultValueToggle = document.getElementById('defaultValueToggle');
    
    const selectedTask = taskSelect.value;
    
    // 全て初期化
    kindSelect.disabled = false;
    kindText.disabled = true;
    captionSelect.disabled = false;
    captionText.disabled = false;
    defaultValueToggle.disabled = false;
    
    switch (selectedTask) {
        case 'column追加':
            // デフォルト状態（変更なし）
            await loadKinds(); // 通常のkind読み込み
            await updateCaptionSelect(); // カラム選択肢を更新
            break;
            
        case 'kind改名':
            // new_kindを除外してkindのみ選択可能
            await loadKindsForRename();
            captionSelect.disabled = true;
            captionText.disabled = true;
            kindText.disabled = false; // 修正: kind改名では kindText を有効化
            kindText.placeholder = '新種別名';
            defaultValueToggle.disabled = true;
            break;
            
        case 'column改名':
            // new_kindを除外してkindのみ選択可能
            await loadKindsForRename();
            kindText.disabled = true;
            captionText.disabled = false;
            captionText.placeholder = '新カラム名';
            defaultValueToggle.disabled = true;
            break;
            
        case 'kind・column両方改名':
            // 両方改名の場合
            await loadKindsForRename();
            kindText.disabled = false; // 新種別名入力を有効
            kindText.placeholder = '新種別名';
            captionText.placeholder = '新カラム名';
            defaultValueToggle.disabled = true;
            break;
            
        case 'column表から削除':
        case 'column全体から削除':
            // new_kindを除外してkindのみ選択可能
            await loadKindsForRename();
            kindText.disabled = true;
            captionText.disabled = true;
            defaultValueToggle.disabled = true;
            break;
    }
}

function updateCaptionText() {
    const captionSelect = document.getElementById('captionSelect');
    const captionText = document.getElementById('captionText');
    const taskSelect = document.getElementById('taskSelect');
    
    const selectedTask = taskSelect.value;
    
    // タスクに応じて制御を変更
    if (selectedTask === 'column追加') {
        // column追加時はnew_column選択時のみテキスト入力可能
        if (captionSelect.value === 'new_column') {
            captionText.disabled = false;
            captionText.placeholder = '新カラム名';
        } else {
            captionText.disabled = true;
            captionText.value = captionSelect.value;
        }
    } else if (selectedTask === 'column改名' || selectedTask === 'kind・column両方改名') {
        // 追加・改名タスクでは常にテキスト入力を有効にする
        captionText.disabled = false;
        if (captionSelect.value && captionSelect.value !== 'new_column') {
            captionText.value = captionSelect.value; // 既存値をコピー
        }
    } else if (captionSelect.value === 'new_column') {
        captionText.disabled = false;
        captionText.placeholder = "新カラム名";
    } else {
        captionText.disabled = true;
        captionText.value = captionSelect.value;
    }
}

async function updateCaptionSelect() {
    const kindSelect = document.getElementById('kindSelect');
    const kindText = document.getElementById('kindText');
    const captionSelect = document.getElementById('captionSelect');
    const taskSelect = document.getElementById('taskSelect');
    
    const selectedKind = kindSelect.value;
    const selectedTask = taskSelect.value;
    
    if (selectedKind === 'new_kind') {
        kindText.disabled = false;
        captionSelect.innerHTML = '<option value="new_column">new_column</option>';
    } else {
        // kind改名タスクの場合は常にkindText入力を有効にする
        if (selectedTask === 'kind改名' || selectedTask === 'kind・column両方改名') {
            kindText.disabled = false;
        } else {
            kindText.disabled = true;
        }
        
        // タスクに応じて処理分岐
        if (selectedTask === 'column追加') {
            // column追加時は表にないカラムのみ表示
            await loadCaptionsForAdd(selectedKind);
        } else if (selectedTask === 'column改名' || selectedTask === 'column表から削除' || selectedTask === 'kind・column両方改名') {
            // 表にあるカラムのみ表示
            await loadCaptionsForRename();
        } else if (selectedTask === 'column全体から削除') {
            // 全カラム表示（表になくても削除可能）
            await loadCaptionsByKind(selectedKind);
        } else if (selectedTask === 'kind改名') {
            // kind改名の場合はカラム選択不要
            captionSelect.innerHTML = '';
        } else {
            await loadCaptionsByKind(selectedKind);
        }
    }
}

async function loadKinds() {
    try {
        const response = await fetch('/get_kinds');
        const result = await response.json();
        
        const kindSelect = document.getElementById('kindSelect');
        kindSelect.innerHTML = '';
        
        result.kinds.forEach(kind => {
            const option = document.createElement('option');
            option.value = kind;
            option.textContent = kind;
            kindSelect.appendChild(option);
        });
        
        await updateCaptionSelect();
    } catch (error) {
        console.error('Error loading kinds:', error);
    }
}

async function loadKindsForRename() {
    try {
        const response = await fetch('/get_kinds');
        const result = await response.json();
        
        const kindSelect = document.getElementById('kindSelect');
        kindSelect.innerHTML = '';
        
        // new_kindを除外
        const filteredKinds = result.kinds.filter(kind => kind !== 'new_kind');
        
        filteredKinds.forEach(kind => {
            const option = document.createElement('option');
            option.value = kind;
            option.textContent = kind;
            kindSelect.appendChild(option);
        });
        
        await updateCaptionSelect();
    } catch (error) {
        console.error('Error loading kinds for rename:', error);
    }
}

async function loadCaptionsByKind(kind) {
    try {
        const response = await fetch(`/get_captions_by_kind/${kind}`);
        const result = await response.json();
        
        const captionSelect = document.getElementById('captionSelect');
        captionSelect.innerHTML = '';
        
        // new_columnを除外してリスト作成
        const filteredCaptions = result.captions.filter(caption => caption !== 'new_column');
        
        filteredCaptions.forEach(caption => {
            const option = document.createElement('option');
            option.value = caption;
            option.textContent = caption;
            captionSelect.appendChild(option);
        });
        
        updateCaptionText();
    } catch (error) {
        console.error('Error loading captions:', error);
    }
}

async function loadCaptionsForAdd(kind) {
    if (kind === 'new_kind') {
        // new_kind選択時はnew_columnのみ
        const captionSelect = document.getElementById('captionSelect');
        captionSelect.innerHTML = '<option value="new_column">new_column</option>';
        updateCaptionText();
        return;
    }
    
    try {
        // 全カラム情報を取得
        const response = await fetch(`/get_captions_by_kind/${kind}`);
        const result = await response.json();
        
        // 現在のテーブルカラム情報を取得
        const tableResponse = await fetch(`/get_table_captions_by_kind/${kind}`);
        const tableResult = await tableResponse.json();
        
        const captionSelect = document.getElementById('captionSelect');
        captionSelect.innerHTML = '<option value="new_column">new_column</option>';
        
        // 全カラムから表にあるカラムを除外（表に存在しないカラムのみ追加）
        const allCaptions = result.captions.filter(caption => caption !== 'new_column');
        const tableCaptions = tableResult.captions.filter(caption => caption !== 'new_column');
        const notInTableCaptions = allCaptions.filter(caption => !tableCaptions.includes(caption));
        
        notInTableCaptions.forEach(caption => {
            const option = document.createElement('option');
            option.value = caption;
            option.textContent = caption;
            captionSelect.appendChild(option);
        });
        
        updateCaptionText();
    } catch (error) {
        console.error('Error loading captions for add:', error);
        // エラー時はnew_columnのみ
        const captionSelect = document.getElementById('captionSelect');
        captionSelect.innerHTML = '<option value="new_column">new_column</option>';
        updateCaptionText();
    }
}

async function loadCaptionsForRename() {
    const kindSelect = document.getElementById('kindSelect');
    const taskSelect = document.getElementById('taskSelect');
    const selectedKind = kindSelect.value;
    const selectedTask = taskSelect.value;
    
    if (!selectedKind) return;
    
    try {
        // タスクに応じてAPIを使い分け
        let apiUrl;
        if (selectedTask === 'column表から削除' || selectedTask === 'column改名') {
            // 表から削除・改名の場合は表内カラムのみ
            apiUrl = `/get_table_captions_by_kind/${selectedKind}`;
        } else {
            // その他の場合は全カラム
            apiUrl = `/get_captions_by_kind/${selectedKind}`;
        }
        
        const response = await fetch(apiUrl);
        const result = await response.json();
        
        const captionSelect = document.getElementById('captionSelect');
        captionSelect.innerHTML = '';
        
        // new_columnを除外
        const filteredCaptions = result.captions.filter(caption => caption !== 'new_column');
        
        filteredCaptions.forEach(caption => {
            const option = document.createElement('option');
            option.value = caption;
            option.textContent = caption;
            captionSelect.appendChild(option);
        });
        
        updateCaptionText();
    } catch (error) {
        console.error('Error loading captions for rename:', error);
    }
}

async function loadExistingProjects() {
    try {
        console.log('Loading existing projects...');
        const response = await fetch('/get_existing_projects');
        const result = await response.json();
        
        console.log('Projects response:', result);
        
        const select = document.getElementById('existingProjects');
        select.innerHTML = '<option value="">-- 既存プロジェクトを選択 --</option>';
        
        if (result.projects && result.projects.length > 0) {
            result.projects.forEach(project => {
                console.log('Adding project:', project);
                const option = document.createElement('option');
                option.value = project.name;
                option.textContent = `${project.name} (${project.image_path})`;
                select.appendChild(option);
            });
            console.log(`Added ${result.projects.length} projects to select`);
        } else {
            console.log('No projects found');
            showStatus('既存プロジェクトが見つかりませんでした');
        }
    } catch (error) {
        console.error('Error loading projects:', error);
        showStatus('プロジェクト一覧取得エラー: ' + error.message, true);
    }
}

async function loadExistingProject() {
    const select = document.getElementById('existingProjects');
    const projectName = select.value;
    
    if (!projectName) return;
    
    try {
        const response = await fetch('/load_existing_project', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({project_name: projectName})
        });
        
        const result = await response.json();
        if (result.success) {
            document.getElementById('imageDir').value = result.image_dir;
            showStatus('プロジェクトを読み込みました');
            await refreshTable();
        } else {
            showStatus(result.message, true);
        }
    } catch (error) {
        showStatus('プロジェクト読み込みエラー: ' + error.message, true);
    }
}

async function loadDirectory() {
    const imageDir = document.getElementById('imageDir').value;
    if (!imageDir) {
        showStatus('ディレクトリパスを入力してください', true);
        return;
    }
    
    try {
        const response = await fetch('/load_directory', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({image_dir: imageDir})
        });
        
        const result = await response.json();
        if (result.success) {
            showStatus('ディレクトリを読み込みました');
            await refreshTable();
        } else {
            showStatus(result.message, true);
        }
    } catch (error) {
        showStatus('エラーが発生しました: ' + error.message, true);
    }
}

async function refreshTable() {
    try {
        console.log('refreshTable: Starting table refresh...');
        const response = await fetch('/get_table_data');
        const data = await response.json();
        
        console.log('refreshTable: Received data:', data);
        currentData = data.data;
        await renderTable(data.columns, data.data);
        console.log('refreshTable: Table refresh completed');
    } catch (error) {
        console.error('refreshTable: Error updating table:', error);
        showStatus('テーブル更新エラー: ' + error.message, true);
    }
}

async function renderTable(columns, data) {
    const headerRow = document.getElementById('tableHeader');
    const tbody = document.getElementById('tableBody');
    
    // 選択状態をクリア
    selectedRows.clear();
    
    // カラムを種別ごとにグループ化して表示
    await renderGroupedTable(columns, data);
}

// kind列の表示/非表示を管理するグローバル変数
let hiddenKinds = new Set();
let isDeadVisible = true; // 削除済み画像の表示状態

function toggleKindColumns(kind) {
    if (hiddenKinds.has(kind)) {
        hiddenKinds.delete(kind);
    } else {
        hiddenKinds.add(kind);
    }
    
    // テーブルを再描画
    refreshTable();
}

function toggleDeadVisibility() {
    isDeadVisible = !isDeadVisible;
    refreshTable();
}

async function renderGroupedTable(columns, data) {
    try {
        const response = await fetch('/get_columns_by_kind');
        const result = await response.json();
        const columnsByKind = result.columns_by_kind;
        
        // グローバル変数に保存
        window.currentColumnsByKind = columnsByKind;
        
        const thead = document.querySelector('#tableHeader').parentNode;
        const tbody = document.getElementById('tableBody');
        
        // ヘッダー部分を完全に初期化
        thead.innerHTML = '';
        
        // 種別ヘッダー行作成
        const kindHeaderRow = document.createElement('tr');
        const orderedColumns = ['idx', 'サムネイル']; // インデックスカラムを追加
        
        // インデックス列の種別ヘッダー（空白）
        const idxKindTh = document.createElement('th');
        idxKindTh.textContent = '\u00A0'; // Non-breaking space
        idxKindTh.style.textAlign = 'center';
        idxKindTh.style.backgroundColor = '#e9ecef';
        idxKindTh.style.borderRight = '1px solid #dee2e6';
        idxKindTh.style.width = '50px';
        idxKindTh.style.minWidth = '50px';
        idxKindTh.style.maxWidth = '50px';
        idxKindTh.classList.add('sticky-header');
        kindHeaderRow.appendChild(idxKindTh);
        
        // サムネイル列の種別ヘッダー（空白）
        const thumbnailKindTh = document.createElement('th');
        thumbnailKindTh.textContent = '\u00A0'; // Non-breaking space
        thumbnailKindTh.style.textAlign = 'center';
        thumbnailKindTh.style.backgroundColor = '#e9ecef';
        thumbnailKindTh.style.borderRight = '2px solid #dee2e6';
        thumbnailKindTh.classList.add('sticky-header');
        kindHeaderRow.appendChild(thumbnailKindTh);
        
        // 各種別のヘッダー
        Object.keys(columnsByKind).forEach(kind => {
            const isHidden = hiddenKinds.has(kind);
            
            if (!isHidden) {
                const kindTh = document.createElement('th');
                kindTh.textContent = kind + ' ▼'; // 表示中
                kindTh.colSpan = columnsByKind[kind].length;
                kindTh.style.textAlign = 'center';
                kindTh.style.backgroundColor = '#e9ecef';
                kindTh.style.borderRight = '2px solid #dee2e6';
                kindTh.style.cursor = 'pointer';
                kindTh.classList.add('sticky-header');
                
                // クリックイベントを追加
                kindTh.addEventListener('click', () => toggleKindColumns(kind));
                
                kindHeaderRow.appendChild(kindTh);
                
                // カラム順序に追加
                orderedColumns.push(...columnsByKind[kind]);
            } else {
                // 非表示時は折りたたまれた表示
                const kindTh = document.createElement('th');
                kindTh.textContent = kind + ' ▶'; // 折りたたまれている
                kindTh.colSpan = 1; // 1列分のみ
                kindTh.style.textAlign = 'center';
                kindTh.style.backgroundColor = '#d6d8db';
                kindTh.style.borderRight = '2px solid #dee2e6';
                kindTh.style.cursor = 'pointer';
                kindTh.style.width = '60px'; // 幅を半分に
                kindTh.style.minWidth = '60px';
                kindTh.style.maxWidth = '60px';
                kindTh.classList.add('sticky-header');
                
                // クリックイベントを追加
                kindTh.addEventListener('click', () => toggleKindColumns(kind));
                
                kindHeaderRow.appendChild(kindTh);
                
                // 折りたたまれた列として1列分のプレースホルダーを追加
                orderedColumns.push(`${kind}_collapsed`);
            }
        });
        
        // カラムヘッダー行作成
        const colHeaderRow = document.createElement('tr');
        colHeaderRow.id = 'tableHeader'; // IDを維持
        
        // インデックス列
        const idxColTh = document.createElement('th');
        idxColTh.textContent = 'idx';
        idxColTh.style.backgroundColor = '#f8f9fa';
        idxColTh.style.borderRight = '1px solid #dee2e6';
        idxColTh.style.width = '50px';
        idxColTh.style.minWidth = '50px';
        idxColTh.style.maxWidth = '50px';
        idxColTh.style.fontSize = '0.7em';
        idxColTh.classList.add('sticky-header');
        colHeaderRow.appendChild(idxColTh);
        
        // サムネイル列
        const thumbnailColTh = document.createElement('th');
        thumbnailColTh.textContent = 'サムネイル';
        thumbnailColTh.style.backgroundColor = '#f8f9fa';
        thumbnailColTh.style.borderRight = '2px solid #dee2e6';
        thumbnailColTh.classList.add('sticky-header');
        colHeaderRow.appendChild(thumbnailColTh);
        
        // 各カラムのヘッダー
        let kindIndex = 0;
        Object.keys(columnsByKind).forEach(kind => {
            const isHidden = hiddenKinds.has(kind);
            const isEvenKind = kindIndex % 2 === 0;
            const headerBgColor = isEvenKind ? '#f8f9fa' : '#e9ecef';
            
            if (!isHidden) {
                columnsByKind[kind].forEach((col, index) => {
                    const colTh = document.createElement('th');
                    colTh.textContent = col;
                    colTh.style.fontSize = '0.7em'; // 2段階下げる：0.9em → 0.7em
                    colTh.style.backgroundColor = headerBgColor;
                    colTh.classList.add('sticky-header');
                    
                    // 種別グループの最後のカラムに境界線を追加
                    if (index === columnsByKind[kind].length - 1) {
                        colTh.style.borderRight = '2px solid #dee2e6';
                    }
                    
                    colHeaderRow.appendChild(colTh);
                });
            } else {
                // 折りたたまれた場合は空のヘッダー
                const colTh = document.createElement('th');
                colTh.textContent = '...';
                colTh.style.fontSize = '0.7em';
                colTh.style.backgroundColor = '#d6d8db';
                colTh.style.borderRight = '2px solid #dee2e6';
                colTh.style.width = '60px'; // 幅を半分に
                colTh.style.minWidth = '60px';
                colTh.style.maxWidth = '60px';
                colTh.classList.add('sticky-header');
                colHeaderRow.appendChild(colTh);
            }
            kindIndex++;
        });
        
        // ヘッダーを追加
        thead.appendChild(kindHeaderRow);
        thead.appendChild(colHeaderRow);
        
        // ボディ作成 - 最初から正しい色を設定
        tbody.innerHTML = '';
        data.forEach((row, index) => {
            // is_deadフラグチェック
            const isDead = row.is_dead || false;
            
            // 削除済み画像の表示/非表示制御
            if (!isDeadVisible && isDead) {
                return; // 削除済み非表示時はスキップ
            }
            
            const tr = document.createElement('tr');
            tr.style.cursor = 'pointer';
            
            // 削除済み行のスタイル適用
            if (isDead) {
                tr.classList.add('dead-row');
            }
            
            // 行クリックイベント
            tr.addEventListener('click', (e) => {
                if (e.target.type !== 'checkbox') {
                    toggleRowSelection(index, e);
                }
            });
            
            // 順序に従ってセル作成
            let currentKindIndex = 0;
            let currentKindColumnCount = 0;
            const kindKeys = Object.keys(columnsByKind);
            
            // 順序に従ってセル作成
            let kindIndexForCells = 0;
            let kindColumnCount = 0;
            const kindKeysForCells = Object.keys(columnsByKind);
            
            orderedColumns.forEach(col => {
                const td = document.createElement('td');
                
                if (col === 'idx') {
                    // インデックス列
                    const idxText = (index+1).toString().padStart(3, '0'); // 3桁0埋め
                    td.textContent = idxText;
                    td.style.textAlign = 'center';
                    td.style.fontSize = '0.8em';
                    td.style.borderRight = '1px solid #dee2e6';
                    td.style.width = '50px';
                    td.style.minWidth = '50px';
                    td.style.maxWidth = '50px';
                    
                    // インデックス列の背景色（削除済みの場合は上書きされる）
                    if (!isDead) {
                        const isEvenRow = index % 2 === 0;
                        const rowBgColor = isEvenRow ? '#fff5f5' : '#fffbf0';
                        td.style.backgroundColor = rowBgColor;
                    }
                    
                } else if (col === 'サムネイル') {
                    const img = document.createElement('img');
                    img.src = thumbnailUrl(row[col]);
                    img.className = 'thumbnail-cell';
                    img.alt = 'thumbnail';

                    img.addEventListener('click', (e) => {
                        e.stopPropagation();
                        showImageModal(row[col]);
                    });

                    td.appendChild(img);
                    td.style.borderRight = '2px solid #dee2e6';
                    
                    // サムネイル列の背景色（削除済みの場合は上書きされる）
                    if (!isDead) {
                        const isEvenRow = index % 2 === 0;
                        const rowBgColor = isEvenRow ? '#fff5f5' : '#fffbf0';
                        td.style.backgroundColor = rowBgColor;
                    }
                    
                } else if (col.endsWith('_collapsed')) {
                    // 折りたたまれたkindの列 - kindインデックスを進める
                    const kindName = col.replace('_collapsed', '');
                    const isEvenKind = kindIndexForCells % 2 === 0;
                    
                    td.textContent = '...';
                    td.style.textAlign = 'center';
                    td.style.borderRight = '2px solid #dee2e6';
                    td.style.width = '60px';
                    td.style.minWidth = '60px';
                    td.style.maxWidth = '60px';
                    td.classList.add('collapsed-column');
                    
                    // 折りたたまれた列も行の色と濃淡を適用（削除済みの場合は上書きされる）
                    if (!isDead) {
                        const isEvenRow = index % 2 === 0;
                        if (isEvenRow) {
                            td.style.backgroundColor = isEvenKind ? '#fff0f0' : '#ffebeb';
                        } else {
                            td.style.backgroundColor = isEvenKind ? '#fffdf0' : '#fffaeb';
                        }
                    }
                    
                    // kindインデックスを次に進める
                    kindIndexForCells++;
                    kindColumnCount = 0;
                    
                } else {
                    // 通常の列
                    // 折りたたまれたkindをスキップしてkindインデックスを調整
                    while (kindIndexForCells < kindKeysForCells.length && 
                           (hiddenKinds.has(kindKeysForCells[kindIndexForCells]) || 
                            kindColumnCount >= columnsByKind[kindKeysForCells[kindIndexForCells]].length)) {
                        if (hiddenKinds.has(kindKeysForCells[kindIndexForCells])) {
                            // 隠されたkindは既にcollapsed列で処理済みなのでスキップ
                            kindIndexForCells++;
                            kindColumnCount = 0;
                        } else {
                            // 通常のkind切り替え
                            kindIndexForCells++;
                            kindColumnCount = 0;
                        }
                    }
                    
                    if (kindIndexForCells < kindKeysForCells.length) {
                        // セルの背景色を最初から正しく設定（削除済みの場合は上書きされる）
                        if (!isDead) {
                            const isEvenRow = index % 2 === 0;
                            const isEvenKind = kindIndexForCells % 2 === 0;
                            
                            if (isEvenRow) {
                                td.style.backgroundColor = isEvenKind ? '#fff0f0' : '#ffebeb';
                            } else {
                                td.style.backgroundColor = isEvenKind ? '#fffdf0' : '#fffaeb';
                            }
                        }
                        
                        // 種別グループの最後のカラムに境界線
                        if (kindColumnCount === columnsByKind[kindKeysForCells[kindIndexForCells]].length - 1) {
                            td.style.borderRight = '2px solid #dee2e6';
                        }
                        
                        const checkbox = document.createElement('input');
                        checkbox.type = 'checkbox';
                        checkbox.checked = row[col] || false;
                        checkbox.onchange = (e) => handleCheckboxChange(index, col, checkbox.checked, e);
                        td.appendChild(checkbox);
                        
                        kindColumnCount++;
                    }
                }
                
                tr.appendChild(td);
            });
            
            tbody.appendChild(tr);
        });
        
    } catch (error) {
        console.error('Error rendering grouped table:', error);
        // フォールバック：通常のテーブル表示
        renderSimpleTable(columns, data);
    }
}

function renderSimpleTable(columns, data) {
    // 元の単純なテーブル表示（フォールバック用）
    const headerRow = document.getElementById('tableHeader');
    const tbody = document.getElementById('tableBody');
    
    selectedRows.clear();
    
    headerRow.innerHTML = '';
    columns.forEach(col => {
        const th = document.createElement('th');
        th.textContent = col;
        headerRow.appendChild(th);
    });
    
    tbody.innerHTML = '';
    data.forEach((row, index) => {
        const tr = document.createElement('tr');
        tr.style.cursor = 'pointer';
        
        tr.addEventListener('click', (e) => {
            if (e.target.type !== 'checkbox') {
                toggleRowSelection(index, e);
            }
        });
        
        columns.forEach(col => {
            const td = document.createElement('td');
            
            if (col === 'サムネイル') {
                const img = document.createElement('img');
                img.src = thumbnailUrl(row[col]);
                img.className = 'thumbnail-cell';
                img.alt = 'thumbnail';

                img.addEventListener('click', (e) => {
                    e.stopPropagation();
                    showImageModal(row[col]);
                });
                
                td.appendChild(img);
            } else {
                const checkbox = document.createElement('input');
                checkbox.type = 'checkbox';
                checkbox.checked = row[col] || false;
                checkbox.onchange = (e) => handleCheckboxChange(index, col, checkbox.checked, e);
                td.appendChild(checkbox);
            }
            
            tr.appendChild(td);
        });
        
        tbody.appendChild(tr);
    });
}

async function updateCell(rowIndex, columnName, value) {
    try {
        const response = await fetch('/update_cell', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                row_index: rowIndex,
                column_name: columnName,
                value: value
            })
        });
        
        const result = await response.json();
        if (!result.success) {
            showStatus('セル更新エラー', true);
        }
    } catch (error) {
        showStatus('セル更新エラー: ' + error.message, true);
    }
}

async function executeTask() {
    const taskSelect = document.getElementById('taskSelect');
    const selectedTask = taskSelect.value;
    
    switch (selectedTask) {
        case 'column追加':
            await addColumn();
            break;
        case 'kind改名':
            await renameKind();
            break;
        case 'column改名':
            await renameColumn();
            break;
        case 'kind・column両方改名':
            await renameBoth();
            break;
        case 'column表から削除':
            await removeFromTable();
            break;
        case 'column全体から削除':
            await removeCompletely();
            break;
        default:
            showStatus('不明なタスクです', true);
    }
}

async function addColumn() {
    const kindSelect = document.getElementById('kindSelect');
    const kindText = document.getElementById('kindText');
    const captionSelect = document.getElementById('captionSelect');
    const captionText = document.getElementById('captionText');
    const defaultValue = document.getElementById('defaultValueToggle').checked;
    
    let kind = kindSelect.value;
    let columnName;
    
    console.log('addColumn: Starting column addition');
    console.log('addColumn: kindSelect.value =', kindSelect.value);
    console.log('addColumn: kindText.value =', kindText.value);
    console.log('addColumn: captionSelect.value =', captionSelect.value);
    console.log('addColumn: captionText.value =', captionText.value);
    
    // 種別の決定
    if (kind === 'new_kind') {
        if (!kindText.value.trim()) {
            showStatus('新しい種別名を入力してください', true);
            return;
        }
        kind = kindText.value.trim();
    }
    
    // カラム名の決定
    if (captionSelect.value === 'new_column') {
        // new_column選択時はテキスト入力から取得
        if (!captionText.value.trim()) {
            showStatus('新しいカラム名を入力してください', true);
            return;
        }
        columnName = captionText.value.trim();
        
        // 空白文字チェック
        if (!columnName || columnName === '') {
            showStatus('空白のキャプション名は使用できません', true);
            return;
        }
    } else {
        // 既存カラム選択時は選択値を使用
        columnName = captionSelect.value;
    }
    
    console.log('addColumn: Final values - kind:', kind, 'columnName:', columnName, 'defaultValue:', defaultValue);
    
    try {
        const response = await fetch('/add_column', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                column_name: columnName,
                kind: kind,
                default_value: defaultValue
            })
        });
        
        const result = await response.json();
        console.log('addColumn: Server response:', result);
        
        if (result.success === true) {  // 明示的に === true で比較
            showStatus(`カラム「${columnName}」(種別: ${kind})を追加しました（初期値：${defaultValue}）`);
            
            // UI初期化
            kindText.value = '';
            captionText.value = '';
            
            // 選択肢更新とテーブル更新を順次実行
            await loadKinds();
            await updateTaskUI(); // タスクUIも更新
            await refreshTable();
        } else {
            console.log('addColumn: Addition failed, result.success =', result.success);
            showStatus('カラム追加に失敗しました: ' + (result.error || '不明なエラー'), true);
        }
    } catch (error) {
        console.error('addColumn: Error:', error);
        showStatus('カラム追加エラー: ' + error.message, true);
    }
}

async function renameKind() {
    const kindSelect = document.getElementById('kindSelect');
    const kindText = document.getElementById('kindText'); // 修正: kindText を使用
    
    const oldKind = kindSelect.value;
    const newKind = kindText.value.trim(); // 修正: kindText から取得
    
    if (!oldKind) {
        showStatus('変更対象の種別を選択してください', true);
        return;
    }
    
    if (!newKind) {
        showStatus('新しい種別名を入力してください', true);
        return;
    }
    
    if (oldKind === newKind) {
        showStatus('同じ種別名です', true);
        return;
    }
    
    try {
        const response = await fetch('/rename_kind', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                old_kind: oldKind,
                new_kind: newKind
            })
        });
        
        const result = await response.json();
        if (result.success) {
            showStatus(`種別「${oldKind}」を「${newKind}」に変更しました`);
            
            // UI初期化
            kindText.value = ''; // 修正: kindText をクリア
            
            // データを保存して確実に永続化
            await saveData();
            
            // 選択肢更新 - 順序を調整して確実に更新
            await loadKindsForRename(); // kind改名では改名用のリストを再読み込み
            await refreshTable();
        } else {
            showStatus('種別名変更に失敗しました', true);
        }
    } catch (error) {
        showStatus('種別名変更エラー: ' + error.message, true);
    }
}

async function renameBoth() {
    const kindSelect = document.getElementById('kindSelect');
    const kindText = document.getElementById('kindText');
    const captionSelect = document.getElementById('captionSelect');
    const captionText = document.getElementById('captionText');
    
    const oldKind = kindSelect.value;
    const newKind = kindText.value.trim();
    const oldColumn = captionSelect.value;
    const newColumn = captionText.value.trim();
    
    if (!oldKind || !oldColumn) {
        showStatus('変更対象の種別とカラムを選択してください', true);
        return;
    }
    
    if (!newKind || !newColumn) {
        showStatus('新しい種別名とカラム名を入力してください', true);
        return;
    }
    
    if (oldKind === newKind && oldColumn === newColumn) {
        showStatus('変更がありません', true);
        return;
    }
    
    try {
        const response = await fetch('/rename_both', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                old_kind: oldKind,
                new_kind: newKind,
                old_column: oldColumn,
                new_column: newColumn
            })
        });
        
        const result = await response.json();
        if (result.success) {
            showStatus(`種別「${oldKind}」→「${newKind}」、カラム「${oldColumn}」→「${newColumn}」に変更しました`);
            
            // UI初期化
            kindText.value = '';
            captionText.value = '';
            
            // データを保存して確実に永続化
            await saveData();
            
            // 選択肢更新とテーブル更新を順次実行
            await loadKindsForRename(); // 改名用のリストを再読み込み
            await refreshTable();
        } else {
            showStatus('両方改名に失敗しました', true);
        }
    } catch (error) {
        showStatus('両方改名エラー: ' + error.message, true);
    }
}

async function renameColumn() {
    const kindSelect = document.getElementById('kindSelect');
    const captionSelect = document.getElementById('captionSelect');
    const captionText = document.getElementById('captionText');
    
    const kind = kindSelect.value;
    const oldColumn = captionSelect.value;
    const newColumn = captionText.value.trim();
    
    if (!kind || !oldColumn) {
        showStatus('変更対象のカラムを選択してください', true);
        return;
    }
    
    if (!newColumn) {
        showStatus('新しいカラム名を入力してください', true);
        return;
    }
    
    if (oldColumn === newColumn) {
        showStatus('同じカラム名です', true);
        return;
    }
    
    try {
        const response = await fetch('/rename_column', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                old_column: oldColumn,
                new_column: newColumn,
                kind: kind
            })
        });
        
        const result = await response.json();
        if (result.success) {
            showStatus(`カラム「${oldColumn}」を「${newColumn}」に変更しました`);
            
            // UI初期化
            captionText.value = '';
            
            // 選択肢更新とテーブル更新を順次実行
            await loadKinds();
            await updateTaskUI(); // タスクUIも更新
            await refreshTable();
        } else {
            showStatus('カラム名変更に失敗しました', true);
        }
    } catch (error) {
        showStatus('カラム名変更エラー: ' + error.message, true);
    }
}

async function removeFromTable() {
    const captionSelect = document.getElementById('captionSelect');
    const captionText = document.getElementById('captionText');
    
    let columnName = captionSelect.value;
    if (columnName === 'new_column') {
        if (!captionText.value.trim()) {
            showStatus('削除するカラム名を指定してください', true);
            return;
        }
        columnName = captionText.value.trim();
    }
    
    try {
        const response = await fetch('/remove_column_from_table', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({column_name: columnName})
        });
        
        const result = await response.json();
        if (result.success) {
            showStatus(`カラム「${columnName}」をテーブルから削除しました`);
            await loadKinds(); // 選択肢も更新
            await updateTaskUI(); // タスクUIも更新
            await refreshTable();
        } else {
            showStatus('テーブルからの削除に失敗しました', true);
        }
    } catch (error) {
        showStatus('削除エラー: ' + error.message, true);
    }
}

async function removeCompletely() {
    const captionSelect = document.getElementById('captionSelect');
    const captionText = document.getElementById('captionText');
    
    let columnName = captionSelect.value;
    if (columnName === 'new_column') {
        if (!captionText.value.trim()) {
            showStatus('削除するカラム名を指定してください', true);
            return;
        }
        columnName = captionText.value.trim();
    }
    
    if (!confirm(`カラム「${columnName}」を完全に削除します。この操作は取り消せません。よろしいですか？`)) {
        return;
    }
    
    try {
        const response = await fetch('/remove_column_completely', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({column_name: columnName})
        });
        
        const result = await response.json();
        if (result.success) {
            showStatus(`カラム「${columnName}」を完全に削除しました`);
            
            // UI初期化
            captionText.value = '';
            
            // 選択肢更新とテーブル更新を順次実行
            await loadKinds();
            await updateTaskUI(); // タスクUIも更新
            await refreshTable();
        } else {
            showStatus('完全削除に失敗しました', true);
        }
    } catch (error) {
        showStatus('削除エラー: ' + error.message, true);
    }
}

async function saveData() {
    try {
        const response = await fetch('/save_data', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'}
        });
        
        const result = await response.json();
        if (result.success) {
            showStatus('データを保存しました');
            // 保存後はサーバー側でload_dataが実行されるため、UI側も更新
            await loadKinds();
            await refreshTable();
        } else {
            showStatus(result.message, true);
        }
    } catch (error) {
        showStatus('保存エラー: ' + error.message, true);
    }
}

async function removeAllDead() {
    const deadCount = currentData.filter(row => row.is_dead === true).length;
    
    if (deadCount === 0) {
        showStatus('削除済み画像がありません', true);
        return;
    }
    
    if (!confirm(`${deadCount}件の削除済み画像を完全に削除します。\nこの操作は取り消せません。\n実行しますか？`)) {
        return;
    }
    
    try {
        const response = await fetch('/remove_all_dead', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'}
        });
        
        const result = await response.json();
        if (result.success) {
            showStatus(result.message);
            await refreshTable();
        } else {
            showStatus(result.message || '削除に失敗しました', true);
        }
    } catch (error) {
        showStatus('削除エラー: ' + error.message, true);
    }
}

// 初期化
document.addEventListener('DOMContentLoaded', async function() {
    // トグルスイッチのラベル更新
    const toggle = document.getElementById('defaultValueToggle');
    const label = document.getElementById('toggleLabel');
    
    toggle.addEventListener('change', function() {
        label.textContent = this.checked ? 'True' : 'False';
    });
    
    // 削除済み表示トグルのイベントリスナー
    const isDeadVisibleToggle = document.getElementById('isDeadVisibleToggle');
    isDeadVisibleToggle.addEventListener('change', function() {
        isDeadVisible = this.checked;
        refreshTable();
    });
    await loadExistingProjects();
    
    // 種別一覧読み込み
    await loadKinds();
    
    // タスクUI初期化
    await updateTaskUI();
    
    // 自動的にテーブルを更新しようとする（データがある場合）
    setTimeout(refreshTable, 500);
});