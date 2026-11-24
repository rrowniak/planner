import { renderChart } from "./chart.js?v=4";
import { definitionToToml, normalizeDefinition } from "./toml.js?v=2";

const state = {
  builtins: new Map(),
  uploaded: new Map(),
  examples: [],
  mode: "toml",
  definition: null,
  lastGeneratedToml: null,
};

const elements = {
  project: document.getElementById("project-toml"),
  render: document.getElementById("render"),
  status: document.getElementById("status"),
  messages: document.getElementById("messages"),
  chart: document.getElementById("chart"),
  chartMeta: document.getElementById("chart-meta"),
  examples: document.getElementById("examples"),
  calendarChips: document.getElementById("calendar-chips"),
  calendarFile: document.getElementById("calendar-file"),
  tabToml: document.getElementById("tab-toml"),
  tabDefinition: document.getElementById("tab-definition"),
  tomlView: document.getElementById("toml-view"),
  definitionView: document.getElementById("definition-view"),
  definition: document.getElementById("definition"),
  calendarOptions: document.getElementById("calendar-options"),
};

function setStatus(text, kind = "") {
  elements.status.textContent = text;
  elements.status.className = `status ${kind}`.trim();
}

function clearMessages() {
  elements.messages.innerHTML = "";
}

function addMessage(kind, title, items) {
  const box = document.createElement("div");
  box.className = `message ${kind}`;
  if (items.length === 1) {
    box.textContent = items[0].text;
    if (items[0].loc) {
      const loc = document.createElement("span");
      loc.className = "loc";
      loc.textContent = ` (${items[0].loc})`;
      box.append(loc);
    }
  } else {
    const heading = document.createElement("strong");
    heading.textContent = title;
    const list = document.createElement("ul");
    for (const item of items) {
      const li = document.createElement("li");
      li.textContent = item.text;
      if (item.loc) {
        const loc = document.createElement("span");
        loc.className = "loc";
        loc.textContent = ` (${item.loc})`;
        li.append(loc);
      }
      if (item.hint) {
        li.append(document.createElement("br"));
        const hint = document.createElement("span");
        hint.className = "loc";
        hint.textContent = item.hint;
        li.append(hint);
      }
      list.append(li);
    }
    box.append(heading, list);
  }
  elements.messages.append(box);
}

function showErrors(errors, title = "Could not build the schedule") {
  const items = (errors || []).map((error) => {
    const loc = [error.source, error.path, error.line ? `line ${error.line}` : null, error.column ? `col ${error.column}` : null]
      .filter(Boolean)
      .join(" · ");
    return { text: error.message || "Unknown error", loc, hint: error.hint };
  });
  addMessage("error", title, items.length ? items : [{ text: "Unknown error" }]);
}

function showWarnings(warnings) {
  if (!warnings || !warnings.length) return;
  addMessage(
    "warning",
    "Warnings",
    warnings.map((warning) => ({ text: warning })),
  );
}

function chip(name, uploaded) {
  const node = document.createElement("span");
  node.className = `chip${uploaded ? " uploaded" : ""}`;
  node.append(document.createTextNode(uploaded && state.builtins.has(name) ? `${name} (override)` : name));
  if (uploaded) {
    const remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = "×";
    remove.title = `Remove ${name}`;
    remove.setAttribute("aria-label", `Remove ${name}`);
    remove.addEventListener("click", () => {
      state.uploaded.delete(name);
      renderCalendarChips();
      refreshDatalists();
    });
    node.append(remove);
  }
  return node;
}

function renderCalendarChips() {
  elements.calendarChips.innerHTML = "";
  for (const name of state.builtins.keys()) {
    if (!state.uploaded.has(name)) {
      elements.calendarChips.append(chip(name, false));
    }
  }
  for (const name of state.uploaded.keys()) {
    elements.calendarChips.append(chip(name, true));
  }
}

function renderExamples() {
  elements.examples.innerHTML = "";
  for (const example of state.examples) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "example-btn";
    button.textContent = example.name;
    button.title = `Load ${example.id}.toml`;
    button.addEventListener("click", () => {
      elements.project.value = example.content;
      state.definition = null;
      state.lastGeneratedToml = null;
      clearMessages();
      setStatus(`Loaded example: ${example.name}`);
      if (state.mode === "definition") loadDefinition();
    });
    elements.examples.append(button);
  }
}

