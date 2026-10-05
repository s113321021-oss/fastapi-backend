const healthBtn = document.getElementById('healthBtn');
const healthResult = document.getElementById('healthResult');
const loadBtn = document.getElementById('loadBtn');
const notesList = document.getElementById('notesList');
const noteForm = document.getElementById('noteForm');
const noteMessage = document.getElementById('noteMessage');

const API_BASE = '/s113321021';

async function fetchJson(url, options = {}) {
  const res = await fetch(`${API_BASE}${url}`, options);
  if (!res.ok) {
    const error = await res.json().catch(() => ({}));
    throw new Error(error.detail || 'Request failed');
  }
  return res.json();
}

healthBtn.addEventListener('click', async () => {
  try {
    const data = await fetchJson('/api/health');
    healthResult.textContent = 'API 狀態: ' + JSON.stringify(data);
  } catch (err) {
    healthResult.textContent = '錯誤: ' + err.message;
  }
});

async function loadNotes() {
  try {
    const data = await fetchJson('/api/notes');
    notesList.innerHTML = '';
    if (!data.length) {
      notesList.innerHTML = '<li>目前沒有筆記</li>';
      return;
    }

    data.forEach((note) => {
      const li = document.createElement('li');
      li.textContent = `${note.id}. ${note.title} - ${note.content}`;
      notesList.appendChild(li);
    });
  } catch (err) {
    notesList.innerHTML = '<li>讀取失敗</li>';
    console.error(err);
  }
}

loadBtn.addEventListener('click', loadNotes);

noteForm.addEventListener('submit', async (event) => {
  event.preventDefault();

  const title = document.getElementById('title').value.trim();
  const content = document.getElementById('content').value.trim();

  try {
    await fetchJson('/api/note', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ title, content })
    });

    noteMessage.textContent = '新增成功';
    noteForm.reset();
    await loadNotes();
  } catch (err) {
    noteMessage.textContent = '新增失敗: ' + err.message;
  }
});

loadNotes();
