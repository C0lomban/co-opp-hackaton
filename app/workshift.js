// Workshift module.
// Principle: the AI understands messy human input, plain code does the math.
//
//   1. Availability agent (AI, mock fallback): free text notes -> structured availability
//   2. Scheduler (code): assigns shifts fairly, respecting availability, preferences, hour target
//   3. Workshift agent (AI, mock fallback): drafts the weekly announcement and reminders
//
// Works in Node (require) and in the browser (standalone build), like agents.js.

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const DAY_WORDS = {
  mon: "Mon", monday: "Mon", mondays: "Mon", tue: "Tue", tues: "Tue", tuesday: "Tue", tuesdays: "Tue",
  wed: "Wed", wednesday: "Wed", wednesdays: "Wed", thu: "Thu", thur: "Thu", thurs: "Thu", thursday: "Thu", thursdays: "Thu",
  fri: "Fri", friday: "Fri", fridays: "Fri", sat: "Sat", saturday: "Sat", saturdays: "Sat",
  sun: "Sun", sunday: "Sun", sundays: "Sun",
};
const CATEGORIES = {
  kitchen: ["kitchen", "dish", "dishes", "cook", "cooking", "dinner", "lunch", "breakfast", "food", "pots"],
  cleaning: ["clean", "cleaning", "bathroom", "bathrooms", "sweep", "mop", "vacuum", "trash", "recycling", "compost"],
  outdoor: ["garden", "yard", "outdoor", "outside", "porch"],
  errands: ["groceries", "shopping", "errand", "errands", "pickup", "delivery"],
};

function categoryOf(text) {
  const t = text.toLowerCase();
  for (const [cat, words] of Object.entries(CATEGORIES)) if (words.some((w) => t.includes(w))) return cat;
  return "other";
}

// ---------- parsing the raw inputs (plain code) ----------

// "Dishes after dinner | Mon | 2"
function parseShifts(text) {
  return text.split("\n").map((l) => l.trim()).filter(Boolean).map((line, i) => {
    const [name, day, hours] = line.split("|").map((s) => (s || "").trim());
    const d = DAY_WORDS[(day || "").toLowerCase()] || "Mon";
    return { id: `s${i + 1}`, name, day: d, hours: Number(hours) || 1, category: categoryOf(name) };
  });
}

// "Alice: can't do Thursdays, prefers kitchen | done 2"
function splitMembers(text) {
  return text.split("\n").map((l) => l.trim()).filter(Boolean).map((line) => {
    const [main, done] = line.split("|");
    const idx = main.indexOf(":");
    const name = (idx >= 0 ? main.slice(0, idx) : main).trim();
    const notes = idx >= 0 ? main.slice(idx + 1).trim() : "";
    const m = (done || "").match(/(\d+(?:\.\d+)?)/);
    return { name, notes, lastWeekDone: m ? Number(m[1]) : null };
  });
}

// ---------- 1. Availability agent ----------

