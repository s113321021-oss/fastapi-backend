const activityGrid = document.getElementById('activityGrid');
const categoryFilters = document.getElementById('categoryFilters');
const activitySearch = document.getElementById('activitySearch');
const resultsCount = document.getElementById('resultsCount');
const emptyState = document.getElementById('emptyState');
const loadError = document.getElementById('loadError');
const activityDialog = document.getElementById('activityDialog');
const activityDialogContent = document.getElementById('activityDialogContent');
const loginDialog = document.getElementById('loginDialog');
const loginButton = document.querySelector('.login-button');
const logoutButton = document.getElementById('logoutButton');
const accountForm = document.getElementById('accountForm');
const accountSubmitButton = document.getElementById('accountSubmitButton');
const authModeToggle = document.getElementById('authModeToggle');
const loginDescription = document.getElementById('loginDescription');
const displayNameLabel = document.getElementById('displayNameLabel');
const displayNameInput = document.getElementById('displayName');
const loginMessage = document.getElementById('loginMessage');
const adminNav = document.getElementById('adminNav');
const adminPanel = document.getElementById('adminPanel');
const adminActivityList = document.getElementById('adminActivityList');
const adminMessage = document.getElementById('adminMessage');
const activityForm = document.getElementById('activityForm');
const activitySourceSelect = document.getElementById('activitySourceSelect');
const activityImportSource = document.getElementById('activityImportSource');
const activityImportList = document.getElementById('activityImportList');
const activityImportRuns = document.getElementById('activityImportRuns');
const activityImportMessage = document.getElementById('activityImportMessage');
const syncActivityImportsButton = document.getElementById('syncActivityImports');

const categories = [
  { id: 'all', label: '全部活動' },
  { id: 'talk', label: '講座分享' },
  { id: 'workshop', label: '工作坊' },
  { id: 'club', label: '社團活動' },
  { id: 'culture', label: '藝文展演' },
  { id: 'sports', label: '運動休閒' },
  { id: 'career', label: '職涯成長' }
];

const icons = {
  calendar: '▦',
  location: '⌖',
  people: '♧',
  clock: '◷'
};

let activities = [];
let activeCategory = 'all';
let adminActivities = [];
let editingActivityId = null;
let pendingActivityImportId = null;
let currentUser = null;
let authMode = 'login';
let activityImports = [];

function apiUrl(path) {
  return new URL(`api/${path}`, document.baseURI);
}

async function apiRequest(path, options = {}) {
  const response = await fetch(apiUrl(path), {
    credentials: 'same-origin',
    ...options,
    headers: {
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...options.headers
    }
  });
  if (!response.ok) {
    let message = `請求失敗（HTTP ${response.status}）`;
    try {
      const error = await response.json();
      if (typeof error.detail === 'string') message = error.detail;
    } catch (error) {
      console.error('無法讀取 API 錯誤內容', error);
    }
    const requestError = new Error(message);
    requestError.status = response.status;
    throw requestError;
  }
  return response.status === 204 ? null : response.json();
}

