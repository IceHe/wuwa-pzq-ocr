const fileInput = document.getElementById("file-input");
const dropzone = document.getElementById("dropzone");
const previewCard = document.getElementById("preview-card");
const previewImage = document.getElementById("preview-image");
const previewName = document.getElementById("preview-name");
const previewOpen = document.getElementById("preview-open");
const zoomButton = document.getElementById("zoom-button");
const clearButton = document.getElementById("clear-button");
const uploaderNicknameInput = document.getElementById("uploader-nickname");
const uploaderEmailInput = document.getElementById("uploader-email");
const uploaderWechatInput = document.getElementById("uploader-wechat");
const uploaderQqInput = document.getElementById("uploader-qq");
const submitButton = document.getElementById("submit-button");
const statusText = document.getElementById("status-text");
const resultFilename = document.getElementById("result-filename");
const userIdText = document.getElementById("user-id-text");
const lockedText = document.getElementById("locked-text");
const tables = document.getElementById("tables");
const originalTable = document.getElementById("original-table");
const newTable = document.getElementById("new-table");
const jsonCard = document.getElementById("json-card");
const jsonOutput = document.getElementById("json-output");
const historyList = document.getElementById("history-list");
const historyStatus = document.getElementById("history-status");
const historyRefresh = document.getElementById("history-refresh");
const historyLatest = document.getElementById("history-latest");
const historyPrev = document.getElementById("history-prev");
const historyNext = document.getElementById("history-next");
const historyPageText = document.getElementById("history-page-text");
const historyPageInput = document.getElementById("history-page-input");
const historyJump = document.getElementById("history-jump");
const imageModal = document.getElementById("image-modal");
const modalImage = document.getElementById("modal-image");
const modalClose = document.getElementById("modal-close");

let currentFile = null;
let previewUrl = null;
let modalOpen = false;
let lastFocusedElement = null;
let recognizer = null;
let selectedHistoryId = null;
let historyOffset = 0;
let historyHasMore = false;

const HISTORY_PAGE_SIZE = 20;

const STAT_NAME_ALIASES = {
  "普攻伤害加成": "普攻",
  "重击伤害加成": "重击",
  "共鸣技能伤害加成": "共鸣技能",
  "共鸣解放伤害加成": "共鸣解放",
};

const STAT_COLOR_CLASS_BY_NAME = {
  "暴击": "stat-crit",
  "暴击伤害": "stat-crit-dmg",
  "攻击": "stat-atk-pct",
  "防御": "stat-def-pct",
  "生命": "stat-hp-pct",
  "攻击固定值": "stat-atk-flat",
  "防御固定值": "stat-def-flat",
  "生命固定值": "stat-hp-flat",
  "共鸣效率": "stat-energy",
  "普攻": "stat-normal",
  "重击": "stat-heavy",
  "共鸣技能": "stat-skill",
  "共鸣解放": "stat-liberation",
};

fileInput.addEventListener("change", (event) => {
  const [file] = event.target.files || [];
  setCurrentFile(file || null);
});

dropzone.addEventListener("dragover", (event) => {
  event.preventDefault();
  dropzone.classList.add("dragover");
});

dropzone.addEventListener("dragleave", () => {
  dropzone.classList.remove("dragover");
});

dropzone.addEventListener("drop", (event) => {
  event.preventDefault();
  dropzone.classList.remove("dragover");
  const [file] = event.dataTransfer.files || [];
  setCurrentFile(file || null);
});

document.addEventListener("paste", async (event) => {
  const items = event.clipboardData?.items || [];
  for (const item of items) {
    if (item.type.startsWith("image/")) {
      const file = item.getAsFile();
      if (file) {
        setCurrentFile(file);
        setStatus("已从剪贴板读取图片");
      }
      return;
    }
  }
});

clearButton.addEventListener("click", () => {
  fileInput.value = "";
  setCurrentFile(null);
  resetResult();
  setStatus("等待上传");
});

