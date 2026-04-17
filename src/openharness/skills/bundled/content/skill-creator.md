---
name: skill-creator
description: Interactive skill creation wizard — guides you through designing, structuring, and generating new skills for velaris-agent.
version: "1.0.0"
metadata:
  hermes:
    tags:
      - meta
      - creation
      - wizard
---

# Skill Creator

Guide the user through creating a new velaris-agent skill from scratch. Follow the five phases below in order, asking clarifying questions at each stage before moving on.

## When to use

Use when the user wants to create a new skill, asks how to write a skill, or wants to package reusable knowledge as a skill file.

## Skill File Format Specification

Every skill lives in a directory under `~/.velaris-agent/skills/<slug>/` with a main `SKILL.md` file.

### SKILL.md Structure

```markdown
---
name: my-skill
description: One-line summary of what this skill does.
version: "1.0.0"                    # optional
metadata:                           # optional
  hermes:
    tags:
      - category-tag
      - another-tag
---

# Skill Title

Body content: instructions, workflows, rules, examples.
```

### Frontmatter Fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Kebab-case identifier (e.g. `deploy-k8s`) |
| `description` | Yes | One-line summary shown in skill listings |
| `version` | No | SemVer string (e.g. `"1.0.0"`) |
| `metadata.hermes.tags` | No | List of category tags for discovery |

### Support Directories (optional)

A skill directory may include additional resources alongside `SKILL.md`:

| Directory | Purpose | Example files |
|-----------|---------|---------------|
| `references/` | Background docs, API specs, style guides | `api-spec.md`, `style-guide.md` |
| `templates/` | Reusable file templates the skill can emit | `component.tsx.hbs`, `test.py.j2` |
| `scripts/` | Helper scripts the skill may invoke | `validate.sh`, `lint.py` |
| `assets/` | Static assets (images, configs) | `logo.png`, `default-config.yaml` |

### Naming Rules

- Skill name must be kebab-case: lowercase letters, digits, and hyphens only.
- Directory name matches the skill slug (normalized from the name).
- `SKILL.md` is the required entry point — the loader discovers skills by finding this file.

## Five-Phase Guided Flow

### Phase 1 — Discovery

Goal: understand what the user wants to automate or codify.

Ask the user:

1. What task or workflow should this skill help with?
2. When would someone reach for this skill? (trigger conditions)
3. Are there existing tools, commands, or patterns involved?
4. What does success look like after using this skill?

Summarize the answers into a one-paragraph skill purpose statement before proceeding.

### Phase 2 — Design

Goal: define the skill's scope, structure, and key sections.

Based on Phase 1, propose:

1. A skill name (kebab-case) and one-line description.
2. A list of tags for discoverability.
3. The main sections the SKILL.md body should contain. Typical sections include:
   - **When to use** — trigger conditions and context
   - **Workflow** — numbered step-by-step procedure
   - **Rules** — constraints, guardrails, things to avoid
   - **Examples** — concrete input/output demonstrations
   - **References** — links or pointers to external docs
4. Whether any support directories (`references/`, `templates/`, `scripts/`, `assets/`) are needed.

Ask the user to confirm or adjust before proceeding.

### Phase 3 — Architecture

Goal: plan the file layout and any support files.

Produce a tree showing the planned skill directory:

```
~/.velaris-agent/skills/<slug>/
├── SKILL.md
├── references/       # if needed
│   └── ...
├── templates/        # if needed
│   └── ...
├── scripts/          # if needed
│   └── ...
└── assets/           # if needed
    └── ...
```

For each support file, write a one-line description of its purpose. Confirm with the user.

### Phase 4 — Detection

Goal: verify the skill does not duplicate existing skills.

1. Use the `skill` tool to list currently registered skills.
2. Check if any existing skill overlaps significantly with the proposed one.
3. If overlap is found, suggest either extending the existing skill (via `skill_manage(action="patch")`) or proceeding with a new skill that has a clearly differentiated scope.
4. Confirm the decision with the user.

### Phase 5 — Implementation

Goal: generate the skill files and register them.

1. Draft the complete `SKILL.md` content including frontmatter and all body sections.
2. Present the draft to the user for review.
3. After approval, create the skill using the `skill_manage` tool:

```
skill_manage(action="create", name="<slug>", content="<full SKILL.md content>")
```

4. If support files are needed, write each one:

```
skill_manage(action="write_file", name="<slug>", file_path="references/api-spec.md", file_content="<content>")
```

5. Verify the skill is registered by calling `skill(name="<slug>")`.
6. Report the result to the user.

## Rules

- Always follow the five phases in order. Do not skip phases.
- Ask for user confirmation before moving from one phase to the next.
- Keep skill content concise and actionable — avoid filler text.
- Frontmatter `name` and `description` are mandatory; omit optional fields unless the user provides values.
- Use `skill_manage` for all file operations — never write directly to the filesystem.
- If the user already has a clear idea, you may condense phases 1-3 into a quick confirmation, but always run phase 4 (detection) and phase 5 (implementation).
