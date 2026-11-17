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
const statisticsActivitySelect = document.getElementById('statisticsActivitySelect');
const activityStatisticsMessage = document.getElementById('activityStatisticsMessage');
const activityStatisticsContent = document.getElementById('activityStatisticsContent');
const activityStatisticsMetrics = document.getElementById('activityStatisticsMetrics');
const attendancePie = document.getElementById('attendancePie');
const attendancePieRate = document.getElementById('attendancePieRate');
const attendanceLegend = document.getElementById('attendanceLegend');
const checkInNav = document.getElementById('checkInNav');
const checkInPanel = document.getElementById('checkInPanel');
const checkInActivitySelect = document.getElementById('checkInActivitySelect');
const checkInSearchForm = document.getElementById('checkInSearchForm');
const checkInSearchInput = document.getElementById('checkInSearchInput');
const checkInSearchButton = document.getElementById('checkInSearchButton');
const startQrScannerButton = document.getElementById('startQrScannerButton');
const stopQrScannerButton = document.getElementById('stopQrScannerButton');
const checkInVideo = document.getElementById('checkInVideo');
const checkInTokenForm = document.getElementById('checkInTokenForm');
const checkInQrTokenInput = document.getElementById('checkInQrToken');
const checkInMessage = document.getElementById('checkInMessage');
const checkInResults = document.getElementById('checkInResults');
const myRegistrationsNav = document.getElementById('myRegistrationsNav');
const myRegistrationsSection = document.getElementById('myRegistrationsSection');
const myRegistrationList = document.getElementById('myRegistrationList');
const myRegistrationMessage = document.getElementById('myRegistrationMessage');
const registrationQrDialog = document.getElementById('registrationQrDialog');
const registrationQrTitle = document.getElementById('registrationQrTitle');
const registrationQrMessage = document.getElementById('registrationQrMessage');
const registrationQrImage = document.getElementById('registrationQrImage');
const adminActivityList = document.getElementById('adminActivityList');
const adminMessage = document.getElementById('adminMessage');
const activityForm = document.getElementById('activityForm');

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
let currentUser = null;
let authMode = 'login';
let activityStatistics = [];
let myRegistrations = [];
let pendingRegistrationActivityId = null;
let registrationQrObjectUrl = null;
let qrMediaStream = null;
let qrDetector = null;
let qrScannerActive = false;

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

function formatDateTime(value) {
  return formatDate(value, {
    year: 'numeric',
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  });
}

function formatDateTimeRange(start, end) {
  if (!start) return formatDateTime(end);
  const formattedStart = formatDateTime(start);
  return end ? `${formattedStart} ~ ${formatDateTime(end)}` : formattedStart;
}

function formatActivityTime(activity) {
  if (activity.ends_at) {
    return formatDateTimeRange(activity.starts_at, activity.ends_at);
  }
  const start = `${formatEventDate(activity.starts_at)} · ${activity.start_time}`;
  return activity.duration ? `${start}（${activity.duration}）` : start;
}

function getRemainingSeats(activity) {
  if (!activity.capacity) return null;
  return Math.max(0, activity.capacity - activity.registered_count);
}

