(() => {
  "use strict";

  const knowledge = JSON.parse(document.getElementById("knowledge-data").textContent);
  const questions = JSON.parse(document.getElementById("question-data").textContent);
  const views = [...document.querySelectorAll(".view")];
  let currentLesson = 0;
  let currentQuestion = 0;
  let selectedAnswer = "";
  let answered = false;

  const text = (value, fallback = "內容整理中") => {
    if (typeof value !== "string") return fallback;
    return value.trim() || fallback;
  };

  const escapeHtml = (value) => text(value, "").replace(/[&<>'"]/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "'": "&#39;",
    '"': "&quot;",
  })[character]);

  const listHtml = (items, fallback = "內容整理中") => {
    const values = Array.isArray(items) ? items.filter(Boolean) : [];
    return `<ul>${(values.length ? values : [fallback]).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
  };

  const sourceHtml = (sources) => {
    const values = Array.isArray(sources) ? sources : [];
    if (!values.length) return '<span>來源整理中</span>';
    return values.map((source) => {
      const id = escapeHtml(source.source_id || "資料來源");
      const section = escapeHtml(source.section || "未標示章節");
      const locator = source.locator ? ` · ${escapeHtml(source.locator)}` : "";
      return `<span><strong>${id}</strong>｜${section}${locator}</span>`;
    }).join("");
  };

  function showView(name, updateHash = true) {
    const target = document.querySelector(`[data-view="${name}"]`);
    if (!target) return;
    views.forEach((view) => view.classList.toggle("is-active", view === target));
    if (updateHash) history.replaceState(null, "", `#${name}`);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function renderLessonList() {
    const container = document.getElementById("lesson-list");
    container.innerHTML = knowledge.map((item, index) => `
      <button class="lesson-row" type="button" data-lesson-index="${index}">
        <span class="lesson-number">${index + 1}</span>
        <span><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.knowledge_id || "L111 知識點")}</small></span>
        <span class="arrow" aria-hidden="true">→</span>
      </button>
    `).join("");
  }

  function renderLesson(index) {
    if (!knowledge[index]) return;
    currentLesson = index;
    const item = knowledge[index];
    document.getElementById("lesson-detail").innerHTML = `
      <button class="back-link" type="button" data-view-target="learn">← 返回知識點列表</button>
      <article class="lesson-card">
        <div class="lesson-topline">
          <span class="lesson-counter">L111 · ${index + 1} / ${knowledge.length}</span>
          <span class="course-pill">${escapeHtml(item.knowledge_id || "知識點")}</span>
        </div>
        <h2>${escapeHtml(item.title)}</h2>
        <section class="detail-block"><h3>定義</h3><p>${escapeHtml(item.definition)}</p></section>
        <section class="detail-block"><h3>白話解釋</h3><p>${escapeHtml(item.plain_explanation)}</p></section>
        <section class="detail-block"><h3>重點</h3>${listHtml(item.key_points)}</section>
        <section class="detail-block confusion"><h3>常見混淆</h3>${listHtml(item.common_confusions, "目前無補充")}</section>
        <section class="detail-block"><h3>來源</h3><div class="source-list">${sourceHtml(item.source_references)}</div></section>
        <nav class="lesson-nav" aria-label="知識點導覽">
          <button class="button" type="button" data-lesson-nav="previous" ${index === 0 ? "disabled" : ""}>← 上一頁</button>
          <button class="button" type="button" data-view-target="learn">返回列表</button>
          <button class="button button-primary" type="button" data-lesson-nav="next" ${index === knowledge.length - 1 ? "disabled" : ""}>下一頁 →</button>
        </nav>
      </article>
    `;
    showView("lesson");
  }

  function renderCheatsheet() {
    document.getElementById("cheatsheet-list").innerHTML = knowledge.map((item, index) => `
      <article class="cheat-card">
        <header><span class="lesson-number">${index + 1}</span><h3>${escapeHtml(item.title)}</h3></header>
        ${listHtml(item.key_points)}
      </article>
    `).join("");
  }

  function startQuiz() {
    currentQuestion = 0;
    selectedAnswer = "";
    answered = false;
    document.getElementById("quiz-intro").classList.add("is-hidden");
    document.getElementById("quiz-stage").classList.remove("is-hidden");
    renderQuestion();
  }

  function renderQuestion() {
    const stage = document.getElementById("quiz-stage");
    const question = questions[currentQuestion];
    if (!question) {
      stage.innerHTML = `
        <div class="empty-state">
          <span aria-hidden="true">🎉</span><h3>你完成 L111 測驗了！</h3>
          <p>已完成全部 ${questions.length} 題。可以回到重點整理，再複習一次核心觀念。</p>
          <button class="button" type="button" data-view-target="cheatsheet">查看重點</button>
          <button class="button button-primary" type="button" id="restart-quiz">再測一次</button>
        </div>`;
      return;
    }

    selectedAnswer = "";
    answered = false;
    const options = Object.entries(question.options || {});
    stage.innerHTML = `
      <div class="quiz-topline">
        <span class="quiz-counter">第 ${currentQuestion + 1} 題 / 共 ${questions.length} 題</span>
        <span class="quiz-progress" aria-hidden="true"><i style="width:${((currentQuestion + 1) / questions.length) * 100}%"></i></span>
      </div>
      <h2 class="quiz-question">${escapeHtml(question.question)}</h2>
      <div class="option-list" role="radiogroup" aria-label="答案選項">
        ${options.map(([key, value]) => `<button class="option-button" type="button" role="radio" aria-checked="false" data-answer="${escapeHtml(key)}"><span class="option-key">${escapeHtml(key)}</span><span>${escapeHtml(value)}</span></button>`).join("")}
      </div>
      <div id="quiz-feedback"></div>
      <div class="quiz-actions"><button class="button button-primary" type="button" id="submit-answer" disabled>送出答案</button></div>
    `;
  }

  function submitAnswer() {
    if (!selectedAnswer || answered) return;
    answered = true;
    const question = questions[currentQuestion];
    const correct = selectedAnswer === question.correct_answer;
    document.querySelectorAll(".option-button").forEach((button) => { button.disabled = true; });
    document.getElementById("submit-answer").remove();
    document.getElementById("quiz-feedback").innerHTML = `
      <section class="quiz-result ${correct ? "" : "is-wrong"}" aria-live="polite">
        <h3>${correct ? "答對了！做得很好 🎉" : "這題答錯了，再記一次重點 💡"}</h3>
        <p>${escapeHtml(question.explanation)}</p>
        <div class="source-list"><strong>來源</strong>${sourceHtml(question.source_references)}</div>
        <button class="button button-primary" type="button" id="next-question">${currentQuestion === questions.length - 1 ? "查看完成畫面" : "下一題 →"}</button>
      </section>`;
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

    const lessonControl = event.target.closest("[data-lesson-index]");
    if (lessonControl) {
      renderLesson(Number(lessonControl.dataset.lessonIndex));
      return;
    }

    const lessonNav = event.target.closest("[data-lesson-nav]");
    if (lessonNav && !lessonNav.disabled) {
      renderLesson(currentLesson + (lessonNav.dataset.lessonNav === "next" ? 1 : -1));
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
  });

  renderLessonList();
  renderCheatsheet();
  const initialView = location.hash.slice(1);
  showView(["home", "learn", "quiz", "cheatsheet", "mistakes", "progress"].includes(initialView) ? initialView : "home", false);
})();
