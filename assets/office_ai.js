(() => {
  "use strict";

  const taskMeta = {
    "image-excel": { title: "圖片轉 Excel", icon: "▦" },
    pdf: { title: "PDF 文件整理", icon: "PDF" },
    meeting: { title: "會議紀錄整理", icon: "記" },
    email: { title: "Email / 商務文字撰寫", icon: "＠" },
    "excel-analysis": { title: "Excel / 表格資料分析", icon: "Σ" },
    engineering: { title: "工程問題分析", icon: "修" },
  };

  const imageRules = {
    merge: "將所有圖片中的資料合併整理成單一資料表",
    device: "設備名稱",
    ip: "IP Address",
    location: "Location",
    remark: "Remark",
    columns: "依照資料內容自動整理成清楚且一致的欄位",
    "text-only": "輸出時移除圖片，只保留辨識後的文字資料",
    xlsx: "完成資料整理後，請產生可下載的 Excel (.xlsx) 檔案",
  };

  const byName = (formData, name) => formData.getAll(name).filter(Boolean);
  const clean = (value, fallback) => String(value || "").trim() || fallback;
  const joinChinese = (items) => {
    if (items.length < 2) return items[0] || "";
    return `${items.slice(0, -1).join("、")}與${items[items.length - 1]}`;
  };

  const buildImagePrompt = (formData) => {
    const dataType = clean(formData.get("image-data-type"), "一般表格");
    const selected = new Set(byName(formData, "image-requirement"));
    const opening = selected.has("merge") ? `我將上傳多張${dataType}資料照片。` : `我將上傳${dataType}資料照片。`;
    const instructions = ["請辨識照片中的表格內容"];
    if (selected.has("merge")) instructions.push(imageRules.merge);

    const fields = ["device", "ip", "location", "remark"]
      .filter((key) => selected.has(key))
      .map((key) => imageRules[key]);
    const paragraphs = [`${opening}${instructions.join("，")}。`];
    if (fields.length) paragraphs.push(`請保留${joinChinese(fields)}。`);
    if (selected.has("columns")) paragraphs.push(`${imageRules.columns}。`);
    if (selected.has("text-only")) paragraphs.push(`${imageRules["text-only"]}。`);
    paragraphs.push("辨識不清楚的內容不要自行猜測；無法確認的欄位請標示為「待確認」。請保留原始資料順序，不要自行補造照片中不存在的資料。");
    if (selected.has("xlsx")) paragraphs.push(`${imageRules.xlsx}。`);
    return paragraphs.join("\n\n");
  };

  const buildCheckedPrompt = (formData, name, opening, fallback, notesName) => {
    const actions = byName(formData, name);
    const requested = actions.length ? joinChinese(actions) : fallback;
    const paragraphs = [`${opening}請協助我${requested}。`, "請使用繁體中文，以清楚的標題與條列呈現；原始資料沒有提到的內容請明確標示，不要自行補造。"];
    const notes = notesName ? clean(formData.get(notesName), "") : "";
    if (notes) paragraphs.splice(1, 0, `補充需求：${notes}`);
    return paragraphs.join("\n\n");
  };

  const builders = {
    "image-excel": buildImagePrompt,
    pdf: (formData) => buildCheckedPrompt(formData, "pdf-action", "我將上傳 PDF 文件。", "整理文件重點", "pdf-notes"),
    meeting: (formData) => buildCheckedPrompt(formData, "meeting-action", "我將提供會議逐字稿、筆記或錄音轉寫內容。", "摘要討論內容", null),
    "excel-analysis": (formData) => buildCheckedPrompt(formData, "excel-action", "我將上傳 Excel 或表格資料。請先確認欄位與資料範圍，再", "整理資料摘要", "excel-notes"),
    email: (formData) => {
      const recipient = clean(formData.get("email-recipient"), "收件人");
      const purpose = clean(formData.get("email-purpose"), "清楚傳達以下事項");
      const points = clean(formData.get("email-points"), "我稍後提供的重點");
      const tone = clean(formData.get("email-tone"), "專業有禮");
      return `請協助我撰寫一封給「${recipient}」的 Email 或商務文字。\n\n目的：${purpose}\n重點：${points}\n語氣：${tone}\n\n請使用繁體中文，提供清楚的主旨與完整內文。內容應精簡、自然且可直接使用；若必要資訊不足，請先列出需要我補充的項目，不要自行虛構。`;
    },
    engineering: (formData) => {
      const system = clean(formData.get("engineering-system"), "尚未提供");
      const device = clean(formData.get("engineering-device"), "尚未提供");
      const symptom = clean(formData.get("engineering-symptom"), "尚未提供");
      const checks = clean(formData.get("engineering-checks"), "尚未進行或尚未提供");
      return `請協助我分析以下工程問題。\n\n系統類型：${system}\n設備：${device}\n問題現象：${symptom}\n已做過的檢查：${checks}\n\n請依下列順序回答：\n1. 整理目前已知資訊。\n2. 列出可能原因，並說明判斷依據。\n3. 依優先順序提供安全、可執行的檢查步驟。\n4. 明確區分「已確認事實」與「推測」，不要把推測寫成事實。\n5. 明確指出不足資訊與需要補充的資料，不可自行假設。`;
    },
  };

  const globalObject = typeof window === "undefined" ? globalThis : window;
  globalObject.OfficeAIPromptBuilders = { builders, buildImagePrompt };
  if (typeof document === "undefined") return;

  const taskView = document.getElementById("task-view");
  const builderView = document.getElementById("builder-view");
  const resultView = document.getElementById("result-view");
  const builderTitle = document.getElementById("builder-title");
  const builderIcon = document.getElementById("builder-icon");
  const form = document.getElementById("prompt-form");
  const formFeedback = document.getElementById("form-feedback");
  const promptOutput = document.getElementById("prompt-output");
  const copyFeedback = document.getElementById("copy-feedback");
  let activeTask = null;

  const scrollAndFocus = (element) => {
    window.scrollTo(0, 0);
    element.focus({ preventScroll: true });
  };

  const showTasks = () => {
    activeTask = null;
    builderView.hidden = true;
    resultView.hidden = true;
    taskView.hidden = false;
    formFeedback.textContent = "";
    copyFeedback.textContent = "";
    scrollAndFocus(document.getElementById("page-title"));
  };

  const showBuilder = (task) => {
    activeTask = task;
    const meta = taskMeta[task];
    document.querySelectorAll(".task-form").forEach((section) => {
      section.hidden = section.dataset.form !== task;
    });
    builderTitle.textContent = meta.title;
    builderIcon.textContent = meta.icon;
    taskView.hidden = true;
    resultView.hidden = true;
    builderView.hidden = false;
    formFeedback.textContent = "";
    copyFeedback.textContent = "";
    scrollAndFocus(builderTitle);
  };

  const validateActiveForm = () => {
    if (activeTask === "email" && !form.elements["email-points"].value.trim()) return "請先填寫要傳達的重點。";
    if (activeTask === "engineering" && !form.elements["engineering-symptom"].value.trim()) return "請先描述問題現象。";
    return "";
  };

  const generatePrompt = () => {
    const validationMessage = validateActiveForm();
    if (validationMessage) {
      formFeedback.textContent = validationMessage;
      return false;
    }
    promptOutput.value = builders[activeTask](new FormData(form));
    formFeedback.textContent = "";
    copyFeedback.textContent = "";
    taskView.hidden = true;
    builderView.hidden = true;
    resultView.hidden = false;
    scrollAndFocus(document.getElementById("result-title"));
    return true;
  };

  const fallbackCopy = (text) => {
    const helper = document.createElement("textarea");
    helper.value = text;
    helper.setAttribute("readonly", "");
    helper.className = "clipboard-helper";
    document.body.append(helper);
    helper.select();
    let copied = false;
    try { copied = document.execCommand("copy"); } catch (_error) { copied = false; }
    helper.remove();
    return copied;
  };

  const copyPrompt = async () => {
    let copied = false;
    if (navigator.clipboard && window.isSecureContext) {
      try { await navigator.clipboard.writeText(promptOutput.value); copied = true; } catch (_error) { copied = false; }
    }
    if (!copied) copied = fallbackCopy(promptOutput.value);
    copyFeedback.textContent = copied ? "提示詞已複製，可以貼到 ChatGPT 使用。" : "複製失敗，請選取上方提示詞後手動複製。";
    copyFeedback.className = copied ? "is-success" : "is-error";
  };

  document.querySelectorAll("[data-task]").forEach((button) => button.addEventListener("click", () => showBuilder(button.dataset.task)));
  document.getElementById("back-tasks").addEventListener("click", showTasks);
  document.getElementById("back-builder").addEventListener("click", () => showBuilder(activeTask));
  document.getElementById("regenerate-prompt").addEventListener("click", generatePrompt);
  document.getElementById("copy-prompt").addEventListener("click", copyPrompt);
  form.addEventListener("submit", (event) => { event.preventDefault(); generatePrompt(); });
  form.addEventListener("input", () => { formFeedback.textContent = ""; copyFeedback.textContent = ""; });
})();
