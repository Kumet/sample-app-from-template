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