function h(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === undefined || value === null) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value);
  }
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child.nodeType ? child : document.createTextNode(String(child)));
  }
  return node;
}

function input(options) {
  const node = document.createElement("input");
  node.type = options.type || "text";
  node.value = options.value ?? "";
  if (options.placeholder) node.placeholder = options.placeholder;
  if (options.step !== undefined) node.step = String(options.step);
  if (options.min !== undefined) node.min = String(options.min);
  if (options.list) node.setAttribute("list", options.list);
  node.addEventListener("input", () => options.onInput?.(node.value));
  if (options.onChange) node.addEventListener("change", () => options.onChange(node.value));
  return node;
}

function select(options) {
  const node = document.createElement("select");
  for (const choice of options.choices) {
    const option = h("option", { value: choice.value, text: choice.label });
    option.selected = String(choice.value) === String(options.value ?? "");
    node.append(option);
  }
  node.addEventListener("change", () => options.onChange?.(node.value));
  return node;
}

function field(label, control) {
  return h("label", { class: "def-field" }, h("span", { text: label }), control);
}

function defSection(title, addLabel, onAdd, content) {
  const head = h("div", { class: "def-head" }, h("h3", { text: title }));
  if (onAdd) head.append(h("button", { type: "button", class: "mini", text: addLabel, onclick: onAdd }));
  return h("section", { class: "def-section" }, head, content);
}

function defRow(className, cells) {
  return h("div", { class: `def-row ${className}` }, ...cells);
}

function defHeader(className, labels) {
  return defRow(`def-row-head ${className}`, labels.map((label) => h("span", { text: label })));
}

function removeButton(label, onClick) {
  return h("button", {
    type: "button",
    class: "def-remove",
    title: `Remove ${label}`,
    "aria-label": `Remove ${label}`,
    text: "×",
    onclick: onClick,
  });
}

function syncDefinition() {
  if (!state.definition) return;
  const toml = definitionToToml(state.definition);
  elements.project.value = toml;
  state.lastGeneratedToml = toml;
  setStatus("Definition changed — press Render chart");
}

function fillDatalist(list, values) {
  list.innerHTML = "";
  for (const value of new Set(values.filter(Boolean))) {
    list.append(h("option", { value }));
  }
}

function refreshDatalists() {
  if (!state.definition) return;
  fillDatalist(elements.calendarOptions, [...state.builtins.keys(), ...state.uploaded.keys()]);
}

function dateList(member, key, label, addLabel) {
  const ranges = member[key];
  const add = () => {
    ranges.push({ start: "", end: "" });
    renderDefinition();
    syncDefinition();
  };
  const rows = ranges.map((range, index) => {
    const remove = () => {
      ranges.splice(index, 1);
      renderDefinition();
      syncDefinition();
    };
    return h(
      "div",
      { class: "range-row" },
      input({
        type: "date",
        value: range.start,
        onInput: (value) => {
          range.start = value;
          syncDefinition();
        },
      }),
      h("span", { class: "range-sep", text: "→" }),
      input({
        type: "date",
        value: range.end,
        onInput: (value) => {
          range.end = value;
          syncDefinition();
        },
      }),
      removeButton("date range", remove),
    );
  });
  if (!rows.length) rows.push(h("span", { class: "muted", text: "None" }));
  return h(
    "div",
    { class: "date-list" },
    h(
      "div",
      { class: "date-list-head" },
      h("span", { class: "date-list-label", text: label }),
      h("button", { type: "button", class: "mini", text: addLabel, onclick: add }),
    ),
    ...rows,
  );
}