previewOpen.addEventListener("click", (event) => {
  event.preventDefault();
  event.stopPropagation();
  openImageModal();
});
zoomButton.addEventListener("click", (event) => {
  event.preventDefault();
  event.stopPropagation();
  openImageModal();
});
modalClose.addEventListener("click", (event) => {
  event.preventDefault();
  closeImageModal();
});
modalImage.addEventListener("click", closeImageModal);
imageModal.addEventListener("click", (event) => {
  if (event.target === imageModal) {
    closeImageModal();
  }
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeImageModal();
  }
});
historyRefresh.addEventListener("click", () => {
  void refreshHistory();
});
historyLatest.addEventListener("click", () => {
  if (historyOffset === 0) {
    return;
  }
  historyOffset = 0;
  void refreshHistory();
});
historyPrev.addEventListener("click", () => {
  if (historyOffset === 0) {
    return;
  }
  historyOffset = Math.max(0, historyOffset - HISTORY_PAGE_SIZE);
  void refreshHistory();
});
historyNext.addEventListener("click", () => {
  if (!historyHasMore) {
    return;
  }
  historyOffset += HISTORY_PAGE_SIZE;
  void refreshHistory();
});
historyJump.addEventListener("click", () => {
  void jumpToHistoryPage();
});
historyPageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    void jumpToHistoryPage();
  }
});

submitButton.addEventListener("click", async () => {
  if (!currentFile) {
    return;
  }

  const fileToUpload = currentFile;
  submitButton.disabled = true;
  setStatus("首次识别可能较慢");

  try {
    const currentRecognizer = getRecognizer();
    const payload = await currentRecognizer.recognizeFile(currentFile, (message) => {
      setStatus(`浏览器本地识别中: ${message}`);
    });
    renderResult(payload);
    if (!shouldSaveRebuildLog(payload)) {
      selectedHistoryId = null;
      setStatus("识别完成，但结果疑似失败，未保存记录", "warning");
      return;
    }
    const saveResponse = await saveRebuildLog(payload);
    selectedHistoryId = saveResponse.id;
    historyOffset = 0;
    if (!saveResponse.duplicated) {
      void uploadRecognizedImage(fileToUpload, saveResponse.id).catch((error) => {
        console.warn("图片上传失败", error);
      });
    }
    await refreshHistory();
    revealSelectedHistory();
    setStatus(
      saveResponse.duplicated
        ? `检测到重复结果，未新增记录，沿用 #${saveResponse.id}`
        : `识别完成，已保存 #${saveResponse.id}`,
      saveResponse.duplicated ? "duplicate" : "success",
    );
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    submitButton.disabled = !currentFile;
  }
});

function getRecognizer() {
  if (recognizer) {
    return recognizer;
  }
  if (!window.WuwaBrowserRecognizer) {
    throw new Error("OCR 脚本加载失败，请刷新页面后重试。");
  }
  recognizer = new window.WuwaBrowserRecognizer();
  return recognizer;
}

function setCurrentFile(file) {
  currentFile = file;
  submitButton.disabled = !file;

  if (previewUrl) {
    URL.revokeObjectURL(previewUrl);
    previewUrl = null;
  }

  if (!file) {
    previewCard.hidden = true;
    previewImage.removeAttribute("src");
    previewName.textContent = "未选择图片";
    closeImageModal();
    return;
  }

  previewUrl = URL.createObjectURL(file);
  previewImage.src = previewUrl;
  previewName.textContent = `${file.name || "clipboard.png"} · ${formatSize(file.size)}`;
  previewCard.hidden = false;
}

function resetResult() {
  resultFilename.textContent = "尚未识别";
  userIdText.textContent = "-";
  lockedText.textContent = "-";
  tables.hidden = true;
  jsonCard.hidden = true;
  jsonCard.open = false;
  originalTable.innerHTML = "";
  newTable.innerHTML = "";
  jsonOutput.textContent = "";
}

function renderResult(payload) {
  const result = payload.result;
  const originalStats = result.original_stats || [];
  const newStats = result.new_stats || [];
  const totalLocked = originalStats.filter((item) => item.is_locked).length;

  resultFilename.textContent = payload.filename || "未命名图片";
  userIdText.textContent = result.user_id || result.user_id_raw || "-";
  lockedText.textContent = String(totalLocked);

  originalTable.innerHTML = buildTable(originalStats, newStats);
  newTable.innerHTML = buildTable(newStats, originalStats);
  tables.hidden = false;

  jsonOutput.textContent = JSON.stringify(payload, null, 2);
  jsonCard.open = false;
  jsonCard.hidden = false;
}

