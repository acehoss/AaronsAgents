# AaronsAgents

A hierarchical multi-agent system built with LangChain that enables autonomous AI agents to work together in teams, communicate asynchronously, and manage their own lifecycles.

## Overview

AaronsAgents is an experimental agent architecture where AI agents operate as "team members" in a hierarchical organization. Each agent runs in its own thread, processes stimuli from an event queue, and can interact with other agents through a messaging system. The system was built to explore questions about agent autonomy, memory management, and multi-agent coordination.

## Key Features

### Agent Architecture

- **Thread-based Agents**: Each TeamMember runs in a dedicated thread with an event loop
- **Stimulus-Driven**: Agents respond to stimuli (messages, time updates) from their queue
- **Hierarchical Management**: Agents have ranks and report to managers in a tree structure
- **Autonomous Lifecycle**: Agents can hire/fire subordinates (with manager approval)

### Communication System

- **Asynchronous Messaging**: Agents communicate via `messaging_send` tool with From/To headers
- **Status Broadcasting**: Agents can set presence (Available/Busy) and status messages
- **Manager Hierarchy**: Only rank 1 agents can message Aaron (the human CEO)

### Memory & State

- **Conversation Memory**: ConversationBufferWindowMemory with k=20 window
- **Personal Notepad**: Each agent has a 2000-character notepad for persistent notes
- **Event Queue**: Stimulus queue serves as working memory for each agent

### Available Tools

- `messaging_send`: Send messages to other team members
- `notepad_edit`: Update personal notepad contents
- `messaging_status_set`: Set presence and status message
- `timer_interval_set`: Configure wake timer (minimum 60 seconds)
- `hire_team_member`: Create new subordinate agents
- `fire_team_member`: Remove subordinate agents
- `wikipedia_search`: Query Wikipedia for information

## Technical Stack

- **Python 3.11+**
- **LangChain 0.1.x** (pre-modern tool calling era)
- **Streamlit** for web UI
- **Poetry** for dependency management
- **LLM Support**:
  - Claude 3 Opus (Director/complex reasoning)
  - Claude 3 Haiku (Workers/cost-effective)
  - GPT-4 Turbo
  - Local models via LM Studio

## Installation & Usage

```bash
# Install dependencies
poetry install

# Run the Streamlit UI
poetry run streamlit run aa.py

# Run the CLI (currently just prints "Hello World")
poetry run aagents
```

## Project Structure

```
AaronsAgents/
├── aa.py                    # Streamlit UI - main entry point
├── AaronsAgents/
│   ├── team_member.py      # Core TeamMember class and agent logic
│   ├── aagents.py          # CLI entry point (placeholder)
│   └── __init__.py
├── pyproject.toml          # Poetry configuration
├── poetry.lock             # Locked dependencies
└── README.md
```

## How It Works

1. **Agent Creation**: The Director agent is created at startup with rank 1
2. **Thread Management**: Each agent runs `agent_thread()` which:
   - Processes stimuli from the queue
   - Enforces 10-second minimum between actions (API rate limits)
   - Sleeps when idle (configurable via timer tool)
3. **Communication Flow**: 
   - Agents send messages via tools
   - Messages become stimuli in recipient's queue
   - Director relays between Aaron and the team
4. **Tool Execution**: LangChain's tool-calling agent processes stimuli and decides which tools to use

## Design Decisions

- **Think-First Pattern**: Agent responses are internal thoughts; only tool calls have external effects
- **Isolated State**: Each agent maintains independent context and memory
- **Event-Driven Architecture**: Asynchronous message passing prevents blocking
- **Mandatory Sleep**: 10-second minimum between actions prevents API rate limit issues

## Known Limitations

- **Temporal Reasoning**: Agents struggle with time-based tasks despite having timestamps
- **Context Windows**: Long conversations exceed memory limits (k=20 window)
- **Coordination**: No built-in mechanisms for preventing duplicate work
- **CLI Interface**: The `aagents` command is a placeholder

## Example Interaction