function memberCard(member, index) {
  const remove = () => {
    state.definition.team.splice(index, 1);
    renderDefinition();
    syncDefinition();
  };
  return h(
    "div",
    { class: "member-card" },
    h(
      "div",
      { class: "member-main" },
      field(
        "Name",
        input({
          value: member.name,
          placeholder: "Name",
          onInput: (value) => {
            member.name = value;
            syncDefinition();
          },
          onChange: renderDefinition,
        }),
      ),
      field(
        "Base calendar",
        input({
          value: member.base_calendar,
          placeholder: "calendar.toml",
          list: "calendar-options",
          onInput: (value) => {
            member.base_calendar = value;
            syncDefinition();
          },
        }),
      ),
      field(
        "Focus",
        input({
          type: "number",
          value: member.focus_factor,
          step: "0.05",
          min: "0.01",
          onInput: (value) => {
            member.focus_factor = value;
            syncDefinition();
          },
        }),
      ),
      removeButton("member", remove),
    ),
    h(
      "div",
      { class: "member-dates" },
      dateList(member, "holidays", "Holidays", "Add holiday"),
      dateList(member, "other_duties", "Other duties", "Add duty"),
    ),
  );
}

function parseAfter(value) {
  return String(value ?? "")
    .split(",")
    .map((chunk) => chunk.trim())
    .filter(Boolean);
}

function afterEditor(task) {
  const wrap = h("div", { class: "after-editor" });
  const render = () => {
    wrap.innerHTML = "";
    const selected = parseAfter(task.after);
    const byId = new Map(state.definition.tasks.map((other) => [other.id, other]));
    const label = (id) => {
      const name = String(byId.get(id)?.name ?? "").trim();
      return name ? `${id} — ${name}` : id;
    };
    const chips = h("div", { class: "chips after-chips" });
    for (const id of selected) {
      chips.append(
        h(
          "span",
          { class: "chip" },
          label(id),
          h("button", {
            type: "button",
            title: `Remove dependency ${id}`,
            "aria-label": `Remove dependency ${id}`,
            text: "×",
            onclick: () => {
              task.after = selected.filter((dep) => dep !== id).join(", ");
              render();
              syncDefinition();
            },
          }),
        ),
      );
    }
    const available = state.definition.tasks
      .map((other) => other)
      .filter((other) => other.id && other.id !== task.id && !selected.includes(other.id));
    const picker = select({
      value: "",
      choices: [
        { value: "", label: available.length ? "Add dependency…" : "No other tasks" },
        ...available.map((other) => ({ value: other.id, label: label(other.id) })),
      ],
      onChange: (value) => {
        if (!value) return;
        task.after = [...selected, value].join(", ");
        render();
        syncDefinition();
      },
    });
    picker.disabled = !available.length;
    wrap.append(chips, picker);
  };
  render();
  return wrap;
}

function taskRow(task, index) {
  const remove = () => {
    state.definition.tasks.splice(index, 1);
    renderDefinition();
    syncDefinition();
  };
  return defRow("def-task-row", [
    input({
      value: task.id,
      placeholder: "T1",
      onInput: (value) => {
        task.id = value;
        syncDefinition();
      },
      onChange: renderDefinition,
    }),
    input({
      value: task.name,
      placeholder: "Task name",
      onInput: (value) => {
        task.name = value;
        syncDefinition();
      },
      onChange: renderDefinition,
    }),
    input({
      type: "number",
      value: task.estimate,
      step: "0.25",
      min: "0",
      onInput: (value) => {
        task.estimate = value;
        syncDefinition();
      },
    }),
    afterEditor(task),
    removeButton("task", remove),
  ]);
}

function assignmentRow(assignment, index) {
  const remove = () => {
    state.definition.assignments.splice(index, 1);
    renderDefinition();
    syncDefinition();
  };
  const tasks = state.definition.tasks.filter((task) => task.id);
  const choices = [
    { value: "", label: "— select task —" },
    ...tasks.map((task) => ({
      value: task.id,
      label: task.name ? `${task.id} — ${task.name}` : task.id,
    })),
  ];
  if (assignment.task && !tasks.some((task) => task.id === assignment.task)) {
    choices.push({ value: assignment.task, label: assignment.task });
  }
  const owners = state.definition.team.filter((member) => member.name);
  const ownerChoices = [
    { value: "", label: "— select owner —" },
    ...owners.map((member) => ({ value: member.name, label: member.name })),
  ];
  if (assignment.owner && !owners.some((member) => member.name === assignment.owner)) {
    ownerChoices.push({ value: assignment.owner, label: assignment.owner });
  }
  return defRow("def-assignment-row", [
    select({
      value: assignment.task,
      choices,
      onChange: (value) => {
        assignment.task = value;
        syncDefinition();
      },
    }),
    select({
      value: assignment.owner,
      choices: ownerChoices,
      onChange: (value) => {
        assignment.owner = value;
        syncDefinition();
      },
    }),
    input({
      type: "number",
      value: assignment.focus_factor,
      step: "0.05",
      min: "0.01",
      placeholder: "optional",
      onInput: (value) => {
        assignment.focus_factor = value;
        syncDefinition();
      },
    }),
    removeButton("assignment", remove),
  ]);
}