async function saveRebuildLog(payload) {
  const savePayload = buildSavePayload(payload);
  const response = await fetch("./api/rebuild_log", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(savePayload),
  });

  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data.ok) {
    const error = data.error || `HTTP ${response.status}`;
    throw new Error(`保存失败: ${error}`);
  }
  return data;
}

async function uploadRecognizedImage(file, logId) {
  if (!(file instanceof File)) {
    return null;
  }
  if (!Number.isFinite(Number(logId))) {
    return null;
  }

  const formData = new FormData();
  formData.append("image", file, file.name || "clipboard.png");
  formData.append("log_id", String(logId));

  const uploaderInfo = readUploaderInfo();
  if (uploaderInfo.nickname) {
    formData.append("nickname", uploaderInfo.nickname);
  }

  const response = await fetch("./api/rebuild_image", {
    method: "POST",
    body: formData,
  });

  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data.ok) {
    const error = data.error || `HTTP ${response.status}`;
    throw new Error(`图片上传失败: ${error}`);
  }
  return data;
}

function buildSavePayload(payload) {
  return {
    ...payload,
    uploader: readUploaderInfo(),
  };
}

function readUploaderInfo() {
  return {
    nickname: normalizeOptionalText(uploaderNicknameInput?.value),
    email: normalizeOptionalText(uploaderEmailInput?.value),
    wechat: normalizeOptionalText(uploaderWechatInput?.value),
    qq: normalizeOptionalText(uploaderQqInput?.value),
  };
}

function normalizeOptionalText(value) {
  const text = String(value || "").trim();
  return text || "";
}

function hasRecognizedStat(row) {
  return Boolean(row && row.name && row.value);
}

function countRecognizedStats(rows) {
  return (rows || []).filter(hasRecognizedStat).length;
}

function shouldSaveRebuildLog(payload) {
  const result = payload?.result || {};
  const originalRecognized = countRecognizedStats(result.original_stats);
  const newRecognized = countRecognizedStats(result.new_stats);
  return originalRecognized === 5 && newRecognized === 5;
}

async function refreshHistory() {
  historyRefresh.disabled = true;
  historyLatest.disabled = true;
  historyPrev.disabled = true;
  historyNext.disabled = true;
  historyJump.disabled = true;
  historyPageInput.disabled = true;
  historyStatus.textContent = "正在加载";

  try {
    const response = await fetch(`./api/rebuild_logs?limit=${HISTORY_PAGE_SIZE}&offset=${historyOffset}`);
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.ok) {
      throw new Error(data.error || `HTTP ${response.status}`);
    }
    historyHasMore = Boolean(data.has_more);
    historyOffset = Number.isFinite(data.offset) ? Math.max(0, data.offset) : historyOffset;
    renderHistory(data.items || []);
    updateHistoryPager(data.items || []);
    historyStatus.textContent = `本页 ${data.items?.length || 0} 条`;
  } catch (error) {
    historyList.innerHTML = '<div class="history-empty">历史记录加载失败</div>';
    historyHasMore = false;
    updateHistoryPager([]);
    historyStatus.innerHTML = `<span class="error-text">${escapeHtml(error.message)}</span>`;
  } finally {
    historyRefresh.disabled = false;
    historyLatest.disabled = historyOffset === 0;
    historyPrev.disabled = historyOffset === 0;
    historyNext.disabled = !historyHasMore;
    historyJump.disabled = false;
    historyPageInput.disabled = false;
  }
}