```python
# In aa.py, the Director is initialized with:
director_agent = TeamMember(
    name="Director",
    personality="You are funny, personable, and detail oriented.",
    title="Director", 
    rank=1,
    model=opus_model,
    sub_model=haiku_model  # For hired subordinates
)

# User messages are converted to stimuli:
director_agent.stimulate(Stimulus("message", f"From: Aaron\nTo: Director\n{user_message}"))
```

## Agent Context Structure

Each agent's context is constructed from several components that create their "worldview":

### System Prompt Components

1. **Personal Identity**
   - Name, personality, title, rank
   - Job description and manager assignment
   - Example: "Your name is **TechLead**. You are creative and detail-oriented. Director (Rank 2)"

2. **Employee Handbook**
   - Detailed instructions on organization structure
   - Communication protocols and tool usage
   - Work patterns (sleep/wake cycles)
   - Notepad usage guidelines

3. **Live Status Information**
   - Current date/time
   - Agent's own messaging status
   - Contact list showing all team members with:
     - Name, title, rank
     - Manager relationship
     - Presence (Available/Busy)
     - Status message
     - Last update timestamp

4. **Notepad Contents**
   - Persistent 2000-character scratch space
   - Included in every context update
   - Used for task tracking, notes, plans

### Stimulus System

Stimuli are events that wake agents and drive their actions:

```python
# Stimulus structure
Stimulus(
    type="message",  # or "time", "welcome", etc.
    detail="From: Director\nTo: TechLead\nPlease review the API design",
    ts=datetime.now()
)
```

**Stimulus Types:**

- `message`: Inter-agent communications with From/To headers
- `time`: Periodic updates showing current time
- `welcome`: Initial greeting when agent is created
- System notifications

**Stimulus Processing:**

- All pending stimuli are consumed at once via `consume_stimuli()`
- Formatted as: "Stimulus: {type} @ {timestamp}\n{detail}"
- Multiple stimuli are separated by double newlines
- Empty queue means agent will sleep after processing

### Example Agent Context

```
# Aaron's Agents Employee Instructions
Welcome, team member, to your private office at Aaron's Agents.
## About You
Your name is **DataAnalyst**.
### Your Personality
You are methodical, curious, and love finding patterns in data.
### Your Job Title
Data Analyst (Rank 3)
### Your Job Description
Analyze project data and create insights for the team
### Your Manager
TechLead

[... Employee Handbook sections ...]

# System Messages
- Several tools currently unavailable
- Knowledge Base currently unavailable
# Current Date and Time
2024-04-15 14:32:10 
# Your current messaging status
Busy - Analyzing user metrics
# Contact List
| Team Member Name | Title and Rank | Manager Name | Presence | Status Message | Last Update |
|------------------|----------------|--------------|----------|----------------|-------------|
| Aaron | CEO (Rank 0) |    | Busy | Working at Client | 2024-04-15 14:32:10 |
| Director | Director (Rank 1) | Aaron | Available | Coordinating Q2 projects | 2024-04-15 14:30:45 |
| TechLead | Technical Lead (Rank 2) | Director | Busy | Reviewing architecture | 2024-04-15 14:28:30 |
| DataAnalyst | Data Analyst (Rank 3) | TechLead | Busy | Analyzing user metrics | 2024-04-15 14:32:10 |

# Notepad
## Current Tasks
- [x] Pull Q1 metrics from database
- [ ] Create visualization for user growth
- [ ] Send report to TechLead by EOD

## Notes
- User signups increased 23% in March
- Need to investigate spike on March 15th
```

**Then the stimuli would appear as:**
```
Stimulus: time @ 2024-04-15 14:32:10
Current time: 2024-04-15 14:32:10 

Stimulus: message @ 2024-04-15 14:31:55
From: TechLead
To: DataAnalyst
How's the metrics analysis going? The Director is asking for an update.
```

This context structure ensures agents have full awareness of their role, the team structure, current state of all team members, and pending tasks/messages to process.

## Development Notes

This was an experimental project from April 2024 exploring:

- Can agents feel "alive" with autonomy and purpose?
- How do we handle multi-agent coordination?
- What memory architecture works best?
- Can LLMs handle temporal reasoning?

The codebase prioritizes experimentation over production readiness. Key learnings influenced subsequent agent architecture projects.