function getStatus(activity) {
  const remaining = getRemainingSeats(activity);
  const now = new Date();
  if (activity.registration_opens_at && new Date(activity.registration_opens_at) > now) {
    return { label: '尚未開放', className: 'is-not-open' };
  }
  if (new Date(activity.registration_deadline) < now) {
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
    createDetail(icons.calendar, formatActivityTime(activity)),
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
    createDetail(icons.calendar, `活動時間：${formatActivityTime(activity)}`),
    createDetail(icons.location, activity.location),
    createDetail(icons.people, `主辦單位：${activity.organizer}`),
    createDetail(icons.people, getRemainingSeats(activity) === null
      ? `目前 ${activity.registered_count} 人報名，名額不限`
      : `目前 ${activity.registered_count} 人報名，尚餘 ${getRemainingSeats(activity)} 個名額`),
    createDetail(
      icons.clock,
      `報名時間：${formatDateTimeRange(
        activity.registration_opens_at,
        activity.registration_deadline
      )}`
    )
  );
  const alreadyRegistered = myRegistrations.some(
    (registration) => registration.activity_id === activity.id
  );
  const isStudent = currentUser?.role === 'student';
  const statusName = getStatus(activity).className;
  const registerButton = createElement(
    'button',
    'button button-primary modal-register',
    alreadyRegistered ? '已報名' : isStudent ? '立即報名' : '登入並報名'
  );
  registerButton.type = 'button';
  registerButton.disabled = alreadyRegistered ||
    statusName === 'is-full' || statusName === 'is-closed' || statusName === 'is-not-open' ||
    Boolean(currentUser && !isStudent);
  if (alreadyRegistered) {
    registerButton.textContent = '已報名';
  } else if (statusName === 'is-closed') {
    registerButton.textContent = '報名已截止';
  } else if (statusName === 'is-not-open') {
    registerButton.textContent = '報名尚未開始';
  } else if (statusName === 'is-full') {
    registerButton.textContent = '活動已額滿';
  } else if (currentUser && !isStudent) {
    registerButton.textContent = '學生帳號才能報名';
  }
  const registrationFeedback = createElement('p', 'modal-register-feedback');
  registrationFeedback.id = 'registrationFeedback';
  registerButton.addEventListener('click', () => {
    if (!currentUser) {
      pendingRegistrationActivityId = activity.id;
      activityDialog.close();
      loginDialog.showModal();
      return;
    }
    registerForActivity(activity, registerButton);
  });

  copy.append(details, registerButton, registrationFeedback);
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

  [activityDialog, loginDialog, registrationQrDialog].forEach((dialog) => {
    dialog.addEventListener('click', (event) => {
      if (event.target === dialog) dialog.close();
    });
  });

  registrationQrDialog.addEventListener('close', () => {
    if (registrationQrObjectUrl) {
      URL.revokeObjectURL(registrationQrObjectUrl);
      registrationQrObjectUrl = null;
    }
    registrationQrImage.removeAttribute('src');
    registrationQrImage.hidden = true;
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
  const isStudent = user?.role === 'student';
  myRegistrationsNav.hidden = !isStudent;
  myRegistrationsSection.hidden = !isStudent;
  const canCheckIn = user?.role === 'admin' || user?.role === 'checkin';
  checkInNav.hidden = !canCheckIn;
  checkInPanel.hidden = !canCheckIn;
  if (!canCheckIn) stopQrScanner();
  if (!isStudent) {
    myRegistrations = [];
    myRegistrationList.replaceChildren();
  }
  if (user) logoutButton.setAttribute('aria-label', `登出 ${user.display_name}`);
}

function setAuthMode(mode) {
  authMode = mode;
  const isRegistering = authMode === 'register';
  displayNameLabel.hidden = !isRegistering;
  displayNameInput.hidden = !isRegistering;
  displayNameInput.required = isRegistering;
  const loginEmailLabel = document.querySelector('label[for="loginEmail"]');
  const loginEmailInput = document.getElementById('loginEmail');
  loginEmailLabel.textContent = isRegistering ? '校內學生信箱' : '信箱';
  loginEmailInput.placeholder = isRegistering
    ? 's學號@ncnu.edu.tw'
    : 'name@example.edu.tw';
  if (isRegistering) {
    loginEmailInput.pattern = 's[0-9]+@ncnu\\.edu\\.tw';
  } else {
    loginEmailInput.removeAttribute('pattern');
  }
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
    if (pendingRegistrationActivityId && currentUser?.role === 'student') {
      const activity = activities.find((item) => item.id === pendingRegistrationActivityId);
      pendingRegistrationActivityId = null;
      if (activity) {
        openActivity(activity);
        const button = activityDialogContent.querySelector('.modal-register');
        if (button && !button.disabled) await registerForActivity(activity, button);
      }
    }
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
    updateCheckInActivityOptions();
    renderCategoryFilters();
    renderActivities();
  } catch (error) {
    console.error(error);
    activityGrid.replaceChildren();
    resultsCount.textContent = '活動資料載入失敗';
    loadError.hidden = false;
  }
}

function updateCheckInActivityOptions() {
  const selectedActivityId = checkInActivitySelect.value;
  checkInActivitySelect.replaceChildren(new Option('請選擇活動', ''));
  activities.forEach((activity) => {
    const option = new Option(
      `${activity.title} · ${formatEventDate(activity.starts_at)}`,
      String(activity.id)
    );
    checkInActivitySelect.add(option);
  });
  if (activities.some((activity) => String(activity.id) === selectedActivityId)) {
    checkInActivitySelect.value = selectedActivityId;
  }
}

function setCheckInMessage(message, isError = false) {
  checkInMessage.textContent = message;
  checkInMessage.classList.toggle('is-error', isError);
}

function renderCheckInResults(registrations) {
  if (!registrations.length) {
    checkInResults.replaceChildren(
      createElement('p', 'admin-empty', '找不到符合條件的報名資料。')
    );
    return;
  }

  const fragment = document.createDocumentFragment();
  registrations.forEach((registration) => {
    const card = createElement('article', 'check-in-result');
    const details = createElement('div', '');
    details.append(
      createElement('h3', '', registration.student_name),
      createElement(
        'p',
        'check-in-result-meta',
        `${registration.activity_title} · Registration ID ${registration.registration_id}`
      ),
      createElement('p', 'check-in-result-meta', registration.student_email),
      createElement(
        'p',
        'check-in-result-meta',
        `報名時間：${formatDate(registration.registered_at, {
          year: 'numeric', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit'
        })}`
      ),
      createElement(
        'p',
        'check-in-identity-note',
        '請先核對本人與校園照片證件，再確認簽到。'
      )
    );

    const action = createElement('div', 'check-in-result-action');
    const alreadyCheckedIn = Boolean(registration.checked_in_at);
    action.append(createElement(
      'span',
      `my-registration-status${alreadyCheckedIn ? ' is-checked-in' : ''}`,
      alreadyCheckedIn
        ? `已簽到 · ${formatDate(registration.checked_in_at, { hour: '2-digit', minute: '2-digit' })}`
        : '尚未簽到'
    ));
    if (!alreadyCheckedIn) {
      const confirmButton = createElement('button', 'button button-primary', '確認本人並簽到');
      confirmButton.type = 'button';
      confirmButton.addEventListener('click', () => confirmCheckIn(registration, confirmButton));
      action.append(confirmButton);
    }
    card.append(details, action);
    fragment.append(card);
  });
  checkInResults.replaceChildren(fragment);
}

async function searchCheckInRegistrations(event) {
  event.preventDefault();
  const activityId = checkInActivitySelect.value;
  if (!activityId) {
    setCheckInMessage('請先選擇活動。', true);
    return;
  }
  checkInSearchButton.disabled = true;
  setCheckInMessage('正在搜尋報名資料...');
  try {
    const query = new URLSearchParams({ activity_id: activityId });
    const search = checkInSearchInput.value.trim();
    if (search) query.set('search', search);
    const results = await apiRequest(`check-in/registrations?${query.toString()}`);
    renderCheckInResults(results);
    setCheckInMessage(`找到 ${results.length} 筆報名資料。`);
  } catch (error) {
    setCheckInMessage(error.message, true);
  } finally {
    checkInSearchButton.disabled = false;
  }
}

async function lookupCheckInQr(token) {
  const activityId = checkInActivitySelect.value;
  if (!activityId) {
    setCheckInMessage('請先選擇活動，再掃描 QR Code。', true);
    return;
  }
  try {
    const registration = await apiRequest('check-in/qr/lookup', {
      method: 'POST',
      body: JSON.stringify({ token, activity_id: Number(activityId) })
    });
    renderCheckInResults([registration]);
    setCheckInMessage('已找到報名資料，請核對本人與校園照片證件。');
  } catch (error) {
    setCheckInMessage(error.message, true);
    checkInResults.replaceChildren();
  }
}

async function confirmCheckIn(registration, button) {
  if (!window.confirm('請確認已核對本人與校園照片證件。現在要完成簽到嗎？')) return;
  button.disabled = true;
  button.textContent = '簽到處理中...';
  try {
    const result = await apiRequest(
      `check-in/registrations/${registration.registration_id}/confirm`,
      { method: 'POST' }
    );
    registration.checked_in_at = result.checked_in_at;
    renderCheckInResults([registration]);
    setCheckInMessage(`${registration.student_name} 已完成簽到。`);
  } catch (error) {
    button.disabled = false;
    button.textContent = '確認本人並簽到';
    if (error.status === 409) {
      try {
        const query = new URLSearchParams({
          activity_id: String(registration.activity_id),
          search: String(registration.registration_id)
        });
        const latest = await apiRequest(`check-in/registrations?${query.toString()}`);
        if (latest.length) renderCheckInResults(latest);
        setCheckInMessage('這筆報名已由其他工作人員完成簽到。');
        return;
      } catch (refreshError) {
        console.error('無法重新載入簽到狀態', refreshError);
      }
    }
    setCheckInMessage(error.message, true);
  }
}

function stopQrScanner() {
  qrScannerActive = false;
  if (qrMediaStream) {
    qrMediaStream.getTracks().forEach((track) => track.stop());
    qrMediaStream = null;
  }
  checkInVideo.pause();
  checkInVideo.srcObject = null;
  checkInVideo.hidden = true;
  startQrScannerButton.hidden = false;
  stopQrScannerButton.hidden = true;
}

async function scanQrFrame() {
  if (!qrScannerActive || !qrMediaStream) return;
  try {
    if (checkInVideo.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) {
      const codes = await qrDetector.detect(checkInVideo);
      const token = codes.find((code) => code.format === 'qr_code')?.rawValue;
      if (token) {
        stopQrScanner();
        checkInQrTokenInput.value = token;
        await lookupCheckInQr(token);
        return;
      }
    }
  } catch (error) {
    stopQrScanner();
    setCheckInMessage('相機掃描失敗，請改用 QR token 貼上查詢。', true);
    return;
  }
  if (qrScannerActive) window.requestAnimationFrame(scanQrFrame);
}

async function startQrScanner() {
  if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
    setCheckInMessage('相機需要 HTTPS 與瀏覽器授權，請使用 QR token 貼上查詢。', true);
    return;
  }
  if (!('BarcodeDetector' in window)) {
    setCheckInMessage('此瀏覽器不支援相機 QR 掃描，請使用 QR token 貼上查詢。', true);
    return;
  }
  try {
    const formats = await BarcodeDetector.getSupportedFormats();
    if (!formats.includes('qr_code')) {
      setCheckInMessage('此瀏覽器不支援 QR Code 格式，請使用 token 貼上查詢。', true);
      return;
    }
    qrDetector = new BarcodeDetector({ formats: ['qr_code'] });
    qrMediaStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: 'environment' } },
      audio: false
    });
    checkInVideo.srcObject = qrMediaStream;
    checkInVideo.hidden = false;
    await checkInVideo.play();
    qrScannerActive = true;
    startQrScannerButton.hidden = true;
    stopQrScannerButton.hidden = false;
    setCheckInMessage('相機已啟動，請將報名 QR Code 對準畫面。');
    window.requestAnimationFrame(scanQrFrame);
  } catch (error) {
    stopQrScanner();
    setCheckInMessage('無法啟動相機，請確認權限或改用 QR token 貼上查詢。', true);
  }
}

