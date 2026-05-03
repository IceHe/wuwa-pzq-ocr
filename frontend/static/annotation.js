(function () {
  const STAT_NAMES = [
    "暴击",
    "暴击伤害",
    "攻击",
    "生命",
    "防御",
    "共鸣效率",
    "普攻伤害加成",
    "重击伤害加成",
    "共鸣技能伤害加成",
    "共鸣解放伤害加成",
  ];

  const STAT_VALUE_TABLE = {
    "暴击": { values: [6.3, 6.9, 7.5, 8.1, 8.7, 9.3, 9.9, 10.5], isPercent: true },
    "暴击伤害": { values: [12.6, 13.8, 15.0, 16.2, 17.4, 18.6, 19.8, 21.0], isPercent: true },
    "攻击": { values: [6.4, 7.1, 7.9, 8.6, 9.4, 10.1, 10.9, 11.6], isPercent: true },
    "生命": { values: [6.4, 7.1, 7.9, 8.6, 9.4, 10.1, 10.9, 11.6], isPercent: true },
    "防御": { values: [8.1, 9.0, 10.0, 10.9, 11.8, 12.8, 13.8, 14.7], isPercent: true },
    "共鸣效率": { values: [6.8, 7.6, 8.4, 9.2, 10.0, 10.8, 11.6, 12.4], isPercent: true },
    "普攻伤害加成": { values: [6.4, 7.1, 7.9, 8.6, 9.4, 10.1, 10.9, 11.6], isPercent: true },
    "重击伤害加成": { values: [6.4, 7.1, 7.9, 8.6, 9.4, 10.1, 10.9, 11.6], isPercent: true },
    "共鸣技能伤害加成": { values: [6.4, 7.1, 7.9, 8.6, 9.4, 10.1, 10.9, 11.6], isPercent: true },
    "共鸣解放伤害加成": { values: [6.4, 7.1, 7.9, 8.6, 9.4, 10.1, 10.9, 11.6], isPercent: true },
    "固定攻击": { values: [30, 40, 50, 60], isPercent: false },
    "固定生命": { values: [320, 360, 390, 430, 470, 510, 540, 580], isPercent: false },
    "固定防御": { values: [40, 50, 60, 70], isPercent: false },
  };

  const STAT_KIND_INDEX = {
    "暴击": "crit",
    "暴击伤害": "crit-damage",
    "攻击": "attack",
    "生命": "health",
    "防御": "defense",
    "共鸣效率": "energy",
    "普攻伤害加成": "basic",
    "重击伤害加成": "heavy",
    "共鸣技能伤害加成": "skill",
    "共鸣解放伤害加成": "liberation",
    "固定攻击": "attack",
    "固定生命": "health",
    "固定防御": "defense",
  };

  const state = {
    groups: [],
    items: [],
    selectedId: null,
    currentLabel: null,
    dirty: false,
    recognizer: null,
    ocrDraftRequestId: 0,
    ocrBusy: false,
  };

  const configured = document.body.dataset.annotationConfigured === "1";
  const authenticated = document.body.dataset.annotationAuthenticated === "1";

  function $(selector) {
    return document.querySelector(selector);
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      credentials: "same-origin",
      ...options,
      headers: {
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...(options.headers || {}),
      },
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload.ok === false) {
      const error = payload.error || `HTTP ${response.status}`;
      throw new Error(error);
    }
    return payload;
  }

  function setStatus(message, kind = "") {
    const element = $("#annotation-status") || $("#login-status");
    if (!element) {
      return;
    }
    element.textContent = message || "";
    element.classList.toggle("is-error", kind === "error");
    element.classList.toggle("is-success", kind === "success");
  }

  function warnIfOcrBusy() {
    if (!state.ocrBusy) {
      return false;
    }
    setStatus("正在自动识别，请先等等", "error");
    return true;
  }

  function setOcrBusy(isBusy) {
    state.ocrBusy = isBusy;
    for (const selector of ["#save-button", "#prev-button", "#next-button", "#ocr-draft-button", "#run-regression-button", "#refresh-button"]) {
      const button = $(selector);
      if (button) {
        button.disabled = isBusy;
      }
    }
    for (const button of document.querySelectorAll(".sample-button")) {
      button.disabled = isBusy;
    }
  }

  function initLogin() {
    const form = $("#login-form");
    if (!form) {
      return;
    }
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const input = $("#password-input");
      const password = input ? input.value : "";
      setStatus("正在验证口令");
      try {
        await api("/annotation/api/login", {
          method: "POST",
          body: JSON.stringify({ password }),
        });
        window.location.reload();
      } catch (error) {
        setStatus(`口令错误: ${error.message}`, "error");
      }
    });
  }

  function initApp() {
    if (!configured || !authenticated) {
      initLogin();
      return;
    }

    $("#refresh-button")?.addEventListener("click", () => {
      if (warnIfOcrBusy()) {
        return;
      }
      loadSamples({ keepSelection: true });
    });
    $("#group-filter")?.addEventListener("change", () => renderSampleList());
    $("#status-filter")?.addEventListener("change", () => renderSampleList());
    $("#save-button")?.addEventListener("click", saveCurrentLabel);
    $("#prev-button")?.addEventListener("click", () => selectAdjacent(-1));
    $("#next-button")?.addEventListener("click", () => selectAdjacent(1));
    $("#ocr-draft-button")?.addEventListener("click", importOcrDraft);
    $("#run-regression-button")?.addEventListener("click", runBrowserRegression);
    $("#logout-button")?.addEventListener("click", logout);
    $("#label-form")?.addEventListener("input", (event) => {
      state.dirty = true;
      const row = event.target.closest?.(".stat-row");
      if (row) {
        refreshAutoTier(row);
        syncLockedCounterpart(row, event.target);
      }
    });
    $("#label-form")?.addEventListener("change", (event) => {
      const row = event.target.closest?.(".stat-row");
      if (row && event.target.matches('[data-field="is_locked"]')) {
        state.dirty = true;
        syncLockedCounterpart(row, event.target);
      }
    });

    ensureStatNameDatalist();
    loadSamples();
  }

  async function logout() {
    await api("/annotation/api/logout", { method: "POST" }).catch(() => null);
    window.location.reload();
  }

  async function loadSamples({ keepSelection = false } = {}) {
    setStatus("正在加载样本");
    const payload = await api("/annotation/api/samples");
    state.groups = payload.groups || [];
    state.items = payload.items || [];
    renderFilters();

    const previousSelection = keepSelection ? state.selectedId : null;
    const nextSelection =
      previousSelection && state.items.some((item) => item.id === previousSelection)
        ? previousSelection
        : state.items.find((item) => !item.completed)?.id || state.items[0]?.id || null;

    renderSampleList();
    if (nextSelection) {
      await selectSample(nextSelection, { skipDirtyCheck: true });
    } else {
      setStatus("没有找到可标注样本");
    }
  }

  function renderFilters() {
    const groupFilter = $("#group-filter");
    if (!groupFilter) {
      return;
    }

    const current = groupFilter.value || "all";
    const counts = new Map();
    for (const item of state.items) {
      const groupCounts = counts.get(item.group) || { total: 0, completed: 0 };
      groupCounts.total += 1;
      groupCounts.completed += item.completed ? 1 : 0;
      counts.set(item.group, groupCounts);
    }
    groupFilter.innerHTML = [
      `<option value="all">全部样本组</option>`,
      ...state.groups.map((group) => {
        const groupCounts = counts.get(group.key) || { total: group.count, completed: group.completed };
        const label = `${group.label} (${groupCounts.completed}/${groupCounts.total})`;
        return `<option value="${escapeHtml(group.key)}">${escapeHtml(label)}</option>`;
      }),
    ].join("");

    groupFilter.value = state.groups.some((group) => group.key === current) ? current : "all";
    const completed = state.items.filter((item) => item.completed).length;
    const stats = $("#sample-stats");
    if (stats) {
      stats.textContent = `${completed}/${state.items.length} 已完成`;
    }
  }

  function filteredItems() {
    const groupValue = $("#group-filter")?.value || "all";
    const statusValue = $("#status-filter")?.value || "all";
    return state.items.filter((item) => {
      if (groupValue !== "all" && item.group !== groupValue) {
        return false;
      }
      if (statusValue === "todo" && item.completed) {
        return false;
      }
      if (statusValue === "done" && !item.completed) {
        return false;
      }
      return true;
    });
  }

  function renderSampleList() {
    const list = $("#sample-list");
    if (!list) {
      return;
    }

    const items = filteredItems();
    if (!items.length) {
      list.innerHTML = `<p class="hint">当前筛选下没有样本</p>`;
      return;
    }

    list.innerHTML = items
      .map((item) => {
        const size = item.image_size ? `${item.image_size.width}x${item.image_size.height}` : "unknown";
        const status = item.completed ? `<span class="done-pill">已完成</span>` : `<span class="todo-pill">未完成</span>`;
        return `
          <button class="sample-button ${item.id === state.selectedId ? "active" : ""}" type="button" data-id="${escapeHtml(item.id)}">
            <span class="sample-name">${escapeHtml(item.filename)}</span>
            <span class="sample-meta">
              <span>${escapeHtml(item.group_label)}</span>
              <span>${escapeHtml(size)}</span>
            </span>
            <span class="sample-meta">
              ${status}
              <span>${escapeHtml(item.updated_at || "")}</span>
            </span>
          </button>
        `;
      })
      .join("");

    for (const button of list.querySelectorAll(".sample-button")) {
      button.addEventListener("click", () => selectSample(button.dataset.id));
    }
  }

  async function selectSample(id, { skipDirtyCheck = false } = {}) {
    if (!skipDirtyCheck && warnIfOcrBusy()) {
      return;
    }
    if (!skipDirtyCheck && state.dirty && !window.confirm("当前标签尚未保存，确定切换样本？")) {
      return;
    }

    const item = state.items.find((candidate) => candidate.id === id);
    if (!item) {
      return;
    }

    state.selectedId = id;
    renderSampleList();
    setStatus("正在加载标签");

    const image = $("#sample-image");
    if (image) {
      image.src = item.image_url;
    }
    clearOcrDebug();

    $("#editor-title").textContent = item.filename;
    const size = item.image_size ? `${item.image_size.width}x${item.image_size.height}` : "unknown";
    $("#editor-subtitle").textContent = `${item.group_label} · ${size}`;

    const payload = await api(item.label_url);
    state.currentLabel = payload.label || createEmptyLabel(item);
    renderLabelForm(state.currentLabel);
    updateNavButtons();
    state.dirty = false;
    if (payload.label) {
      setStatus("已加载已有标签");
    } else {
      setStatus("未标注样本，正在自动导入 OCR 草稿");
      importOcrDraft({ automatic: true, skipDirtyConfirm: true, expectedId: item.id });
    }
  }

  function ensureStatNameDatalist() {
    if ($("#stat-name-options")) {
      return;
    }
    const datalist = document.createElement("datalist");
    datalist.id = "stat-name-options";
    datalist.innerHTML = STAT_NAMES.map((name) => `<option value="${escapeHtml(name)}"></option>`).join("");
    document.body.appendChild(datalist);
  }

  function updateNavButtons() {
    const items = filteredItems();
    const index = items.findIndex((item) => item.id === state.selectedId);
    const prev = $("#prev-button");
    const next = $("#next-button");
    if (prev) {
      prev.disabled = index <= 0;
    }
    if (next) {
      next.disabled = index < 0 || index >= items.length - 1;
    }
  }

  function selectAdjacent(delta) {
    if (warnIfOcrBusy()) {
      return;
    }
    const items = filteredItems();
    const index = items.findIndex((item) => item.id === state.selectedId);
    const next = items[index + delta];
    if (next) {
      selectSample(next.id);
    }
  }

  function nextFilteredItemId() {
    const items = filteredItems();
    const index = items.findIndex((candidate) => candidate.id === state.selectedId);
    return index >= 0 && index < items.length - 1 ? items[index + 1].id : null;
  }

  function createEmptyLabel(item) {
    return {
      sample_group: item.group,
      filename: item.filename,
      image_size: item.image_size,
      user_id: "",
      original_stats: Array.from({ length: 5 }, () => emptyRow(false)),
      new_stats: Array.from({ length: 5 }, () => emptyRow(true)),
      notes: "",
    };
  }

  function emptyRow(isNew) {
    return {
      name: "",
      value: "",
      tier: "",
      is_locked: false,
      is_new: isNew,
    };
  }

  function renderLabelForm(label) {
    $("#user-id-input").value = label.user_id || "";
    $("#notes-input").value = label.notes || "";
    renderRows("#original-rows", label.original_stats || [], "original");
    renderRows("#new-rows", label.new_stats || [], "new");
    syncLockedRowsFromRight();
  }

  function renderRows(selector, rows, side) {
    const container = $(selector);
    if (!container) {
      return;
    }

    const normalizedRows = Array.from({ length: 5 }, (_, index) => rows[index] || emptyRow(side === "new"));
    container.innerHTML = normalizedRows.map((row, index) => renderRow(row, index, side)).join("");
    for (const rowElement of container.querySelectorAll(".stat-row")) {
      refreshAutoTier(rowElement);
    }
  }

  function renderRow(row, index, side) {
    return `
      <div class="stat-row" data-side="${side}" data-index="${index}">
        <span class="stat-index">${index + 1}</span>
        <label class="stat-field stat-name-field">
          <span>词条</span>
          <input data-field="name" type="text" list="stat-name-options" autocomplete="off" placeholder="输入或选择词条名" value="${escapeHtml(row.name || "")}" />
        </label>
        <div class="stat-controls">
          <label class="stat-field">
            <span>数值</span>
            <input data-field="value" type="text" autocomplete="off" placeholder="6.3% / 60 / 580" value="${escapeHtml(row.value || "")}" />
          </label>
          <label class="stat-field auto-tier-field">
            <span>档位</span>
            <output data-field="tier-display" class="auto-tier-value">${escapeHtml(row.tier ? `T${row.tier}` : "-")}</output>
          </label>
          <label class="lock-field">
            <input data-field="is_locked" type="checkbox" ${row.is_locked ? "checked" : ""} ${side === "new" ? "disabled" : ""} />
            锁定
          </label>
        </div>
      </div>
    `;
  }

  function refreshAutoTier(rowElement) {
    const name = rowElement.querySelector('[data-field="name"]')?.value || "";
    const value = rowElement.querySelector('[data-field="value"]')?.value || "";
    const tier = inferTier(name, value);
    rowElement.dataset.statKind = resolveStatKind(name, value);
    rowElement.dataset.tier = tier ? String(tier) : "";
    const display = rowElement.querySelector('[data-field="tier-display"]');
    if (display) {
      display.value = tier ? `T${tier}` : "-";
      display.textContent = tier ? `T${tier}` : "-";
      display.dataset.empty = tier ? "0" : "1";
    }
  }

  function syncLockedCounterpart(rowElement, sourceElement) {
    const index = rowElement.dataset.index;
    const side = rowElement.dataset.side;
    const originalRow = document.querySelector(`.stat-row[data-side="original"][data-index="${index}"]`);
    const newRow = document.querySelector(`.stat-row[data-side="new"][data-index="${index}"]`);
    if (!originalRow || !newRow || !isOriginalRowLocked(index)) {
      return;
    }

    const sourceField = sourceElement?.dataset?.field || "";
    if (sourceField === "is_locked") {
      const originalHasContent = rowHasContent(originalRow);
      const newHasContent = rowHasContent(newRow);
      copyRowValues(originalHasContent || !newHasContent ? originalRow : newRow, originalHasContent || !newHasContent ? newRow : originalRow);
      return;
    }

    if (!["name", "value"].includes(sourceField)) {
      return;
    }
    copyRowValues(side === "new" ? newRow : originalRow, side === "new" ? originalRow : newRow);
  }

  function syncLockedRowsFromRight() {
    for (let index = 0; index < 5; index += 1) {
      if (!isOriginalRowLocked(index)) {
        continue;
      }
      const originalRow = document.querySelector(`.stat-row[data-side="original"][data-index="${index}"]`);
      const newRow = document.querySelector(`.stat-row[data-side="new"][data-index="${index}"]`);
      if (originalRow && newRow && rowHasContent(newRow)) {
        copyRowValues(newRow, originalRow);
      }
    }
  }

  function isOriginalRowLocked(index) {
    return Boolean(document.querySelector(`.stat-row[data-side="original"][data-index="${index}"] [data-field="is_locked"]`)?.checked);
  }

  function rowHasContent(rowElement) {
    const name = rowElement.querySelector('[data-field="name"]')?.value.trim() || "";
    const value = rowElement.querySelector('[data-field="value"]')?.value.trim() || "";
    return Boolean(name || value);
  }

  function copyRowValues(sourceRow, targetRow) {
    for (const field of ["name", "value"]) {
      const source = sourceRow.querySelector(`[data-field="${field}"]`);
      const target = targetRow.querySelector(`[data-field="${field}"]`);
      if (source && target && target.value !== source.value) {
        target.value = source.value;
      }
    }
    refreshAutoTier(targetRow);
  }

  function collectLabelForm() {
    const item = state.items.find((candidate) => candidate.id === state.selectedId);
    if (!item) {
      throw new Error("missing_selected_sample");
    }
    return {
      sample_group: item.group,
      filename: item.filename,
      user_id: $("#user-id-input").value.trim(),
      original_stats: collectRows("original"),
      new_stats: collectRows("new"),
      notes: $("#notes-input").value.trim(),
    };
  }

  function collectRows(side) {
    return Array.from(document.querySelectorAll(`.stat-row[data-side="${side}"]`)).map((element) => {
      const name = element.querySelector('[data-field="name"]').value;
      const value = element.querySelector('[data-field="value"]').value.trim();
      const locked = element.querySelector('[data-field="is_locked"]').checked;
      return {
        name,
        value,
        tier: inferTier(name, value),
        is_locked: side === "original" ? locked : false,
        is_new: side === "new",
      };
    });
  }

  function resolveStatDefinition(name, value) {
    const normalizedName = String(name || "").trim();
    const rawValue = String(value || "");
    if (["攻击", "生命", "防御"].includes(normalizedName) && !rawValue.includes("%")) {
      return STAT_VALUE_TABLE[`固定${normalizedName}`] || null;
    }
    return STAT_VALUE_TABLE[normalizedName] || null;
  }

  function parseStatNumber(value) {
    const cleaned = String(value || "").replace("%", "").trim();
    if (!cleaned) {
      return null;
    }
    const numeric = Number(cleaned);
    return Number.isFinite(numeric) ? numeric : null;
  }

  function inferTier(name, value) {
    const definition = resolveStatDefinition(name, value);
    const numeric = parseStatNumber(value);
    if (!definition || numeric == null) {
      return null;
    }

    let nearestIndex = 0;
    for (let index = 1; index < definition.values.length; index += 1) {
      if (Math.abs(definition.values[index] - numeric) < Math.abs(definition.values[nearestIndex] - numeric)) {
        nearestIndex = index;
      }
    }

    const tolerance = definition.isPercent ? 0.11 : 0.5;
    return Math.abs(definition.values[nearestIndex] - numeric) <= tolerance ? nearestIndex + 1 : null;
  }

  function resolveStatKind(name, value) {
    const normalizedName = String(name || "").trim();
    const rawValue = String(value || "");
    if (["攻击", "生命", "防御"].includes(normalizedName) && !rawValue.includes("%")) {
      return STAT_KIND_INDEX[`固定${normalizedName}`] || "unknown";
    }
    return STAT_KIND_INDEX[normalizedName] || "unknown";
  }

  async function saveCurrentLabel() {
    if (warnIfOcrBusy()) {
      return;
    }
    const item = state.items.find((candidate) => candidate.id === state.selectedId);
    if (!item) {
      setStatus("请先选择样本", "error");
      return;
    }

    setStatus("正在保存标签");
    try {
      const nextId = nextFilteredItemId();
      const label = collectLabelForm();
      const payload = await api(item.label_url, {
        method: "PUT",
        body: JSON.stringify(label),
      });
      state.currentLabel = payload.label;
      item.completed = true;
      item.updated_at = payload.label.updated_at;
      state.dirty = false;
      renderFilters();
      renderSampleList();
      if (nextId) {
        setStatus("标签已保存，正在切换到下一个样本", "success");
        await selectSample(nextId, { skipDirtyCheck: true });
      } else {
        setStatus("标签已保存，当前筛选下已经是最后一个样本", "success");
      }
    } catch (error) {
      setStatus(`保存失败: ${error.message}`, "error");
    }
  }

  async function importOcrDraft({ automatic = false, skipDirtyConfirm = false, expectedId = null } = {}) {
    if (!automatic && warnIfOcrBusy()) {
      return;
    }
    const item = state.items.find((candidate) => candidate.id === state.selectedId);
    if (!item) {
      return;
    }
    if (!window.WuwaBrowserRecognizer || !window.Tesseract) {
      setStatus(automatic ? "OCR 运行时尚未加载完成，可稍后手动导入草稿" : "OCR 运行时尚未加载完成", automatic ? "" : "error");
      return;
    }
    if (!skipDirtyConfirm && state.dirty && !window.confirm("导入 OCR 草稿会覆盖当前表单，确定继续？")) {
      return;
    }

    const requestId = state.ocrDraftRequestId + 1;
    state.ocrDraftRequestId = requestId;
    const targetId = expectedId || item.id;
    const button = $("#ocr-draft-button");
    setOcrBusy(true);
    setStatus(automatic ? "正在自动预填 OCR 草稿" : "正在下载图片并运行 OCR");
    try {
      const imageResponse = await fetch(item.image_url, { credentials: "same-origin" });
      if (!imageResponse.ok) {
        throw new Error(`image_http_${imageResponse.status}`);
      }
      const blob = await imageResponse.blob();
      const file = new File([blob], item.filename, { type: blob.type || "image/png" });
      state.recognizer = state.recognizer || new window.WuwaBrowserRecognizer();
      const ocr = await state.recognizer.recognizeFile(file, (message) => setStatus(`OCR: ${message}`));
      if (state.ocrDraftRequestId !== requestId || state.selectedId !== targetId) {
        return;
      }
      const result = ocr.result || {};
      renderOcrDebug(result);
      const draft = {
        ...createEmptyLabel(item),
        user_id: result.user_id || "",
        original_stats: normalizeOcrRows(result.original_stats || [], false),
        new_stats: normalizeOcrRows(result.new_stats || [], true),
        notes: "OCR 草稿，需人工确认",
      };
      state.currentLabel = draft;
      renderLabelForm(draft);
      state.dirty = true;
      setStatus(automatic ? "已自动预填 OCR 草稿，请逐项确认后保存" : "已导入 OCR 草稿，请逐项确认后保存", "success");
    } catch (error) {
      setStatus(`${automatic ? "自动预填失败" : "OCR 草稿导入失败"}: ${error.message}`, "error");
      clearOcrDebug();
    } finally {
      if (state.ocrDraftRequestId === requestId) {
        setOcrBusy(false);
      }
    }
  }

  function normalizeOcrRows(rows, isNew) {
    return Array.from({ length: 5 }, (_, index) => {
      const row = rows[index] || {};
      return {
        name: STAT_NAMES.includes(row.name) ? row.name : "",
        value: row.value || "",
        tier: row.tier || "",
        is_locked: isNew ? false : Boolean(row.is_locked),
        is_new: isNew,
      };
    });
  }

  async function runBrowserRegression() {
    if (warnIfOcrBusy()) {
      return;
    }
    if (!window.WuwaBrowserRecognizer || !window.Tesseract) {
      setStatus("OCR 运行时尚未加载完成", "error");
      return;
    }
    if (state.dirty && !window.confirm("当前标签尚未保存，继续回归会保留未保存表单但不纳入报告，确定继续？")) {
      return;
    }

    const button = $("#run-regression-button");
    const output = $("#regression-output");
    if (button) {
      button.disabled = true;
    }
    if (output) {
      output.hidden = false;
      output.textContent = "正在读取标签...";
    }

    try {
      const labelsPayload = await api("/annotation/api/labels");
      const labels = labelsPayload.labels || {};
      const labeledItems = state.items.filter((item) => labels[item.id]);
      if (!labeledItems.length) {
        setStatus("没有已保存标签，无法回归", "error");
        if (output) {
          output.textContent = "没有已保存标签。";
        }
        return;
      }

      state.recognizer = state.recognizer || new window.WuwaBrowserRecognizer();
      const results = [];
      for (let index = 0; index < labeledItems.length; index += 1) {
        const item = labeledItems[index];
        setStatus(`回归中 ${index + 1}/${labeledItems.length}: ${item.filename}`);
        if (output) {
          output.textContent = `回归中 ${index + 1}/${labeledItems.length}: ${item.id}\n已完成 ${results.length} 张`;
        }
        const actual = await recognizeItem(item);
        const expected = labels[item.id];
        results.push(compareRecognition(item, expected, actual));
      }

      const failedItems = results.filter((result) => result.errors.length > 0);
      const report = {
        total: results.length,
        passed: results.length - failedItems.length,
        failed: failedItems.length,
        groups: summarizeByGroup(results),
        items: results,
      };
      const saved = await api("/annotation/api/regression_reports", {
        method: "POST",
        body: JSON.stringify(report),
      });
      renderRegressionOutput(report, saved.filename);
      setStatus(`回归完成: ${report.passed}/${report.total} 通过，报告 ${saved.filename}`, failedItems.length ? "error" : "success");
    } catch (error) {
      setStatus(`回归失败: ${error.message}`, "error");
      if (output) {
        output.textContent = `回归失败: ${error.message}`;
      }
    } finally {
      if (button) {
        button.disabled = false;
      }
    }
  }

  async function recognizeItem(item) {
    const imageResponse = await fetch(item.image_url, { credentials: "same-origin" });
    if (!imageResponse.ok) {
      throw new Error(`image_http_${imageResponse.status}`);
    }
    const blob = await imageResponse.blob();
    const file = new File([blob], item.filename, { type: blob.type || "image/png" });
    const ocr = await state.recognizer.recognizeFile(file, (message) => setStatus(`OCR: ${message}`));
    return ocr.result || {};
  }

  function compareRecognition(item, expected, actual) {
    const errors = [];
    compareValue(errors, "user_id", normalizeScalar(expected.user_id), normalizeScalar(actual.user_id));
    compareRows(errors, "original_stats", expected.original_stats || [], actual.original_stats || [], true);
    compareRows(errors, "new_stats", expected.new_stats || [], actual.new_stats || [], false);
    return {
      id: item.id,
      group: item.group,
      filename: item.filename,
      passed: errors.length === 0,
      errors,
      diagnostics: buildDiagnostics(expected, actual),
      expected,
      actual,
    };
  }

  function buildDiagnostics(expected, actual) {
    return {
      layout: actual.layout || null,
      scale: actual.scale ?? null,
      anchor_box: actual.anchor_box || null,
      user_id: {
        expected: normalizeScalar(expected.user_id),
        actual: normalizeScalar(actual.user_id),
        raw: actual.user_id_raw || "",
        box: actual.user_id_box || null,
        confidence: actual.user_id_confidence ?? null,
      },
      original_rows: buildRowDiagnostics(expected.original_stats || [], actual.original_stats || []),
      new_rows: buildRowDiagnostics(expected.new_stats || [], actual.new_stats || []),
    };
  }

  function buildRowDiagnostics(expectedRows, actualRows) {
    return Array.from({ length: 5 }, (_, index) => {
      const expected = expectedRows[index] || {};
      const actual = actualRows[index] || {};
      return {
        index: index + 1,
        expected: {
          name: normalizeScalar(expected.name),
          value: normalizeScalar(expected.value),
          tier: normalizeScalar(expected.tier),
          is_locked: Boolean(expected.is_locked),
        },
        actual: {
          name: normalizeScalar(actual.name),
          value: normalizeScalar(actual.value),
          tier: normalizeScalar(actual.tier),
          is_locked: Boolean(actual.is_locked),
        },
        raw: {
          name: actual.name_raw || "",
          value: actual.value_raw || "",
        },
        confidence: actual.confidence ?? null,
        row_box: actual.row_box || null,
        name_box: actual.name_box || null,
        value_box: actual.value_box || null,
      };
    });
  }

  function compareRows(errors, field, expectedRows, actualRows, compareLock) {
    for (let index = 0; index < 5; index += 1) {
      const expected = expectedRows[index] || {};
      const actual = actualRows[index] || {};
      const prefix = `${field}[${index + 1}]`;
      compareValue(errors, `${prefix}.name`, normalizeScalar(expected.name), normalizeScalar(actual.name));
      compareValue(errors, `${prefix}.value`, normalizeValue(expected.value), normalizeValue(actual.value));
      compareValue(errors, `${prefix}.tier`, normalizeScalar(expected.tier), normalizeScalar(actual.tier));
      if (compareLock) {
        compareValue(errors, `${prefix}.is_locked`, Boolean(expected.is_locked), Boolean(actual.is_locked));
      }
    }
  }

  function compareValue(errors, path, expected, actual) {
    if (expected !== actual) {
      errors.push({ path, expected, actual });
    }
  }

  function normalizeScalar(value) {
    if (value == null) {
      return "";
    }
    return String(value).trim();
  }

  function normalizeValue(value) {
    return normalizeScalar(value).replace(/\s+/g, "");
  }

  function summarizeByGroup(results) {
    const groups = {};
    for (const result of results) {
      groups[result.group] = groups[result.group] || { total: 0, passed: 0, failed: 0 };
      groups[result.group].total += 1;
      if (result.errors.length) {
        groups[result.group].failed += 1;
      } else {
        groups[result.group].passed += 1;
      }
    }
    return groups;
  }

  function renderRegressionOutput(report, filename) {
    const output = $("#regression-output");
    if (!output) {
      return;
    }
    const failedItems = report.items.filter((item) => item.errors.length > 0);
    const lines = [
      `报告: ${filename}`,
      `总计: ${report.total}`,
      `通过: ${report.passed}`,
      `失败: ${report.failed}`,
      "",
      "分组:",
      ...Object.entries(report.groups).map(([group, stats]) => `${group}: ${stats.passed}/${stats.total} 通过`),
      "",
      "失败明细:",
    ];
    for (const item of failedItems.slice(0, 20)) {
      lines.push(`- ${item.id}`);
      lines.push(`  layout: ${formatLayoutDiagnostics(item.diagnostics)}`);
      lines.push(`  user_id: expected=${JSON.stringify(item.diagnostics.user_id.expected)} actual=${JSON.stringify(item.diagnostics.user_id.actual)} raw=${JSON.stringify(item.diagnostics.user_id.raw)}`);
      for (const error of item.errors.slice(0, 12)) {
        lines.push(`  ${error.path}: expected=${JSON.stringify(error.expected)} actual=${JSON.stringify(error.actual)}`);
        const rowDebug = formatErrorRowDebug(item.diagnostics, error.path);
        if (rowDebug) {
          lines.push(`    ${rowDebug}`);
        }
      }
    }
    if (!failedItems.length) {
      lines.push("无");
    }
    if (failedItems.length > 20) {
      lines.push(`还有 ${failedItems.length - 20} 个失败样本，查看报告 JSON 获取完整明细。`);
    }
    output.hidden = false;
    output.textContent = lines.join("\n");
  }

  function clearOcrDebug() {
    const output = $("#ocr-debug-output");
    if (!output) {
      return;
    }
    output.hidden = true;
    output.textContent = "";
  }

  function renderOcrDebug(result) {
    const output = $("#ocr-debug-output");
    if (!output) {
      return;
    }
    const layout = result.layout || {};
    const lines = [
      "当前样本 OCR 调试:",
      `layout: ${formatLayoutDiagnostics({ layout })}`,
      `top candidates: ${formatLayoutCandidates(layout.candidates || [])}`,
      `user_id: actual=${JSON.stringify(result.user_id || "")} raw=${JSON.stringify(result.user_id_raw || "")} variant=${result.user_id_variant || "n/a"} confidence=${formatConfidence(result.user_id_confidence)}`,
      `user_id_box: ${JSON.stringify(result.user_id_box || null)}`,
      "",
      "原词条:",
      ...formatDebugRows(result.original_stats || []),
      "",
      "新词条:",
      ...formatDebugRows(result.new_stats || []),
    ];
    output.hidden = false;
    output.textContent = lines.join("\n");
  }

  function formatLayoutCandidates(candidates) {
    if (!candidates.length) {
      return "n/a";
    }
    return candidates
      .map((candidate) => `refY=${candidate.reference_offset_y} offsetY=${candidate.offset_y} score=${Number(candidate.score).toFixed(3)}`)
      .join(" | ");
  }

  function formatDebugRows(rows) {
    return Array.from({ length: 5 }, (_, index) => {
      const row = rows[index] || {};
      const nameBox = row.name_box ? JSON.stringify(row.name_box) : "n/a";
      const valueBox = row.value_box ? JSON.stringify(row.value_box) : "n/a";
      return [
        `${index + 1}.`,
        `${row.name || "-"} ${row.value || "-"} ${row.tier ? `T${row.tier}` : "T-"}`,
        `locked=${Boolean(row.is_locked)}`,
        `rawName=${JSON.stringify(row.name_raw || "")}`,
        `rawValue=${JSON.stringify(row.value_raw || "")}`,
        `variant=${row.name_variant || "n/a"}/${row.value_variant || "n/a"}`,
        `confidence=${formatConfidence(row.confidence)}`,
        `nameBox=${nameBox}`,
        `valueBox=${valueBox}`,
      ].join(" ");
    });
  }

  function formatConfidence(value) {
    return value == null ? "n/a" : Number(value).toFixed(2);
  }

  function formatLayoutDiagnostics(diagnostics) {
    const layout = diagnostics?.layout || {};
    const parts = [];
    if (layout.name) {
      parts.push(layout.name);
    }
    if (layout.score != null) {
      parts.push(`score=${Number(layout.score).toFixed(2)}`);
    }
    if (layout.offset_y != null) {
      parts.push(`offsetY=${layout.offset_y}`);
    }
    return parts.length ? parts.join(" ") : "n/a";
  }

  function formatErrorRowDebug(diagnostics, path) {
    const match = String(path || "").match(/^(original_stats|new_stats)\[(\d+)\]/);
    if (!match) {
      return "";
    }
    const rows = match[1] === "original_stats" ? diagnostics.original_rows : diagnostics.new_rows;
    const row = rows?.[Number(match[2]) - 1];
    if (!row) {
      return "";
    }
    const confidence = row.confidence == null ? "n/a" : Number(row.confidence).toFixed(2);
    return [
      `rawName=${JSON.stringify(row.raw.name)}`,
      `rawValue=${JSON.stringify(row.raw.value)}`,
      `confidence=${confidence}`,
      `rowBox=${JSON.stringify(row.row_box)}`,
    ].join(" ");
  }

  initApp();
})();
