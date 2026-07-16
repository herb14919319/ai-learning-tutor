(() => {
  "use strict";

  const STORAGE = {
    read: "ipas_ai_planner_v1_read_chapters",
    results: "ipas_ai_planner_v1_quiz_results",
    completed: "ipas_ai_planner_v1_quiz_completed",
  };
  const answerUrl = document.body.dataset.answerUrl;
  const views = [...document.querySelectorAll(".view")];

  const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "'": "&#39;",
    '"': "&quot;",
  })[character]);

  function parseEmbeddedJson(id, fallback) {
    try {
      const element = document.getElementById(id);
      return element ? JSON.parse(element.textContent) : fallback;
    } catch (_error) {
      return fallback;
    }
  }

  const course = parseEmbeddedJson("course-data", {});
  const chapters = parseEmbeddedJson("chapter-data", []);
  const questions = parseEmbeddedJson("question-data", []);

  function loadStored(key, fallback, validator) {
    try {
      const raw = localStorage.getItem(key);
      if (raw === null) return fallback;
      const value = JSON.parse(raw);
      if (!validator(value)) throw new Error("invalid stored value");
      return value;
    } catch (_error) {
      try { localStorage.removeItem(key); } catch (_storageError) { /* storage unavailable */ }
      return fallback;
    }
  }

  function saveStored(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch (_error) { /* storage unavailable */ }
  }

  const readChapters = new Set(loadStored(STORAGE.read, [], Array.isArray).filter((value) => typeof value === "string"));
  const completedQuizzes = new Set(loadStored(STORAGE.completed, [], Array.isArray).filter((value) => typeof value === "string"));
  const storedResults = loadStored(STORAGE.results, {}, (value) => value && typeof value === "object" && !Array.isArray(value));
  const quizResults = Object.fromEntries(Object.entries(storedResults).filter(([, value]) => value && typeof value === "object"));

  let currentChapter = 0;
  let activeQuizChapterId = chapters[0]?.chapter_id || "";
  let activeQuestions = [];
  let currentQuestion = 0;
  let selectedAnswer = "";
  let answered = false;

  const inlineMarkdown = (value) => escapeHtml(value)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/__([^_]+)__/g, "<strong>$1</strong>")
    .replace(/\[([^\]]+)]\([^)]+\)/g, "$1");

  const tableCells = (line) => line.trim().replace(/^\||\|$/g, "").split("|").map((cell) => cell.trim());

  function markdownToHtml(markdown) {
    const lines = String(markdown ?? "").replace(/\r\n?/g, "\n").split("\n");
    const output = [];
    let index = 0;
    while (index < lines.length) {
      const line = lines[index];
      if (!line.trim()) { index += 1; continue; }
      if (/^```/.test(line.trim())) {
        const code = [];
        index += 1;
        while (index < lines.length && !/^```/.test(lines[index].trim())) {
          code.push(lines[index]);
          index += 1;
        }
        if (index < lines.length) index += 1;
        output.push(`<pre><code>${escapeHtml(code.join("\n"))}</code></pre>`);
        continue;
      }
      const heading = line.match(/^(#{1,6})\s+(.+)$/);
      if (heading) {
        const level = Math.min(heading[1].length + 1, 6);
        output.push(`<h${level}>${inlineMarkdown(heading[2])}</h${level}>`);
        index += 1;
        continue;
      }
      if (/^\s*([-*_])(?:\s*\1){2,}\s*$/.test(line)) {
        output.push("<hr>");
        index += 1;
        continue;
      }
      if (line.includes("|") && index + 1 < lines.length && /^\s*\|?\s*:?-{3,}/.test(lines[index + 1])) {
        const headers = tableCells(line);
        const rows = [];
        index += 2;
        while (index < lines.length && lines[index].includes("|") && lines[index].trim()) {
          rows.push(tableCells(lines[index]));
          index += 1;
        }
        output.push(`<div><table><thead><tr>${headers.map((cell) => `<th>${inlineMarkdown(cell)}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${row.map((cell) => `<td>${inlineMarkdown(cell)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`);
        continue;
      }
      if (/^\s*>/.test(line)) {
        const quote = [];
        while (index < lines.length && /^\s*>/.test(lines[index])) {
          quote.push(lines[index].replace(/^\s*>\s?/, ""));
          index += 1;
        }
        output.push(`<blockquote>${quote.map(inlineMarkdown).join("<br>")}</blockquote>`);
        continue;
      }
      if (/^\s*[-+*]\s+/.test(line)) {
        const items = [];
        while (index < lines.length && /^\s*[-+*]\s+/.test(lines[index])) {
          items.push(lines[index].replace(/^\s*[-+*]\s+/, ""));
          index += 1;
        }
        output.push(`<ul>${items.map((item) => `<li>${inlineMarkdown(item)}</li>`).join("")}</ul>`);
        continue;
      }
      if (/^\s*\d+[.)]\s+/.test(line)) {
        const items = [];
        while (index < lines.length && /^\s*\d+[.)]\s+/.test(lines[index])) {
          items.push(lines[index].replace(/^\s*\d+[.)]\s+/, ""));
          index += 1;
        }
        output.push(`<ol>${items.map((item) => `<li>${inlineMarkdown(item)}</li>`).join("")}</ol>`);
        continue;
      }
      const paragraph = [line.trim()];
      index += 1;
      while (index < lines.length && lines[index].trim() && !/^(#{1,6})\s+|^```|^\s*[-+*]\s+|^\s*\d+[.)]\s+|^\s*>/.test(lines[index])) {
        if (lines[index].includes("|") && index + 1 < lines.length && /^\s*\|?\s*:?-{3,}/.test(lines[index + 1])) break;
        paragraph.push(lines[index].trim());
        index += 1;
      }
      output.push(`<p>${paragraph.map(inlineMarkdown).join("<br>")}</p>`);
    }
    return output.join("");
  }

  function questionsForChapter(chapterId) {
    return questions.filter((question) => question.chapter_id === chapterId);
  }

  function chapterById(chapterId) {
    return chapters.find((chapter) => chapter.chapter_id === chapterId);
  }

  function showView(name, hash = name) {
    const target = document.querySelector(`[data-view="${name}"]`);
    if (!target) return;
    views.forEach((view) => view.classList.toggle("is-active", view === target));
    if (hash) history.replaceState(null, "", `#${hash}`);
    if (name === "learn") renderChapterList();
    if (name === "cheatsheet") renderCheatsheet();
    if (name === "mistakes") renderMistakes();
    if (name === "progress" || name === "home") renderProgress();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function persistProgress() {
    saveStored(STORAGE.read, [...readChapters]);
    saveStored(STORAGE.completed, [...completedQuizzes]);
    saveStored(STORAGE.results, quizResults);
  }

  function renderChapterList() {
    const container = document.getElementById("lesson-list");
    if (!container) return;
    if (!chapters.length) {
      container.innerHTML = '<div class="empty-state"><span aria-hidden="true">📚</span><h3>目前沒有可閱讀的章節</h3><p>請稍後重新載入課程。</p></div>';
      return;
    }
    container.innerHTML = chapters.map((chapter) => {
      const read = readChapters.has(chapter.chapter_id);
      const tested = completedQuizzes.has(chapter.chapter_id);
      const status = read && tested ? "已完成" : read ? "已閱讀" : tested ? "測驗完成" : "尚未開始";
      return `
        <button class="lesson-row" type="button" data-open-chapter="${escapeHtml(chapter.chapter_id)}">
          <span class="lesson-number">${escapeHtml(chapter.order)}</span>
          <span><strong>${escapeHtml(chapter.title)}</strong><small>${escapeHtml(chapter.chapter_id)} · ${escapeHtml(chapter.lesson_code)} · ${status} · ${escapeHtml(chapter.question_count)} 題</small></span>
          <span class="arrow" aria-hidden="true">→</span>
        </button>`;
    }).join("");
  }

  function renderChapter(chapterId) {
    const index = chapters.findIndex((chapter) => chapter.chapter_id === chapterId);
    if (index < 0) return;
    currentChapter = index;
    const chapter = chapters[index];
    readChapters.add(chapter.chapter_id);
    persistProgress();
    document.getElementById("lesson-detail").innerHTML = `
      <button class="back-link" type="button" data-view-target="learn">← 返回七章目錄</button>
      <article class="lesson-card">
        <div class="lesson-topline"><span class="lesson-counter">${escapeHtml(chapter.chapter_id)} · ${index + 1} / ${chapters.length}</span><span class="course-pill">${escapeHtml(chapter.lesson_code)}</span></div>
        <h2>${escapeHtml(chapter.title)}</h2>
        <section class="detail-block"><h3>正式教材</h3><div class="markdown-body">${markdownToHtml(chapter.content_markdown)}</div></section>
        <nav class="lesson-nav" aria-label="章節導覽">
          <button class="button" type="button" data-chapter-nav="previous" ${index === 0 ? "disabled" : ""}>← 上一章</button>
          <button class="button" type="button" data-view-target="learn">返回目錄</button>
          <button class="button button-primary" type="button" data-quiz-chapter="${escapeHtml(chapter.chapter_id)}">進行本章測驗</button>
          <button class="button" type="button" data-chapter-nav="next" ${index === chapters.length - 1 ? "disabled" : ""}>下一章 →</button>
        </nav>
      </article>`;
    renderProgress();
    showView("lesson", `chapter-${chapter.chapter_id}`);
  }

  function extractReviewMarkdown(markdown) {
    const lines = String(markdown || "").split(/\r?\n/);
    const wanted = /本章重點整理|關鍵名詞|學習重點/;
    const sections = [];
    for (let index = 0; index < lines.length; index += 1) {
      const heading = lines[index].match(/^(#{1,6})\s+(.+)$/);
      if (!heading || !wanted.test(heading[2])) continue;
      const level = heading[1].length;
      const section = [lines[index]];
      index += 1;
      while (index < lines.length) {
        const nextHeading = lines[index].match(/^(#{1,6})\s+/);
        if (nextHeading && nextHeading[1].length <= level) { index -= 1; break; }
        section.push(lines[index]);
        index += 1;
      }
      sections.push(section.join("\n"));
    }
    return sections.join("\n\n");
  }

  function renderCheatsheet() {
    const container = document.getElementById("cheatsheet-list");
    if (!container) return;
    if (!chapters.length) {
      container.innerHTML = '<div class="empty-state"><span aria-hidden="true">📖</span><h3>目前沒有重點內容</h3></div>';
      return;
    }
    container.innerHTML = chapters.map((chapter) => {
      const review = extractReviewMarkdown(chapter.content_markdown);
      return `<article class="cheat-card"><header><span class="lesson-number">${escapeHtml(chapter.order)}</span><h3>${escapeHtml(chapter.title)}</h3></header><div class="markdown-body">${review ? markdownToHtml(review) : "<p>本章重點請至正式教材查看。</p>"}</div><button class="button" type="button" data-open-chapter="${escapeHtml(chapter.chapter_id)}">閱讀本章</button></article>`;
    }).join("");
  }

  function prepareQuiz(chapterId, startImmediately = false, questionId = "") {
    const chapter = chapterById(chapterId) || chapters[0];
    if (!chapter) return;
    activeQuizChapterId = chapter.chapter_id;
    activeQuestions = questionsForChapter(activeQuizChapterId);
    currentQuestion = questionId ? Math.max(0, activeQuestions.findIndex((item) => item.question_id === questionId)) : 0;
    selectedAnswer = "";
    answered = false;
    document.getElementById("quiz-chapter-code").textContent = `${chapter.chapter_id} · ${chapter.lesson_code}`;
    document.getElementById("quiz-title").textContent = `${chapter.title}章末測驗`;
    document.getElementById("quiz-intro-copy").textContent = activeQuestions.length
      ? `本章共 ${activeQuestions.length} 題。送出後由後端批改，再顯示正確答案與說明。`
      : "本章目前沒有可用題目。";
    document.getElementById("quiz-intro").classList.toggle("is-hidden", startImmediately);
    document.getElementById("quiz-stage").classList.toggle("is-hidden", !startImmediately);
    showView("quiz", `quiz-${chapter.chapter_id}`);
    if (startImmediately) renderQuestion();
  }

  function startQuiz() {
    currentQuestion = 0;
    document.getElementById("quiz-intro").classList.add("is-hidden");
    document.getElementById("quiz-stage").classList.remove("is-hidden");
    renderQuestion();
  }

  function renderQuestion() {
    const stage = document.getElementById("quiz-stage");
    const chapter = chapterById(activeQuizChapterId);
    const question = activeQuestions[currentQuestion];
    selectedAnswer = "";
    answered = false;
    if (!activeQuestions.length) {
      stage.innerHTML = '<div class="empty-state"><span aria-hidden="true">📝</span><h3>本章目前沒有題目</h3><p>請返回七章目錄選擇其他章節。</p><button class="button" type="button" data-view-target="learn">返回目錄</button></div>';
      return;
    }
    if (!question) {
      const correctCount = activeQuestions.filter((item) => quizResults[item.question_id]?.correct).length;
      stage.innerHTML = `<div class="empty-state"><span aria-hidden="true">🎉</span><h3>完成 ${escapeHtml(chapter?.title || "本章")}測驗</h3><p>本章 ${activeQuestions.length} 題，目前答對 ${correctCount} 題。可重新測驗或繼續下一章。</p><button class="button" type="button" data-view-target="learn">查看七章</button><button class="button button-primary" type="button" id="restart-quiz">再測一次</button></div>`;
      return;
    }
    stage.innerHTML = `
      <div class="quiz-topline"><span class="quiz-counter">${escapeHtml(chapter?.lesson_code || "")} · 第 ${currentQuestion + 1} 題 / 共 ${activeQuestions.length} 題</span><span class="quiz-progress" aria-hidden="true"><i style="width:${((currentQuestion + 1) / activeQuestions.length) * 100}%"></i></span></div>
      <h2 class="quiz-question">${escapeHtml(question.question_text)}</h2>
      <div class="option-list" role="radiogroup" aria-label="答案選項">${Object.entries(question.options || {}).map(([key, value]) => `<button class="option-button" type="button" role="radio" aria-checked="false" data-answer="${escapeHtml(key)}"><span class="option-key">${escapeHtml(key)}</span><span>${escapeHtml(value)}</span></button>`).join("")}</div>
      <div id="quiz-feedback" aria-live="polite"></div>
      <div class="quiz-actions"><button class="button" type="button" id="previous-question" ${currentQuestion === 0 ? "disabled" : ""}>← 上一題</button><button class="button button-primary" type="button" id="submit-answer" disabled>送出答案</button></div>`;
  }

  async function submitAnswer() {
    if (!selectedAnswer || answered) return;
    const question = activeQuestions[currentQuestion];
    const submit = document.getElementById("submit-answer");
    answered = true;
    submit.disabled = true;
    submit.textContent = "批改中…";
    try {
      const response = await fetch(answerUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Accept": "application/json" },
        body: JSON.stringify({ question_id: question.question_id, answer: selectedAnswer }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || !payload.ok) throw new Error(payload.message || "批改失敗，請稍後再試。");
      const previous = quizResults[question.question_id] || {};
      quizResults[question.question_id] = {
        selected_answer: selectedAnswer,
        correct: Boolean(payload.correct),
        attempts: Number(previous.attempts || 0) + 1,
        ever_wrong: Boolean(previous.ever_wrong) || !payload.correct,
        resolved: Boolean(previous.ever_wrong) && Boolean(payload.correct),
      };
      if (activeQuestions.every((item) => quizResults[item.question_id])) completedQuizzes.add(activeQuizChapterId);
      persistProgress();
      document.querySelectorAll(".option-button").forEach((button) => { button.disabled = true; });
      submit.remove();
      document.getElementById("quiz-feedback").innerHTML = `
        <section class="quiz-result ${payload.correct ? "" : "is-wrong"}">
          <h3>${payload.correct ? "答對了！做得很好 🎉" : "這題答錯了，再記一次重點 💡"}</h3>
          <p>你的答案：${escapeHtml(selectedAnswer)}；正確答案：${escapeHtml(payload.correct_answer)}</p>
          <p>${escapeHtml(payload.explanation)}</p>
          <nav class="lesson-nav" aria-label="測驗題目導覽"><button class="button" type="button" id="previous-question" ${currentQuestion === 0 ? "disabled" : ""}>← 上一題</button><button class="button button-primary" type="button" id="next-question">${currentQuestion === activeQuestions.length - 1 ? "查看完成畫面" : "下一題 →"}</button></nav>
        </section>`;
      renderProgress();
    } catch (error) {
      answered = false;
      submit.disabled = false;
      submit.textContent = "重新送出";
      document.getElementById("quiz-feedback").innerHTML = `<section class="quiz-result is-wrong" role="alert"><h3>暫時無法批改</h3><p>${escapeHtml(error.message || "網路連線失敗，請稍後再試。")}</p></section>`;
    }
  }

  function renderMistakes() {
    const container = document.getElementById("mistakes-list");
    if (!container) return;
    const mistakes = Object.entries(quizResults).filter(([, result]) => result.ever_wrong);
    if (!mistakes.length) {
      container.innerHTML = '<div class="empty-state"><span aria-hidden="true">🌱</span><h3>目前還沒有錯題紀錄</h3><p>完成任一章測驗後，答錯的題目會出現在這裡。</p><button class="button button-primary" type="button" data-view-target="learn">選擇章節測驗</button></div>';
      return;
    }
    container.innerHTML = `<div class="cheatsheet-grid">${mistakes.map(([questionId, result]) => {
      const question = questions.find((item) => item.question_id === questionId);
      const chapter = question && chapterById(question.chapter_id);
      if (!question) return "";
      return `<article class="cheat-card"><header><span class="lesson-number">${escapeHtml(question.question_number)}</span><h3>${escapeHtml(question.question_text)}</h3></header><p>${escapeHtml(chapter?.lesson_code || question.chapter_id)} · 你的最近答案：${escapeHtml(result.selected_answer || "未記錄")}</p><p>${result.resolved ? "已重新作答並答對" : "尚待重新作答"} · 作答 ${escapeHtml(result.attempts || 1)} 次</p><button class="button button-primary" type="button" data-retry-question="${escapeHtml(question.question_id)}">重新作答</button></article>`;
    }).join("")}</div>`;
  }

  function renderProgress() {
    const totalUnits = Math.max(chapters.length * 2, 1);
    const completedUnits = chapters.reduce((count, chapter) => count + Number(readChapters.has(chapter.chapter_id)) + Number(completedQuizzes.has(chapter.chapter_id)), 0);
    const percent = Math.round((completedUnits / totalUnits) * 100);
    const completedChapters = chapters.filter((chapter) => readChapters.has(chapter.chapter_id) && completedQuizzes.has(chapter.chapter_id)).length;
    const answeredCount = questions.filter((question) => quizResults[question.question_id]).length;
    const correctCount = questions.filter((question) => quizResults[question.question_id]?.correct).length;
    document.getElementById("home-progress-value").textContent = `${percent}%`;
    document.getElementById("home-progress-ring").style.setProperty("--progress", percent);
    document.getElementById("home-progress-copy").textContent = `${completedChapters} / ${chapters.length} 章完成，已作答 ${answeredCount} / ${questions.length} 題。`;
    document.getElementById("course-progress-value").textContent = `${percent}%`;
    document.getElementById("course-progress-bar").style.width = `${percent}%`;
    document.getElementById("course-progress-track").setAttribute("aria-valuenow", String(percent));
    document.getElementById("progress-stats").innerHTML = `<span><strong>${readChapters.size} / ${chapters.length}</strong> 已閱讀章節</span><span><strong>${answeredCount} / ${questions.length}</strong> 已作答題目</span><span><strong>${correctCount}</strong> 最近答對題目</span>`;
    document.getElementById("chapter-progress-list").innerHTML = chapters.map((chapter) => {
      const read = readChapters.has(chapter.chapter_id);
      const quizDone = completedQuizzes.has(chapter.chapter_id);
      const chapterQuestions = questionsForChapter(chapter.chapter_id);
      const answered = chapterQuestions.filter((question) => quizResults[question.question_id]).length;
      const complete = read && quizDone;
      return `<article class="chapter-card ${complete ? "is-completed" : (read || quizDone) ? "is-learning" : ""}"><span class="chapter-state-icon" aria-hidden="true">${complete ? "✓" : escapeHtml(chapter.order)}</span><div class="chapter-content"><div class="chapter-topline"><span>${escapeHtml(chapter.chapter_id)} · ${escapeHtml(chapter.lesson_code)}</span><span class="status-badge ${complete ? "completed-badge" : "learning-badge"}">${complete ? "已完成" : read || quizDone ? "學習中" : "尚未開始"}</span></div><h4>${escapeHtml(chapter.title)}</h4><p>閱讀：${read ? "完成" : "未完成"} · 測驗：${answered} / ${chapterQuestions.length}</p><div class="chapter-progress-row"><span class="chapter-progress-track"><i style="width:${((Number(read) + Number(quizDone)) / 2) * 100}%"></i></span><strong>${Number(read) + Number(quizDone)} / 2</strong></div></div></article>`;
    }).join("");
  }

  function showFatal(message) {
    const shell = document.querySelector(".app-shell");
    shell.innerHTML = `<section class="view is-active"><div class="empty-state" role="alert"><span aria-hidden="true">📚</span><h3>課程無法顯示</h3><p>${escapeHtml(message)}</p></div></section>`;
  }

  document.addEventListener("click", (event) => {
    const viewControl = event.target.closest("[data-view-target]");
    if (viewControl) { showView(viewControl.dataset.viewTarget); return; }
    const brandControl = event.target.closest("[data-view-link]");
    if (brandControl) { event.preventDefault(); showView(brandControl.dataset.viewLink); return; }
    const chapterControl = event.target.closest("[data-open-chapter]");
    if (chapterControl) { renderChapter(chapterControl.dataset.openChapter); return; }
    const chapterNav = event.target.closest("[data-chapter-nav]");
    if (chapterNav && !chapterNav.disabled) {
      const target = chapters[currentChapter + (chapterNav.dataset.chapterNav === "next" ? 1 : -1)];
      if (target) renderChapter(target.chapter_id);
      return;
    }
    const quizControl = event.target.closest("[data-quiz-chapter]");
    if (quizControl) { prepareQuiz(quizControl.dataset.quizChapter); return; }
    const retryControl = event.target.closest("[data-retry-question]");
    if (retryControl) {
      const question = questions.find((item) => item.question_id === retryControl.dataset.retryQuestion);
      if (question) prepareQuiz(question.chapter_id, true, question.question_id);
      return;
    }
    const option = event.target.closest("[data-answer]");
    if (option && !answered) {
      selectedAnswer = option.dataset.answer;
      document.querySelectorAll(".option-button").forEach((button) => {
        const selected = button === option;
        button.classList.toggle("is-selected", selected);
        button.setAttribute("aria-checked", String(selected));
      });
      document.getElementById("submit-answer").disabled = false;
      return;
    }
    if (event.target.closest("#start-quiz") || event.target.closest("#restart-quiz")) startQuiz();
    if (event.target.closest("#submit-answer")) submitAnswer();
    if (event.target.closest("#previous-question") && currentQuestion > 0) { currentQuestion -= 1; renderQuestion(); }
    if (event.target.closest("#next-question")) { currentQuestion += 1; renderQuestion(); }
  });

  if (!Array.isArray(chapters) || !chapters.length) {
    showFatal("目前沒有可載入的正式課程章節，請稍後再試。");
    return;
  }
  if (!Array.isArray(questions)) {
    showFatal("題庫資料格式不正確，請稍後再試。");
    return;
  }
  renderChapterList();
  renderCheatsheet();
  renderMistakes();
  renderProgress();

  const initialHash = location.hash.slice(1);
  const chapterHash = initialHash.match(/^chapter-(CH-0[1-7])$/i);
  const quizHash = initialHash.match(/^quiz-(CH-0[1-7])$/i);
  if (chapterHash) renderChapter(chapterHash[1].toUpperCase());
  else if (quizHash) prepareQuiz(quizHash[1].toUpperCase());
  else if (initialHash === "quiz") prepareQuiz(chapters[0].chapter_id);
  else showView(["home", "learn", "cheatsheet", "mistakes", "progress"].includes(initialHash) ? initialHash : "home", "");
})();
