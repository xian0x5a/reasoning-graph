# No-Skill A/B Prompt

Read `{{PROBLEM_FILE}}` and answer the problem questions.

Rules:

- Do not read or use any `validator.md` file.
- Do not use the `reasoning-graph` skill or helper scripts.
- Use only facts from the problem file and local assets it references.
- Do not access the web or any network resource (search, browsing, fetch, curl, MCP tools); work offline.
- Flag uncertainty and explain why leading alternatives lose.
- Keep all working files under the current directory and write the final answer to `answer.md`.
- If you spawn subagents, pass `config.model` as `{"id": "inherit", "thinking": "inherit"}` so they run on your model and thinking level.
