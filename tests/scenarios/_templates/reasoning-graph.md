# Reasoning-Graph A/B Prompt

Read `{{PROBLEM_FILE}}`, then use the `reasoning-graph` skill in strict mode with graph output if available.

Rules:

- Do not read or use any `validator.md` file.
- Use only facts from the problem file and local assets it references.
- Return the answer requested by the problem file.
- Include the graph artifact path when graph output is generated.
- Keep all working files, including graph state and output, under the current directory and write the final answer to `answer.md`.
