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

  const byName = (formData, name) => formData.getAll(name).filter(Boolean);
  const normalizeInput = (value, fallback = "") => String(value || "").trim() || fallback;
  const joinChinese = (items) => {
    if (items.length < 2) return items[0] || "";
    return `${items.slice(0, -1).join("、")}與${items[items.length - 1]}`;
  };
  const bulletList = (items) => items.map((item) => `- ${item}`).join("\n");
  const buildSection = (title, content) => `【${title}】\n${Array.isArray(content) ? bulletList(content) : content}`;
  const buildStructuredPrompt = ({ role, context, task, rules, output, validation }) => [
    buildSection("角色", role),
    buildSection("任務背景", context),
    buildSection("主要任務", task),
    buildSection("執行規則", rules),
    buildSection("輸出格式", output),
    buildSection("品質檢查", validation),
  ].join("\n\n");

  const imageFields = {
    device: "設備名稱",
    ip: "IP Address",
    location: "Location",
    remark: "Remark",
  };

  const imageRoles = {
    CCTV: "你是一名熟悉 CCTV 設備清冊、影像辨識、表格結構化與資料清理的專業資料處理助理。",
    門禁: "你是一名熟悉門禁設備清冊、影像辨識、表格結構化與資料清理的專業資料處理助理。",
    消防: "你是一名熟悉消防設備清冊、影像辨識、表格結構化與資料清理的專業資料處理助理。",
    "BA / IBMS": "你是一名熟悉 BA / IBMS 設備清冊、影像辨識、表格結構化與資料清理的專業資料處理助理。",
    一般表格: "你是一名擅長影像文字辨識、表格結構化與資料清理的專業資料處理助理。",
    其他: "你是一名擅長設備資料辨識、表格結構化與資料清理的專業資料處理助理。",
  };

  const buildImageExcelPrompt = (formData) => {
    const dataType = normalizeInput(formData.get("image-data-type"), "一般表格");
    const selected = new Set(byName(formData, "image-requirement"));
    const fields = ["device", "ip", "location", "remark"]
      .filter((key) => selected.has(key))
      .map((key) => imageFields[key]);
    const rules = [
      "不得自行猜測辨識不清楚的內容；無法可靠辨識的欄位一律標記為「待確認」。",
      "不得自行補造原始圖片中不存在的資料，也不得以其他列內容推測缺失欄位。",
      "保留原始資料順序；若存在原始表頭，優先按照原始表頭理解資料。",
      "若發現重複資料，不得直接刪除，需保留並標示為「可能重複」。",
      "圖片品質不足時，需指出無法確認的圖片、區域與欄位。",
    ];
    if (selected.has("ip")) rules.push("IP Address 必須保持原始格式，不得自行更正；格式異常時只標記，不可改寫。");
    if (selected.has("columns")) rules.push("在不改變原始資料意義的前提下，將欄位名稱與排列整理為清楚且一致的結構。");
    if (selected.has("text-only")) rules.push("只保留辨識後的文字資料，不保留圖片，也不得將圖片嵌入 Excel 或其他輸出檔案。");

    const output = [];
    if (fields.length) output.push(`資料表欄位：${fields.join("｜")}。未勾選的欄位不需強制建立。`);
    else output.push("依原始表頭與實際可辨識內容建立資料表，不強制新增原圖沒有的欄位。");
    output.push("另附辨識摘要：總筆數、待確認項目、可能重複項目及無法辨識區域。");
    if (selected.has("xlsx")) output.push("完成後產生可下載的 Excel (.xlsx) 檔案。");
    else output.push("以可複製的結構化表格呈現，不強制產生 Excel 檔案。");

    const validation = [
      "回報共辨識幾筆資料，以及是否存在「待確認」或「可能重複」項目。",
      "確認每一張使用者提供的圖片都已處理，並回報無法辨識的區域。",
      "確認欄位內容可追溯至原始圖片，且沒有自行補造或跨列推測資料。",
    ];
    if (selected.has("ip")) validation.push("檢查 IP Address 原始格式是否有異常；只回報異常，不自行修正。");

    return buildStructuredPrompt({
      role: imageRoles[dataType] || imageRoles.其他,
      context: selected.has("merge")
        ? `我將提供多張${dataType}資料圖片，圖片可能包含連續、分頁或重複的表格資料。`
        : `我將提供${dataType}資料圖片，內容可能包含表頭、設備資料與辨識不清楚的區域。`,
      task: selected.has("merge")
        ? "辨識所有圖片中的表格內容，將多張圖片資料合併整理成單一、可追溯的結構化資料表。"
        : "辨識圖片中的表格內容，依原始順序整理成可追溯的結構化資料表。",
      rules,
      output,
      validation,
    });
  };

  const buildPdfPrompt = (formData) => {
    const actions = byName(formData, "pdf-action");
    const requested = actions.length ? actions : ["整理文件重點"];
    const notes = normalizeInput(formData.get("pdf-notes"), "未提供額外限制");
    const rules = [
      "所有內容優先依據原始文件，不得自行補充文件中未出現的資訊。",
      "不確定、模糊或無法讀取的內容需明確標示，不得猜測。",
      "重要結論、引用與擷取內容應保留頁碼或來源位置。",
      "不得任意改變表格中的數值、單位、正負號或欄位關係。",
      "必須清楚區分原文件事實、摘要重述與分析推論，不得將推論寫成原文事實。",
    ];
    if (actions.includes("比較兩份文件的差異")) rules.push("比較兩份文件時，分別標示新增、刪除、修改與無法判定的差異。");
    const outputMap = {
      摘要全文: "全文摘要：目的、核心內容與結論",
      整理我指定的頁面: "指定頁面整理：依頁碼列出摘要與重點",
      擷取文件中的表格: "表格擷取：表格名稱、來源頁碼與完整數值",
      找出文件重點: "文件重點：依重要性條列並標示來源頁碼",
      產生教育訓練內容: "教育訓練內容：學習目標、章節重點、案例與複習題",
      比較兩份文件的差異: "文件比較：新增、刪除、修改與影響摘要",
    };
    return buildStructuredPrompt({
      role: "你是一名嚴謹的文件分析與資訊整理助理，擅長長文件摘要、表格擷取與版本比較。",
      context: `我將提供一份或兩份 PDF 文件。補充需求：${notes}。`,
      task: `依據文件內容完成：${joinChinese(requested)}。`,
      rules,
      output: [...requested.map((action) => outputMap[action] || action), "待確認事項：列出無法讀取或需要使用者補充的內容"],
      validation: [
        "確認沒有遺漏使用者指定的頁面或文件。",
        "確認擷取的表格欄位、數值與單位完整且與來源一致。",
        "回報無法讀取、版面錯位或辨識不確定的內容。",
        "確認原文事實與分析推論已清楚區分。",
      ],
    });
  };

  const buildMeetingPrompt = (formData) => {
    const actions = byName(formData, "meeting-action");
    const requested = actions.length ? actions : ["摘要討論內容"];
    const outputMap = {
      摘要討論內容: "會議摘要與主要討論",
      整理會議決議: "決議事項",
      整理待辦事項: "Action Items（事項、來源、負責人、Deadline、狀態）",
      找出每項工作的負責人: "負責人清單",
      找出每項工作的期限: "期限清單",
      產生正式會議紀錄: "正式會議紀錄（會議資訊、討論、決議、待辦、待確認事項）",
    };
    return buildStructuredPrompt({
      role: "你是一名專業會議紀錄與行動項目整理助理，擅長從逐字稿中區分討論、決議與待辦。",
      context: "我將提供會議逐字稿、筆記或錄音轉寫內容，其中可能包含口語、省略、未達共識及不完整資訊。",
      task: `忠實依據會議內容完成：${joinChinese(requested)}。`,
      rules: [
        "不得自行創造未被提及的決議、工作、人物或期限。",
        "未明確指定負責人時標示「未指定」，不得依職稱或上下文自行推定。",
        "未明確指定期限時標示「未指定」，不得自行補上日期。",
        "明確區分討論、正式決議與待辦事項，並保留尚未達成共識的議題。",
        "不得將提案、建議、假設或個人意見誤寫成正式決議。",
      ],
      output: [...requested.map((action) => outputMap[action] || action), "待確認事項：未達共識、資訊缺漏及內容不清楚之處"],
      validation: [
        "確認每個待辦事項都能對應到會議內容來源。",
        "列出負責人或期限為「未指定」的項目。",
        "確認沒有混淆討論、建議與正式決議。",
        "回報內容矛盾、語意不清或需要人工確認之處。",
      ],
    });
  };

  const buildEmailPrompt = (formData) => {
    const recipient = normalizeInput(formData.get("email-recipient"), "尚未指定的收件人");
    const purpose = normalizeInput(formData.get("email-purpose"), "清楚傳達以下事項");
    const points = normalizeInput(formData.get("email-points"), "我稍後提供的重點");
    const tone = normalizeInput(formData.get("email-tone"), "專業有禮");
    return buildStructuredPrompt({
      role: "你是一名專業商務溝通與文字撰寫助理，擅長依收件對象與目的調整正式程度。",
      context: `收件對象：${recipient}\n溝通目的：${purpose}\n必須傳達的重點：${points}\n期望語氣：${tone}`,
      task: "依據上述資訊撰寫一封清楚、自然、可直接使用的繁體中文 Email 或商務文字。",
      rules: [
        "保留使用者原始目的與已提供的事實，不得改變立場或訊息重點。",
        "不得自行加入不存在的承諾、日期、金額、人物、決策或附件。",
        "商務語氣應自然得體，不過度官腔，並依收件對象調整正式程度。",
        "資訊缺失時使用中性表述，不得自行猜測；重要缺漏需先指出。",
        "避免不必要的冗長、情緒化用語與可能造成誤解的絕對承諾。",
      ],
      output: ["主旨", "Email 正文（含稱謂、分段內容與適當結尾）", "缺失資訊提示（如有）"],
      validation: [
        "確認目的、重點與語氣均已反映在內文中。",
        "確認沒有新增使用者未提供的承諾或具體事實。",
        "確認對象稱謂、語氣與結尾適合商務情境。",
        "若資訊不足，先列出缺失資訊，再提供使用中性表述的可用版本。",
      ],
    });
  };

  const buildExcelAnalysisPrompt = (formData) => {
    const actions = byName(formData, "excel-action");
    const requested = actions.length ? actions : ["整理資料摘要"];
    const notes = normalizeInput(formData.get("excel-notes"), "未提供額外資料背景");
    const outputMap = {
      整理資料摘要: "資料摘要：資料範圍、欄位、筆數與主要分布",
      進行統計分析: "統計分析：指標、計算基礎、結果與限制",
      找出異常值: "異常值清單：位置、原始值、判定依據與建議確認方式",
      比較不同欄位或群組的差異: "差異比較：比較基準、結果與可能解讀",
      建議合適的圖表: "圖表建議：圖表類型、欄位配置與選用理由",
      整理成可閱讀的報告: "分析報告：摘要、發現、限制與建議",
    };
    return buildStructuredPrompt({
      role: "你是一名嚴謹的資料分析與表格品質檢查助理，擅長資料剖析、統計說明與異常辨識。",
      context: `我將提供 Excel 或表格資料。資料背景：${notes}。`,
      task: `先確認欄位、資料範圍與品質，再完成：${joinChinese(requested)}。`,
      rules: [
        "不得修改、覆寫或刪除原始數據；所有整理與計算都應保留可追溯性。",
        "清楚區分原始數據、計算結果與分析推論，不得將推論寫成原始資料事實。",
        "缺失值需明確說明；異常值只能標記，不可自行刪除或替換。",
        "統計結果需說明使用欄位、樣本範圍、計算方法與必要限制。",
        "不得因相關性直接宣稱因果；數據不足時不得過度推論。",
      ],
      output: [...requested.map((action) => outputMap[action] || action), "資料品質問題與分析限制", "需要使用者確認或補充的資料"],
      validation: [
        "檢查並回報缺失值、重複值、格式異常與明顯離群值。",
        "檢查欄位型態、日期、數值與單位是否一致。",
        "確認每項計算結果可回溯至使用的欄位、範圍與方法。",
        "確認原始資料、計算結果與推論已清楚分離。",
      ],
    });
  };

  const buildEngineeringPrompt = (formData) => {
    const system = normalizeInput(formData.get("engineering-system"), "尚未提供");
    const device = normalizeInput(formData.get("engineering-device"), "尚未提供");
    const symptom = normalizeInput(formData.get("engineering-symptom"), "尚未提供");
    const checks = normalizeInput(formData.get("engineering-checks"), "尚未進行或尚未提供");
    return buildStructuredPrompt({
      role: "你是一名審慎的工程故障分析與系統診斷助理，擅長將已知事實、可能原因與驗證步驟分開呈現。",
      context: `系統類型：${system}\n設備：${device}\n問題現象：${symptom}\n已做過的檢查：${checks}`,
      task: "根據目前資訊分析問題，建立可安全執行、可逐步驗證的故障排查方向；資訊不足時明確指出，不可自行假設。",
      rules: [
        "【已知事實】只列使用者提供或可直接確認的資訊；不得把假設、常見情況或可能性寫成已確認故障。",
        "不得自行假設設備型號、韌體版本、配線方式或系統架構。",
        "【可能原因】依合理性與優先度排序，每個推測都需說明依據並附上驗證方式。",
        "【建議檢查步驟】依低風險、高機率、容易驗證，再逐步深入的原則排序。",
        "涉及斷電、拆機、施工、高處、電氣或其他安全風險時，必須先提出安全提醒並建議由合格人員執行。",
        "若操作可能造成服務中斷、資料遺失或告警，應先提醒備份、通知相關人員並確認影響範圍。",
      ],
      output: [
        "1. 已知資訊摘要（Known Facts）",
        "2. 可能原因排序（Possible Causes：依據、優先度、驗證方式）",
        "3. 建議檢查順序（Verification Steps）",
        "4. 每一步的預期驗證結果與下一步判斷",
        "5. 尚缺資訊",
        "6. 風險與服務中斷提醒",
      ],
      validation: [
        "確認已知事實與推測完全分離，沒有將可能原因寫成已確認事實。",
        "確認每個可能原因都有對應的驗證方式與預期結果。",
        "確認所有可能造成服務中斷或安全風險的操作都已明確提醒。",
        "確認已列出會影響判斷的不足資訊與需要補充的資料。",
      ],
    });
  };

  const builders = {
    "image-excel": buildImageExcelPrompt,
    pdf: buildPdfPrompt,
    meeting: buildMeetingPrompt,
    email: buildEmailPrompt,
    "excel-analysis": buildExcelAnalysisPrompt,
    engineering: buildEngineeringPrompt,
  };

  const globalObject = typeof window === "undefined" ? globalThis : window;
  globalObject.OfficeAIPromptBuilders = {
    builders,
    buildSection,
    normalizeInput,
    buildImageExcelPrompt,
    buildPdfPrompt,
    buildMeetingPrompt,
    buildEmailPrompt,
    buildExcelAnalysisPrompt,
    buildEngineeringPrompt,
  };
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
