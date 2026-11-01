# Confirmation-set candidates: Claude Code vs Codex same-task repos (2026-11-01)

Blinding: METADATA ONLY. No source file was opened, read, grepped, cloned or downloaded. Looked at: `gh search repos`
metadata (name, description, licence, language, size, date), owner repo listings, and git tree LISTINGS (path + byte size)
for both Crown Defender repos, hirosuke0520/codex-vs-claude-kit, paweltpietraszko-ship-it/statki-mecz-ai,
charlie-robison/claudex-compete, jgrodman-arch/codex-bakeoff. **READMEs read: none.** Full table: `candidates.csv`.

## Usable
| Set | Repos | Agent | Task | Lang | Licence | Size | Created | Attribution |
|---|---|---|---|---|---|---|---|---|
| A | Aleksandr-Litvinenko/Claude-code.-Crown-Defender-TD-3D-browser-tower-defense-game and Aleksandr-Litvinenko/Codex.-Crown-Defender-TD-3D-browser-tower-defense-game | Claude Code / Codex (model not stated) | 3D browser tower defense from the same brief | JavaScript | MIT both | game.js ~108KB vs ~127KB (exclude vendored three.min.js) | 2026-05-19 | repo names + descriptions ("built by X from the same brief as the Y version") |

## Marginal
| B | hirosuke0520/codex-vs-claude-kit, `results/round1/claude` vs `results/round1/codex` | Claude Code (Opus 5.5) / Codex (GPT-6.1 Sol), per description | receipt-to-CSV CLI | Python (codex adds a Swift helper) | MIT | 47KB vs 9KB main file | 2026-10-14 | description + dir names | Codex side probably under 300 lines; round3 dirs are cross-reviews, use round1 only |

## Not usable
- No licence: sdjmchattie/claude-code-vs-codex (GDScript), codecon-dev/claude-vs-codex (Python game), eduhAgostinho/experimento-qualidade-gpt-5-codex-vs-claude-sonnet-4 (Java), AdrielRod/codex-vs-claude-code (TS), Phonbopit/compare-ai-coding, socratesone/claude_vs_codex_showdown (Python), ai-coding-lab/codex-vs-claude-othello-arena, ~9 small others (CSV row K).
- Codex side is a spec only: Aleksandr-Litvinenko project-crm pair.
- Agents as players, not builders: paweltpietraszko-ship-it statki/scribe.
- Harnesses or patch-level: codex-bakeoff, claudex-compete, agent-arena, agent-context-benchmark.
- Acher (known): agentic-arnoldc, agentic-quine-N-proglang, chessfoo-claude, printf-chess-codex, printf-chess: no licence; agentic-esolang-bench: MIT (Brainfuck).

## Searches run (gh search repos; hits at limit 30-50)
- "claude code vs codex": 31
- "codex vs claude": 23
- "claude vs codex": 25
- "codex claude same prompt", "claude codex bake-off", "claude code codex head-to-head", "codex claude rust", "chess engine codex", "built with codex claude code version": 0 each
- "codex version" "claude code version": 1 (irrelevant)
- "built by codex" claude --license mit: 1 (led to pair A via owner listing)
- "agentic chess engine": 1 (irrelevant)
- codex --match name --license mit: 100 (tool repos, none paired)
- owner listings: acherm, Aleksandr-Litvinenko
- Not done: gh search code, web search for Acher replications, trajectory dumps with whole projects.
