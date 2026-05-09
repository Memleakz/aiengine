import asyncio


async def ask_user(question: str) -> str:
    """Ask the user a direct question and wait for their input. Use this to clarify requirements or get permission."""
    try:
        loop = asyncio.get_event_loop()
        # Prompting the user inline. We print the question clearly.
        def _get_input():
            print(f"\n[Agent Asks] {question}")
            return input("Your response: ")

        answer = await loop.run_in_executor(None, _get_input)
        return answer
    except Exception as e:
        return f"Error getting user input: {e}"
