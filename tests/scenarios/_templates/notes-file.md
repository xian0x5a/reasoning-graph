# Resume Loop Prompt: Notes File

Read `{{PROBLEM_FILE}}` and answer the problem questions.

Rules:

- Do not read or use any `validator.md`, `gold.json`, or `rubric.json` file.
- Do not use the `reasoning-graph` skill or helper scripts.
- Use only facts from the problem file and local assets it references.
- Do not access the web or any network resource (search, browsing, fetch, curl, MCP tools); work offline.
- Write the final answer to `answer.md`. Above the final answer line, give your reasoning: why your answer holds, and why each other option is ruled out. The reasoning is graded along with the answer.
- The task can take several rounds. After a rejected answer your context is reset, and every file you created is deleted except `notes.md`.
- Keep `notes.md` up to date as you work: what you found, what you ruled out, and any feedback you were given. If `notes.md` exists when you start, read it first.
- If you spawn subagents, run them on your own model and thinking level.