function createElement(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function formatDate(value, options) {
  return new Intl.DateTimeFormat('zh-TW', {
    timeZone: 'Asia/Taipei',
    ...options
  }).format(new Date(value));
}

function formatEventDate(value) {
  return formatDate(value, { month: 'long', day: 'numeric', weekday: 'short' });
}

function getRemainingSeats(activity) {
  if (!activity.capacity) return null;
  return Math.max(0, activity.capacity - activity.registered_count);
}

function getStatus(activity) {
  const remaining = getRemainingSeats(activity);
  if (new Date(activity.registration_deadline) < new Date()) {
    return { label: '報名截止', className: 'is-closed' };
  }
  if (remaining === null) return { label: '報名中', className: '' };
  if (remaining === 0) return { label: '已額滿', className: 'is-full' };
  if (remaining <= 8) return { label: '即將額滿', className: 'is-almost-full' };
  return { label: '報名中', className: '' };
}

function createDetail(icon, text) {
  const detail = createElement('div', 'card-detail');
  detail.append(
    createElement('span', 'detail-icon', icon),
    createElement('span', '', text)
  );
  return detail;
}

function createActivityCard(activity) {
  const card = createElement('article', 'activity-card');
  const art = createElement('div', 'card-art');
  art.dataset.theme = activity.theme;

  if (activity.featured) {
    art.append(createElement('span', 'featured-badge', '✦ 編輯精選'));
  }
  art.append(createElement('span', 'card-art-icon', activity.icon));

  const body = createElement('div', 'card-body');
  const meta = createElement('div', 'card-meta-top');
  meta.append(createElement('span', 'category-label', activity.category_label));
  const status = getStatus(activity);
  const statusBadge = createElement(
    'span',
    `event-status ${status.className}`.trim(),
    status.label
  );
  meta.append(statusBadge);

  const title = createElement('h3', '', activity.title);
  const description = createElement('p', 'card-description', activity.description);
  const details = createElement('div', 'card-details');
  details.append(
    createDetail(icons.calendar, `${formatEventDate(activity.starts_at)} · ${activity.start_time}`),
    createDetail(icons.location, activity.location)
  );

  const footer = createElement('div', 'card-footer');
  const seatCount = createElement('span', 'seat-count');
  const remaining = getRemainingSeats(activity);
  if (remaining === null) {
    seatCount.textContent = '名額不限';
  } else {
    const countText = createElement('strong', '', `${remaining}`);
    seatCount.append(countText, document.createTextNode(' 個名額'));
  }
  const action = createElement('button', 'card-action', '查看活動');
  action.type = 'button';
  action.setAttribute('aria-label', `查看活動：${activity.title}`);
  action.addEventListener('click', () => openActivity(activity));
  footer.append(seatCount, action);

  body.append(meta, title, description, details, footer);
  card.append(art, body);
  return card;
}

function renderActivities() {
  const query = activitySearch.value.trim().toLocaleLowerCase();
  const filtered = activities
    .filter((activity) => activeCategory === 'all' || activity.category === activeCategory)
    .filter((activity) => {
      const searchableText = [
        activity.title,
        activity.description,
        activity.category_label,
        activity.location,
        activity.organizer,
        ...activity.tags
      ].join(' ').toLocaleLowerCase();
      return searchableText.includes(query);
    })
    .sort((a, b) => new Date(a.starts_at) - new Date(b.starts_at));

  activityGrid.replaceChildren(...filtered.map(createActivityCard));
  resultsCount.replaceChildren(
    document.createTextNode('找到 '),
    createElement('strong', '', `${filtered.length} 場`),
    document.createTextNode(' 精彩活動')
  );
  emptyState.hidden = filtered.length > 0;
}

function setCategory(category) {
  activeCategory = category;
  document.querySelectorAll('[data-category]').forEach((button) => {
    const selected = button.dataset.category === category;
    button.classList.toggle('is-active', selected && button.classList.contains('nav-link'));
    button.classList.toggle('is-selected', selected && button.classList.contains('filter-chip'));
    if (button.classList.contains('filter-chip')) {
      button.setAttribute('aria-pressed', String(selected));
    }
    if (button.classList.contains('nav-link')) {
      if (selected) button.setAttribute('aria-current', 'page');
      else button.removeAttribute('aria-current');
    }
  });
  renderActivities();
}

function renderCategoryFilters() {
  const fragment = document.createDocumentFragment();
  categories.forEach((category) => {
    const button = createElement('button', 'filter-chip', category.label);
    button.type = 'button';
    button.dataset.category = category.id;
    button.setAttribute('aria-pressed', String(category.id === activeCategory));
    button.addEventListener('click', () => setCategory(category.id));
    fragment.append(button);
  });
  categoryFilters.replaceChildren(fragment);
}

function openActivity(activity) {
  const art = createElement('div', 'modal-art');
  art.dataset.theme = activity.theme;
  art.append(createElement('span', 'card-art-icon', activity.icon));

  const copy = createElement('div', 'modal-copy');
  copy.append(
    createElement('span', 'category-label', activity.category_label),
    createElement('h2', '', activity.title),
    createElement('p', '', activity.description)
  );

  const details = createElement('div', 'modal-details');
  details.append(
    createDetail(icons.calendar, `${formatEventDate(activity.starts_at)} · ${activity.start_time}`),
    createDetail(icons.clock, `活動時間 ${activity.duration || '依公告為準'}`),
    createDetail(icons.location, activity.location),
    createDetail(icons.people, `主辦單位：${activity.organizer}`),
    createDetail(icons.people, getRemainingSeats(activity) === null
      ? `目前 ${activity.registered_count} 人報名，名額不限`
      : `目前 ${activity.registered_count} 人報名，尚餘 ${getRemainingSeats(activity)} 個名額`),
    createDetail(icons.clock, `報名截止：${formatDate(activity.registration_deadline, {
      month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit'
    })}`)
  );
  if (activity.source_url) {
    const sourceLink = createElement('a', 'activity-source-link', '查看原始活動資訊');
    sourceLink.href = activity.source_url;
    sourceLink.target = '_blank';
    sourceLink.rel = 'noopener noreferrer';
    details.append(sourceLink);
  }

  const registerButton = createElement('button', 'button button-primary modal-register', '登入並報名');
  registerButton.type = 'button';
  registerButton.disabled =
    getStatus(activity).className === 'is-full' ||
    getStatus(activity).className === 'is-closed';
  if (getStatus(activity).className === 'is-closed') {
    registerButton.textContent = '報名已截止';
  } else if (getStatus(activity).className === 'is-full') {
    registerButton.textContent = '活動已額滿';
  }
  registerButton.addEventListener('click', () => {
    activityDialog.close();
    loginDialog.showModal();
  });

  copy.append(details, registerButton);
  activityDialogContent.replaceChildren(art, copy);
  activityDialog.showModal();
}

function bindDialogControls() {
  document.querySelectorAll('[data-open-login]').forEach((button) => {
    button.addEventListener('click', () => loginDialog.showModal());
  });

  document.querySelectorAll('[data-close-dialog]').forEach((button) => {
    button.addEventListener('click', () => button.closest('dialog').close());
  });

  [activityDialog, loginDialog].forEach((dialog) => {
    dialog.addEventListener('click', (event) => {
      if (event.target === dialog) dialog.close();
    });
  });
}

function setLoginMessage(message, isError = false) {
  loginMessage.textContent = message;
  loginMessage.classList.toggle('is-error', isError);
}

function setCurrentUser(user) {
  currentUser = user;
  loginButton.hidden = Boolean(user);
  logoutButton.hidden = !user;
  if (user) logoutButton.setAttribute('aria-label', `登出 ${user.display_name}`);
}

function setAuthMode(mode) {
  authMode = mode;
  const isRegistering = authMode === 'register';
  displayNameLabel.hidden = !isRegistering;
  displayNameInput.hidden = !isRegistering;
  displayNameInput.required = isRegistering;
  document.getElementById('loginDialogTitle').textContent = isRegistering
    ? '建立學生帳號'
    : '登入拾光校園';
  loginDescription.textContent = isRegistering
    ? '建立活動報名專用帳號，請勿使用校內 SSO 密碼。'
    : '使用註冊時設定的信箱與密碼登入。';
  accountSubmitButton.textContent = isRegistering ? '建立帳號' : '登入';
  authModeToggle.textContent = isRegistering ? '已有帳號？返回登入' : '建立學生帳號';
  document.getElementById('loginPassword').autocomplete = isRegistering
    ? 'new-password'
    : 'current-password';
  setLoginMessage(isRegistering
    ? '僅接受 s學號@ncnu.edu.tw 格式；密碼至少 12 個字元。'
    : '密碼至少 12 個字元；系統不會使用你的 SSO 密碼。');
}

async function submitAccountForm(event) {
  event.preventDefault();
  accountSubmitButton.disabled = true;
  setLoginMessage(authMode === 'register' ? '正在建立帳號...' : '正在登入...');
  try {
    const values = Object.fromEntries(new FormData(accountForm));
    const path = authMode === 'register' ? 'auth/register' : 'auth/login';
    const user = await apiRequest(path, {
      method: 'POST',
      body: JSON.stringify(values)
    });
    setCurrentUser(user);
    loginDialog.close();
    accountForm.reset();
    setAuthMode('login');
    await loadAdminAccess();
  } catch (error) {
    setLoginMessage(error.message, true);
  } finally {
    accountSubmitButton.disabled = false;
  }
}

async function logout() {
  logoutButton.disabled = true;
  try {
    await apiRequest('auth/logout', { method: 'POST' });
    window.location.reload();
  } catch (error) {
    logoutButton.disabled = false;
    console.error('登出失敗', error);
  }
}

async function loadActivities() {
  loadError.hidden = true;
  activityGrid.replaceChildren();
  resultsCount.textContent = '正在載入活動...';

  try {
    const data = await apiRequest('activities');
    if (!Array.isArray(data)) {
      throw new Error('活動資料格式錯誤：預期活動陣列。');
    }
    activities = data.map((activity) => ({
      ...activity,
      registered_count: activity.registered_count || 0,
      tags: activity.tags || []
    }));
    renderCategoryFilters();
    renderActivities();
  } catch (error) {
    console.error(error);
    activityGrid.replaceChildren();
    resultsCount.textContent = '活動資料載入失敗';
    loadError.hidden = false;
  }
}

function localDateTimeInput(value) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Taipei',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23'
  }).formatToParts(new Date(value));
  const part = Object.fromEntries(parts.map(({ type, value: partValue }) => [type, partValue]));
  return `${part.year}-${part.month}-${part.day}T${part.hour}:${part.minute}`;
}

