"use strict";

const RESOURCE_NAMES = Object.freeze([
  "projects",
  "dashboard",
  "tasks",
  "taskDetail",
  "tags",
  "comments",
  "activities",
]);

function resourceFlags(initialValue) {
  return Object.fromEntries(RESOURCE_NAMES.map((name) => [name, initialValue]));
}

const state = {
  projects: [],
  selectedProjectId: null,
  dashboard: null,
  tasks: {
    items: [],
    total: 0,
    query: {
      q: "",
      status: [],
      priority: [],
      tagId: null,
      dueAfter: null,
      dueBefore: null,
      sort: "created_at",
      order: "asc",
      limit: 50,
      offset: 0,
    },
  },
  selectedTaskId: null,
  taskDetail: null,
  tags: [],
  comments: {
    items: [],
    total: 0,
    limit: 50,
    offset: 0,
  },
  activities: {
    items: [],
    total: 0,
    limit: 50,
    offset: 0,
  },
  loading: resourceFlags(false),
  errors: resourceFlags(null),
  activeRequests: resourceFlags(null),
  requestSequence: resourceFlags(0),
  mutationLocks: Object.create(null),
};

class ApiError extends Error {
  constructor(message, options = {}) {
    super(message);
    this.name = "ApiError";
    this.status = options.status ?? null;
    this.details = options.details ?? null;
    this.kind = options.kind ?? "response";
  }
}

class DuplicateMutationError extends Error {
  constructor(key) {
    super(`The ${key} operation is already in progress.`);
    this.name = "DuplicateMutationError";
  }
}

function isPlainObject(value) {
  if (value === null || typeof value !== "object") {
    return false;
  }
  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
}

function omitUndefined(value) {
  if (Array.isArray(value)) {
    return value.filter((item) => item !== undefined).map(omitUndefined);
  }
  if (!isPlainObject(value)) {
    return value;
  }
  return Object.fromEntries(
    Object.entries(value)
      .filter(([, item]) => item !== undefined)
      .map(([key, item]) => [key, omitUndefined(item)]),
  );
}

function validationMessage(detail) {
  if (!Array.isArray(detail)) {
    return null;
  }
  const messages = detail
    .map((item) => {
      if (!isPlainObject(item) || typeof item.msg !== "string") {
        return null;
      }
      const location = Array.isArray(item.loc)
        ? item.loc.filter((part) => part !== "body").join(".")
        : "";
      return location ? `${location}: ${item.msg}` : item.msg;
    })
    .filter((message) => message !== null);
  return messages.length > 0 ? messages.join("; ") : null;
}

function responseError(response, payload) {
  const detail = isPlainObject(payload) ? payload.detail : null;
  const message =
    (typeof detail === "string" && detail) ||
    validationMessage(detail) ||
    `Request failed with status ${response.status}.`;
  return new ApiError(message, {
    status: response.status,
    details: detail,
    kind: response.status === 422 ? "validation" : "response",
  });
}

async function parseResponse(response) {
  if (response.status === 204) {
    return null;
  }

  const body = await response.text();
  let payload = null;
  if (body !== "") {
    try {
      payload = JSON.parse(body);
    } catch (error) {
      if (!response.ok) {
        throw responseError(response, null);
      }
      throw new ApiError("The server returned an unreadable response.", {
        status: response.status,
        kind: "malformed",
      });
    }
  }

  if (!response.ok) {
    throw responseError(response, payload);
  }
  if (body === "") {
    throw new ApiError("The server returned an empty response.", {
      status: response.status,
      kind: "malformed",
    });
  }
  return payload;
}

function safeApiPath(path) {
  if (
    typeof path !== "string" ||
    !path.startsWith("/api/") ||
    path.startsWith("//") ||
    path.includes("\\") ||
    /[\u0000-\u001f\u007f]/u.test(path)
  ) {
    throw new ApiError("The API path is invalid.", { kind: "client" });
  }
  const url = new URL(path, window.location.origin);
  if (
    url.origin !== window.location.origin ||
    !url.pathname.startsWith("/api/")
  ) {
    throw new ApiError("The API path must be same-origin.", { kind: "client" });
  }
  return `${url.pathname}${url.search}`;
}

