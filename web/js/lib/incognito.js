// Incognito — a conversation the user asked NOT to keep.
//
// The panel's half of the feature, kept pure so it can be tested without a
// DOM. The toggle itself lives in the composer toolbar (comfyui-mcp-panel.js);
// these three decisions are what it changes:
//
//   - persistableThreads: an incognito thread never reaches the durable
//     history store (IndexedDB), so a reload forgets it;
//   - withIncognito: the outbound user_message carries `incognito: true`
//     while the toggle is on, and the orchestrator then keeps nothing of its
//     own (no log text, no resume record, no transcript, the Claude session
//     file deleted at turn end);
//   - markIncognito: the thread a message is recorded into while the toggle
//     is on becomes incognito, and STAYS so — a conversation that already
//     went unrecorded does not become recordable by flipping the toggle off.
//
// Langfuse, on the custom lane's proxy, is deliberately outside this: it is
// the user's own observability, switched on by them.

/** The threads that may be written to the durable history store. */
export function persistableThreads(threads) {
  if (!Array.isArray(threads)) return [];
  return threads.filter((t) => !(t && typeof t === "object" && t.incognito === true));
}

/** The outbound frame, stamped while the toggle is on; untouched otherwise. */
export function withIncognito(frame, on) {
  return on === true ? { ...frame, incognito: true } : frame;
}

/**
 * Flag `thread` as incognito when the toggle is on. Returns whether the thread
 * is incognito afterwards (a thread flagged earlier stays flagged).
 */
export function markIncognito(thread, on) {
  if (!thread || typeof thread !== "object") return false;
  if (on === true) thread.incognito = true;
  return thread.incognito === true;
}
