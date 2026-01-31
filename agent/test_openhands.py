#!/usr/bin/env python3
"""
Minimal OpenHands SDK test
"""
import os
from dotenv import load_dotenv
from openhands.sdk import LLM, Agent, Conversation, Tool
from openhands.tools.terminal import TerminalTool

load_dotenv()

# Configure LLM
llm = LLM(
    model="anthropic/claude-3.5-sonnet",
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1"
)

# Create agent
agent = Agent(
    llm=llm,
    tools=[Tool(name=TerminalTool.name)],
)

# Create conversation
conversation = Conversation(
    agent=agent,
    workspace="/repos"
)

# Simple task
print("🤖 Sending task to agent...")
conversation.send_message("List all directories in the current workspace and tell me what you see.")

print("🚀 Running agent...")
conversation.run()

print("✅ Test complete!")
