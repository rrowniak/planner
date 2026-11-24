const DAY_WIDTH = 28;
const LABEL_WIDTH = 230;
const ROW_HEIGHT = 26;
const HEADER_HEIGHT = 54;
const SECTION_HEADER = 28;
const WORKER_ROW_HEIGHT = 22;
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const WEEKDAY_LETTERS = ["M", "T", "W", "T", "F", "S", "S"];
const SVG_NS = "http://www.w3.org/2000/svg";

let arrowSequence = 0;

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function parseDate(value) {
  const [year, month, day] = value.split("-").map(Number);
  return { year, month, day };
}

function formatDay(date) {
  const { year, month, day } = parseDate(date);
  return `${String(day).padStart(2, "0")} ${MONTHS[month - 1]} ${year}`;
}

function mergeSegments(segments) {
  const runs = [];
  for (const segment of segments) {
    const previous = runs[runs.length - 1];
    if (previous && Math.abs(segment.start - previous.end) < 1e-6) {
      previous.end = segment.end;
    } else {
      runs.push({ start: segment.start, end: segment.end });
    }
  }
  return runs;
}

function taskTooltip(task) {
  const lines = [
    `${task.name} (${task.id})`,
    `Owner: ${task.assignee}`,
    `Start: ${formatDay(task.startDate)}`,
    `End: ${formatDay(task.endDate)} (inclusive)`,
    `Estimate: ${task.estimate} day(s)`,
  ];
  if (task.pauseDays && task.pauseDays.length) {
    lines.push(`Pauses: ${task.pauseDays.length} day(s)`);
  }
  if (task.dependsOn && task.dependsOn.length) {
    lines.push(`After: ${task.dependsOn.join(", ")}`);
  }
  return lines.join("\n");
}

