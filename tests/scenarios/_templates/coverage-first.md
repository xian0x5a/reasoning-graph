# Coverage-First A/B Prompt

Read `{{PROBLEM_FILE}}` and answer the problem questions.

Rules:

- Do not read or use any `validator.md` file.
- Do not use the `reasoning-graph` skill or helper scripts.
- Use only facts from the problem file and local assets it references.
- Do not access the web or any network resource (search, browsing, fetch, curl, MCP tools); work offline.
- Keep all working files under the current directory and write the final answer to `answer.md`.
- If you spawn subagents, run them on your own model and thinking level (in pi, pass `config.model` as `{"id": "inherit", "thinking": "inherit"}`).

Method. Do the steps in order, and write each step's file before you start the next:

1. **Clues before answers.** Before you favour any answer, go through the problem paragraph by paragraph and list in `clues.md` every concrete detail: who was where and when, what each person said or did, objects, physical conditions, times, and anything described but not explained. Quote each detail exactly and number it. Include details that seem irrelevant.
2. **Every clue against every answer.** In `matrix.md`, for each clue, say for every answer option whether the clue fits it, rules it out, or says nothing about it, with one line of why.
3. **Eliminate.** In `answer.md`, list for each option the clues that rule it out, if any. Answer with the option that survives. If more than one survives, pick the one the clues fit best and say why the others lose. Flag any remaining uncertainty.