function mockAvailability(members) {
  return members.map((m) => {
    const t = m.notes.toLowerCase();
    const unavailable = new Set();
    // negative phrases followed by days: "can't do Thursdays", "no Mon or Tue", "busy on Friday"
    const neg = /(can'?t|cannot|can not|no|not|busy|away|unavailable|never)\b([^.;,]*)/g;
    let r;
    while ((r = neg.exec(t))) {
      for (const w of r[2].split(/[^a-z]+/)) if (DAY_WORDS[w]) unavailable.add(DAY_WORDS[w]);
    }
    if (/weekends?/.test(t) && /(can'?t|no|not|busy|away)[^.;]*weekends?/.test(t)) { unavailable.add("Sat"); unavailable.add("Sun"); }
    const prefers = [];
    const pos = /(prefer|prefers|love|loves|like|likes|happy to do|good at)\b([^.;]*)/g;
    while ((r = pos.exec(t))) { const c = categoryOf(r[2]); if (c !== "other") prefers.push(c); }
    const avoids = [];
    const av = /(hate|hates|avoid|allergic|not good at|no )\b([^.;]*)/g;
    while ((r = av.exec(t))) { const c = categoryOf(r[2]); if (c !== "other") avoids.push(c); }
    return { name: m.name, unavailableDays: [...unavailable], prefers: [...new Set(prefers)], avoids: [...new Set(avoids)], lastWeekDone: m.lastWeekDone, notes: m.notes };
  });
}

async function liveAvailability(members, callClaude) {
  const out = await callClaude(
    "You are the Availability agent of a student housing co-op. You turn members' free text notes into structured availability. " +
      "Days must be one of Mon, Tue, Wed, Thu, Fri, Sat, Sun. Categories must be one of kitchen, cleaning, outdoor, errands. " +
      "Only use what the note says; if a note is empty, return empty lists. " +
      'Return only JSON: {"members":[{"name":string,"unavailableDays":[string],"prefers":[string],"avoids":[string]}]}',
    members.map((m) => `${m.name}: ${m.notes || "(no notes)"}`).join("\n")
  );
  const byName = Object.fromEntries(out.members.map((m) => [m.name.toLowerCase(), m]));
  return members.map((m) => {
    const p = byName[m.name.toLowerCase()] || {};
    return {
      name: m.name,
      unavailableDays: (p.unavailableDays || []).filter((d) => DAYS.includes(d)),
      prefers: p.prefers || [], avoids: p.avoids || [],
      lastWeekDone: m.lastWeekDone, notes: m.notes,
    };
  });
}

// ---------- 2. Scheduler (plain code, deterministic) ----------

function schedule(people, shifts, targetHours) {
  const load = Object.fromEntries(people.map((p) => [p.name, 0]));
  const lastCat = {};
  const assignments = [];
  const unfilled = [];
  // hardest to fill first: fewest eligible people, then longest
  const eligible = (s) => people.filter((p) => !p.unavailableDays.includes(s.day));
  const order = [...shifts].sort((a, b) => eligible(a).length - eligible(b).length || b.hours - a.hours);

  for (const s of order) {
    const cands = eligible(s)
      .filter((p) => load[p.name] + s.hours <= targetHours + 1) // allow 1h over target at most
      .map((p) => {
        let score = load[p.name] * 10;                // fairness first
        if (p.prefers.includes(s.category)) score -= 6; // preference bonus
        if (p.avoids.includes(s.category)) score += 8;  // avoid penalty
        if (lastCat[p.name] === s.category) score += 2; // variety
        return { p, score };
      })
      .sort((a, b) => a.score - b.score || a.p.name.localeCompare(b.p.name));
    if (!cands.length) { unfilled.push({ ...s, reason: eligible(s).length ? "everyone available already has enough hours" : `nobody is available on ${s.day}` }); continue; }
    const who = cands[0].p;
    load[who.name] += s.hours;
    lastCat[who.name] = s.category;
    const why = [];
    if (who.prefers.includes(s.category)) why.push(`prefers ${s.category}`);
    if (who.avoids.includes(s.category)) why.push(`note: usually avoids ${s.category}`);
    assignments.push({ ...s, member: who.name, why: why.join(", ") });
  }

  assignments.sort((a, b) => DAYS.indexOf(a.day) - DAYS.indexOf(b.day));
  const members = people.map((p) => ({
    name: p.name, hours: load[p.name], target: targetHours,
    status: load[p.name] >= targetHours ? "ok" : "under",
    lastWeekDone: p.lastWeekDone,
    behindLastWeek: p.lastWeekDone != null && p.lastWeekDone < targetHours,
    unavailableDays: p.unavailableDays, prefers: p.prefers,
  }));
  const totalNeeded = people.length * targetHours;
  const totalOffered = shifts.reduce((a, s) => a + s.hours, 0);
  return { assignments, unfilled, members, totalNeeded, totalOffered };
}

// ---------- 3. Workshift agent (announcement + reminders) ----------

function mockMessages({ houseName, weekOf }, plan) {
  const house = houseName || "the house";
  const byDay = DAYS.map((d) => {
    const items = plan.assignments.filter((a) => a.day === d);
    return items.length ? `${d}: ${items.map((a) => `${a.name} (${a.member}, ${a.hours}h)`).join("; ")}` : null;
  }).filter(Boolean);
  const announcement = {
    subject: `Workshifts for the week of ${weekOf} at ${house}`,
    body:
      `Hi everyone,\n\nHere are this week's workshifts:\n\n${byDay.join("\n")}\n\n` +
      (plan.unfilled.length ? `Still open, volunteers welcome: ${plan.unfilled.map((u) => `${u.name} (${u.day})`).join(", ")}.\n\n` : "") +
      `Can't make your shift? Find a swap and tell the workshift manager before the shift starts.\n\nThanks for keeping ${house} running,\n[Workshift manager]`,
  };
  const reminders = plan.members.filter((m) => m.behindLastWeek).map((m) => ({
    to: m.name,
    body: `Hi ${m.name}, quick heads up: you logged ${m.lastWeekDone}h of workshift last week, below the ${m.target}h we each owe. ` +
      `This week you have ${m.hours}h assigned. If something is going on, let me know and we'll figure it out together. [Workshift manager]`,
  }));
  return { announcement, reminders };
}

async function liveMessages(input, plan, callClaude) {
  return callClaude(
    "You are the Workshift agent of a student housing co-op. You write friendly, short messages for the workshift manager to review and send; you never send anything yourself. " +
      "Use only the schedule data given. Reminders must be kind, never shaming, and offer help. " +
      'Return only JSON: {"announcement":{"subject":string,"body":string},"reminders":[{"to":string,"body":string}]}. ' +
      "Write one reminder only for members whose behindLastWeek is true.",
    `House: ${input.houseName || "the house"}\nWeek of: ${input.weekOf}\nSchedule:\n${JSON.stringify(plan, null, 2)}`
  );
}

// ---------- pipeline ----------

async function runWorkshift(raw, { callClaude, liveAvailable } = {}) {
  const input = {
    members: raw.members || "", shifts: raw.shifts || "",
    targetHours: Number(raw.targetHours) || 4,
    houseName: raw.houseName || "", weekOf: raw.weekOf || new Date().toISOString().slice(0, 10),
  };
  let mode = raw.mode === "live" && callClaude && liveAvailable && liveAvailable() ? "live" : "mock";
  const log = [];
  const run = async (agent, action, liveFn, mockFn, summarize) => {
    const t0 = Date.now(); let res, used = mode, fb = null;
    if (mode === "live") { try { res = await liveFn(); } catch (e) { fb = e.message.slice(0, 160); used = "mock"; } }
    if (used === "mock") res = mockFn();
    log.push({ agent, action, ms: Date.now() - t0, mode: used, summary: summarize(res) + (fb ? ` · Live AI failed (${fb}), used demo agent` : "") });
    return { res, fb };
  };

  const rawMembers = splitMembers(input.members);
  const shifts = parseShifts(input.shifts);

  const a = await run("Availability agent", "Read members' notes and extracted availability",
    () => liveAvailability(rawMembers, callClaude), () => mockAvailability(rawMembers),
    (ps) => `${ps.length} members · ${ps.filter((p) => p.unavailableDays.length).length} with day constraints`);

  const t0 = Date.now();
  const plan = schedule(a.res, shifts, input.targetHours);
  log.push({ agent: "Scheduler (code)", action: "Assigned shifts fairly, respecting availability and preferences", ms: Date.now() - t0, mode: "code",
    summary: `${plan.assignments.length}/${shifts.length} shifts filled · ${plan.members.filter((m) => m.status === "under").length} members under ${input.targetHours}h` });

  const m = await run("Workshift agent", "Drafted the weekly announcement and reminders",
    () => liveMessages(input, plan, callClaude), () => mockMessages(input, plan),
    (r) => `announcement + ${r.reminders.length} reminder(s)`);

  log.push({ agent: "Orchestrator", action: "Handed the plan to the workshift manager for review", ms: 0, mode: "code", summary: "Nothing is sent automatically. The manager decides." });

  const anyFallback = a.fb || m.fb;
  return { mode: mode === "live" && !anyFallback ? "live" : "mock", fallback: anyFallback, people: a.res, ...plan, ...m.res, log };
}

module.exports = { runWorkshift, parseShifts, splitMembers, mockAvailability, schedule };
