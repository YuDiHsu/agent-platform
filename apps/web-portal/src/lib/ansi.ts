// Implements: REQ-010. Minimal SGR parser so terminal output keeps its colours without raw escape codes.

export interface AnsiSpan {
  text: string;
  className: string;
}

const COLORS = ["black", "red", "green", "yellow", "blue", "magenta", "cyan", "white"];
// eslint-disable-next-line no-control-regex
const ESCAPE = /\x1b\[([0-9;]*)m/g;
// eslint-disable-next-line no-control-regex
const OTHER_ESCAPES = /\x1b\[[0-9;?]*[A-LN-Za-ln-z]/g;

export function parseAnsi(input: string): AnsiSpan[] {
  const text = input.replace(OTHER_ESCAPES, "");
  const spans: AnsiSpan[] = [];
  let classes = new Set<string>();
  let cursor = 0;

  const push = (chunk: string) => {
    if (chunk) spans.push({ text: chunk, className: [...classes].join(" ") });
  };

  for (const match of text.matchAll(ESCAPE)) {
    push(text.slice(cursor, match.index));
    cursor = (match.index ?? 0) + match[0].length;
    const codes = match[1] === "" ? [0] : match[1].split(";").map(Number);
    for (const code of codes) {
      if (code === 0) classes = new Set();
      else if (code === 1) classes.add("ansi-bold");
      else if (code === 22) classes.delete("ansi-bold");
      else if (code >= 30 && code <= 37) setColor(classes, `ansi-fg-${COLORS[code - 30]}`);
      else if (code >= 90 && code <= 97) setColor(classes, `ansi-fg-bright-${COLORS[code - 90]}`);
      else if (code === 39) setColor(classes, "");
    }
  }
  push(text.slice(cursor));
  return spans;
}

function setColor(classes: Set<string>, next: string): void {
  for (const name of [...classes]) {
    if (name.startsWith("ansi-fg-")) classes.delete(name);
  }
  if (next) classes.add(next);
}
