from agent import agent
from langchain_core.messages import HumanMessage, AIMessage
import asyncio
from loguru import logger






logger.info("Starting the agent")
async def main():
    async for message, metadata in agent.astream(
        {"messages": [HumanMessage(content="Hello there")]},
        {"configurable": {"thread_id": "1"}},
        stream_mode="messages"
    ):
        logger.info(f"Message: {message}")
        if isinstance(message, AIMessage):
            if message.content:
                print(message.content[0]['text'])

asyncio.run(main())

logger.info("Agent finished")