
async def subagent(prompt: str, context: str = "", workdir: str | None = None) -> str:
    """Spawn a sub-agent to solve a specific sub-problem or research a question without cluttering your own conversation history.
    The sub-agent will have access to all standard tools.
    """
    try:
        # Lazy import to avoid circular dependencies
        from agent_engine.engine import LightweightEngine

        # We spawn a new engine instance. It will run in the provided workdir.
        engine = LightweightEngine(
            manage_history=False,
            workdir=workdir,
            system_prompt="You are a specialized sub-agent. Solve the task provided and give a clear, concise final answer."
        )

        full_prompt = f"Context provided by main agent: {context}\n\nTask: {prompt}" if context else prompt

        response = ""
        # We iterate over the events and only collect the final tokens yielded by the LLM
        async for event in engine.run(full_prompt):
            if event.type == "token":
                response += event.data

        await engine.close()

        if not response.strip():
            return "Sub-agent finished but returned no text."

        return f"Sub-agent Response:\n{response}"

    except Exception as e:
        return f"Error running sub-agent: {e}"
