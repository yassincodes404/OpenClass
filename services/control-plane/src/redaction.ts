/** Redaction for safe display/log copies (mirrors the engine's redaction module). */

const EMAIL = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g;
const PHONE = /(?<!\d)(?:\+?\d{1,3}[\s-]?)?(?:\(\d{2,4}\)[\s-]?)?\d{3,4}[\s-]?\d{3,4}(?!\d)/g;
const CREDIT_CARD = /\b(?:\d[ -]?){13,16}\b/g;
const SSN = /\b\d{3}-\d{2}-\d{4}\b/g;
const SECRET_TOKEN = /\b(?:sk|pk|api|bearer|token|oc_dev)[-_]?(?:key|token)?[A-Za-z0-9_-]{12,}\b/gi;

const DEFAULT_PATTERNS = [CREDIT_CARD, SSN, EMAIL, PHONE, SECRET_TOKEN];

export function redactText(text: string, blocklist: readonly string[] = []): string {
  let redacted = text;
  for (const term of blocklist) {
    if (term.trim()) redacted = redacted.split(term).join("[redacted]");
  }
  for (const pattern of DEFAULT_PATTERNS) {
    redacted = redacted.replace(pattern, "[redacted]");
  }
  return redacted;
}
