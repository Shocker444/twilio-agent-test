from agent import agent
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
import asyncio
from loguru import logger






logger.info("Starting the agent")
async def main():
    async for message, metadata in agent.astream(
        {"messages": [HumanMessage(content="Hello there, I'm trying to look up my information, my ID is 12346")]},
        {"configurable": {"thread_id": "1"}},
        stream_mode="messages"
    ):
        if isinstance(message, AIMessage):
            if message.content:
                print(message.content)
            if message.tool_calls:
                print(message.tool_calls)
        elif isinstance(message, ToolMessage):
            print(message.content)

asyncio.run(main())

logger.info("Agent finished")