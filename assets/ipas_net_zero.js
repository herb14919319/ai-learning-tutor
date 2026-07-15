(() => {
  "use strict";

  const body = document.body;
  const chapters = JSON.parse(document.getElementById("chapter-data").textContent);
  const questions = JSON.parse(document.getElementById("question-data").textContent);
  const answerUrl = body.dataset.answerUrl;
  const cardUrlTemplate = body.dataset.cardUrlTemplate;
  const views = [...document.querySelectorAll(".view")];
  let currentChapter = 0;
  let currentQuestion = 0;
  let selectedAnswer = "";
  let answered = false;

  const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "'": "&#39;",
    '"': "&quot;",
  })[character]);

  const inlineMarkdown = (value) => escapeHtml(value)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/__([^_]+)__/g, "<strong>$1</strong>")
    .replace(/\[([^\]]+)]\((?:https?:\/\/)?[^)]+\)/g, "$1");

  const tableCells = (line) => line.trim().replace(/^\||\|$/g, "").split("|").map((cell) => cell.trim());

  function markdownToHtml(markdown) {
    const lines = String(markdown ?? "").replace(/\r\n?/g, "\n").split("\n");
    const output = [];
    let index = 0;

    while (index < lines.length) {
      const line = lines[index];
      if (!line.trim()) {
        index += 1;
        continue;
      }

      if (/^```/.test(line.trim())) {
        const code = [];
        index += 1;
        while (index < lines.length && !/^```/.test(lines[index].trim())) {
          code.push(lines[index]);
          index += 1;
        }
        index += index < lines.length ? 1 : 0;
        output.push(`<pre><code>${escapeHtml(code.join("\n"))}</code></pre>`);
        continue;
      }

      const heading = line.match(/^(#{1,4})\s+(.+)$/);
      if (heading) {
        const level = Math.min(heading[1].length + 1, 5);
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
        index += 2;
        const rows = [];
        while (index < lines.length && lines[index].includes("|") && lines[index].trim()) {
          rows.push(tableCells(lines[index]));
          index += 1;
        }
        output.push(`<div class="markdown-table-wrap"><table><thead><tr>${headers.map((cell) => `<th>${inlineMarkdown(cell)}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${row.map((cell) => `<td>${inlineMarkdown(cell)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`);
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
      while (index < lines.length && lines[index].trim() && !/^(#{1,4})\s+|^```|^\s*[-+*]\s+|^\s*\d+[.)]\s+|^\s*>/.test(lines[index])) {
        if (lines[index].includes("|") && index + 1 < lines.length && /^\s*\|?\s*:?-{3,}/.test(lines[index + 1])) break;
        paragraph.push(lines[index].trim());
        index += 1;
      }
      output.push(`<p>${paragraph.map(inlineMarkdown).join("<br>")}</p>`);
    }

    return output.join("");
  }

  const sourceHtml = (sources) => {
    const values = Array.isArray(sources) ? sources : [];
    if (!values.length) return "<span>來源整理中</span>";
    return values.map((source) => `<span><strong>${escapeHtml(source.source_id || "資料來源")}</strong>｜${escapeHtml(source.section || "未標示章節")}${source.locator ? ` · ${escapeHtml(source.locator)}` : ""}</span>`).join("");
  };

  function showView(name, hash = name) {
    const target = document.querySelector(`[data-view="${name}"]`);
    if (!target) return;
    views.forEach((view) => view.classList.toggle("is-active", view === target));
    if (hash) history.replaceState(null, "", `#${hash}`);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function cardUrl(path) {
    const relative = String(path || "").replace(/^cards\//, "");
    const encoded = relative.split("/").map(encodeURIComponent).join("/");
    return cardUrlTemplate.replace("__CARD__", encoded);
  }

  function renderChapterList(query = "") {
    const normalized = query.trim().toLocaleLowerCase("zh-Hant");
    const matches = chapters.filter((chapter) => {
      if (!normalized) return true;
      return [chapter.title, chapter.summary, ...(chapter.headings || []), chapter.markdown]
        .join(" ")
        .toLocaleLowerCase("zh-Hant")
        .includes(normalized);
    });
    document.getElementById("chapter-list").innerHTML = matches.length
      ? matches.map((chapter) => `
        <button class="lesson-row" type="button" data-open-chapter="${escapeHtml(chapter.chapter_id)}">
          <span class="lesson-number">${chapter.chapter_number}</span>
          <span><strong>${escapeHtml(chapter.title)}</strong><small>${escapeHtml(chapter.summary)} · 圖卡 ${(chapter.cards || []).length} 張</small></span>
          <span class="arrow" aria-hidden="true">→</span>
        </button>`).join("")
      : '<div class="net-zero-no-results"><strong>找不到符合的章節</strong><span>請換一個關鍵字再試一次。</span></div>';
    document.getElementById("search-status").textContent = normalized
      ? `找到 ${matches.length} 個符合章節`
      : `共 ${chapters.length} 章`;
  }

  function renderChapter(chapterId) {
    const index = chapters.findIndex((chapter) => chapter.chapter_id === chapterId);
    if (index < 0) return;
    currentChapter = index;
    const chapter = chapters[index];
    const cards = Array.isArray(chapter.cards) ? chapter.cards : [];
    document.getElementById("chapter-detail").innerHTML = `
      <button class="back-link" type="button" data-view-target="chapters">← 返回章節列表</button>
      <article class="lesson-card net-zero-lesson">
        <div class="lesson-topline">
          <span class="lesson-counter">${escapeHtml(chapter.chapter_id.toUpperCase())} · ${index + 1} / ${chapters.length}</span>
          <span class="course-pill">圖卡 ${cards.length} 張</span>
        </div>
        <h2>${escapeHtml(chapter.title)}</h2>
        <p class="net-zero-summary">${escapeHtml(chapter.summary)}</p>
        <section class="detail-block"><h3>教材內容</h3><div class="markdown-body">${markdownToHtml(chapter.markdown)}</div></section>
        <section class="detail-block"><h3>章節圖卡</h3>
          ${cards.length ? `<div class="net-zero-card-grid">${cards.map((path, cardIndex) => `
            <figure class="net-zero-study-card">
              <img src="${cardUrl(path)}" alt="${escapeHtml(chapter.title)}圖卡 ${cardIndex + 1}" loading="lazy">
              <figcaption>${escapeHtml(chapter.chapter_id.toUpperCase())} 圖卡 ${cardIndex + 1}</figcaption>
            </figure>`).join("")}</div>` : '<p class="net-zero-muted">本章目前沒有圖卡。</p>'}
        </section>
        <section class="detail-block"><h3>來源追溯</h3><div class="source-list"><span><strong>${escapeHtml(chapter.chapter_id.toUpperCase())}</strong>｜${escapeHtml(chapter.title)} · ${escapeHtml(chapter.source_path)}</span></div></section>
        <nav class="lesson-nav" aria-label="章節導覽">
          <button class="button" type="button" data-chapter-nav="previous" ${index === 0 ? "disabled" : ""}>← 上一章</button>
          <button class="button" type="button" data-view-target="chapters">返回列表</button>
          <button class="button button-primary" type="button" data-chapter-nav="next" ${index === chapters.length - 1 ? "disabled" : ""}>下一章 →</button>
        </nav>
      </article>`;
    showView("lesson", `chapter-${chapter.chapter_id}`);
  }

  function startQuiz() {
    currentQuestion = 0;
    document.getElementById("quiz-intro").classList.add("is-hidden");
    document.getElementById("quiz-stage").classList.remove("is-hidden");
    renderQuestion();
  }

  function renderQuestion() {
    const stage = document.getElementById("quiz-stage");
    const question = questions[currentQuestion];
    if (!question) {
      stage.innerHTML = `<div class="empty-state"><span aria-hidden="true">🎉</span><h3>你完成淨零碳章節測驗了！</h3><p>已完成全部 ${questions.length} 題，可以回到章節列表繼續複習。</p><button class="button" type="button" data-view-target="chapters">查看章節</button><button class="button button-primary" type="button" id="restart-quiz">再測一次</button></div>`;
      return;
    }
    selectedAnswer = "";
    answered = false;
    stage.innerHTML = `
      <div class="quiz-topline"><span class="quiz-counter">第 ${currentQuestion + 1} 題 / 共 ${questions.length} 題</span><span class="quiz-progress" aria-hidden="true"><i style="width:${((currentQuestion + 1) / questions.length) * 100}%"></i></span></div>
      <h2 class="quiz-question">${escapeHtml(question.question)}</h2>
      <div class="option-list" role="radiogroup" aria-label="答案選項">${Object.entries(question.options || {}).map(([key, value]) => `<button class="option-button" type="button" role="radio" aria-checked="false" data-answer="${escapeHtml(key)}"><span class="option-key">${escapeHtml(key)}</span><span>${escapeHtml(value)}</span></button>`).join("")}</div>
      <div id="quiz-feedback" aria-live="polite"></div>
      <div class="quiz-actions"><button class="button button-primary" type="button" id="submit-answer" disabled>送出答案</button></div>`;
  }

  async function submitAnswer() {
    if (!selectedAnswer || answered) return;
    answered = true;
    const submit = document.getElementById("submit-answer");
    submit.disabled = true;
    submit.textContent = "批改中…";
    try {
      const response = await fetch(answerUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Accept": "application/json" },
        body: JSON.stringify({ question_id: questions[currentQuestion].question_id, answer: selectedAnswer }),
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok) throw new Error(payload.message || "批改失敗");
      document.querySelectorAll(".option-button").forEach((button) => {
        button.disabled = true;
        button.classList.toggle("is-correct", button.dataset.answer === payload.correct_answer);
        button.classList.toggle("is-wrong", button.dataset.answer === selectedAnswer && !payload.correct);
      });
      submit.remove();
      document.getElementById("quiz-feedback").innerHTML = `
        <section class="quiz-result ${payload.correct ? "" : "is-wrong"}">
          <h3>${payload.correct ? "答對了！做得很好 🎉" : "這題答錯了，再記一次重點 💡"}</h3>
          <p>正確答案：${escapeHtml(payload.correct_answer)}</p>
          <p>${escapeHtml(payload.explanation)}</p>
          <div class="source-list"><strong>來源</strong>${sourceHtml(payload.source_references)}</div>
          <button class="button button-primary" type="button" id="next-question">${currentQuestion === questions.length - 1 ? "查看完成畫面" : "下一題 →"}</button>
        </section>`;
    } catch (error) {
      answered = false;
      submit.disabled = false;
      submit.textContent = "重新送出";
      document.getElementById("quiz-feedback").innerHTML = `<p class="net-zero-api-error" role="alert">${escapeHtml(error.message || "批改失敗，請稍後再試。")}</p>`;
    }
  }

  document.addEventListener("click", (event) => {
    const viewControl = event.target.closest("[data-view-target]");
    if (viewControl) {
      showView(viewControl.dataset.viewTarget);
      return;
    }
    const brandControl = event.target.closest("[data-view-link]");
    if (brandControl) {
      event.preventDefault();
      showView(brandControl.dataset.viewLink);
      return;
    }
    const chapterControl = event.target.closest("[data-open-chapter]");
    if (chapterControl) {
      renderChapter(chapterControl.dataset.openChapter);
      return;
    }
    const chapterNav = event.target.closest("[data-chapter-nav]");
    if (chapterNav && !chapterNav.disabled) {
      renderChapter(chapters[currentChapter + (chapterNav.dataset.chapterNav === "next" ? 1 : -1)].chapter_id);
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
    if (event.target.closest("#next-question")) {
      currentQuestion += 1;
      renderQuestion();
    }
    if (event.target.closest("#clear-search")) {
      const input = document.getElementById("chapter-search");
      input.value = "";
      renderChapterList();
      input.focus();
    }
  });

  document.addEventListener("error", (event) => {
    if (!event.target.matches(".net-zero-study-card img")) return;
    event.target.hidden = true;
    const placeholder = document.createElement("div");
    placeholder.className = "net-zero-card-missing";
    placeholder.textContent = "圖卡暫時無法載入";
    event.target.before(placeholder);
  }, true);

  document.getElementById("chapter-search").addEventListener("input", (event) => renderChapterList(event.target.value));
  renderChapterList();

  const initialHash = location.hash.slice(1);
  if (/^chapter-ch0[1-8]$/.test(initialHash)) {
    renderChapter(initialHash.replace("chapter-", ""));
  } else {
    showView(["home", "chapters", "quiz"].includes(initialHash) ? initialHash : "home", "");
  }
})();