function renderHistory(items) {
  if (!items.length) {
    historyList.innerHTML = '<div class="history-empty">还没有保存记录</div>';
    return;
  }

  historyList.innerHTML = items.map((item) => {
    const isSelected = item.id === selectedHistoryId;
    const diffRows = buildHistoryDiffRows(item.original_descs || [], item.new_descs || [], item.locked_bitmap || 0);
    const lockCount = Number.isFinite(item.locked_count) ? item.locked_count : countBits(item.locked_bitmap || 0);
    return `
      <article class="history-item ${isSelected ? "is-selected" : ""}" data-log-id="${item.id}">
        <button type="button" class="history-main" data-action="open" data-log-id="${item.id}">
          <div class="history-meta">
            <strong>#${item.id}</strong>
            <span>${escapeHtml(item.source_image || "未命名图片")}</span>
          </div>
          <div class="history-submeta">
            <span>User ${escapeHtml(String(item.user_id ?? "-"))}</span>
            <span>${escapeHtml(formatDateTime(item.created_at))}</span>
            <span>锁定 ${lockCount}</span>
          </div>
          <div class="history-diff">${diffRows}</div>
        </button>
      </article>
    `;
  }).join("");
}

function updateHistoryPager(items) {
  const page = Math.floor(historyOffset / HISTORY_PAGE_SIZE) + 1;
  historyPageText.textContent = `第 ${page} 页`;
  historyPageInput.value = String(page);
  historyLatest.disabled = historyOffset === 0;
  historyPrev.disabled = historyOffset === 0;
  historyNext.disabled = !historyHasMore || items.length === 0;
}

async function jumpToHistoryPage() {
  const rawPage = Number.parseInt(historyPageInput.value, 10);
  const page = Number.isFinite(rawPage) ? Math.max(1, rawPage) : 1;
  const nextOffset = (page - 1) * HISTORY_PAGE_SIZE;
  if (nextOffset === historyOffset) {
    historyPageInput.value = String(page);
    return;
  }
  historyOffset = nextOffset;
  await refreshHistory();
}

historyList.addEventListener("click", async (event) => {
  const actionTarget = event.target.closest("[data-action]");
  if (!actionTarget) {
    return;
  }

  const logId = Number(actionTarget.dataset.logId);
  if (!Number.isFinite(logId)) {
    return;
  }

  if (actionTarget.dataset.action === "open") {
    event.preventDefault();
    await openHistory(logId);
  }
});

async function openHistory(logId) {
  historyStatus.textContent = `加载记录 #${logId}`;
  try {
    const response = await fetch(`./api/rebuild_log/${logId}`);
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.ok) {
      throw new Error(data.error || `HTTP ${response.status}`);
    }
    selectedHistoryId = logId;
    renderResult(data.item.payload || {});
    await refreshHistory();
    revealSelectedHistory();
    setStatus(`已加载记录 #${logId}`, "success");
  } catch (error) {
    historyStatus.innerHTML = `<span class="error-text">${escapeHtml(error.message)}</span>`;
  }
}

function setStatus(message, tone = "default") {
  statusText.textContent = message;
  statusText.className = "status-text";
  if (tone !== "default") {
    statusText.classList.add(`is-${tone}`);
  }
}

