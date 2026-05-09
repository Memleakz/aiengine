import asyncio


async def sleep(seconds: int) -> str:
    """Pause execution for a specified number of seconds.
    Useful when waiting for a background server to start or a background task to generate logs before reading them.
    """
    max_sleep = 60
    if seconds <= 0:
        return "Error: seconds must be positive."
    if seconds > max_sleep:
        return f"Error: maximum sleep time is {max_sleep} seconds."

    await asyncio.sleep(seconds)
    return f"Slept for {seconds} seconds."
