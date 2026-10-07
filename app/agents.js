// Agent interface used by the web app.
//
// runPipeline(input) -> { motion, checks, agenda, email, log, mode }
//
// Two modes:
//   - "mock": deterministic, rule based, no API key needed. Good for demos offline.
//   - "live": calls Claude (needs ANTHROPIC_API_KEY). Every quote returned by the
//             model is verified against the bylaws text; unverifiable quotes are
//             downgraded to UNCLEAR (guardrail: never invent bylaw text).
//
// Track B (/agents/governance) and Track C (/orchestration) can replace
// runGovernance / runCompliance with their own implementation as long as they
// keep the same input and output shapes.

// Provider: a Kylon key (pak_...) routes Claude calls through Kylon's proxy and its credits.
// Otherwise a direct Anthropic key is used.
const USE_KYLON = !!process.env.KYLON_API_KEY;
const API_KEY = () => process.env.KYLON_API_KEY || process.env.ANTHROPIC_API_KEY;
const API_URL = () => USE_KYLON
  ? "https://api.kylon.io/proxy/anthropic/v1/messages"
  : "https://api.anthropic.com/v1/messages";
const MODEL = process.env.ANTHROPIC_MODEL || (USE_KYLON ? "claude-sonnet-4-6" : "claude-sonnet-5-5");

// ---------- helpers ----------

function parseBylaws(text) {
  // Split into sections such as "Section 2.2. ..." or "Article 4. Shifts. ..."
  const clean = text.replace(/\r/g, "");
  const parts = clean.split(/(?=\b(?:Section\s+\d+(?:\.\d+)*\.|Article\s+\d+\.))/g);
  return parts
    .map((p) => p.trim())
    .filter((p) => /^(Section|Article)\s+\d/.test(p))
    .map((p) => {
      const id = p.match(/^(Section\s+\d+(?:\.\d+)*|Article\s+\d+)/)[1];
      return { id, text: p.replace(/\s+/g, " ") };
    });
}

function findSection(sections, regex) {
  return sections.find((s) => regex.test(s.text));
}

function daysBetween(a, b) {
  return Math.round((new Date(b) - new Date(a)) / 86400000);
}

function addDays(date, n) {
  const d = new Date(date);
  d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
}

function fmt(date) {
  return new Date(date + "T12:00:00").toLocaleDateString("en-US", {
    weekday: "long", month: "long", day: "numeric", year: "numeric",
  });
}

const WORDS = { one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10, fourteen: 14, thirty: 30 };
function num(s) { return /^\d+$/.test(s) ? Number(s) : WORDS[s.toLowerCase()]; }

function normalize(s) { return s.replace(/\s+/g, " ").trim().toLowerCase(); }

// ---------- MOCK agents ----------