function renderMyRegistrations() {
  if (!myRegistrations.length) {
    myRegistrationList.replaceChildren(
      createElement('p', 'admin-empty', '目前尚未報名活動。')
    );
    return;
  }

  const fragment = document.createDocumentFragment();
  myRegistrations.forEach((registration) => {
    const card = createElement('article', 'my-registration-card');
    const details = createElement('div', 'my-registration-details');
    details.append(
      createElement('h3', '', registration.activity_title),
      createElement(
        'p',
        'my-registration-meta',
        `${formatEventDate(registration.starts_at)} · ${formatDate(registration.starts_at, {
          hour: '2-digit', minute: '2-digit'
        })} · ${registration.location}`
      ),
      createElement(
        'p',
        'my-registration-meta',
        `報名時間：${formatDate(registration.registered_at, {
          year: 'numeric', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit'
        })}`
      )
    );
    const checkedIn = Boolean(registration.checked_in_at);
    const statusText = checkedIn
      ? `已簽到 · ${formatDate(registration.checked_in_at, { hour: '2-digit', minute: '2-digit' })}`
      : '已報名';
    const actions = createElement('div', 'my-registration-actions');
    const activityButton = createElement('button', 'button button-outline', '查看活動');
    activityButton.type = 'button';
    activityButton.addEventListener('click', async () => {
      let activity = activities.find((item) => item.id === registration.activity_id);
      if (!activity) {
        await loadActivities();
        activity = activities.find((item) => item.id === registration.activity_id);
      }
      if (activity) openActivity(activity);
      else {
        myRegistrationMessage.textContent = '此活動目前無法顯示詳情。';
      }
    });
    const qrButton = createElement('button', 'button button-primary', '查看 QR Code');
    qrButton.type = 'button';
    qrButton.addEventListener('click', () => showRegistrationQr(registration));
    actions.append(activityButton, qrButton);

    card.append(
      details,
      createElement('span', `my-registration-status${checkedIn ? ' is-checked-in' : ''}`, statusText),
      actions
    );
    fragment.append(card);
  });
  myRegistrationList.replaceChildren(fragment);
}

