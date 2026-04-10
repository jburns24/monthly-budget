# Installed Skills — When to Use Them

These skills are installed in this environment. Use them (via the `Skill` tool) when working in the relevant areas. When spawning sub-agents, include the applicable skill names in the agent prompt so they know to invoke them too.

## Anytime
| Trigger | Skill |
|---|---|
| Before implementing any feature or bugfix | `test-driven-development` |
| Encountering a bug, test failure, or unexpected behavior | `systematic-debugging` |
| After making changes — review for quality/simplicity | `simplify` |
| Local code review before committing | `local_review` |

## Backend (`backend/` — FastAPI, SQLAlchemy, Python)
| Trigger | Skill |
|---|---|
| Building new FastAPI endpoints or service patterns | `fastapi-templates` |
| Designing or refactoring backend architecture | `architecture-patterns` |
| Optimizing slow Python code or investigating memory issues | `python-performance-optimization` |

## Frontend (`frontend/` — React, TypeScript, Chakra UI)
| Trigger | Skill |
|---|---|
| Writing or reviewing React components | `vercel-react-best-practices` |
| Refactoring components (boolean prop proliferation, composition) | `vercel-composition-patterns` |
| Building new UI screens or visual components | `frontend-design` |
| Working with complex TypeScript types or generics | `typescript-advanced-types` |
| Auditing UI for accessibility or design guidelines | `web-design-guidelines` |
| Writing or running Playwright / E2E tests | `webapp-testing` |

## Infrastructure
| Trigger | Skill |
|---|---|
| Modifying `Tiltfile` or debugging dev service issues | `tilt-dev` |

## Feature Development Workflow (non-trivial features)
Use these in order for significant new features:
1. `claude-workflow:cw-spec` — write a structured spec
2. `claude-workflow:cw-plan` — break spec into a task graph
3. `claude-workflow:cw-execute` — implement each task
4. `claude-workflow:cw-review` — review implementation
5. `claude-workflow:cw-validate` — validate against spec

## Passing Skills to Sub-Agents
When spawning an agent via the `Agent` tool for work in any of the above areas, include a line in the prompt such as:

> "This project uses installed skills. For backend work invoke `fastapi-templates` and `test-driven-development` via the Skill tool before writing implementation code. For frontend work invoke `vercel-react-best-practices`. For any bug use `systematic-debugging` first."

Tailor the list to the area the sub-agent is working in.