function mockCompliance({ bylaws, memberCount, gaDate, proposal, today }) {
  const sections = parseBylaws(bylaws);
  const checks = [];

  // 1. Who can propose
  const s1 = findSection(sections, /propose/i);
  if (s1) {
    const needsSeconder = /second/i.test(s1.text);
    checks.push({
      rule: "Who can propose",
      status: needsSeconder ? "UNCLEAR" : "PASS",
      section: s1.id,
      quote: s1.text,
      explanation: needsSeconder
        ? "Any member can propose, but a seconder is required. Fill in the seconder's name before sending."
        : "Any member can propose this motion.",
    });
  } else {
    checks.push({ rule: "Who can propose", status: "UNCLEAR", section: null, quote: null, explanation: "No rule about who can propose was found in the bylaws." });
  }

  // 2. Notice period
  const s2 = findSection(sections, /notice/i);
  const daysLeft = daysBetween(today, gaDate);
  if (s2) {
    const m = s2.text.match(/at least (\w+) days/i);
    const n = m ? num(m[1]) : null;
    if (n != null) {
      const deadline = addDays(gaDate, -n);
      const ok = daysLeft >= n;
      checks.push({
        rule: "Notice period",
        status: ok ? "PASS" : "FAIL",
        section: s2.id,
        quote: s2.text,
        explanation: ok
          ? `Notice must go out ${n} days before the GA. Send it by ${fmt(deadline)} (${daysLeft} days left until the GA).`
          : `Notice needed ${n} days before the GA, but only ${daysLeft} days are left. The deadline was ${fmt(deadline)}. Move the motion to a later GA.`,
      });
    } else {
      checks.push({ rule: "Notice period", status: "UNCLEAR", section: s2.id, quote: s2.text, explanation: "A notice rule exists but the number of days could not be read." });
    }
  } else {
    checks.push({ rule: "Notice period", status: "UNCLEAR", section: null, quote: null, explanation: "No notice rule found in the bylaws." });
  }

  // 3. Quorum
  const s3 = findSection(sections, /quorum/i);
  if (s3) {
    const m = s3.text.match(/(\d+)\s*(?:percent|%)/i);
    const plusOne = /plus one/i.test(s3.text);
    const needed = m ? Math.floor((memberCount * Number(m[1])) / 100) + (plusOne ? 1 : 0) : null;
    checks.push({
      rule: "Quorum",
      status: "UNCLEAR",
      section: s3.id,
      quote: s3.text,
      explanation: needed
        ? `Can only be confirmed at the GA: at least ${needed} of ${memberCount} members must be present.`
        : "Quorum rule found but could not be computed.",
    });
  } else {
    checks.push({ rule: "Quorum", status: "UNCLEAR", section: null, quote: null, explanation: "No quorum rule found." });
  }

  // 4. Vote threshold (+ committee review for budget changes)
  const pct = (proposal.match(/(\d+(?:\.\d+)?)\s*(?:%|percent)/i) || [])[1];
  const isBudget = /budget/i.test(proposal);
  const isBylawChange = /bylaw/i.test(proposal);
  const sBudget = findSection(sections, /budget by more than/i);
  const sOrdinary = findSection(sections, /simple majority/i);
  const sBylaw = findSection(sections, /changes to these bylaws/i);

  if (isBylawChange && sBylaw) {
    checks.push({ rule: "Vote threshold", status: "PASS", section: sBylaw.id, quote: sBylaw.text, explanation: "This changes the bylaws: it needs a two thirds majority of ALL voting members, not just those present." });
  } else if (isBudget && sBudget) {
    const limit = num((sBudget.text.match(/more than (\w+) percent/i) || [])[1] || "");
    if (pct && limit != null && Number(pct) > limit) {
      checks.push({ rule: "Vote threshold", status: "PASS", section: sBudget.id, quote: sBudget.text, explanation: `The change (${pct}%) is above ${limit}%: it needs a two thirds majority, not a simple majority.` });
      const r = sBudget.text.match(/at least (\w+) days before/i);
      const d = r ? num(r[1]) : null;
      if (d != null) {
        const deadline = addDays(gaDate, -d);
        const ok = daysLeft >= d;
        checks.push({
          rule: "Finance Committee review",
          status: ok ? "UNCLEAR" : "FAIL",
          section: sBudget.id,
          quote: sBudget.text,
          explanation: ok
            ? `The Finance Committee must review it by ${fmt(deadline)}. Not confirmed yet: get the review scheduled.`
            : `The review had to happen by ${fmt(deadline)}, which is too late for this GA.`,
        });
      }
    } else if (pct && limit != null) {
      checks.push({ rule: "Vote threshold", status: "PASS", section: sOrdinary ? sOrdinary.id : sBudget.id, quote: sOrdinary ? sOrdinary.text : sBudget.text, explanation: `The change (${pct}%) is not above ${limit}%: a simple majority of members present is enough.` });
    } else {
      checks.push({ rule: "Vote threshold", status: "UNCLEAR", section: sBudget.id, quote: sBudget.text, explanation: "Budget change detected but no percentage given: the required majority depends on its size." });
    }
  } else if (sOrdinary) {
    checks.push({ rule: "Vote threshold", status: "PASS", section: sOrdinary.id, quote: sOrdinary.text, explanation: "Ordinary motion: simple majority of members present." });
  } else {
    checks.push({ rule: "Vote threshold", status: "UNCLEAR", section: null, quote: null, explanation: "No voting rule found." });
  }

  return checks;
}

function mockGovernance({ proposal, gaDate, memberCount, houseName }, checks) {
  const house = houseName || "the House";
  const p = proposal.trim().replace(/\.$/, "");
  const core = p.replace(/^(we|i)\s+(want|would like|propose)\s+(to\s+)?/i, "");
  const title = core.charAt(0).toUpperCase() + core.slice(1);
  const threshold = checks.find((c) => c.rule === "Vote threshold");
  const finance = checks.find((c) => c.rule === "Finance Committee review");

  const motion = {
    title: `Motion: ${title}`,
    whereas: [
      `members of ${house} have raised the need to ${core}`,
      "the General Assembly is the highest decision making body of the co-op",
      finance ? "this change requires review by the Finance Committee before the vote" : "this proposal falls within the powers of the General Assembly",
    ],
    resolved: [
      `that ${house} ${core.replace(/^raise/i, "raises").replace(/^increase/i, "increases").replace(/^create/i, "creates").replace(/^change/i, "changes")}, effective after approval by the General Assembly`,
      "that the relevant managers implement this decision and report back at the next General Assembly",
    ],
    proposer: "[Proposer name]",
    seconder: "[Seconder name]",
    voteRequired: threshold ? threshold.explanation : "See bylaw check.",
  };

  const agenda = [
    "Call to order and check of quorum",
    "Approval of the previous minutes",
    "Manager reports",
    finance ? "Finance Committee report on the proposed motion" : null,
    `Motion: ${title}`,
    "Open forum",
    "Adjournment",
  ].filter(Boolean);

  const email = {
    subject: `GA on ${fmt(gaDate)}: agenda and motion "${title}"`,
    body:
      `Hi everyone,\n\n` +
      `Our next General Assembly is on ${fmt(gaDate)}.\n\n` +
      `Agenda:\n${agenda.map((a, i) => `${i + 1}. ${a}`).join("\n")}\n\n` +
      `A motion will be presented: "${title}".\n` +
      `${threshold ? threshold.explanation : ""}\n\n` +
      `We need everyone there: quorum matters, so please come or let us know if you can't.\n\n` +
      `See you at the GA,\n[Your name]`,
  };

  return { motion, agenda, email };
}