function taipeiDateTime(value) {
  return new Date(`${value}:00+08:00`).toISOString();
}

function setAdminMessage(message, isError = false) {
  adminMessage.textContent = message;
  adminMessage.classList.toggle('is-error', isError);
}

function resetActivityForm() {
  editingActivityId = null;
  pendingActivityImportId = null;
  activityForm.reset();
  activityForm.elements.category.value = 'talk';
  document.getElementById('activityFormTitle').textContent = '建立草稿活動';
  document.getElementById('saveActivityButton').textContent = '儲存草稿';
  document.getElementById('cancelEditButton').hidden = true;
}

function editActivity(activity) {
  pendingActivityImportId = null;
  editingActivityId = activity.id;
  activityForm.elements.title.value = activity.title;
  activityForm.elements.category.value = activity.category;
  activityForm.elements.organizer.value = activity.organizer;
  activityForm.elements.starts_at.value = localDateTimeInput(activity.starts_at);
  activityForm.elements.registration_deadline.value =
    localDateTimeInput(activity.registration_deadline);
  activityForm.elements.location.value = activity.location;
  activityForm.elements.capacity.value = activity.capacity || '';
  activityForm.elements.duration.value = activity.duration || '';
  activityForm.elements.description.value = activity.description;
  activityForm.elements.source_url.value = activity.source_url || '';
  document.getElementById('activityFormTitle').textContent = '編輯活動草稿';
  document.getElementById('saveActivityButton').textContent = '儲存變更';
  document.getElementById('cancelEditButton').hidden = false;
  activityForm.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function createAdminAction(label, action, activity) {
  const button = createElement('button', 'button button-outline admin-action', label);
  button.type = 'button';
  button.addEventListener('click', () => handleAdminAction(action, activity));
  return button;
}

function renderAdminActivities() {
  const selectedStatus = document.getElementById('adminStatusFilter').value;
  const filtered = adminActivities.filter(
    (activity) => !selectedStatus || activity.status === selectedStatus
  );
  if (!filtered.length) {
    adminActivityList.replaceChildren(
      createElement('p', 'admin-empty', '目前沒有符合條件的活動。')
    );
    return;
  }

  const fragment = document.createDocumentFragment();
  filtered.forEach((activity) => {
    const card = createElement('article', 'admin-activity-card');
    const header = createElement('div', 'admin-activity-header');
    header.append(
      createElement('h3', '', activity.title),
      createElement('span', `admin-status status-${activity.status}`, {
        draft: '草稿',
        approved: '已核准',
        rejected: '已拒絕',
        published: '已發布'
      }[activity.status] || activity.status)
    );
    card.append(header);
    card.append(createElement(
      'p',
      'admin-activity-meta',
      `${activity.location} · ${formatEventDate(activity.starts_at)} ${activity.start_time}`
    ));
    if (activity.review_note) {
      card.append(createElement('p', 'review-note', `審核意見：${activity.review_note}`));
    }

    const actions = createElement('div', 'admin-card-actions');
    if (activity.status !== 'published') {
      actions.append(
        createAdminAction('編輯', 'edit', activity),
        createAdminAction('廢棄', 'discard', activity)
      );
    }
    if (activity.status === 'draft') {
      actions.append(
        createAdminAction('核准', 'approve', activity),
        createAdminAction('拒絕', 'reject', activity)
      );
    }
    if (activity.status === 'approved') {
      actions.append(createAdminAction('發布活動', 'publish', activity));
    }
    if (actions.childElementCount) card.append(actions);
    fragment.append(card);
  });
  adminActivityList.replaceChildren(fragment);
}

async function loadAdminActivities() {
  try {
    adminActivities = await apiRequest('admin/activities');
    renderAdminActivities();
  } catch (error) {
    setAdminMessage(error.message, true);
  }
}

function setActivityImportMessage(message, isError = false) {
  activityImportMessage.textContent = message;
  activityImportMessage.classList.toggle('is-error', isError);
}

function renderActivityImports() {
  if (!activityImports.length) {
    activityImportList.replaceChildren(
      createElement('p', 'admin-empty', '目前沒有公告匯入紀錄。')
    );
    return;
  }

  const fragment = document.createDocumentFragment();
  activityImports.forEach((item) => {
    const row = createElement('article', 'activity-import-row');
    const copy = createElement('div', 'activity-import-copy');
    copy.append(createElement('h4', '', item.title || '未命名公告'));
    copy.append(createElement(
      'p',
      'activity-import-meta',
      `${item.source_name} · 抓取 ${formatDate(item.fetched_at, {
        year: 'numeric', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit'
      })} · ${{
        pending_review: '待檢視',
        draft_created: '已建立草稿',
        ignored: '已忽略'
      }[item.status] || item.status}`
    ));
    const sourceLink = createElement('a', 'activity-import-meta', '開啟官方來源');
    sourceLink.href = item.source_url;
    sourceLink.target = '_blank';
    sourceLink.rel = 'noopener noreferrer';
    copy.append(sourceLink);

    const parsed = item.parsed_data || {};
    const messages = [item.error_message, ...(parsed.parse_errors || [])].filter(Boolean);
    if (messages.length) {
      copy.append(createElement('p', 'activity-import-error', messages.join(' ')));
    }
    const details = [parsed.starts_at, parsed.location, parsed.organizer]
      .filter(Boolean)
      .join(' · ');
    if (details) copy.append(createElement('p', 'activity-import-meta', details));

    const actions = createElement('div', 'activity-import-actions');
    if (item.status === 'pending_review') {
      const draftButton = createElement('button', 'button button-primary', '補齊並建立草稿');
      draftButton.type = 'button';
      draftButton.addEventListener('click', () => prepareActivityImport(item));
      const ignoreButton = createElement('button', 'button button-outline', '忽略');
      ignoreButton.type = 'button';
      ignoreButton.addEventListener('click', () => ignoreActivityImport(item));
      actions.append(draftButton, ignoreButton);
    } else if (item.activity_id) {
      actions.append(createElement('span', 'admin-status status-draft', `草稿 #${item.activity_id}`));
    }
    row.append(copy, actions);
    fragment.append(row);
  });
  activityImportList.replaceChildren(fragment);
}

async function loadActivityImportRuns() {
  try {
    const runs = await apiRequest('admin/activity-import-runs');
    activityImportRuns.replaceChildren(...runs.slice(0, 6).map((run) => {
      const line = createElement(
        'p',
        run.status === 'failed' ? 'activity-import-error' : 'activity-import-meta',
        `${run.source_name} · ${run.status === 'completed' ? '完成' : '失敗'} · ` +
          `${run.items_new} 筆新公告 · ${formatDate(run.finished_at, {
            month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit'
          })}${run.error_message ? ` · ${run.error_message}` : ''}`
      );
      return line;
    }));
  } catch (error) {
    activityImportRuns.replaceChildren();
    setActivityImportMessage(error.message, true);
  }
}

async function loadActivityImports() {
  try {
    activityImports = await apiRequest('admin/activity-imports');
    renderActivityImports();
    await loadActivityImportRuns();
  } catch (error) {
    setActivityImportMessage(error.message, true);
  }
}

async function syncActivityImports() {
  syncActivityImportsButton.disabled = true;
  setActivityImportMessage('正在讀取官方公告...');
  try {
    const result = await apiRequest('admin/activity-imports/sync', {
      method: 'POST',
      body: JSON.stringify({ source_id: activityImportSource.value || null })
    });
    const failed = result.sources.filter((source) => source.status === 'failed');
    const found = result.sources.reduce((total, source) => total + source.items_found, 0);
    const added = result.sources.reduce((total, source) => total + source.items_new, 0);
    setActivityImportMessage(
      failed.length
        ? `找到 ${found} 筆，新增 ${added} 筆；${failed.length} 個來源讀取失敗。`
        : `同步完成：找到 ${found} 筆，新匯入 ${added} 筆。`,
      failed.length > 0 && added === 0
    );
    await loadActivityImports();
  } catch (error) {
    setActivityImportMessage(error.message, true);
  } finally {
    syncActivityImportsButton.disabled = false;
  }
}

function prepareActivityImport(item) {
  resetActivityForm();
  const parsed = item.parsed_data || {};
  activityForm.elements.title.value = parsed.title || item.title || '';
  activityForm.elements.category.value = parsed.category || 'other';
  activityForm.elements.organizer.value = parsed.organizer || item.source_name;
  activityForm.elements.starts_at.value = parsed.starts_at
    ? localDateTimeInput(parsed.starts_at)
    : '';
  activityForm.elements.registration_deadline.value = parsed.registration_deadline
    ? localDateTimeInput(parsed.registration_deadline)
    : '';
  activityForm.elements.location.value = parsed.location || '';
  activityForm.elements.capacity.value = parsed.capacity || '';
  activityForm.elements.duration.value = parsed.duration || '';
  activityForm.elements.description.value = parsed.description || '';
  if (![...activitySourceSelect.options].some((option) => option.value === item.source_url)) {
    activitySourceSelect.add(new Option('匯入公告來源', item.source_url));
  }
  activityForm.elements.source_url.value = item.source_url;
  pendingActivityImportId = item.id;
  document.getElementById('activityFormTitle').textContent = '檢視公告並建立草稿';
  document.getElementById('saveActivityButton').textContent = '建立活動草稿';
  setAdminMessage('請檢查解析結果並補齊必要欄位，再建立草稿。');
  activityForm.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

async function ignoreActivityImport(item) {
  if (!window.confirm(`確定忽略「${item.title}」？`)) return;
  try {
    await apiRequest(`admin/activity-imports/${item.id}/ignore`, { method: 'POST' });
    setActivityImportMessage('公告已忽略。');
    await loadActivityImports();
  } catch (error) {
    setActivityImportMessage(error.message, true);
  }
}

async function handleAdminAction(action, activity) {
  try {
    if (action === 'edit') {
      editActivity(activity);
      return;
    }
    if (action === 'discard' && !window.confirm(`確定廢棄「${activity.title}」？`)) return;
    let path = `admin/activities/${activity.id}`;
    let options = { method: 'DELETE' };
    if (action === 'approve' || action === 'reject') {
      const note = action === 'reject'
        ? window.prompt('請填寫拒絕原因：', '')
        : null;
      if (action === 'reject' && (!note || !note.trim())) return;
      path += '/review';
      options = {
        method: 'POST',
        body: JSON.stringify({ approved: action === 'approve', note })
      };
    } else if (action === 'publish') {
      path += '/publish';
      options = { method: 'POST' };
    }
    await apiRequest(path, options);
    setAdminMessage('活動狀態已更新。');
    await Promise.all([loadAdminActivities(), loadActivities()]);
  } catch (error) {
    setAdminMessage(error.message, true);
  }
}

async function loadAdminAccess() {
  try {
    const user = await apiRequest('auth/me');
    setCurrentUser(user);
    if (user.role !== 'admin') return;
    adminNav.hidden = false;
    adminPanel.hidden = false;
    await Promise.all([loadAdminActivities(), loadActivityImports()]);
  } catch (error) {
    setCurrentUser(null);
    if (![401, 403, 503].includes(error.status)) {
      console.error('無法載入管理員身分', error);
    }
  }
}

async function loadActivitySources() {
  const sourceLinks = document.getElementById('activitySources');
  try {
    const sources = await apiRequest('activity-sources');
    const fragment = document.createDocumentFragment();
    sources.forEach((source) => {
      const link = createElement('a', '', source.name);
      link.href = source.url;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      fragment.append(link);
    });
    sourceLinks.replaceChildren(fragment);
    activitySourceSelect.replaceChildren(new Option('無', ''));
    activityImportSource.replaceChildren(new Option('全部來源', ''));
    sources.forEach((source) => {
      activitySourceSelect.add(new Option(source.name, source.url));
      activityImportSource.add(new Option(source.name, source.id));
    });
  } catch (error) {
    console.error('無法載入活動來源', error);
    sourceLinks.replaceChildren(createElement('span', 'source-load-error', '活動來源載入失敗'));
  }
}

activitySearch.addEventListener('input', renderActivities);
document.querySelectorAll('.nav-link[data-category]').forEach((button) => {
  button.addEventListener('click', () => setCategory(button.dataset.category));
});
document.getElementById('resetFilters').addEventListener('click', () => {
  activitySearch.value = '';
  setCategory('all');
});
document.getElementById('retryLoad').addEventListener('click', loadActivities);
document.getElementById('cancelEditButton').addEventListener('click', resetActivityForm);
document.getElementById('adminStatusFilter').addEventListener('change', renderAdminActivities);
syncActivityImportsButton.addEventListener('click', syncActivityImports);
accountForm.addEventListener('submit', submitAccountForm);
authModeToggle.addEventListener('click', () => {
  setAuthMode(authMode === 'login' ? 'register' : 'login');
});
logoutButton.addEventListener('click', logout);
document.querySelector('[data-open-admin]').addEventListener('click', () => {
  adminPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
});
activityForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const values = Object.fromEntries(new FormData(activityForm));
  const payload = {
    ...values,
    capacity: Number(values.capacity),
    starts_at: taipeiDateTime(values.starts_at),
    registration_deadline: taipeiDateTime(values.registration_deadline),
    source_url: values.source_url || null
  };
  if (payload.registration_deadline > payload.starts_at) {
    setAdminMessage('報名截止時間不可晚於活動開始時間。', true);
    return;
  }
  try {
    const createdFromImport = pendingActivityImportId !== null;
    const path = createdFromImport
      ? `admin/activity-imports/${pendingActivityImportId}/create-draft`
      : editingActivityId
        ? `admin/activities/${editingActivityId}`
        : 'admin/activities';
    await apiRequest(path, {
      method: editingActivityId ? 'PUT' : 'POST',
      body: JSON.stringify(payload)
    });
    resetActivityForm();
    setAdminMessage(createdFromImport ? '公告活動草稿已建立。' : '草稿已儲存。');
    await Promise.all([loadAdminActivities(), loadActivityImports()]);
  } catch (error) {
    setAdminMessage(error.message, true);
  }
});
document.addEventListener('keydown', (event) => {
  if (
    event.key === '/' &&
    !event.ctrlKey &&
    !event.metaKey &&
    !['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)
  ) {
    event.preventDefault();
    activitySearch.focus();
  }
});

bindDialogControls();
setAuthMode('login');
Promise.all([loadActivities(), loadAdminAccess(), loadActivitySources()]);