async function apiRequest(path, options = {}) {
  const method = options.method ?? "GET";
  const headers = { Accept: "application/json" };
  const request = {
    method,
    headers,
    credentials: "same-origin",
    referrerPolicy: "no-referrer",
    signal: options.signal,
  };
  if (options.json !== undefined) {
    headers["Content-Type"] = "application/json";
    request.body = JSON.stringify(omitUndefined(options.json));
  }

  let response;
  try {
    response = await fetch(safeApiPath(path), request);
  } catch (error) {
    if (error instanceof ApiError || error?.name === "AbortError") {
      throw error;
    }
    throw new ApiError("The server could not be reached.", {
      kind: "network",
    });
  }
  try {
    return await parseResponse(response);
  } catch (error) {
    if (error instanceof ApiError || error?.name === "AbortError") {
      throw error;
    }
    throw new ApiError("The server response could not be read.", {
      kind: "network",
    });
  }
}

function requireResource(resource) {
  if (!RESOURCE_NAMES.includes(resource)) {
    throw new TypeError(`Unknown resource: ${resource}`);
  }
}

function beginRequest(resource) {
  requireResource(resource);
  const previous = state.activeRequests[resource];
  if (previous !== null) {
    previous.controller.abort();
  }
  const identity = state.requestSequence[resource] + 1;
  const handle = {
    resource,
    identity,
    controller: new AbortController(),
  };
  state.requestSequence[resource] = identity;
  state.activeRequests[resource] = handle;
  state.loading[resource] = true;
  state.errors[resource] = null;
  return handle;
}

function isCurrentRequest(handle) {
  return state.activeRequests[handle.resource]?.identity === handle.identity;
}

function completeRequest(handle, error = null) {
  if (!isCurrentRequest(handle)) {
    return false;
  }
  state.activeRequests[handle.resource] = null;
  state.loading[handle.resource] = false;
  state.errors[handle.resource] = error;
  return true;
}

async function requestLatest(resource, path, options = {}) {
  const handle = beginRequest(resource);
  try {
    const data = await apiRequest(path, {
      ...options,
      signal: handle.controller.signal,
    });
    if (!completeRequest(handle)) {
      return { accepted: false, data: null };
    }
    return { accepted: true, data };
  } catch (error) {
    const aborted = error?.name === "AbortError";
    const current = isCurrentRequest(handle);
    if (!current || aborted) {
      if (current) {
        completeRequest(handle);
      }
      return { accepted: false, data: null };
    }
    completeRequest(handle, error);
    throw error;
  }
}

async function runMutation(key, operation) {
  if (state.mutationLocks[key] === true) {
    throw new DuplicateMutationError(key);
  }
  state.mutationLocks[key] = true;
  try {
    return await operation();
  } finally {
    delete state.mutationLocks[key];
  }
}

function showStatus(message) {
  const output = document.getElementById("global-status");
  output.textContent = message;
}

function showError(error) {
  const output = document.getElementById("global-error");
  output.textContent =
    error instanceof Error ? error.message : "An unexpected error occurred.";
  output.hidden = false;
}

function clearError() {
  const output = document.getElementById("global-error");
  output.textContent = "";
  output.hidden = true;
}

function element(tagName, text = null) {
  const node = document.createElement(tagName);
  if (text !== null) {
    node.textContent = String(text);
  }
  return node;
}

