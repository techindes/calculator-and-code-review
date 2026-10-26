"use strict";

const MAX_LENGTH = 100;
const TIMEOUT_MS = 10000;
const DECIMAL = /^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)$/;
const SYMBOLS = { "+": "+", "-": "\u2212", "*": "\u00d7", "/": "\u00f7" };
const ERRORS = Object.freeze({
  DIVISION_BY_ZERO: "Cannot divide by zero.",
  RESULT_OUT_OF_RANGE: "Result exceeds the 100-character limit.",
  INVALID_INPUT: "Enter a valid decimal number.",
  INVALID_OPERATOR: "Choose a supported operation.",
});
const display = document.querySelector(".display");
const output = document.querySelector("#result");
const expression = document.querySelector("#expression");
const status = document.querySelector("#status");
const statusText = document.querySelector("#status-text");
const keypad = document.querySelector("#keypad");
const buttons = [...keypad.querySelectorAll("button")];

let entry = "0";
let left = null;
let operator = null;
let phase = "entry";
let expressionText = "";
let message = "";
let isError = false;
let busy = false;
let generation = 0;
let controller = null;

function render() {
  output.textContent = entry;
  output.dataset.size = entry.length > 28 ? "long" : entry.length > 9 ? "medium" : "short";
  expression.textContent = expressionText || "\u00a0";
  statusText.textContent = busy ? "Calculating..." : message;
  statusText.classList.toggle("visually-hidden", !busy && !isError);
  status.dataset.error = String(isError);
  display.setAttribute("aria-busy", String(busy));
  for (const button of buttons) {
    button.disabled = busy && button.dataset.action !== "clear";
    if (button.dataset.operator) {
      button.setAttribute("aria-pressed", String(operator === button.dataset.operator));
    }
  }
}

function clear() {
  generation += 1;
  controller?.abort();
  controller = null;
  entry = "0";
  left = null;
  operator = null;
  phase = "entry";
  expressionText = "";
  message = "";
  isError = false;
  busy = false;
  render();
}

function prepareEntry() {
  if (phase !== "entry") {
    if (phase !== "waiting") {
      left = null;
      operator = null;
      expressionText = "";
    }
    entry = "0";
    phase = "entry";
  }
}

function setEntry(candidate) {
  if (candidate.length > MAX_LENGTH) {
    message = "Maximum 100 characters.";
    isError = true;
  } else {
    entry = candidate;
    message = "";
    isError = false;
  }
  render();
}

function enterDigit(digit) {
  prepareEntry();
  const prefix = entry.startsWith("-") ? "-" : "";
  setEntry(entry === "0" || entry === "-0" ? prefix + digit : entry + digit);
}

function enterDecimal() {
  prepareEntry();
  if (!entry.includes(".")) setEntry(entry + ".");
}

function changeSign() {
  if (phase === "waiting" || phase === "error") prepareEntry();
  if (phase === "result") {
    phase = "entry";
    expressionText = "";
  }
  setEntry(entry.startsWith("-") ? entry.slice(1) : "-" + entry);
}

function backspace() {
  if (phase !== "entry") return;
  const shortened = entry.slice(0, -1);
  setEntry(shortened === "" || shortened === "-" ? "0" : shortened);
}

async function evaluate(nextOperator = null) {
  if (busy || left === null || operator === null || phase !== "entry") return;
  const requestGeneration = ++generation;
  const activeController = new AbortController();
  controller = activeController;
  const payload = { left, operator, right: entry };
  const completedExpression = `${left} ${SYMBOLS[operator]} ${entry} =`;
  let timedOut = false;
  const timeout = setTimeout(() => {
    timedOut = true;
    activeController.abort();
  }, TIMEOUT_MS);
  busy = true;
  isError = false;
  render();
  try {
    const response = await fetch("/api/calculate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "omit",
      redirect: "error",
      body: JSON.stringify(payload),
      signal: activeController.signal,
    });
    const contentType = (response.headers.get("Content-Type") || "").split(";")[0].trim();
    if (contentType.toLowerCase() !== "application/json") throw new Error("protocol");
    const data = await response.json();
    if (requestGeneration !== generation) return;
    if (!data || typeof data !== "object" || Array.isArray(data)) throw new Error("protocol");
    if (!response.ok) {
      if (Object.keys(data).length === 2 && typeof data.message === "string" &&
          typeof data.error === "string" && Object.hasOwn(ERRORS, data.error)) {
        throw new Error(data.error);
      }
      throw new Error("protocol");
    }
    if (Object.keys(data).length !== 1 || typeof data.result !== "string" ||
        data.result.length > MAX_LENGTH || !DECIMAL.test(data.result)) {
      throw new Error("protocol");
    }
    entry = data.result;
    left = nextOperator ? entry : null;
    operator = nextOperator;
    phase = nextOperator ? "waiting" : "result";
    expressionText = nextOperator ? `${entry} ${SYMBOLS[nextOperator]}` : completedExpression;
    message = `Result: ${entry}`;
  } catch (error) {
    if (requestGeneration !== generation) return;
    left = null;
    operator = null;
    phase = "error";
    expressionText = completedExpression;
    entry = "0";
    isError = true;
    message = timedOut ? "Request timed out. Try again." :
      Object.hasOwn(ERRORS, error.message) ? ERRORS[error.message] :
      "Unable to calculate. Try again.";
  } finally {
    clearTimeout(timeout);
    if (requestGeneration === generation) {
      busy = false;
      controller = null;
      render();
    }
  }
}

function chooseOperator(nextOperator) {
  if (phase === "error") return;
  if (left !== null && phase === "entry") {
    void evaluate(nextOperator);
    return;
  }
  left = entry;
  operator = nextOperator;
  phase = "waiting";
  expressionText = `${left} ${SYMBOLS[operator]}`;
  message = "";
  isError = false;
  render();
}

function act(action, value) {
  if (action === "clear") {
    clear();
    return;
  }
  if (busy) return;
  if (action === "digit") enterDigit(value);
  else if (action === "operator") chooseOperator(value);
  else if (action === "decimal") enterDecimal();
  else if (action === "sign") changeSign();
  else if (action === "backspace") backspace();
  else if (action === "equals") void evaluate();
}

keypad.addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (!button || button.disabled) return;
  if (button.dataset.digit !== undefined) act("digit", button.dataset.digit);
  else if (button.dataset.operator) act("operator", button.dataset.operator);
  else act(button.dataset.action);
});

document.addEventListener("keydown", (event) => {
  if (event.ctrlKey || event.metaKey || event.altKey || event.isComposing ||
      event.target.matches("input, textarea, select, [contenteditable]")) return;
  let action;
  let value;
  if (/^[0-9]$/.test(event.key)) {
    action = "digit";
    value = event.key;
  } else if (Object.hasOwn(SYMBOLS, event.key)) {
    action = "operator";
    value = event.key;
  } else {
    action = { ".": "decimal", Enter: "equals", "=": "equals", Escape: "clear", Backspace: "backspace", F9: "sign" }[event.key];
  }
  if (action) {
    event.preventDefault();
    act(action, value);
  }
});

render();