async function showRegistrationQr(registration) {
  registrationQrTitle.textContent = registration.activity_title;
  registrationQrMessage.textContent = '正在產生專屬 QR Code...';
  registrationQrMessage.classList.remove('is-error');
  registrationQrImage.hidden = true;
  registrationQrDialog.showModal();

  if (registrationQrObjectUrl) {
    URL.revokeObjectURL(registrationQrObjectUrl);
    registrationQrObjectUrl = null;
  }

  try {
    const response = await fetch(
      apiUrl(`registrations/me/${registration.id}/qr`),
      { credentials: 'same-origin', cache: 'no-store' }
    );
    if (!response.ok) {
      let message = `QR Code 載入失敗（HTTP ${response.status}）`;
      try {
        const error = await response.json();
        if (typeof error.detail === 'string') message = error.detail;
      } catch (error) {
        console.error('無法讀取 QR Code 錯誤內容', error);
      }
      throw new Error(message);
    }
    registrationQrObjectUrl = URL.createObjectURL(await response.blob());
    registrationQrImage.src = registrationQrObjectUrl;
    registrationQrImage.hidden = false;
    registrationQrMessage.textContent = '此 QR Code 僅對應你的這筆報名。';
  } catch (error) {
    registrationQrMessage.textContent = error.message;
    registrationQrMessage.classList.add('is-error');
  }
}