function setExplicitState(resource, itemCount) {
  const loading = document.getElementById(`${resource}-loading`);
  const empty = document.getElementById(`${resource}-empty`);
  const error = document.getElementById(`${resource}-error`);
  loading.hidden = !state.loading[resource];
  error.hidden = state.errors[resource] === null;
  if (state.errors[resource] !== null) {
    error.textContent = state.errors[resource].message;
  }
  empty.hidden =
    state.loading[resource] || state.errors[resource] !== null || itemCount !== 0;
}

function projectApiPath(projectId, suffix = "") {
  if (!Number.isInteger(projectId) || projectId <= 0) {
    throw new ApiError("The selected Project is invalid.", { kind: "client" });
  }
  return `/api/projects/${projectId}${suffix}`;
}

function selectedProject() {
  return (
    state.projects.find((project) => project.id === state.selectedProjectId) ??
    null
  );
}

function cancelResourceRequest(resource) {
  const active = state.activeRequests[resource];
  if (active !== null) {
    active.controller.abort();
  }
  state.activeRequests[resource] = null;
  state.loading[resource] = false;
  state.errors[resource] = null;
}

function resetProjectDependents() {
  for (const resource of RESOURCE_NAMES.filter(
    (name) => name !== "projects",
  )) {
    cancelResourceRequest(resource);
  }
  state.dashboard = null;
  state.tasks.items = [];
  state.tasks.total = 0;
  state.tasks.query.offset = 0;
  state.selectedTaskId = null;
  state.taskDetail = null;
  state.tags = [];
  state.comments.items = [];
  state.comments.total = 0;
  state.comments.offset = 0;
  state.activities.items = [];
  state.activities.total = 0;
  state.activities.offset = 0;
}

function renderProjectList() {
  const list = document.getElementById("project-list");
  const fragment = document.createDocumentFragment();
  for (const project of state.projects) {
    const item = element("li");
    const button = element("button", project.name);
    button.type = "button";
    if (project.id === state.selectedProjectId) {
      button.setAttribute("aria-current", "page");
    }
    button.addEventListener("click", () => selectProject(project.id));
    item.append(button);
    fragment.append(item);
  }
  list.replaceChildren(fragment);
  list.setAttribute("aria-busy", String(state.loading.projects));
  setExplicitState("projects", state.projects.length);
}

function renderSelectedProject() {
  const project = selectedProject();
  document.getElementById("no-project-view").hidden = project !== null;
  document.getElementById("project-view").hidden = project === null;
  if (project === null) {
    document.getElementById("selected-project-heading").textContent =
      "Project details";
    document.getElementById("selected-project-description").textContent = "";
    document.getElementById("project-edit-panel").hidden = true;
    return;
  }
  document.getElementById("selected-project-heading").textContent = project.name;
  document.getElementById("selected-project-description").textContent =
    project.description ?? "No description.";
}

function addDefinition(list, label, value) {
  list.append(element("dt", label), element("dd", value));
}

function titledDefinitionList(title, values) {
  const section = element("section");
  section.append(element("h3", title));
  const list = element("dl");
  for (const [label, value] of values) {
    addDefinition(list, label, value);
  }
  section.append(list);
  return section;
}

