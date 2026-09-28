# Resume Loop Prompt: No Memory

Read `{{PROBLEM_FILE}}` and answer the problem questions.

Rules:

- Do not read or use any `validator.md`, `gold.json`, or `rubric.json` file.
- Do not use the `reasoning-graph` skill or helper scripts.
- Use only facts from the problem file and local assets it references.
- Do not access the web or any network resource (search, browsing, fetch, curl, MCP tools); work offline.
- Write the final answer to `answer.md`, and explain why: why your answer holds and why leading alternatives lose.
- The task can take several rounds. After a rejected answer your context is reset, and every file you created is deleted.
- If you spawn subagents, run them on your own model and thinking level.