function markerRow(marker, index) {
  const remove = () => {
    state.definition.time_markers.splice(index, 1);
    renderDefinition();
    syncDefinition();
  };
  return defRow("def-marker-row", [
    input({
      value: marker.time,
      placeholder: "2024-12-09:2024-12-25",
      onInput: (value) => {
        marker.time = value;
        syncDefinition();
      },
    }),
    input({
      value: marker.label,
      placeholder: "Label",
      onInput: (value) => {
        marker.label = value;
        syncDefinition();
      },
    }),
    input({
      value: marker.color,
      placeholder: "optional",
      onInput: (value) => {
        marker.color = value;
        syncDefinition();
      },
    }),
    removeButton("marker", remove),
  ]);
}

function renderDefinition() {
  elements.definition.innerHTML = "";
  const definition = state.definition;
  if (!definition) {
    elements.definition.append(
      h("div", { class: "empty", text: "Fix the TOML errors, then reopen the Definition tab." }),
    );
    return;
  }

  elements.definition.append(
    defSection(
      "Project",
      null,
      null,
      h(
        "div",
        { class: "def-fields" },
        field(
          "Project name",
          input({
            value: definition.project_name,
            onInput: (value) => {
              definition.project_name = value;
              syncDefinition();
            },
          }),
        ),
        field(
          "Start date",
          input({
            type: "date",
            value: definition.start_date,
            onInput: (value) => {
              definition.start_date = value;
              syncDefinition();
            },
          }),
        ),
      ),
    ),
    defSection(
      "Team",
      "Add member",
      () => {
        definition.team.push({
          name: "",
          base_calendar: "",
          focus_factor: 1,
          holidays: [],
          other_duties: [],
        });
        renderDefinition();
        syncDefinition();
      },
      h("div", { class: "member-list" }, ...definition.team.map(memberCard)),
    ),
    defSection(
      "Tasks",
      "Add task",
      () => {
        definition.tasks.push({ id: "", name: "", estimate: 1, after: "" });
        renderDefinition();
        syncDefinition();
      },
      h(
        "div",
        { class: "def-table" },
        defHeader("def-task-row", ["Id", "Name", "Estimate", "After", ""]),
        ...definition.tasks.map(taskRow),
      ),
    ),
    defSection(
      "Assignments",
      "Add assignment",
      () => {
        definition.assignments.push({ task: "", owner: "", focus_factor: "" });
        renderDefinition();
        syncDefinition();
      },
      h(
        "div",
        { class: "def-table" },
        defHeader("def-assignment-row", ["Task", "Owner", "Focus (optional)", ""]),
        ...definition.assignments.map(assignmentRow),
      ),
    ),
    defSection(
      "Time markers",
      "Add marker",
      () => {
        definition.time_markers.push({ time: "", label: "", color: "" });
        renderDefinition();
        syncDefinition();
      },
      h(
        "div",
        { class: "def-table" },
        defHeader("def-marker-row", ["Time", "Label", "Color", ""]),
        ...definition.time_markers.map(markerRow),
      ),
    ),
  );
  refreshDatalists();
}