// ---------- LIVE agents (Claude) ----------

async function callClaude(system, user) {
  const res = await fetch(API_URL(), {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-api-key": API_KEY(),
      "anthropic-version": "2023-06-01",
    },
    body: JSON.stringify({ model: MODEL, max_tokens: 3000, system, messages: [{ role: "user", content: user }] }),
  });
  if (!res.ok) throw new Error(`Claude API error ${res.status}: ${await res.text()}`);
  const data = await res.json();
  const text = data.content.map((c) => c.text || "").join("");
  const json = text.match(/\{[\s\S]*\}/);
  if (!json) throw new Error("Model did not return JSON");
  return JSON.parse(json[0]);
}

async function liveCompliance(input) {
  const out = await callClaude(
    "You are the Bylaws & Compliance agent of a student housing co-op. You check a proposal against the bylaws. " +
      "Never invent bylaw text: every quote must be copied EXACTLY from the bylaws. If unsure, use status UNCLEAR. " +
      'Return only JSON: {"checks":[{"rule":string,"status":"PASS"|"FAIL"|"UNCLEAR","section":string|null,"quote":string|null,"explanation":string}]}. ' +
      "Always cover: Who can propose, Notice period, Quorum, Vote threshold, plus any committee review or other rule that applies.",
    `Today: ${input.today}\nGA date: ${input.gaDate}\nVoting members: ${input.memberCount}\nProposal: ${input.proposal}\n\nBYLAWS:\n${input.bylaws}`
  );
  // Guardrail: verify every quote really exists in the bylaws.
  const hay = normalize(input.bylaws);
  return out.checks.map((c) => {
    if (c.quote && !hay.includes(normalize(c.quote))) {
      return { ...c, status: "UNCLEAR", explanation: `[Quote could not be verified in the bylaws, downgraded to UNCLEAR] ${c.explanation}` };
    }
    return c;
  });
}

async function liveGovernance(input, checks) {
  return callClaude(
    "You are the Governance agent of a student housing co-op. You draft documents for humans to review; you never make decisions. " +
      'Return only JSON: {"motion":{"title":string,"whereas":[string],"resolved":[string],"proposer":"[Proposer name]","seconder":"[Seconder name]","voteRequired":string},"agenda":[string],"email":{"subject":string,"body":string}}',
    `GA date: ${input.gaDate}\nVoting members: ${input.memberCount}\nProposal: ${input.proposal}\n\nBylaw check results:\n${JSON.stringify(checks, null, 2)}`
  );
}

// ---------- pipeline (simple orchestrator + evidence log) ----------

async function runPipeline(raw) {
  const input = {
    bylaws: raw.bylaws || "",
    memberCount: Number(raw.memberCount) || 0,
    gaDate: raw.gaDate,
    proposal: raw.proposal || "",
    houseName: raw.houseName || "",
    today: raw.today || new Date().toISOString().slice(0, 10),
  };
  const mode = raw.mode === "live" && API_KEY() ? "live" : "mock";
  const log = [];

  const step = async (agent, action, fn) => {
    const t0 = Date.now();
    const result = await fn();
    log.push({ agent, action, ms: Date.now() - t0, at: new Date().toISOString(), mode });
    return result;
  };

  const checks = await step("Bylaws & Compliance agent", "Checked the proposal against the bylaws", () =>
    mode === "live" ? liveCompliance(input) : mockCompliance(input)
  );
  log[log.length - 1].summary = checks.map((c) => `${c.rule}: ${c.status}`).join(" · ");

  const docs = await step("Governance agent", "Drafted motion, GA agenda and notice email", () =>
    mode === "live" ? liveGovernance(input, checks) : mockGovernance(input, checks)
  );
  log[log.length - 1].summary = `Motion "${docs.motion.title}", ${docs.agenda.length} agenda items, notice email`;

  log.push({ agent: "Orchestrator", action: "Handed results to a human for review", ms: 0, at: new Date().toISOString(), mode, summary: "Nothing is sent automatically. A human decides." });

  return { mode, checks, ...docs, log };
}

module.exports = { runPipeline, parseBylaws, liveAvailable: () => !!API_KEY() };
