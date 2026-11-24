function objects(value) {
  return Array.isArray(value)
    ? value.filter((item) => item && typeof item === "object" && !Array.isArray(item))
    : [];
}

function normalizeDate(value) {
  const match = /^(\d{4})-(\d{1,2})-(\d{1,2})$/.exec(String(value ?? "").trim());
  if (!match) return String(value ?? "").trim();
  return `${match[1]}-${match[2].padStart(2, "0")}-${match[3].padStart(2, "0")}`;
}

function parseRanges(value) {
  return String(value ?? "")
    .split(",")
    .map((chunk) => chunk.trim())
    .filter(Boolean)
    .map((chunk) => {
      const [start, end] = chunk.split(":");
      return {
        start: normalizeDate(start),
        end: normalizeDate(end ?? start),
      };
    });
}

function rangesToText(ranges) {
  return ranges
    .map((range) => {
      const start = String(range.start ?? "").trim();
      const end = String(range.end ?? "").trim();
      if (!start) return "";
      return !end || end === start ? start : `${start}:${end}`;
    })
    .filter(Boolean)
    .join(", ");
}

export function normalizeDefinition(raw) {
  return {
    project_name: raw.project_name ?? "",
    start_date: raw.start_date ?? "",
    team: objects(raw.team).map((member) => ({
      name: member.name ?? "",
      base_calendar: member.base_calendar ?? "",
      focus_factor: member.focus_factor ?? 1,
      holidays: parseRanges(member.holidays),
      other_duties: parseRanges(member.other_duties),
    })),
    tasks: objects(raw.tasks).map((task) => ({
      id: task.id ?? "",
      name: task.name ?? "",
      estimate: task.estimate ?? 0,
      after: Array.isArray(task.after) ? task.after.join(", ") : (task.after ?? ""),
    })),
    assignments: objects(raw.assignments).map((assignment) => ({
      task: assignment.task ?? "",
      owner: assignment.owner ?? "",
      focus_factor: assignment.focus_factor ?? "",
    })),
    time_markers: objects(raw.time_markers).map((marker) => ({
      time: marker.time ?? "",
      label: marker.label ?? "",
      color: marker.color ?? "",
    })),
  };
}

function tomlString(value) {
  const escaped = String(value ?? "")
    .replace(/\\/g, "\\\\")
    .replace(/"/g, '\\"')
    .replace(/\n/g, "\\n")
    .replace(/\r/g, "\\r")
    .replace(/\t/g, "\\t");
  return `"${escaped}"`;
}

function tomlNumber(value, fallback) {
  const raw = String(value ?? "").trim();
  if (!raw) return fallback;
  const number = Number(raw);
  return Number.isFinite(number) ? String(number) : raw;
}

export function definitionToToml(definition) {
  const lines = [
    `project_name = ${tomlString(definition.project_name)}`,
    `start_date = ${tomlString(definition.start_date)}`,
    "",
    "team = [",
  ];
  for (const member of definition.team) {
    lines.push(
      `    { name=${tomlString(member.name)}, base_calendar=${tomlString(member.base_calendar)}, focus_factor=${tomlNumber(member.focus_factor, "1")}, holidays=${tomlString(rangesToText(member.holidays))}, other_duties=${tomlString(rangesToText(member.other_duties))} },`,
    );
  }
  lines.push("]", "", "tasks = [");
  for (const task of definition.tasks) {
    const after = String(task.after ?? "").trim();
    const afterPart = after ? `, after=${tomlString(after)}` : "";
    lines.push(
      `    { id=${tomlString(task.id)}, name=${tomlString(task.name)}, estimate=${tomlNumber(task.estimate, "0")}${afterPart} },`,
    );
  }
  lines.push("]", "", "assignments = [");
  for (const assignment of definition.assignments) {
    const focus = String(assignment.focus_factor ?? "").trim();
    const focusPart = focus ? `, focus_factor=${tomlNumber(focus, "1")}` : "";
    lines.push(`    { task=${tomlString(assignment.task)}, owner=${tomlString(assignment.owner)}${focusPart} },`);
  }
  lines.push("]");
  if (definition.time_markers.length) {
    lines.push("", "time_markers = [");
    for (const marker of definition.time_markers) {
      const color = String(marker.color ?? "").trim();
      const colorPart = color ? `, color=${tomlString(color)}` : "";
      lines.push(`    { time=${tomlString(marker.time)}, label=${tomlString(marker.label)}${colorPart} },`);
    }
    lines.push("]");
  }
  return `${lines.join("\n")}\n`;
}
