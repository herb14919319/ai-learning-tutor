(() => {
  "use strict";

  const body = document.body;
  const scenariosUrl = body.dataset.scenariosUrl;
  const homeView = document.getElementById("home-view");
  const homeTitle = document.getElementById("home-title");
  const scenarioGrid = document.getElementById("scenario-grid");
  const scenarioStatus = document.getElementById("scenario-status");
  const loadError = document.getElementById("load-error");
  const retryScenarios = document.getElementById("retry-scenarios");
  const promptView = document.getElementById("prompt-view");
  const promptIcon = document.getElementById("prompt-icon");
  const promptTitle = document.getElementById("prompt-title");
  const promptDescription = document.getElementById("prompt-description");
  const demoPanel = document.getElementById("demo-panel");
  const demoImage = document.getElementById("demo-image");
  const demoTitle = document.getElementById("demo-title");
  const demoMessage = document.getElementById("demo-message");
  const questionGuide = document.getElementById("question-guide");
  const questionList = document.getElementById("question-list");
  const promptBuilder = document.getElementById("prompt-builder");
  const formFields = document.getElementById("form-fields");
  const updatePrompt = document.getElementById("update-prompt");
  const builderFeedback = document.getElementById("builder-feedback");
  const promptPaperTitle = document.getElementById("prompt-paper-title");
  const promptContent = document.getElementById("prompt-content");
  const promptEditor = document.getElementById("prompt-editor");
  const copyPrompt = document.getElementById("copy-prompt");
  const copyFeedback = document.getElementById("copy-feedback");
  const backHome = document.getElementById("back-home");

  const scenarioVisuals = {
    "bedtime-story": { icon: "🌙", className: "story-card" },
    "drawing-to-ai-character": { icon: "🎨", className: "drawing-card" },
    "shared-reading-activity": { icon: "📚", className: "reading-card" },
  };

  let selectedScenario = null;

  const setCopyFeedback = (message, state = "") => {
    copyFeedback.textContent = message;
    copyFeedback.className = state;
  };

  const setBuilderFeedback = (message, state = "") => {
    builderFeedback.textContent = message;
    builderFeedback.className = state;
  };

  const showHome = () => {
    promptView.hidden = true;
    homeView.hidden = false;
    selectedScenario = null;
    setCopyFeedback("");
    setBuilderFeedback("");
    window.scrollTo(0, 0);
    homeTitle.focus({ preventScroll: true });
  };

  const showPrompt = (scenario) => {
    const visual = scenarioVisuals[scenario.id] || {
      icon: scenario.icon || "🌱",
    };
    selectedScenario = scenario;
    promptIcon.textContent = visual.icon;
    promptTitle.textContent = scenario.title;
    promptDescription.textContent = scenario.description;
    if (scenario.demo_image) {
      demoImage.src = scenario.demo_image;
      demoImage.alt = scenario.demo_image_alt;
      demoTitle.textContent = scenario.demo_title;
      demoMessage.textContent = scenario.demo_message;
      demoPanel.hidden = false;
    } else {
      demoPanel.hidden = true;
      demoImage.removeAttribute("src");
      demoImage.alt = "";
    }
    promptContent.textContent = scenario.prompt;
    promptEditor.value = scenario.prompt;
    promptEditor.hidden = !scenario.editable;
    promptContent.hidden = Boolean(scenario.editable);
    promptPaperTitle.textContent = scenario.editable
      ? "把想法填進提示詞，也可以自由修改"
      : "把這段提示詞帶去 AI";
    const questions = Array.isArray(scenario.questions) ? scenario.questions : [];
    questionList.replaceChildren(
      ...questions.map((question) => {
        const item = document.createElement("li");
        const label = document.createElement("strong");
        const examples = document.createElement("span");
        label.textContent = question.label;
        examples.textContent = question.examples;
        item.append(label, examples);
        return item;
      }),
    );
    questionGuide.hidden = questions.length === 0;
    const fields = Array.isArray(scenario.form_fields)
      ? scenario.form_fields
      : [];
    formFields.replaceChildren(
      ...fields.map((field) => {
        const group = document.createElement("div");
        const label = document.createElement("label");
        const examples = document.createElement("span");
        const input = document.createElement("input");
        const inspirationLabel = document.createElement("span");
        const inspirationCards = document.createElement("div");
        group.className = "form-field";
        label.htmlFor = field.id;
        label.textContent = field.label;
        examples.className = "field-examples";
        examples.textContent = `一起想想：${field.examples}`;
        input.id = field.id;
        input.type = "text";
        input.placeholder = field.placeholder;
        input.dataset.token = field.token;
        input.autocomplete = "off";
        input.addEventListener("input", () => setBuilderFeedback(""));
        inspirationLabel.className = "inspiration-label";
        inspirationLabel.textContent = "靈感小卡";
        inspirationCards.className = "inspiration-cards";
        inspirationCards.append(
          ...field.inspirations.map((inspiration) => {
            const card = document.createElement("button");
            card.type = "button";
            card.className = "inspiration-card";
            card.textContent = inspiration;
            card.setAttribute(
              "aria-label",
              `把「${inspiration}」填入「${field.label}」`,
            );
            card.addEventListener("click", () => {
              input.value = inspiration;
              input.focus();
              setBuilderFeedback(
                "靈感已放進欄位，你可以繼續改成自己的版本！",
                "is-success",
              );
            });
            return card;
          }),
        );
        group.append(
          label,
          examples,
          input,
          inspirationLabel,
          inspirationCards,
        );
        return group;
      }),
    );
    updatePrompt.textContent = scenario.update_button_text || "";
    promptBuilder.hidden = fields.length === 0;
    setCopyFeedback("");
    setBuilderFeedback("");
    homeView.hidden = true;
    promptView.hidden = false;
    window.scrollTo(0, 0);
    promptTitle.focus({ preventScroll: true });
  };

  const updateSelectedPrompt = () => {
    if (!selectedScenario || !selectedScenario.form_fields) {
      return;
    }

    let updatedPrompt = selectedScenario.prompt;
    formFields.querySelectorAll("input[data-token]").forEach((input) => {
      const replacement = input.value.trim() ? input.value : input.dataset.token;
      updatedPrompt = updatedPrompt.split(input.dataset.token).join(replacement);
    });
    promptEditor.value = updatedPrompt;
    setBuilderFeedback(selectedScenario.update_success_message, "is-success");
    setCopyFeedback("");
  };

  const createScenarioCard = (scenario) => {
    const visual = scenarioVisuals[scenario.id] || {
      icon: scenario.icon || "🌱",
      className: scenario.card_class || "default-card",
    };
    const card = document.createElement("button");
    card.type = "button";
    card.className = `scenario-card ${visual.className}`;
    card.dataset.scenarioId = scenario.id;
    card.setAttribute(
      "aria-label",
      `${scenario.title}，${scenario.description}，一起開始`,
    );

    const icon = document.createElement("span");
    icon.className = "scenario-icon";
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = visual.icon;

    const copy = document.createElement("span");
    copy.className = "scenario-copy";

    const title = document.createElement("strong");
    title.textContent = scenario.title;

    const description = document.createElement("span");
    description.textContent = scenario.description;

    const action = document.createElement("span");
    action.className = "scenario-action";
    action.textContent = scenario.action_label || "一起開始";
    action.setAttribute("aria-hidden", "true");

    copy.append(title, description);
    card.append(icon, copy, action);
    card.addEventListener("click", () => showPrompt(scenario));
    return card;
  };

  const showLoading = () => {
    scenarioGrid.hidden = false;
    scenarioGrid.setAttribute("aria-busy", "true");
    scenarioGrid.replaceChildren(
      ...Array.from({ length: 4 }, () => {
        const placeholder = document.createElement("div");
        placeholder.className = "loading-card";
        placeholder.setAttribute("aria-hidden", "true");
        return placeholder;
      }),
    );
    loadError.hidden = true;
    scenarioStatus.textContent = "小樹正在準備活動…";
    scenarioStatus.className = "";
  };

  const showLoadError = () => {
    scenarioGrid.replaceChildren();
    scenarioGrid.hidden = true;
    scenarioGrid.setAttribute("aria-busy", "false");
    loadError.hidden = false;
    scenarioStatus.textContent = "活動暫時無法載入。";
    scenarioStatus.className = "is-error";
  };

  const loadScenarios = async () => {
    showLoading();
    try {
      const response = await fetch(scenariosUrl, {
        headers: { Accept: "application/json" },
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok || !Array.isArray(payload.scenarios)) {
        throw new Error("scenarios_unavailable");
      }

      scenarioGrid.replaceChildren(...payload.scenarios.map(createScenarioCard));
      scenarioGrid.setAttribute("aria-busy", "false");
      scenarioStatus.textContent = "四個親子活動，等你們一起發現！";
    } catch (_error) {
      showLoadError();
    }
  };

  const fallbackCopy = (text) => {
    const textArea = document.createElement("textarea");
    textArea.value = text;
    textArea.setAttribute("readonly", "");
    textArea.setAttribute("aria-hidden", "true");
    textArea.className = "clipboard-helper";
    document.body.append(textArea);
    textArea.select();

    let copied = false;
    try {
      copied = document.execCommand("copy");
    } catch (_error) {
      copied = false;
    } finally {
      textArea.remove();
      copyPrompt.focus();
    }
    return copied;
  };

  const copySelectedPrompt = async () => {
    if (!selectedScenario) {
      return;
    }

    const promptText = selectedScenario.editable
      ? promptEditor.value
      : selectedScenario.prompt;
    let copied = false;
    if (navigator.clipboard && window.isSecureContext) {
      try {
        await navigator.clipboard.writeText(promptText);
        copied = true;
      } catch (_error) {
        copied = false;
      }
    }
    if (!copied) {
      copied = fallbackCopy(promptText);
    }

    if (copied) {
      setCopyFeedback(
        "提示詞已複製，可以貼到你喜歡的 AI 繪圖工具囉！",
        "is-success",
      );
      return;
    }
    setCopyFeedback(
      "這次沒有複製成功，請長按或選取上方提示詞再複製。",
      "is-error",
    );
  };

  retryScenarios.addEventListener("click", loadScenarios);
  backHome.addEventListener("click", showHome);
  copyPrompt.addEventListener("click", copySelectedPrompt);
  updatePrompt.addEventListener("click", updateSelectedPrompt);
  promptEditor.addEventListener("input", () => {
    setCopyFeedback("");
    setBuilderFeedback("");
  });
  demoImage.addEventListener("error", () => {
    demoPanel.hidden = true;
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !promptView.hidden) {
      showHome();
    }
  });

  loadScenarios();
})();
