(function () {
  const REFERENCE_WIDTH = 1920;
  const REFERENCE_HEIGHT = 1080;
  const REFERENCE_ARROW_BOX = { x: 928, y: 628, width: 66, height: 62 };
  const REFERENCE_LEFT_PANEL = { x: 345, y: 523, width: 518, height: 271 };
  const REFERENCE_RIGHT_PANEL = { x: 1053, y: 523, width: 518, height: 271 };
  const REFERENCE_ROW_HEIGHT = 47;
  const REFERENCE_ROW_GAP = 9;
  const REFERENCE_NAME_X_PADDING = 36;
  const REFERENCE_NAME_WIDTH = 275;
  const REFERENCE_TEXT_Y_PADDING = 3;
  const REFERENCE_LEFT_VALUE_X_PADDING = 145;
  const REFERENCE_LEFT_VALUE_WIDTH = 110;
  const REFERENCE_RIGHT_VALUE_X_PADDING = 140;
  const REFERENCE_RIGHT_VALUE_WIDTH = 150;
  const REFERENCE_USER_ID_CROP_WIDTH = 420;
  const REFERENCE_USER_ID_CROP_HEIGHT = 100;
  const NAME_MIN_SIMILARITY = 0.56;
  const VALUE_SNAP_TOLERANCE_PERCENT = 1.1;
  const VALUE_SNAP_TOLERANCE_FLAT = 25.0;
  const LOCK_BRIGHT_THRESHOLD = 170;
  const LOCK_BRIGHT_RATIO = 0.1;

  const STAT_DEFINITIONS = [
    { name: "暴击", allowedValues: [6.3, 6.9, 7.5, 8.1, 8.7, 9.3, 9.9, 10.5], isPercent: true, aliases: ["暴市", "暴山", "景击"] },
    { name: "暴击伤害", allowedValues: [12.6, 13.8, 15.0, 16.2, 17.4, 18.6, 19.8, 21.0], isPercent: true, aliases: ["暴伤", "暴击份害", "暴击仿害"] },
    { name: "攻击", allowedValues: [6.4, 7.1, 7.9, 8.6, 9.4, 10.1, 10.9, 11.6], isPercent: true, aliases: ["功击"] },
    { name: "生命", allowedValues: [6.4, 7.1, 7.9, 8.6, 9.4, 10.1, 10.9, 11.6], isPercent: true, aliases: ["生俞"] },
    { name: "防御", allowedValues: [8.1, 9.0, 10.0, 10.9, 11.8, 12.8, 13.8, 14.7], isPercent: true, aliases: ["防卸"] },
    { name: "共鸣效率", allowedValues: [6.8, 7.6, 8.4, 9.2, 10.0, 10.8, 11.6, 12.4], isPercent: true, aliases: ["共鸣效串", "共呜效率", "共鸣効率"] },
    { name: "普攻伤害加成", allowedValues: [6.4, 7.1, 7.9, 8.6, 9.4, 10.1, 10.9, 11.6], isPercent: true, aliases: ["普通伤害加成", "普攻份害加成"] },
    { name: "重击伤害加成", allowedValues: [6.4, 7.1, 7.9, 8.6, 9.4, 10.1, 10.9, 11.6], isPercent: true, aliases: ["重吉伤害加成"] },
    { name: "共鸣技能伤害加成", allowedValues: [6.4, 7.1, 7.9, 8.6, 9.4, 10.1, 10.9, 11.6], isPercent: true, aliases: ["共鸣技能份害加成"] },
    { name: "共鸣解放伤害加成", allowedValues: [6.4, 7.1, 7.9, 8.6, 9.4, 10.1, 10.9, 11.6], isPercent: true, aliases: ["共鸣解放份害加成"] },
    { name: "固定生命", allowedValues: [320, 360, 390, 430, 470, 510, 540, 580], isPercent: false, aliases: ["生命"] },
    { name: "固定防御", allowedValues: [40, 50, 60, 70], isPercent: false, aliases: ["防御"] },
    { name: "固定攻击", allowedValues: [30, 40, 50, 60], isPercent: false, aliases: ["攻击"] },
  ];

  const STAT_NAME_INDEX = new Map();
  for (const definition of STAT_DEFINITIONS) {
    STAT_NAME_INDEX.set(definition.name, definition);
    for (const alias of definition.aliases) {
      if (!STAT_NAME_INDEX.has(alias)) {
        STAT_NAME_INDEX.set(alias, definition);
      }
    }
  }

  function createCanvas(width, height) {
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(width));
    canvas.height = Math.max(1, Math.round(height));
    return canvas;
  }

  function clampBox(box, width, height) {
    const x = Math.max(0, Math.min(width, box.x));
    const y = Math.max(0, Math.min(height, box.y));
    const x2 = Math.max(x, Math.min(width, box.x + box.width));
    const y2 = Math.max(y, Math.min(height, box.y + box.height));
    return { x, y, width: Math.max(1, x2 - x), height: Math.max(1, y2 - y) };
  }

  function cropCanvas(sourceCanvas, box) {
    const safeBox = clampBox(box, sourceCanvas.width, sourceCanvas.height);
    const canvas = createCanvas(safeBox.width, safeBox.height);
    const context = canvas.getContext("2d", { willReadFrequently: true });
    context.drawImage(
      sourceCanvas,
      safeBox.x,
      safeBox.y,
      safeBox.width,
      safeBox.height,
      0,
      0,
      safeBox.width,
      safeBox.height,
    );
    return canvas;
  }

  function scaleReferenceBox(box, scale, dx, dy) {
    return {
      x: Math.round(box.x * scale) + dx,
      y: Math.round(box.y * scale) + dy,
      width: Math.max(1, Math.round(box.width * scale)),
      height: Math.max(1, Math.round(box.height * scale)),
    };
  }

  function buildRowBoxes(panelBox, scale) {
    const rowHeight = Math.round(REFERENCE_ROW_HEIGHT * scale);
    const rowGap = Math.round(REFERENCE_ROW_GAP * scale);
    const rows = [];
    let y = panelBox.y;
    for (let index = 0; index < 5; index += 1) {
      rows.push({ x: panelBox.x, y, width: panelBox.width, height: rowHeight });
      y += rowHeight + rowGap;
    }
    return rows;
  }

  function splitNameAndValue(rowBox, side) {
    const scale = rowBox.height / REFERENCE_ROW_HEIGHT;
    const leftPadding = Math.round(REFERENCE_NAME_X_PADDING * scale);
    const yPadding = Math.round(REFERENCE_TEXT_Y_PADDING * scale);
    const nameWidth = Math.round(REFERENCE_NAME_WIDTH * scale);
    const valueWidth = Math.round((side === "left" ? REFERENCE_LEFT_VALUE_WIDTH : REFERENCE_RIGHT_VALUE_WIDTH) * scale);
    const valueXPadding = Math.round((side === "left" ? REFERENCE_LEFT_VALUE_X_PADDING : REFERENCE_RIGHT_VALUE_X_PADDING) * scale);

    return {
      nameBox: {
        x: rowBox.x + leftPadding,
        y: rowBox.y + yPadding,
        width: Math.max(1, nameWidth),
        height: Math.max(1, rowBox.height - yPadding * 2),
      },
      valueBox: {
        x: rowBox.x + rowBox.width - valueXPadding,
        y: rowBox.y + yPadding,
        width: Math.max(1, valueWidth),
        height: Math.max(1, rowBox.height - yPadding * 2),
      },
    };
  }

  function preprocessCrop(canvas) {
    const targetHeight = 96;
    const scale = Math.max(1, targetHeight / Math.max(1, canvas.height));
    const scaledWidth = Math.max(1, Math.round(canvas.width * scale));
    const scaledHeight = Math.max(1, Math.round(canvas.height * scale));
    const resized = createCanvas(scaledWidth, scaledHeight);
    const resizedContext = resized.getContext("2d", { willReadFrequently: true });
    resizedContext.drawImage(canvas, 0, 0, scaledWidth, scaledHeight);

    const imageData = resizedContext.getImageData(0, 0, scaledWidth, scaledHeight);
    const data = imageData.data;
    const grayValues = new Uint8ClampedArray(scaledWidth * scaledHeight);
    let sum = 0;
    for (let index = 0, pixel = 0; index < data.length; index += 4, pixel += 1) {
      const gray = Math.max(0, Math.min(255, Math.round((data[index] * 0.299 + data[index + 1] * 0.587 + data[index + 2] * 0.114) * 1.8 + 6)));
      grayValues[pixel] = gray;
      sum += gray;
    }

    const threshold = sum / grayValues.length;
    for (let index = 0, pixel = 0; index < data.length; index += 4, pixel += 1) {
      const value = grayValues[pixel] > threshold ? 255 : 0;
      data[index] = value;
      data[index + 1] = value;
      data[index + 2] = value;
      data[index + 3] = 255;
    }
    resizedContext.putImageData(imageData, 0, 0);

    const padded = createCanvas(scaledWidth + 48, scaledHeight + 32);
    const paddedContext = padded.getContext("2d");
    paddedContext.fillStyle = "#000";
    paddedContext.fillRect(0, 0, padded.width, padded.height);
    paddedContext.drawImage(resized, 24, 16);
    return padded;
  }

  function cleanText(text) {
    return String(text || "")
      .replaceAll(" ", "")
      .replaceAll("·", "")
      .replaceAll(".", "")
      .replaceAll("。", "")
      .replaceAll(":", "")
      .trim();
  }

  function cleanValueText(text) {
    return String(text || "")
      .replaceAll("O", "0")
      .replaceAll("o", "0")
      .replaceAll("Q", "0")
      .replaceAll("l", "1")
      .replaceAll("I", "1")
      .replaceAll("S", "5")
      .replaceAll("新", "")
      .replaceAll(" ", "");
  }

  function extractNumber(rawValue) {
    const cleaned = cleanValueText(rawValue);
    const match = cleaned.match(/\d+(?:\.\d+)?/);
    return match ? Number(match[0]) : null;
  }

  function levenshteinDistance(a, b) {
    const rows = a.length + 1;
    const cols = b.length + 1;
    const matrix = Array.from({ length: rows }, () => new Array(cols).fill(0));
    for (let row = 0; row < rows; row += 1) {
      matrix[row][0] = row;
    }
    for (let col = 0; col < cols; col += 1) {
      matrix[0][col] = col;
    }
    for (let row = 1; row < rows; row += 1) {
      for (let col = 1; col < cols; col += 1) {
        const cost = a[row - 1] === b[col - 1] ? 0 : 1;
        matrix[row][col] = Math.min(
          matrix[row - 1][col] + 1,
          matrix[row][col - 1] + 1,
          matrix[row - 1][col - 1] + cost,
        );
      }
    }
    return matrix[rows - 1][cols - 1];
  }

  function similarity(a, b) {
    if (!a && !b) {
      return 1;
    }
    const longest = Math.max(a.length, b.length, 1);
    return 1 - levenshteinDistance(a, b) / longest;
  }

  function disambiguateFixedStat(definition, rawValue) {
    if (!definition || !["攻击", "防御", "生命"].includes(definition.name)) {
      return definition;
    }
    const numeric = extractNumber(rawValue);
    if (numeric == null || String(rawValue || "").includes("%")) {
      return definition;
    }
    return STAT_NAME_INDEX.get(`固定${definition.name}`) || definition;
  }

  function displayName(definition) {
    if (!definition) {
      return null;
    }
    if (["固定攻击", "固定防御", "固定生命"].includes(definition.name)) {
      return definition.name.replace("固定", "");
    }
    return definition.name;
  }

  function normalizeName(rawName, rawValue) {
    const text = cleanText(rawName);
    if (!text) {
      return { name: null, definition: null };
    }

    if (STAT_NAME_INDEX.has(text)) {
      const definition = disambiguateFixedStat(STAT_NAME_INDEX.get(text), rawValue);
      return { name: displayName(definition), definition };
    }

    let best = null;
    for (const [candidate, definition] of STAT_NAME_INDEX.entries()) {
      const score = similarity(text, candidate);
      if (!best || score > best.score) {
        best = { score, definition };
      }
    }

    if (best && best.score >= NAME_MIN_SIMILARITY) {
      const definition = disambiguateFixedStat(best.definition, rawValue);
      return { name: displayName(definition), definition };
    }

    return { name: text, definition: null };
  }

  function normalizeValue(definition, rawValue) {
    const numeric = extractNumber(rawValue);
    if (numeric == null) {
      const cleaned = cleanValueText(rawValue);
      return { value: cleaned || null, tier: null };
    }

    if (!definition) {
      return { value: Number.isInteger(numeric) ? String(numeric) : numeric.toFixed(1), tier: null };
    }

    let nearest = definition.allowedValues[0];
    for (const candidate of definition.allowedValues) {
      if (Math.abs(candidate - numeric) < Math.abs(nearest - numeric)) {
        nearest = candidate;
      }
    }

    const tolerance = definition.isPercent ? VALUE_SNAP_TOLERANCE_PERCENT : VALUE_SNAP_TOLERANCE_FLAT;
    const snapped = Math.abs(nearest - numeric) <= tolerance ? nearest : numeric;
    const tier = snapped === nearest ? definition.allowedValues.indexOf(nearest) + 1 : null;

    if (definition.isPercent) {
      return { value: `${snapped.toFixed(1)}%`, tier };
    }
    return { value: Number.isInteger(snapped) ? String(Math.round(snapped)) : snapped.toFixed(1), tier };
  }

  function extractUserIdFromText(text) {
    const labeled = String(text || "").match(/特征码[:：]?(\d{6,})/);
    if (labeled) {
      return labeled[1];
    }
    const matches = String(text || "").match(/\d{6,}/g) || [];
    if (!matches.length) {
      return null;
    }
    return matches.sort((left, right) => right.length - left.length)[0];
  }

  function detectLock(rowCanvas) {
    const width = Math.max(1, Math.floor(rowCanvas.width / 7));
    const context = rowCanvas.getContext("2d", { willReadFrequently: true });
    const imageData = context.getImageData(0, 0, width, rowCanvas.height).data;
    let bright = 0;
    const pixels = Math.max(1, imageData.length / 4);
    for (let index = 0; index < imageData.length; index += 4) {
      const value = Math.max(imageData[index], imageData[index + 1], imageData[index + 2]);
      if (value > LOCK_BRIGHT_THRESHOLD) {
        bright += 1;
      }
    }
    return bright / pixels > LOCK_BRIGHT_RATIO;
  }

  class BrowserRecognizer {
    constructor() {
      this.worker = null;
      this.workerPromise = null;
      this.statusListener = null;
    }

    async ensureWorker(onStatus) {
      this.statusListener = onStatus || null;
      if (this.worker) {
        return this.worker;
      }
      if (this.workerPromise) {
        return this.workerPromise;
      }
      if (!window.Tesseract || typeof window.Tesseract.createWorker !== "function") {
        throw new Error("OCR 引擎未加载完成，请稍后重试。");
      }

      this.workerPromise = window.Tesseract.createWorker("chi_sim+eng", 1, {
        logger: (message) => {
          if (!this.statusListener) {
            return;
          }
          const progress = typeof message.progress === "number" ? ` ${Math.round(message.progress * 100)}%` : "";
          this.statusListener(`${message.status}${progress}`);
        },
      }).then((worker) => {
        this.worker = worker;
        this.workerPromise = null;
        return worker;
      }).catch((error) => {
        this.workerPromise = null;
        throw error;
      });

      return this.workerPromise;
    }

    async setParameters(parameters) {
      const worker = await this.ensureWorker(this.statusListener);
      if (typeof worker.setParameters === "function") {
        await worker.setParameters(parameters);
      }
      return worker;
    }

    async readText(canvas, mode) {
      const worker = await this.ensureWorker(this.statusListener);
      const parameters = {
        tessedit_pageseg_mode: "7",
        tessedit_char_whitelist: "",
      };

      if (mode === "value") {
        parameters.tessedit_char_whitelist = "0123456789.%OQolIS新";
      } else if (mode === "user_id") {
        parameters.tessedit_char_whitelist = "特征码:：0123456789 ";
      }

      await this.setParameters(parameters);
      let result = await worker.recognize(canvas);
      let text = String(result.data?.text || "").trim();
      let confidence = typeof result.data?.confidence === "number" ? result.data.confidence / 100 : null;

      if (!text) {
        result = await worker.recognize(preprocessCrop(canvas));
        text = String(result.data?.text || "").trim();
        confidence = typeof result.data?.confidence === "number" ? result.data.confidence / 100 : null;
      }

      return { text, confidence };
    }

    async recognizeRow(sourceCanvas, rowBox, side) {
      const rowCanvas = cropCanvas(sourceCanvas, rowBox);
      const { nameBox, valueBox } = splitNameAndValue(rowBox, side);
      const nameCanvas = cropCanvas(sourceCanvas, nameBox);
      const valueCanvas = cropCanvas(sourceCanvas, valueBox);

      const { text: nameRaw, confidence: nameConfidence } = await this.readText(nameCanvas, "name");
      const { text: valueRaw, confidence: valueConfidence } = await this.readText(valueCanvas, "value");
      const normalizedName = normalizeName(nameRaw, valueRaw);
      const normalizedValue = normalizeValue(normalizedName.definition, valueRaw);
      const confidenceValues = [nameConfidence, valueConfidence].filter((value) => value != null);
      const confidence = confidenceValues.length
        ? confidenceValues.reduce((sum, value) => sum + value, 0) / confidenceValues.length
        : null;

      return {
        name: normalizedName.name,
        value: normalizedValue.value,
        is_locked: detectLock(rowCanvas),
        is_new: false,
        tier: normalizedValue.tier,
        confidence,
        name_raw: nameRaw || null,
        value_raw: valueRaw || null,
        row_box: rowBox,
      };
    }

    async recognizeFile(file, onStatus) {
      if (!file) {
        throw new Error("请先选择一张图片。");
      }

      await this.ensureWorker(onStatus);
      this.statusListener = onStatus || null;

      const bitmap = await createImageBitmap(file);
      const sourceCanvas = createCanvas(bitmap.width, bitmap.height);
      sourceCanvas.getContext("2d", { willReadFrequently: true }).drawImage(bitmap, 0, 0);
      bitmap.close();

      const scale = Math.min(sourceCanvas.width / REFERENCE_WIDTH, sourceCanvas.height / REFERENCE_HEIGHT);
      const dx = Math.round((sourceCanvas.width - REFERENCE_WIDTH * scale) / 2);
      const dy = Math.round((sourceCanvas.height - REFERENCE_HEIGHT * scale) / 2);

      const anchorBox = scaleReferenceBox(REFERENCE_ARROW_BOX, scale, dx, dy);
      const originalPanel = scaleReferenceBox(REFERENCE_LEFT_PANEL, scale, dx, dy);
      const newPanel = scaleReferenceBox(REFERENCE_RIGHT_PANEL, scale, dx, dy);
      const originalRows = buildRowBoxes(originalPanel, scale);
      const newRows = buildRowBoxes(newPanel, scale);

      const userIdBox = {
        x: Math.max(0, sourceCanvas.width - Math.round(REFERENCE_USER_ID_CROP_WIDTH * scale)),
        y: Math.max(0, sourceCanvas.height - Math.round(REFERENCE_USER_ID_CROP_HEIGHT * scale)),
        width: Math.min(sourceCanvas.width, Math.round(REFERENCE_USER_ID_CROP_WIDTH * scale)),
        height: Math.min(sourceCanvas.height, Math.round(REFERENCE_USER_ID_CROP_HEIGHT * scale)),
      };
      const userIdCrop = cropCanvas(sourceCanvas, userIdBox);
      const userIdResult = await this.readText(userIdCrop, "user_id");
      const userIdRaw = String(userIdResult.text || "").replace(/\s+/g, "").replace("特征码", "特征码:") || null;
      const userId = extractUserIdFromText(userIdRaw);

      const originalStats = [];
      for (const rowBox of originalRows) {
        if (this.statusListener) {
          this.statusListener("识别原词条");
        }
        originalStats.push(await this.recognizeRow(sourceCanvas, rowBox, "left"));
      }

      const newStats = [];
      for (const rowBox of newRows) {
        if (this.statusListener) {
          this.statusListener("识别新词条");
        }
        newStats.push(await this.recognizeRow(sourceCanvas, rowBox, "right"));
      }

      if (this.statusListener) {
        this.statusListener("识别完成");
      }

      return {
        filename: file.name || "clipboard.png",
        result: {
          anchor_box: anchorBox,
          scale,
          user_id: userId,
          user_id_raw: userIdRaw,
          original_stats: originalStats,
          new_stats: newStats,
        },
      };
    }

    async terminate() {
      if (!this.worker) {
        return;
      }
      await this.worker.terminate();
      this.worker = null;
    }
  }

  window.WuwaBrowserRecognizer = BrowserRecognizer;
})();