async function loadDefinition() {
  const current = elements.project.value;
  if (state.definition && state.lastGeneratedToml === current) {
    renderDefinition();
    return;
  }

  clearMessages();
  setStatus("Parsing definition…", "busy");
  try {
    const response = await fetch("/api/parse", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project_toml: current }),
    });
    const data = await response.json().catch(() => null);
    if (!response.ok || !data || !data.definition) {
      state.definition = null;
      renderDefinition();
      showErrors(
        data && data.errors ? data.errors : [{ message: `HTTP ${response.status}` }],
        "Could not parse the definition",
      );
      setStatus("Definition has errors", "error");
      return;
    }
    state.definition = normalizeDefinition(data.definition);
    state.lastGeneratedToml = current;
    renderDefinition();
    setStatus("Definition loaded");
  } catch (error) {
    state.definition = null;
    renderDefinition();
    addMessage("error", "Could not parse the definition", [{ text: String(error.message || error) }]);
    setStatus("Parse failed", "error");
  }
}

function setMode(mode) {
  state.mode = mode;
  const isToml = mode === "toml";
  elements.tomlView.classList.toggle("hidden", !isToml);
  elements.definitionView.classList.toggle("hidden", isToml);
  elements.tabToml.classList.toggle("active", isToml);
  elements.tabDefinition.classList.toggle("active", !isToml);
  elements.tabToml.setAttribute("aria-selected", String(isToml));
  elements.tabDefinition.setAttribute("aria-selected", String(!isToml));
  if (!isToml) loadDefinition();
}

async function loadInitialData() {
  try {
    const [calendarResponse, exampleResponse] = await Promise.all([
      fetch("/api/calendars"),
      fetch("/api/examples"),
    ]);
    if (!calendarResponse.ok) throw new Error(`calendars: HTTP ${calendarResponse.status}`);
    if (!exampleResponse.ok) throw new Error(`examples: HTTP ${exampleResponse.status}`);

    const calendarData = await calendarResponse.json();
    for (const calendar of calendarData.calendars || []) {
      state.builtins.set(calendar.name, calendar.content);
    }
    renderCalendarChips();

    const exampleData = await exampleResponse.json();
    state.examples = exampleData.examples || [];
    renderExamples();

    if (state.examples.length && !elements.project.value) {
      elements.project.value = state.examples[0].content;
    }
    setStatus(state.examples.length ? "Ready" : "Ready (no examples found)");
  } catch (error) {
    setStatus("Initialization failed", "error");
    addMessage("error", "Could not load application data", [{ text: String(error.message || error) }]);
  }
}

async function render() {
  clearMessages();
  const projectToml = elements.project.value;
  if (!projectToml.trim()) {
    addMessage("error", "Nothing to render", [{ text: "Paste a project definition first." }]);
    return;
  }

  elements.render.disabled = true;
  setStatus("Calculating…", "busy");

  try {
    const response = await fetch("/api/render", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        project_toml: projectToml,
        calendars: Object.fromEntries(state.uploaded),
      }),
    });
    const data = await response.json().catch(() => null);

    if (!response.ok || !data || !data.schedule) {
      showErrors(data && data.errors ? data.errors : [{ message: `HTTP ${response.status}` }]);
      setStatus("Error", "error");
      return;
    }

    const schedule = data.schedule;
    renderChart(elements.chart, schedule);
    elements.chartMeta.textContent = `${schedule.title} · ${schedule.projectStart} → ${schedule.projectEnd}`;
    showWarnings(schedule.warnings);
    setStatus(`Rendered ${schedule.tasks.length} task(s)`, "");
  } catch (error) {
    addMessage("error", "Request failed", [{ text: String(error.message || error) }]);
    setStatus("Request failed", "error");
  } finally {
    elements.render.disabled = false;
  }
}

elements.render.addEventListener("click", render);

elements.tabToml.addEventListener("click", () => setMode("toml"));
elements.tabDefinition.addEventListener("click", () => setMode("definition"));

document.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
    event.preventDefault();
    render();
  }
});

elements.calendarFile.addEventListener("change", async (event) => {
  const files = Array.from(event.target.files || []);
  for (const file of files) {
    if (!file.name.endsWith(".toml")) {
      addMessage("error", "Skipped file", [{ text: `${file.name}: calendars must be .toml files.` }]);
      continue;
    }
    state.uploaded.set(file.name, await file.text());
  }
  event.target.value = "";
  renderCalendarChips();
  refreshDatalists();
  setStatus(`${state.uploaded.size} uploaded calendar(s)`);
});

loadInitialData();
