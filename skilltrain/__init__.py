"""skill-training: gradient descent on an agent's notes.

The pieces, in the order the pipeline uses them:

    dataset     screenplays split into episodes, and their noised counterparts
    prompts     the markdown templates in prompts/, filled in
    agent       the Claude Code CLI, called as a tool-using agent or as plain text
    trajectory  stream-json logs turned into transcripts and read traces
    memory      the pool: layout, linter, and its git repo
    run         run directories and resuming
"""

__all__ = ["agent", "dataset", "memory", "prompts", "run", "trajectory"]