async function loadMyRegistrations() {
  if (currentUser?.role !== 'student') return;
  myRegistrationMessage.textContent = '正在載入報名紀錄...';
  myRegistrationMessage.classList.remove('is-error');
  try {
    myRegistrations = await apiRequest('registrations/me');
    myRegistrationMessage.textContent = '';
    renderMyRegistrations();
  } catch (error) {
    myRegistrationMessage.textContent = error.message;
    myRegistrationMessage.classList.add('is-error');
  }
}

async function registerForActivity(activity, button) {
  const feedback = activityDialogContent.querySelector('#registrationFeedback');
  button.disabled = true;
  button.textContent = '報名處理中...';
  feedback.textContent = '';
  feedback.classList.remove('is-error');
  try {
    await apiRequest(`activities/${activity.id}/registrations`, { method: 'POST' });
    button.textContent = '已報名';
    feedback.textContent = '報名成功，已加入「我的報名」。';
    await Promise.all([loadActivities(), loadMyRegistrations()]);
  } catch (error) {
    button.disabled = false;
    button.textContent = '立即報名';
    feedback.textContent = error.message;
    feedback.classList.add('is-error');
    if (error.status === 409) await loadActivities();
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
  activityForm.reset();
  activityForm.elements.category.value = 'talk';
  document.getElementById('activityFormTitle').textContent = '建立草稿活動';
  document.getElementById('saveActivityButton').textContent = '儲存草稿';
  document.getElementById('cancelEditButton').hidden = true;
}

function editActivity(activity) {
  editingActivityId = activity.id;
  activityForm.elements.title.value = activity.title;
  activityForm.elements.category.value = activity.category;
  activityForm.elements.organizer.value = activity.organizer;
  activityForm.elements.starts_at.value = localDateTimeInput(activity.starts_at);
  activityForm.elements.ends_at.value = activity.ends_at
    ? localDateTimeInput(activity.ends_at)
    : '';
  activityForm.elements.registration_opens_at.value = activity.registration_opens_at
    ? localDateTimeInput(activity.registration_opens_at)
    : '';
  activityForm.elements.registration_deadline.value =
    localDateTimeInput(activity.registration_deadline);
  activityForm.elements.location.value = activity.location;
  activityForm.elements.capacity.value = activity.capacity || '';
  activityForm.elements.description.value = activity.description;
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
      `${activity.location} · ${formatActivityTime(activity)}`
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

function renderActivityStatistics() {
  const statistics = activityStatistics.find(
    (item) => String(item.activity_id) === statisticsActivitySelect.value
  );
  if (!statistics) {
    activityStatisticsContent.hidden = true;
    activityStatisticsMetrics.replaceChildren();
    attendanceLegend.replaceChildren();
    return;
  }

  activityStatisticsContent.hidden = false;
  const metrics = [
    ['總報名數', statistics.registration_count],
    ['已簽到', statistics.check_in_count],
    ['未簽到', statistics.not_checked_in_count],
    ['剩餘名額', statistics.remaining_capacity === null ? '不限額' : statistics.remaining_capacity]
  ];
  activityStatisticsMetrics.replaceChildren(...metrics.map(([label, value]) => {
    const item = createElement('div', 'activity-statistic');
    item.append(
      createElement('span', 'activity-statistic-label', label),
      createElement('strong', 'activity-statistic-value', `${value}`)
    );
    return item;
  }));

  const rate = Number(statistics.check_in_rate) || 0;
  attendancePie.style.setProperty('--checked-in-ratio', `${Math.min(100, Math.max(0, rate))}%`);
  attendancePie.setAttribute(
    'aria-label',
    `簽到率 ${rate}%，已簽到 ${statistics.check_in_count} 人，未簽到 ${statistics.not_checked_in_count} 人`
  );
  attendancePieRate.textContent = `${rate}%`;

  const checkedInLegend = createElement('div', 'attendance-legend-item');
  checkedInLegend.append(
    createElement('span', 'attendance-legend-swatch'),
    createElement('span', '', `已簽到 ${statistics.check_in_count} 人`)
  );
  const notCheckedInLegend = createElement('div', 'attendance-legend-item');
  notCheckedInLegend.append(
    createElement('span', 'attendance-legend-swatch is-not-checked-in'),
    createElement('span', '', `未簽到 ${statistics.not_checked_in_count} 人`)
  );
  attendanceLegend.replaceChildren(checkedInLegend, notCheckedInLegend);
}

async function loadActivityStatistics() {
  activityStatisticsMessage.textContent = '正在載入活動統計...';
  activityStatisticsMessage.classList.remove('is-error');
  try {
    activityStatistics = await apiRequest('admin/activities/statistics');
    const selectedId = statisticsActivitySelect.value;
    statisticsActivitySelect.replaceChildren();
    if (!activityStatistics.length) {
      statisticsActivitySelect.add(new Option('目前沒有活動', ''));
      activityStatisticsMessage.textContent = '尚無活動統計資料。';
      activityStatisticsContent.hidden = true;
      return;
    }
    activityStatistics.forEach((item) => {
      statisticsActivitySelect.add(new Option(
        `${item.title} · ${{
          draft: '草稿', approved: '已核准', rejected: '已拒絕', published: '已發布'
        }[item.status] || item.status}`,
        String(item.activity_id)
      ));
    });
    if (activityStatistics.some((item) => String(item.activity_id) === selectedId)) {
      statisticsActivitySelect.value = selectedId;
    }
    activityStatisticsMessage.textContent = '';
    renderActivityStatistics();
  } catch (error) {
    activityStatisticsMessage.textContent = error.message;
    activityStatisticsMessage.classList.add('is-error');
    activityStatisticsContent.hidden = true;
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
    await Promise.all([loadAdminActivities(), loadActivities(), loadActivityStatistics()]);
  } catch (error) {
    setAdminMessage(error.message, true);
  }
}

async function loadAdminAccess() {
  try {
    const user = await apiRequest('auth/me');
    setCurrentUser(user);
    if (user.role === 'student') {
      await loadMyRegistrations();
      return;
    }
    if (user.role === 'checkin') return;
    if (user.role !== 'admin') return;
    adminNav.hidden = false;
    adminPanel.hidden = false;
    await Promise.all([
      loadAdminActivities(),
      loadActivityStatistics()
    ]);
  } catch (error) {
    setCurrentUser(null);
    if (![401, 403, 503].includes(error.status)) {
      console.error('無法載入管理員身分', error);
    }
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
statisticsActivitySelect.addEventListener('change', renderActivityStatistics);
accountForm.addEventListener('submit', submitAccountForm);
authModeToggle.addEventListener('click', () => {
  setAuthMode(authMode === 'login' ? 'register' : 'login');
});
logoutButton.addEventListener('click', logout);
document.querySelector('[data-open-admin]').addEventListener('click', () => {
  adminPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
});
checkInNav.addEventListener('click', () => {
  checkInPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
});
checkInSearchForm.addEventListener('submit', searchCheckInRegistrations);
checkInTokenForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const token = checkInQrTokenInput.value.trim();
  if (!/^[A-Za-z0-9_-]{43}$/.test(token)) {
    setCheckInMessage('QR token 格式不正確。', true);
    return;
  }
  await lookupCheckInQr(token);
});
startQrScannerButton.addEventListener('click', startQrScanner);
stopQrScannerButton.addEventListener('click', stopQrScanner);
myRegistrationsNav.addEventListener('click', async () => {
  if (currentUser?.role !== 'student') {
    loginDialog.showModal();
    return;
  }
  myRegistrationsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
  await loadMyRegistrations();
});
loginDialog.addEventListener('close', () => {
  if (!currentUser) pendingRegistrationActivityId = null;
});
activityForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const values = Object.fromEntries(new FormData(activityForm));
  const payload = {
    ...values,
    capacity: Number(values.capacity),
    starts_at: taipeiDateTime(values.starts_at),
    ends_at: taipeiDateTime(values.ends_at),
    registration_opens_at: taipeiDateTime(values.registration_opens_at),
    registration_deadline: taipeiDateTime(values.registration_deadline),
  };
  if (payload.ends_at <= payload.starts_at) {
    setAdminMessage('活動結束時間必須晚於開始時間。', true);
    return;
  }
  if (payload.registration_opens_at > payload.registration_deadline) {
    setAdminMessage('報名開始時間不可晚於截止時間。', true);
    return;
  }
  if (payload.registration_deadline > payload.starts_at) {
    setAdminMessage('報名截止時間不可晚於活動開始時間。', true);
    return;
  }
  try {
    const path = editingActivityId
      ? `admin/activities/${editingActivityId}`
      : 'admin/activities';
    await apiRequest(path, {
      method: editingActivityId ? 'PUT' : 'POST',
      body: JSON.stringify(payload)
    });
    resetActivityForm();
    setAdminMessage('草稿已儲存。');
    await Promise.all([loadAdminActivities(), loadActivityStatistics()]);
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
Promise.all([loadActivities(), loadAdminAccess()]);