function renderDashboard() {
  const content = document.getElementById("dashboard-content");
  const asOf = document.getElementById("dashboard-as-of");
  content.setAttribute("aria-busy", String(state.loading.dashboard));
  setExplicitState("dashboard", state.dashboard === null ? 0 : 1);

  if (state.dashboard === null) {
    asOf.textContent = "";
    content.replaceChildren();
    return;
  }

  const dashboard = state.dashboard;
  asOf.textContent = `As of ${dashboard.as_of}`;
  const fragment = document.createDocumentFragment();
  fragment.append(
    titledDefinitionList("Task counts", [
      ["Total", dashboard.tasks.total],
      ["Todo", dashboard.tasks.by_status.todo],
      ["In progress", dashboard.tasks.by_status.in_progress],
      ["Done", dashboard.tasks.by_status.done],
      ["Low priority", dashboard.tasks.by_priority.low],
      ["Medium priority", dashboard.tasks.by_priority.medium],
      ["High priority", dashboard.tasks.by_priority.high],
    ]),
    titledDefinitionList("Due dates", [
      ["Active Tasks", dashboard.due.active_total],
      ["Overdue", dashboard.due.overdue],
      ["Due today", dashboard.due.due_today],
      ["Upcoming 7 days", dashboard.due.upcoming_7_days],
      ["Later", dashboard.due.later],
      ["No due date", dashboard.due.no_due_date],
    ]),
    titledDefinitionList("Comments", [
      ["Total Comments", dashboard.comments.total],
      ["Tasks with Comments", dashboard.comments.tasks_with_comments],
    ]),
  );

  const tagsSection = element("section");
  tagsSection.append(element("h3", "Tags"));
  if (dashboard.tags.length === 0) {
    tagsSection.append(element("p", "No Tags."));
  } else {
    const tags = element("ul");
    for (const tag of dashboard.tags) {
      tags.append(element("li", `${tag.name}: ${tag.task_count} Tasks`));
    }
    tagsSection.append(tags);
  }
  fragment.append(tagsSection);

  const activitySection = element("section");
  activitySection.append(element("h3", "Recent Activity"));
  if (dashboard.recent_activities.length === 0) {
    activitySection.append(element("p", "No recent Activity."));
  } else {
    const activities = element("ol");
    for (const activity of dashboard.recent_activities) {
      const item = element("li");
      const details = element("dl");
      addDefinition(details, "Event", activity.event_type);
      addDefinition(details, "Task", activity.task_id);
      addDefinition(details, "Comment", activity.comment_id);
      addDefinition(details, "Occurred at", activity.occurred_at);
      item.append(details);
      activities.append(item);
    }
    activitySection.append(activities);
  }
  fragment.append(activitySection);
  content.replaceChildren(fragment);
}

async function loadProjects() {
  const pending = requestLatest("projects", "/api/projects");
  renderProjectList();
  try {
    const result = await pending;
    if (!result.accepted) {
      return;
    }
    state.projects = result.data;
    if (
      state.selectedProjectId !== null &&
      selectedProject() === null
    ) {
      state.selectedProjectId = null;
      resetProjectDependents();
    }
    renderProjectList();
    renderSelectedProject();
    renderDashboard();
  } catch (error) {
    renderProjectList();
    showError(error);
  }
}

async function loadDashboard() {
  const projectId = state.selectedProjectId;
  if (projectId === null) {
    state.dashboard = null;
    renderDashboard();
    return;
  }
  const pending = requestLatest(
    "dashboard",
    projectApiPath(projectId, "/dashboard"),
  );
  renderDashboard();
  try {
    const result = await pending;
    if (!result.accepted || state.selectedProjectId !== projectId) {
      return;
    }
    state.dashboard = result.data;
    renderDashboard();
  } catch (error) {
    renderDashboard();
    showError(error);
  }
}

function selectProject(projectId) {
  if (!state.projects.some((project) => project.id === projectId)) {
    return;
  }
  state.selectedProjectId = projectId;
  resetProjectDependents();
  clearError();
  renderProjectList();
  renderSelectedProject();
  renderDashboard();
  showStatus(`Selected Project ${selectedProject().name}.`);
  loadDashboard();
}

function projectPayload(form) {
  const data = new FormData(form);
  return {
    name: String(data.get("name") ?? ""),
    description: String(data.get("description") ?? ""),
  };
}

async function createProject(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const submit = form.querySelector('button[type="submit"]');
  clearError();
  submit.disabled = true;
  try {
    const created = await runMutation("createProject", () =>
      apiRequest("/api/projects", {
        method: "POST",
        json: projectPayload(form),
      }),
    );
    state.projects = [...state.projects, created];
    form.reset();
    document.getElementById("project-create-panel").hidden = true;
    renderProjectList();
    selectProject(created.id);
    showStatus(`Created Project ${created.name}.`);
  } catch (error) {
    showError(error);
  } finally {
    submit.disabled = false;
  }
}

