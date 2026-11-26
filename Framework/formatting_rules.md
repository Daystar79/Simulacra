# Framework Formatting Rules

This document outlines the canonical formatting standards for the files in the `Framework/` directory. The goal is to maximize visual clarity, layout consistency, and readability **without condensing, summarizing, or omitting any existing content or details**.

All future updates to files in the `Framework/` directory, and any automated formatting tools/agents, must adhere to these rules.

---

## 1. Document Structure & Metadata

Every framework document must begin with a clear title and a metadata/status block.

### Rules:
- **Title (H1):** Use a single `# Title` at the very top of the file.
- **Subtitle/Status:** Place a brief italicized summary and last-updated/locked date immediately below the H1 title.
- **Horizontal Rules:** Use `---` with blank lines before and after to separate major logical sections (e.g., between Acts, distinct sections of cosmology, or operational topics).

```markdown
# Document Name
*Locked June 26, 2026 — Canonical Bible / Reference*

---
```

---

## 2. Heading Hierarchy

Ensure a strict, logical progression of heading levels (`#` through `####`). Never skip levels.

### Rules:
- `#` (H1) is reserved for the document title.
- `##` (H2) for primary categories or thematic divisions (e.g., act boundaries, main character profiles, major geographical regions).
- `###` (H3) for specific subsections, chapters, or entities (e.g., individual chapters, specific estate buildings, secondary character profiles).
- `####` (H4) for movements, sub-beats, or specific trait listings within a character profile (e.g., Physical, Presence, Psychology).

---

## 3. Lists and Indentation

Unordered lists must follow a uniform style to ensure clean alignment and readability.

### Rules:
- **Bullet Character:** Use a single hyphen (`-`) for all unordered list bullets. Do not mix `-` and `*`.
- **Indentation:** Use exactly **4 spaces** for each level of nested indentation.
- **Inline Keys:** Use bold text with a trailing colon for key-value lists or lists of traits:
  - Format: `- **Key Name:** Value description.`
- **Spacing:** Do not leave blank lines between list items of the same level unless the items contain multiple paragraphs.

```markdown
- **Character A:** Concrete/practical focus.
- **Character B:** Warm/caregiving register.
    - **Operational Role:** Anchor.
    - **Assigned Work:** Outreach and coordination.
```

---

## 4. Tables for Multi-Dimensional Data

Convert raw lists of comparative data, timelines, schedules, or highly structured parameters into Markdown tables.

### Rules:
- **Alignment:** Align columns appropriately (left-align text, center-align codes/dates/status, right-align numbers).
- **Format:** Ensure the header separator row uses proper colon notation for alignment (e.g., `|:---|:---:|---:|`).
- **Complete Text:** Ensure that cell contents are formatted clearly and preserve the full, original descriptions. Do not abbreviate or condense the information to make the table smaller.

```markdown
| Priority | Source File | Governing Authority |
|:---:|:---|:---|
| **1** | [master_manuscript.md](../Drafts/master_manuscript.md) | On-page prose; what actually happened in the narrative. |
| **2** | [World_Architecture.md](./World_Architecture.md) | Locked synthesis for future drafting. |
```

---

## 5. Callouts and Alerts

Replace uppercase warning text or bolded inline warning paragraphs with standard GitHub-style alerts. This highlights crucial constraints, rules, and locks without cluttering the document flow.

### Rules:
- Use `> [!IMPORTANT]` for locked content, drafting constraints, and rules that must not be broken.
- Use `> [!NOTE]` for general background context, explanations, and cross-references.
- Use `> [!WARNING]` for deprecations, stale data, or potential logic drift.
- Place callouts on their own line with a blank line above and below. Do not nest them.

```markdown
> [!IMPORTANT]
> **No Direct Writing or Draft Edits:** The assistant must not write, edit, or directly modify any story draft files or the manuscript. Keep all prose drafting inside the `Drafts/` directory.

> [!WARNING]
> Do not upload `Novel_Master_Outline.md` as canon to external engines; it contains lagging outline data.
```

---

## 6. Cross-Document Linking (Clickable File Links)

To make navigation between the framework, characters, and drafts seamless, all references to other files must use clickable absolute file links matching the local environment.

### Canonical File Links:

- **Drafting Prompt:** `[Drafting_Prompt.md](./Drafting_Prompt.md)`
- **Drafting Workflow:** `[Drafting_Workflow.md](./Drafting_Workflow.md)`
- **Design Q&A Protocol:** `[Design_QA_Protocol.md](./Design_QA_Protocol.md)`
- **Source Changes:** `[source_changes.md](./source_changes.md)`
- **Characters Psychology:** `[Framework/Psychology/](./Psychology/)`
- **Humanity Protocol:** `[humanity.yaml](./Mechanics/humanity.yaml)`
- **Prose Protocol:** `[prose.yaml](./Mechanics/prose.yaml)`
- **Voices Protocol:** `[voices.yaml](./Mechanics/voices.yaml)`

---

## 7. Formatting Examples (Before vs. After)

### Dense / Unformatted (Before)
```markdown
### Chapter 1 — The Gathering
**Characters**
* Character A — Realm VIII Remnant — Integration (operational role: The Coordinator)
* Character B — Realm IX Remnant — Threshold
* Character C — The Presence (Remnant of Presence)
**Subject Matter**
Character A arrives at the meeting room. Character B is already there — the person from the training hall, the gate, the event Character A never documented. The recognition. The closed loop forming. Nothing named. The video running between the cold cups. Character A steps outside, takes a breath, goes back in. The conversation begins.
```

### Formatted & Structured (After)
```markdown
### Chapter 1 — The Gathering

#### Characters
- **Character A:** Realm VIII Remnant — Integration (Operational Role: *The Coordinator*)
- **Character B:** Realm IX Remnant — Threshold
- **Character C:** The Presence (Remnant of Presence)

#### Subject Matter
Character A arrives at the meeting room. Character B is already there — the person from the training hall, the gate, the event Character A never documented. The recognition. The closed loop forming. Nothing named. The video running between the cold cups.

Character A steps outside, takes a breath, goes back in. The conversation begins.
```

---

## 8. Scene transitions in prose *(Corrections queue)*

One-off prose transition fixes are dropped in **`Framework/Corrections/`** as separate `*.md` files (not this file). On **load framework**: apply each correction → log in `source_changes.md` → delete the file. **If any corrections were applied, run `Build/build.sh`** to rebuild all `Releases/` outputs (Print PDF, KDP DOCX, KDP Bleed DOCX, EPUB).

### The Three T's *(after any `---` break)*

First sentence of the new block must ground:

- **Time** — *Monday dawn*, *Three hours later*, *Earlier in the study*
- **Territory** — *In the south wing*, *At the annex bench*
- **Throughline** — who is present; what they're wearing or carrying

### When **not** to use `---`

Do not separate continuous real-time action (crossing a threshold, walking a path, setting down a cup). Use a paragraph break only. See the review table for flagged instances.

### Non-linear cuts

Parallel or backward jumps need an anchor in the opening line: *Earlier*, *Meanwhile*, *Back in their private quarters*.
