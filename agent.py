from pydantic import BaseModel
from langchain_core.messages import HumanMessage
from typing import TypedDict, Annotated, Literal, Optional
from loguru import logger
from langchain.chat_models import init_chat_model
from langgraph.graph import add_messages
from langchain.messages import (
    SystemMessage,
)
from langchain_core.messages import BaseMessage
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver

#from schema import JDAnalysis
from settings import settings
from prompts import SYSTEM_PROMPT


model = init_chat_model(model=settings.LLM_MODEL_NAME, model_provider="openai", temperature=0, api_key=settings.OPENAI_API_KEY)


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


async def call_llm(state: AgentState):
    """Call the LLM with the given messages."""

    response = await model.ainvoke(
        [
            SystemMessage(content=SYSTEM_PROMPT)]
        + state["messages"]
    )
    return {"messages": response.content}

'''async def technical_phase(state: AgentState):
    """ Call the LLM with the given messages."""

    response = await model.ainvoke(
        [
            SystemMessage(
                content=TECHNICAL_PHASE_PROMPT.format(
                JOB_DESCRIPTION=state["job_description"],
                RESUME_DATA=state.get("resume", "N/A"),
                DURATION = state["duration"],
                JOB_REQUIREMENTS = state.get("job_requirements", "N/A"),
                TIME_LEFT = state["time_left"])
            )   
        ]
        + state["messages"]
    )

    return {"messages": response.content}   

async def end_session(state: AgentState):

    """ Bring the session to a close when the time is almost up"""

    response = await model.ainvoke(
        [
            SystemMessage(
                content=CLOSING_PROMPT.format(
                DURATION = state["duration"],
                TIME_LEFT = state["time_left"])
            )
        ]
        + state["messages"]
    )

    return {"messages": response.content}

async def check_time(state: AgentState) -> Literal["end_session", "technical_phase", "call_llm"]:
    """ Check if the time is almost up"""
    if state["time_left"] <= 60:
        return "end_session"
    elif 60 < state["time_left"] <= 0.9 * state['duration']:
        return "technical_phase"
    else:
        return "call_llm"'''

graph_builder = StateGraph(AgentState)
graph_builder.add_node("call_llm", call_llm)

graph_builder.add_edge(START, "call_llm")
graph_builder.add_edge("call_llm", END)

agent = graph_builder.compile(checkpointer=InMemorySaver())