function openProjectEditor() {
  const project = selectedProject();
  if (project === null) {
    return;
  }
  const panel = document.getElementById("project-edit-panel");
  document.getElementById("project-edit-name").value = project.name;
  document.getElementById("project-edit-description").value =
    project.description ?? "";
  panel.hidden = false;
  document.getElementById("project-edit-name").focus();
}

async function updateProject(event) {
  event.preventDefault();
  const projectId = state.selectedProjectId;
  if (projectId === null) {
    return;
  }
  const form = event.currentTarget;
  const submit = form.querySelector('button[type="submit"]');
  clearError();
  submit.disabled = true;
  try {
    const updated = await runMutation("updateProject", () =>
      apiRequest(projectApiPath(projectId), {
        method: "PATCH",
        json: projectPayload(form),
      }),
    );
    if (state.selectedProjectId !== projectId) {
      return;
    }
    state.projects = state.projects.map((project) =>
      project.id === updated.id ? updated : project,
    );
    document.getElementById("project-edit-panel").hidden = true;
    renderProjectList();
    renderSelectedProject();
    showStatus(`Updated Project ${updated.name}.`);
    await loadDashboard();
  } catch (error) {
    showError(error);
  } finally {
    submit.disabled = false;
  }
}

function requestProjectDeletion() {
  const project = selectedProject();
  if (project === null) {
    return;
  }
  const dialog = document.getElementById("destructive-confirmation-dialog");
  dialog.dataset.action = "delete-project";
  document.getElementById("confirmation-message").textContent =
    `Delete Project ${project.name}? This action cannot be undone.`;
  dialog.showModal();
}

async function deleteSelectedProject() {
  const project = selectedProject();
  if (project === null) {
    return;
  }
  const projectId = project.id;
  clearError();
  document.getElementById("delete-project-button").disabled = true;
  try {
    await runMutation("deleteProject", () =>
      apiRequest(projectApiPath(projectId), { method: "DELETE" }),
    );
    if (state.selectedProjectId !== projectId) {
      return;
    }
    state.projects = state.projects.filter((item) => item.id !== projectId);
    state.selectedProjectId = null;
    resetProjectDependents();
    renderProjectList();
    renderSelectedProject();
    renderDashboard();
    showStatus(`Deleted Project ${project.name}.`);
    await loadProjects();
  } catch (error) {
    showError(error);
  } finally {
    document.getElementById("delete-project-button").disabled = false;
  }
}

function setupProjectUi() {
  document.getElementById("new-project-button").addEventListener("click", () => {
    const panel = document.getElementById("project-create-panel");
    panel.hidden = false;
    document.getElementById("project-create-name").focus();
  });
  document
    .getElementById("cancel-project-create-button")
    .addEventListener("click", () => {
      document.getElementById("project-create-panel").hidden = true;
    });
  document
    .getElementById("project-create-form")
    .addEventListener("submit", createProject);
  document
    .getElementById("edit-project-button")
    .addEventListener("click", openProjectEditor);
  document
    .getElementById("cancel-project-edit-button")
    .addEventListener("click", () => {
      document.getElementById("project-edit-panel").hidden = true;
    });
  document
    .getElementById("project-edit-form")
    .addEventListener("submit", updateProject);
  document
    .getElementById("delete-project-button")
    .addEventListener("click", requestProjectDeletion);
  document
    .getElementById("destructive-confirmation-dialog")
    .addEventListener("close", (event) => {
      const dialog = event.currentTarget;
      if (
        dialog.returnValue === "confirm" &&
        dialog.dataset.action === "delete-project"
      ) {
        deleteSelectedProject();
      }
      delete dialog.dataset.action;
    });
}

setupProjectUi();
renderProjectList();
renderSelectedProject();
renderDashboard();
loadProjects();