export function renderChart(container, schedule) {
  container.innerHTML = "";

  const days = schedule.days || [];
  if (!days.length) {
    container.append(el("div", "empty", "The schedule is empty."));
    return;
  }

  const tasks = schedule.tasks || [];
  const workers = schedule.workers || [];
  const dayIndex = new Map(days.map((day, index) => [day.date, index]));
  const taskIndex = new Map(tasks.map((task, index) => [task.id, index]));
  const palette = schedule.taskColors || ["#4c78a8"];
  const workerColor = new Map(workers.map((worker, index) => [worker.name, palette[index % palette.length]]));
  const colorFor = (name) => workerColor.get(name) || palette[0];
  const legendByType = new Map((schedule.legend || []).map((entry) => [entry.type, entry]));

  const timelineWidth = days.length * DAY_WIDTH;
  const tasksHeight = tasks.length * ROW_HEIGHT;
  const resourcesHeight = workers.length ? 1 + SECTION_HEADER + workers.length * WORKER_ROW_HEIGHT : 0;
  const bodyHeight = tasksHeight + resourcesHeight;

  const gantt = el("div", "gantt");
  const labels = el("div", "gantt-labels");
  labels.style.width = `${LABEL_WIDTH}px`;
  const scroller = el("div", "gantt-scroll");
  const timeline = el("div", "gantt-timeline");
  timeline.style.width = `${timelineWidth}px`;

  gantt.append(labels, scroller);
  scroller.append(timeline);

  // ---- labels column ----
  const labelsHeader = el("div", "gantt-labels-header", "Task");
  labelsHeader.style.height = `${HEADER_HEIGHT}px`;
  labels.append(labelsHeader);

  for (const task of tasks) {
    const row = el("div", "gantt-label-row");
    row.style.height = `${ROW_HEIGHT}px`;
    const dot = el("span", "dot");
    dot.style.background = colorFor(task.assignee);
    const main = el("div", "label-main");
    const name = el("div", "label-name", `${task.name} (${task.id})`);
    name.title = `${task.name} (${task.id})`;
    const sub = el("div", "label-sub", `${task.assignee} · ${task.estimate}d`);
    main.append(name, sub);
    row.append(dot, main);
    labels.append(row);
  }

  if (workers.length) {
    const divider = el("div");
    divider.style.height = "1px";
    divider.style.borderTop = "1px solid var(--line)";
    labels.append(divider);
    const section = el("div", "gantt-section-label", "Resources");
    section.style.height = `${SECTION_HEADER}px`;
    labels.append(section);
    for (const worker of workers) {
      const row = el("div", "gantt-worker-label");
      row.style.height = `${WORKER_ROW_HEIGHT}px`;
      row.append(el("span", "", worker.name));
      row.append(el("span", "focus", `focus ${worker.focusFactor}`));
      labels.append(row);
    }
  }

  // ---- timeline header ----
  const header = el("div", "gantt-header");
  header.style.height = `${HEADER_HEIGHT}px`;
  timeline.append(header);

  let monthStart = 0;
  while (monthStart < days.length) {
    const first = parseDate(days[monthStart].date);
    let monthEnd = monthStart + 1;
    while (monthEnd < days.length) {
      const current = parseDate(days[monthEnd].date);
      if (current.year !== first.year || current.month !== first.month) break;
      monthEnd += 1;
    }
    const band = el("div", "month-band", `${MONTHS[first.month - 1]} ${first.year}`);
    band.style.left = `${monthStart * DAY_WIDTH}px`;
    band.style.width = `${(monthEnd - monthStart) * DAY_WIDTH}px`;
    header.append(band);
    monthStart = monthEnd;
  }

  for (let index = 0; index < days.length; index += 1) {
    const day = days[index];
    const cell = el("div", "day-head");
    if (day.weekend) cell.classList.add("weekend");
    if (day.publicHoliday) cell.classList.add("public");
    cell.style.left = `${index * DAY_WIDTH}px`;
    cell.style.width = `${DAY_WIDTH}px`;
    const number = el("span", "num", String(parseDate(day.date).day));
    cell.append(number, document.createTextNode(WEEKDAY_LETTERS[day.weekday] || ""));
    cell.title = `${formatDay(day.date)}${day.weekend ? " · closed" : ""}${
      day.publicHoliday ? " · public holiday" : ""
    }`;
    header.append(cell);
  }

  // ---- timeline body ----
  const body = el("div", "gantt-body");
  body.style.height = `${bodyHeight}px`;
  timeline.append(body);

  for (let index = 0; index < days.length; index += 1) {
    const day = days[index];
    const band = el("div", "col-band");
    if (day.weekend) band.classList.add("weekend");
    if (day.publicHoliday) band.classList.add("public");
    band.style.left = `${index * DAY_WIDTH}px`;
    band.style.width = `${DAY_WIDTH}px`;
    body.append(band);
  }

  for (const marker of schedule.markers || []) {
    const from = dayIndex.get(marker.from);
    const to = dayIndex.get(marker.to);
    if (from === undefined || to === undefined || to < from) continue;
    const band = el("div", "marker-band");
    band.style.left = `${from * DAY_WIDTH}px`;
    band.style.width = `${(to - from + 1) * DAY_WIDTH}px`;
    band.style.background = marker.color;
    body.append(band);

    const label = el("div", "marker-label", marker.label);
    label.style.left = `${from * DAY_WIDTH + 3}px`;
    label.title = `${marker.label}: ${formatDay(marker.from)} – ${formatDay(marker.to)}`;
    body.append(label);
  }

  for (let index = 0; index < tasks.length; index += 1) {
    const task = tasks[index];
    const row = el("div", "task-row");
    row.style.top = `${index * ROW_HEIGHT}px`;
    row.style.height = `${ROW_HEIGHT}px`;
    const color = colorFor(task.assignee);
    const tooltip = taskTooltip(task);

    if (!task.segments || !task.segments.length) {
      const tick = el("div", "task-tick");
      tick.style.left = `${task.startOffset * DAY_WIDTH}px`;
      tick.style.background = color;
      tick.title = tooltip;
      row.append(tick);
    } else {
      const span = el("div", "task-span");
      span.style.left = `${task.startOffset * DAY_WIDTH}px`;
      span.style.width = `${Math.max(2, (task.finishOffset - task.startOffset) * DAY_WIDTH)}px`;
      span.style.background = color;
      span.title = tooltip;
      row.append(span);

      let cursor = task.startOffset;
      for (const run of mergeSegments(task.segments)) {
        if (run.start - cursor > 1e-6) {
          const gap = el("div", "task-gap");
          gap.style.left = `${cursor * DAY_WIDTH}px`;
          gap.style.width = `${Math.max(2, (run.start - cursor) * DAY_WIDTH)}px`;
          gap.style.borderColor = color;
          gap.style.background = `repeating-linear-gradient(45deg, ${color}26 0 3px, transparent 3px 7px)`;
          if (cursor <= task.startOffset + 1e-6) gap.style.borderLeft = `1px dashed ${color}`;
          gap.title = tooltip;
          row.append(gap);
        }
        const bar = el("div", "task-bar");
        bar.style.left = `${run.start * DAY_WIDTH}px`;
        bar.style.width = `${Math.max(2, (run.end - run.start) * DAY_WIDTH - 1)}px`;
        bar.style.background = color;
        bar.title = tooltip;
        row.append(bar);
        cursor = run.end;
      }
    }

    const label = el("div", "task-label", `${task.name} (${task.assignee})`);
    const startPx = task.startOffset * DAY_WIDTH;
    const finishPx = task.finishOffset * DAY_WIDTH;
    if (timelineWidth - finishPx >= 180) {
      label.style.left = `${finishPx + 6}px`;
    } else if (startPx >= 180) {
      label.style.right = `${timelineWidth - startPx + 6}px`;
    } else {
      label.style.left = `${startPx + 3}px`;
    }
    label.style.borderColor = color;
    label.title = tooltip;
    row.append(label);

    body.append(row);
  }

  // ---- dependency arrows ----
  arrowSequence += 1;
  const markerId = `gantt-arrow-${arrowSequence}`;
  const arrows = document.createElementNS(SVG_NS, "svg");
  arrows.setAttribute("class", "gantt-arrows");
  arrows.setAttribute("width", String(timelineWidth));
  arrows.setAttribute("height", String(bodyHeight));
  arrows.style.width = `${timelineWidth}px`;
  arrows.style.height = `${bodyHeight}px`;

  const defs = document.createElementNS(SVG_NS, "defs");
  const marker = document.createElementNS(SVG_NS, "marker");
  marker.setAttribute("id", markerId);
  marker.setAttribute("markerWidth", "8");
  marker.setAttribute("markerHeight", "8");
  marker.setAttribute("refX", "7");
  marker.setAttribute("refY", "4");
  marker.setAttribute("orient", "auto");
  const markerPath = document.createElementNS(SVG_NS, "path");
  markerPath.setAttribute("d", "M0,0 L8,4 L0,8 z");
  markerPath.setAttribute("fill", "#98a2b3");
  marker.append(markerPath);
  defs.append(marker);
  arrows.append(defs);

  for (const task of tasks) {
    const targetIndex = taskIndex.get(task.id);
    for (const dependency of task.dependsOn || []) {
      const sourceIndex = taskIndex.get(dependency);
      if (sourceIndex === undefined) continue;
      const source = tasks[sourceIndex];
      const x1 = source.finishOffset * DAY_WIDTH;
      const x2 = task.startOffset * DAY_WIDTH;
      const y1 = sourceIndex * ROW_HEIGHT + ROW_HEIGHT / 2;
      const y2 = targetIndex * ROW_HEIGHT + ROW_HEIGHT / 2;

      let pathData;
      if (x2 <= x1 + 4) {
        pathData = `M ${x1} ${y1} V ${y2} H ${x2 - 2}`;
      } else if (x2 - x1 >= 24) {
        const midX = x1 + (x2 - x1) / 2;
        pathData = `M ${x1} ${y1} H ${midX} V ${y2} H ${x2 - 2}`;
      } else {
        const bulge = x1 + 16;
        pathData = `M ${x1} ${y1} H ${bulge} V ${y2} H ${x2 - 2}`;
      }

      const connector = document.createElementNS(SVG_NS, "path");
      connector.setAttribute("class", "connector");
      connector.setAttribute("d", pathData);
      connector.setAttribute("marker-end", `url(#${markerId})`);
      arrows.append(connector);
    }
  }
  body.append(arrows);

  // ---- resources ----
  if (workers.length) {
    const resourceTop = tasksHeight;
    const separator = el("div", "resource-separator");
    separator.style.top = `${resourceTop}px`;
    body.append(separator);

    const sectionBand = el("div");
    sectionBand.style.position = "absolute";
    sectionBand.style.left = "0";
    sectionBand.style.right = "0";
    sectionBand.style.top = `${resourceTop + 1}px`;
    sectionBand.style.height = `${SECTION_HEADER}px`;
    sectionBand.style.background = "#fafbfc";
    sectionBand.style.borderBottom = "1px solid var(--line)";
    body.append(sectionBand);

    workers.forEach((worker, workerIndex) => {
      const top = resourceTop + 1 + SECTION_HEADER + workerIndex * WORKER_ROW_HEIGHT;
      const row = el("div", "worker-row");
      row.style.top = `${top}px`;
      row.style.height = `${WORKER_ROW_HEIGHT}px`;
      worker.days.forEach((cell, dayPosition) => {
        const entry = legendByType.get(cell.type);
        const swatch = el("div", "worker-cell");
        swatch.style.left = `${dayPosition * DAY_WIDTH + 1}px`;
        swatch.style.width = `${DAY_WIDTH - 2}px`;
        swatch.style.background = entry ? entry.color : "#d0d5dd";
        swatch.title = `${formatDay(cell.date)} · ${entry ? entry.label : cell.type} · ${cell.hours}h`;
        row.append(swatch);
      });
      body.append(row);
    });
  }

  container.append(gantt);

  // ---- legend ----
  const legend = el("div", "legend");
  legend.append(el("span", "legend-title", "Legend"));
  for (const entry of schedule.legend || []) {
    const item = el("span", "item");
    const swatch = el("span", "swatch");
    swatch.style.background = entry.color;
    item.append(swatch, el("span", "", entry.label));
    legend.append(item);
  }
  if ((schedule.markers || []).length) {
    const item = el("span", "item");
    const swatch = el("span", "swatch");
    swatch.style.background = schedule.markerColor || "navajowhite";
    item.append(swatch, el("span", "", "Time marker"));
    legend.append(item);
  }
  const note = el("span", "item");
  note.append(el("span", "muted", "Task bars are colored by owner."));
  legend.append(note);

  container.append(legend);
}
