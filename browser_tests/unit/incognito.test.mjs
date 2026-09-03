// Incognito — a conversation the user asked NOT to keep. The panel's half of
// the feature is three decisions, pure enough to test without a DOM:
//
//   - which threads reach the durable history store (never an incognito one);
//   - what an outbound user_message frame carries (the flag, when the toggle
//     is on, so the orchestrator keeps nothing of its own either);
//   - which thread becomes incognito (the one a message is recorded into
//     while the toggle is on — and it stays so: half-kept is not kept).

import { test } from "node:test";
import assert from "node:assert/strict";
import { markIncognito, persistableThreads, withIncognito } from "../../web/js/lib/incognito.js";

test("persistableThreads drops incognito threads and keeps the others in order", () => {
  const threads = [
    { id: "a", incognito: true },
    { id: "b" },
    { id: "c", incognito: false },
    { id: "d", incognito: true },
  ];
  assert.deepEqual(persistableThreads(threads).map((t) => t.id), ["b", "c"]);
  // Not mutated, not reordered.
  assert.equal(threads.length, 4);
  assert.deepEqual(persistableThreads(undefined), []);
});

test("withIncognito stamps the outbound frame only while the toggle is on", () => {
  const frame = { type: "user_message", text: "hello" };
  assert.deepEqual(withIncognito(frame, true), { type: "user_message", text: "hello", incognito: true });
  assert.deepEqual(withIncognito(frame, false), frame);
  assert.equal(Object.hasOwn(withIncognito(frame, false), "incognito"), false);
});

test("markIncognito flags a thread when the toggle is on, and never un-flags it", () => {
  const thread = { id: "t", msgs: [] };
  assert.equal(markIncognito(thread, false), false);
  assert.equal(thread.incognito, undefined);
  assert.equal(markIncognito(thread, true), true);
  assert.equal(thread.incognito, true);
  // Toggling off later does not make a conversation that already went
  // unrecorded recordable: what was said stays out of the history.
  assert.equal(markIncognito(thread, false), true);
  assert.equal(thread.incognito, true);
  assert.equal(markIncognito(null, true), false);
});
