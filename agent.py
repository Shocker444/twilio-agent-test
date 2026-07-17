from datetime import datetime
from pydantic import BaseModel
from langchain_core.messages import ToolMessage
from typing import TypedDict, Annotated, Literal, Optional
from loguru import logger
from langchain.chat_models import init_chat_model
from langgraph.graph import add_messages
from langchain.messages import (
    SystemMessage,
)
import time
from langchain_core.messages import BaseMessage
from langchain_core.tools import tool, InjectedToolArg
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver

#from schema import JDAnalysis
from settings import settings
from prompts import SYSTEM_PROMPT
from tools import tools, tool_dict


model = init_chat_model(model=settings.LLM_MODEL_NAME, model_provider="openai", temperature=0, api_key=settings.OPENAI_API_KEY)
model_with_tools = model.bind_tools(tools)

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


async def call_llm(state: AgentState):
    """Call the LLM with the given messages."""

    response = await model_with_tools.ainvoke(
        [
            SystemMessage(content=SYSTEM_PROMPT)]
        + state["messages"]
    )
    return {"messages": response}

async def tool_node(state: AgentState):
    """Execute tools when necessary."""

    tool_calls = state["messages"][-1].tool_calls
    logger.info(f"The messages are {state['messages']}")
    logger.info(f"The tool calls are {tool_calls}")
    observations = []
    for tool_call in tool_calls:
        tool = tool_dict[tool_call["name"]]
        obs = await tool.ainvoke(tool_call["args"])
        observations.append(ToolMessage(content=str(obs),
                                        tool_name=tool_call["name"], 
                                        tool_call_id=tool_call["id"]))
    
    return {"messages": observations}

async def should_continue(state:AgentState) -> Literal["tool_node", "END"]:
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tool_node"
    return END

graph_builder = StateGraph(AgentState)
graph_builder.add_node("call_llm", call_llm)
graph_builder.add_node("tool_node", tool_node)

graph_builder.add_edge(START, "call_llm")
graph_builder.add_conditional_edges("call_llm",
                                    should_continue,
                                    {
                                        "tool_node": "tool_node",
                                        END: END
                                    }
                                )
graph_builder.add_edge("tool_node", "call_llm")

agent = graph_builder.compile(checkpointer=InMemorySaver())