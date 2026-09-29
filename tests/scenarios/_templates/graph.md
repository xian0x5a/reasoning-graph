# Resume Loop Prompt: Graph

Read `{{PROBLEM_FILE}}` and answer the problem questions.

Rules:

- Do not read or use any `validator.md`, `gold.json`, or `rubric.json` file.
- Use the `reasoning-graph` skill, with the graph state in `state.json`.
- Use only facts from the problem file and local assets it references.
- Do not access the web or any network resource (search, browsing, fetch, curl, MCP tools); work offline.
- Write the final answer to `answer.md`, and explain why: why your answer holds and why leading alternatives lose.
- The task can take several rounds. After a rejected answer your context is reset, and every file you created is deleted except `state.json` and `state.index.md`.
- Keep the graph up to date as you work: what you found, what you ruled out, and any feedback you were given. If `state.index.md` exists when you start, read it first.
- If you spawn subagents, run them on your own model and thinking level.
