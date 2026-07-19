(() => {
  "use strict";

  const body = document.body;
  const categoriesUrl = body.dataset.categoriesUrl;
  const parentingScenariosUrl = body.dataset.parentingScenariosUrl;
  const hero = document.querySelector(".hero");
  const categorySection = document.querySelector(".category-section");
  const grid = document.getElementById("category-grid");
  const status = document.getElementById("category-status");
  const parentingView = document.getElementById("parenting-view");
  const parentingStatus = document.getElementById("parenting-status");
  const parentingGrid = document.getElementById("parenting-scenario-grid");
  const promptView = document.getElementById("prompt-view");
  const promptTitle = document.getElementById("prompt-title");
  const promptDescription = document.getElementById("prompt-description");
  const promptContent = document.getElementById("prompt-content");
  const copyPrompt = document.getElementById("copy-prompt");
  const copyFeedback = document.getElementById("copy-feedback");
  const notice = document.getElementById("coming-soon");
  const noticeTitle = document.getElementById("coming-soon-title");
  const dismissNotice = document.getElementById("dismiss-notice");
  let parentingScenarios = null;
  let selectedPrompt = "";

  const showLoadError = () => {
    grid.replaceChildren();
    grid.setAttribute("aria-busy", "false");
    status.textContent = "分類暫時無法載入。";
    status.classList.add("is-error");
  };

  const showComingSoon = (category) => {
    noticeTitle.textContent = `${category.title} · Coming Soon`;
    notice.hidden = false;
    notice.scrollIntoView({ behavior: "smooth", block: "nearest" });
  };

  const showCategories = () => {
    hero.hidden = false;
    categorySection.hidden = false;
    parentingView.hidden = true;
    promptView.hidden = true;
    notice.hidden = true;
    copyFeedback.textContent = "";
  };

  const showParentingScenarios = async () => {
    hero.hidden = true;
    categorySection.hidden = true;
    promptView.hidden = true;
    notice.hidden = true;
    parentingView.hidden = false;
    copyFeedback.textContent = "";

    if (parentingScenarios) {
      return;
    }

    parentingGrid.setAttribute("aria-busy", "true");
    parentingStatus.textContent = "正在載入親子情境…";
    try {
      const response = await fetch(parentingScenariosUrl, {
        headers: { Accept: "application/json" },
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok || !Array.isArray(payload.scenarios)) {
        throw new Error("parenting_scenarios_unavailable");
      }

      parentingScenarios = payload.scenarios;
      parentingGrid.replaceChildren(
        ...parentingScenarios.map(createScenarioCard),
      );
      parentingStatus.textContent = `${parentingScenarios.length} 個親子情境`;
    } catch (_error) {
      parentingGrid.replaceChildren();
      parentingStatus.textContent = "親子情境暫時無法載入。";
      parentingStatus.classList.add("is-error");
    } finally {
      parentingGrid.setAttribute("aria-busy", "false");
    }
  };

  const showPrompt = (scenario) => {
    selectedPrompt = scenario.prompt;
    promptTitle.textContent = scenario.title;
    promptDescription.textContent = scenario.description;
    promptContent.textContent = scenario.prompt;
    copyFeedback.textContent = "";
    parentingView.hidden = true;
    promptView.hidden = false;
    promptTitle.focus();
  };

  const createScenarioCard = (scenario) => {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "scenario-card";
    card.dataset.scenarioId = scenario.id;
    card.setAttribute("aria-label", `${scenario.title}，${scenario.description}`);

    const title = document.createElement("strong");
    title.textContent = scenario.title;

    const description = document.createElement("span");
    description.textContent = scenario.description;

    const action = document.createElement("span");
    action.className = "scenario-action";
    action.textContent = "查看 Prompt →";

    card.append(title, description, action);
    card.addEventListener("click", () => showPrompt(scenario));
    return card;
  };

  const createCategoryCard = (category) => {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "category-card";
    card.dataset.categoryId = category.id;
    card.dataset.route = category.route;
    card.setAttribute("aria-label", `${category.title}，${category.description}`);

    const icon = document.createElement("span");
    icon.className = "category-icon";
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = category.icon;

    const copy = document.createElement("span");
    copy.className = "category-copy";

    const title = document.createElement("strong");
    title.textContent = category.title;

    const description = document.createElement("span");
    description.textContent = category.description;

    const action = document.createElement("span");
    action.className = "category-action";
    action.textContent = "開始探索 →";

    copy.append(title, description);
    card.append(icon, copy, action);
    card.addEventListener("click", () => {
      if (category.id === "parenting") {
        showParentingScenarios();
        return;
      }
      showComingSoon(category);
    });
    return card;
  };

  const copySelectedPrompt = async () => {
    if (!selectedPrompt) {
      return;
    }
    try {
      await navigator.clipboard.writeText(selectedPrompt);
      copyFeedback.textContent = "Prompt 已複製，可以貼到你使用的 AI 工具中。";
    } catch (_error) {
      copyFeedback.textContent = "無法自動複製，請手動選取上方 Prompt。";
    }
  };

  const loadCategories = async () => {
    try {
      const response = await fetch(categoriesUrl, {
        headers: { Accept: "application/json" },
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok || !Array.isArray(payload.categories)) {
        throw new Error("categories_unavailable");
      }

      grid.replaceChildren(...payload.categories.map(createCategoryCard));
      grid.setAttribute("aria-busy", "false");
      status.textContent = `${payload.categories.length} 個分類`;
    } catch (_error) {
      showLoadError();
    }
  };

  dismissNotice.addEventListener("click", () => {
    notice.hidden = true;
  });
  document.querySelectorAll("[data-back-to-categories]").forEach((button) => {
    button.addEventListener("click", showCategories);
  });
  document.querySelector("[data-back-to-parenting]").addEventListener(
    "click",
    showParentingScenarios,
  );
  copyPrompt.addEventListener("click", copySelectedPrompt);

  loadCategories();
})();
