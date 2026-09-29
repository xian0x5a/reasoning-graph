# Reasoning-Graph A/B Prompt

Read `{{PROBLEM_FILE}}`, then use the `reasoning-graph` skill with graph output if available.

Rules:

- Do not read or use any `validator.md` file.
- Use only facts from the problem file and local assets it references.
- Do not access the web or any network resource (search, browsing, fetch, curl, MCP tools); work offline.
- Return the answer requested by the problem file.
- Include the graph artifact path when graph output is generated.
- Keep all working files, including graph state and output, under the current directory and write the final answer to `answer.md`.
- If you spawn subagents, run them on your own model and thinking level (in pi, pass `config.model` as `{"id": "inherit", "thinking": "inherit"}`).