function revealSelectedHistory() {
  if (selectedHistoryId == null) {
    return;
  }
  const selectedItem = historyList.querySelector(`.history-item[data-log-id="${selectedHistoryId}"]`);
  if (!selectedItem) {
    return;
  }
  selectedItem.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

function openImageModal() {
  if (!previewUrl || modalOpen) {
    return;
  }
  modalOpen = true;
  lastFocusedElement = document.activeElement;
  modalImage.src = previewUrl;
  imageModal.hidden = false;
  imageModal.classList.add("is-open");
  imageModal.setAttribute("aria-hidden", "false");
  document.body.classList.add("modal-open");
  modalClose.focus();
}

function closeImageModal() {
  if (!modalOpen) {
    return;
  }
  modalOpen = false;
  imageModal.classList.remove("is-open");
  imageModal.hidden = true;
  imageModal.setAttribute("aria-hidden", "true");
  modalImage.removeAttribute("src");
  document.body.classList.remove("modal-open");
  if (lastFocusedElement && typeof lastFocusedElement.focus === "function") {
    lastFocusedElement.focus();
  }
  lastFocusedElement = null;
}

function buildTable(rows, otherRows = []) {
  const content = rows.map((row, index) => {
    const changed = isRowChanged(row, otherRows[index]);
    const state = [];
    if (row.is_locked) {
      state.push('<span class="pill locked">锁定</span>');
    }
    if (!state.length) {
      state.push('<span class="pill empty">-</span>');
    }

    return `
      <tr class="${changed ? "is-changed" : ""}">
        <td class="col-index">${index + 1}</td>
        <td class="col-name">${renderStatText(row.name || row.name_raw || "-", row.value || row.value_raw || "")}</td>
        <td class="col-value">${escapeHtml(row.value || row.value_raw || "-")}</td>
        <td class="col-tier">${row.tier ?? "-"}</td>
        <td class="col-state">
          ${changed ? '<span class="pill changed">变化</span>' : ""}
          ${state.join(" ")}
        </td>
      </tr>
    `;
  }).join("");

  return `
    <table class="result-table">
      <thead>
        <tr>
          <th class="col-index">#</th>
          <th class="col-name">词条</th>
          <th class="col-value">数值</th>
          <th class="col-tier">档位</th>
          <th class="col-state">状态</th>
        </tr>
      </thead>
      <tbody>${content}</tbody>
    </table>
  `;
}

function isRowChanged(row, otherRow) {
  if (!row || !otherRow) {
    return false;
  }

  const leftName = String(row.name || row.name_raw || "").trim();
  const rightName = String(otherRow.name || otherRow.name_raw || "").trim();
  const leftValue = String(row.value || row.value_raw || "").trim();
  const rightValue = String(otherRow.value || otherRow.value_raw || "").trim();

  return leftName !== rightName || leftValue !== rightValue;
}

function formatSize(bytes) {
  if (!bytes) {
    return "0 B";
  }
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

function countBits(bits) {
  let value = Number(bits) || 0;
  let count = 0;
  while (value) {
    count += 1;
    value &= value - 1;
  }
  return count;
}

function buildHistoryDiffRows(originalItems, newItems, lockedBitmap = 0) {
  const maxRows = Math.max(originalItems.length, newItems.length, 5);
  return Array.from({ length: maxRows }, (_, index) => {
    const isLocked = Boolean(lockedBitmap & (1 << index));
    const originalText = renderHistoryStatText(originalItems[index] || "-");
    const newText = renderHistoryStatText(newItems[index] || "-");
    return `
      <div class="history-diff-row ${isLocked ? "is-locked" : "is-unlocked"}">
        <span class="history-diff-label hint">原 ${index + 1}</span>
        <span class="history-diff-value">${originalText}</span>
        <span class="history-diff-label hint">新 ${index + 1}</span>
        <span class="history-diff-value">${newText}</span>
        <span class="history-diff-state ${isLocked ? "is-locked" : "is-unlocked"}">${isLocked ? "锁定" : "未锁"}</span>
      </div>
    `;
  }).join("");
}

function renderStatText(name, value) {
  const className = getStatColorClass(name, value);
  return `<span class="stat-text ${className}">${escapeHtml(name || "-")}</span>`;
}

function renderHistoryStatText(text) {
  const rawText = String(text || "-").trim();
  if (!rawText || rawText === "-") {
    return escapeHtml(rawText || "-");
  }
  const match = rawText.match(/^(.+?)\s+(.+)$/);
  if (!match) {
    return renderStatText(rawText, "");
  }
  const [, rawName, rawValue] = match;
  const className = getStatColorClass(rawName, rawValue);
  return `<span class="stat-text ${className}">${escapeHtml(rawText)}</span>`;
}

function getStatColorClass(rawName, rawValue) {
  const normalizedName = normalizeStatName(rawName, rawValue);
  return STAT_COLOR_CLASS_BY_NAME[normalizedName] || "stat-generic";
}

function normalizeStatName(rawName, rawValue) {
  let name = String(rawName || "").trim();
  if (!name) {
    return "";
  }
  name = STAT_NAME_ALIASES[name] || name;
  const valueText = String(rawValue || "").trim();
  if ((name === "攻击" || name === "防御" || name === "生命") && !valueText.includes("%")) {
    return `${name}固定值`;
  }
  return name;
}

function formatDateTime(value) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function escapeHtml(text) {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

resetResult();
setStatus("等待上传");
void refreshHistory();
