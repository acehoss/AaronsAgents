import logging

import streamlit as st
import streamlit.runtime.scriptrunner
from langchain_openai import ChatOpenAI
from streamlit.runtime.scriptrunner import get_script_run_ctx, add_script_run_ctx

import AaronsAgents.team_member
from AaronsAgents.team_member import TeamMember, Stimulus

from threading import Thread
from typing import Sequence
from langchain_core.prompt_values import PromptValue
from langchain_core.runnables import RunnableSerializable
from datetime import datetime
from langchain_core.language_models import BaseChatModel
from langchain_anthropic import ChatAnthropic
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_anthropic.output_parsers import ToolsOutputParser
from langchain_core.messages import AIMessage, HumanMessage, BaseMessage

# Hello Director! Welcome again to the team! Before we dig in, I was curious what thoughts you have on the team structure, workflow, and tools?
# Thanks for that feedback. So at Aaron's Agents, we're working on agentic AI tech. We're trying to prove out a system that allows AI agents to scale automatically to accomplish goals of various sizes. You probably have an idea of what I'm thinking with from what you saw in the employee handbook. We will start out small. Your first project will be the creation of a 5-10 paragraph report on how LTE (the cell phone technology) works. This project is about the process, not the result. Let me know what you need to succeed. Since we are focusing on process, I expect you to hire at least 3 team members. You have my approval to hire up to 5 (you hire team members using the hire_team_member tool). Let me know what your plan is.
# The specific details are not too important, but to help keep things moving let's say we're going to focus on communications protocols. But otherwise it's pretty open ended. I'm curious to see how you will staff up your team and how you all work together.

def incoming_ai_message(team_member: str, message: str):
    with st.chat_message("assistant"):
        st.markdown(f"**{team_member}** says:\n\n {message}")
        st.session_state.messages.append({"role": "assistant", "content": f"{team_member}: {message}"})
        st.rerun()


if "started" not in st.session_state:
    st.session_state.started = True
    st.session_state.messages = []
    st.session_state.gpt4 = ChatOpenAI(model="gpt-4-turbo", temperature=0.25, max_tokens=4096)
    st.session_state.haiku = ChatAnthropic(model="claude-3-haiku-20240307", temperature=0.1, max_tokens=4096)
    st.session_state.opus = ChatAnthropic(model="claude-3-opus-20240229", temperature=0.1, max_tokens=4096)
    st.session_state.lmstudio = ChatOpenAI(
        base_url="http://localhost:1234/v1",
        temperature=0.1,
        api_key="not-needed",
        max_tokens=32768
    )
    AaronsAgents.team_member.aaron_message_callback = incoming_ai_message
    st.session_state.director_agent = TeamMember(name="Director", personality="You are funny, personable, and detail oriented.",
                                title="Director", manager=None,
                                job_description="You are responsible for overseeing the entire AI/LLM team. You interface "
                                                "directly with Aaron to set goals, deliver results, and get approval for "
                                                "resource changes. Unlike other team members, your manager is Aaron, the "
                                                "human CEO. Aaron is very busy, and may take several minutes or even hours "
                                                "to respond.\n"
                                                "As the Director, you don't do work yourself. You delegate it to subordinate "
                                                "team members. Most likely all of your subordinate team members will be managers.",
                                rank=1, model=st.session_state.opus, sub_model=st.session_state.haiku,
                                before_start_callback=lambda m: streamlit.runtime.scriptrunner.add_script_run_ctx(m.thread))


# Display chat messages from history on app rerun
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])


def chat_in():
    global director_agent
    prompt = st.session_state.user_input
    # st.chat_message("user").markdown(prompt)
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.session_state.director_agent.stimulate(Stimulus("message",
                                          f"From: Aaron\n"
                                          f"To: {st.session_state.director_agent.name}\n"
                                          f"{prompt}"))


st.chat_input("What is up?", on_submit=chat_in, key="user_input")


