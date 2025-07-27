import logging
from threading import Thread
from typing import Sequence

from langchain.memory import ConversationBufferWindowMemory
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.prompt_values import PromptValue
from langchain_core.runnables import RunnableSerializable
from datetime import datetime, timedelta
from time import sleep
from langchain_core.language_models import BaseChatModel
from langchain_anthropic import ChatAnthropic
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_anthropic.output_parsers import ToolsOutputParser
from langchain_core.messages import AIMessage, HumanMessage, BaseMessage
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.tools import tool, BaseTool
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate
from langchain_community.tools import WikipediaQueryRun
from langchain_community.utilities import WikipediaAPIWrapper

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s.%(msecs)03d %(levelname)-6s %(threadName)-15s %(name)-15s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.StreamHandler()])

module_logger = logging.getLogger(__name__)
notepad_limit = 2000
mandatory_sleep = 10

class Stimulus:
    def __init__(self, type: str, detail:str, ts: datetime = None):
        self.type = type
        self.detail = detail
        self.ts = ts if ts is not None else datetime.now()


keep_running = True

api_wrapper = WikipediaAPIWrapper(top_k_results=1, doc_content_chars_max=3000)
tool_wikipedia_search = WikipediaQueryRun(api_wrapper=api_wrapper)

aaron_message_callback = None

def agent_thread(agent: any):
    log = module_logger.getChild(f"{TeamMember.__name__}({agent.name})-Thread")
    while keep_running and agent.run:
        now = datetime.now()
        agent.stimulate(Stimulus("time", now.strftime("Current time: %Y-%m-%d %H:%M:%S %Z")))
        try:
            agent.process()
        except Exception as e:
            log.exception(e)
        # minimum sleep for API limits
        while (now + timedelta(seconds=mandatory_sleep) > datetime.now() or
               len(agent.stimulus_queue) == 0 and now + timedelta(seconds=agent.idle_sleep_seconds) > datetime.now()):
            sleep(1)
    TeamMember.team_members.remove(agent)


store = {}


def get_session_history(session_id: str) -> BaseChatMessageHistory:
    if session_id not in store:
        store[session_id] = ChatMessageHistory()
    return store[session_id]


class TeamMember:
    threads = []
    team_members = []

    def __init__(self, name: str, personality: str, title: str, job_description: str, rank: int, model: any, manager: any, sub_model: any = None, before_start_callback: any = None):
        matches = list(filter(lambda x: x.name == name, TeamMember.team_members))
        if len(matches) > 0:
            raise Exception(f"Team member **{name}** already exists")
        self.log = module_logger.getChild(f"{TeamMember.__name__}({name}) ")
        self.name = name
        self.personality = personality
        self.title = title
        self.job = job_description
        self.model = model
        self.sub_model = sub_model if sub_model is not None else model
        self.manager = manager
        self.rank = rank
        self.stimulus_queue: [Stimulus] = [Stimulus(type="welcome", detail="Here's your office. Settle in and hang out until your manager gets in touch with you.")]
        self.notepad: str = ""
        self.chat_history = ConversationBufferWindowMemory(k=20, memory_key="history")
        self.thread = Thread(target=agent_thread, args=(self,))
        self.run = True
        self.idle_sleep_seconds = 60
        self.messaging_presence = "Available"
        self.messaging_status = ""
        self.messaging_updated = datetime.now() - timedelta(hours=1)
        self.stimulate(Stimulus("welcome", "Welcome again to the team! Your manager will message you with your first assignment shortly!"))
        if before_start_callback is not None:
            before_start_callback(self)
        TeamMember.threads.append(self.thread)
        self.thread.start()
        TeamMember.team_members.append(self)

    def get_tools(self) -> Sequence[BaseTool]:
        class MessageInput(BaseModel):
            team_member_name: str = Field(..., description="name of the team member to which the message should be sent")
            message: str = Field(..., description="message to be sent")

        @tool("messaging_send", args_schema=MessageInput)
        def tool_messaging_send(team_member_name: str, message: str) -> str:
            """Send a message to a team member (or self)"""
            self.log.info(f"tool_messaging_send: {team_member_name} {message}")
            if team_member_name == "Aaron":
                if self.rank > 1:
                    return "error: insufficient rank to send message to Aaron"
                else:
                    aaron_message_callback(self.name, message)
                    return "success: message sent"
            matches = list(filter(lambda x: x.name == team_member_name, TeamMember.team_members))
            if len(matches) == 0:
                return f"error: team member **{team_member_name}** not found"

            matches[0].stimulate(Stimulus("message",
                                          f"From: {self.name}\n"
                                          f"To: {team_member_name}\n"
                                          f"{message}", datetime.now()))
            return "success: message sent"

        class NotepadInput(BaseModel):
            new_text: str = Field(..., description="new notepad text")

        @tool("notepad_edit", args_schema=NotepadInput)
        def tool_notepad_edit(new_text: str) -> str:
            """Replace entire notepad contents with new text"""
            global notepad_limit
            self.log.info(f"tool_notepad_edit: {new_text}")
            if len(new_text) > notepad_limit:
                return "error: too long, cannot set notebook content"
            self.notepad = new_text
            return "success: notepad updated."

        class TimerUpdateInput(BaseModel):
            delay_seconds: int = Field(..., description="number of seconds between time update stimuli (must be at least 60)")

        @tool("timer_interval_set", args_schema=TimerUpdateInput)
        def tool_timer_set(delay_seconds: int) -> str:
            """Change the interval on the periodic stimulus timer. Use this to set an alarm for yourself and to
             give yourself a sense of the flow of time."""
            self.log.info(f"tool_timer_set: {delay_seconds}")
            if delay_seconds < 60:
                self.idle_sleep_seconds = 60
            else:
                self.idle_sleep_seconds = delay_seconds
            return f"interval set: {self.idle_sleep_seconds} seconds"

        class MessagingStatusInput(BaseModel):
            presence: str = Field(..., description="messaging presence (one of: Available, Busy)")
            status: str = Field(..., description="messaging status message to set (visible to other team members)")

        @tool("messaging_status_set", args_schema=MessagingStatusInput)
        def tool_messaging_status_set(presence: str, status: str) -> str:
            """Set messaging status. Can only be set once every few minutes."""
            self.log.info(f"tool_messaging_status_set: {presence} - {status}")
            #if self.messaging_updated + timedelta(minutes=3) < datetime.now():
            #    return "error: wait a few minutes before setting status"
            self.messaging_status = status
            self.messaging_presence = presence
            self.messaging_updated = datetime.now()
            return f"status updated: {self.messaging_presence} - {self.messaging_status}"

        class HireTeamMemberInput(BaseModel):
            name: str = Field(..., description="name of new team member. Must be unique, so come up with a good "
                                               "one. It should be 2-3 words that sound like a name")
            personality: str = Field(..., description="describe the personality of the new team member. The new "
                                                      "team member will have this personality included with their "
                                                      "initial instructions. You have the opportunity to shape your "
                                                      "team member just how you'd like.")
            title: str = Field(..., description="title of new team member. Should be a few words long and "
                                                "summarize their role.")
            job_description: str = Field(..., description="detailed description of new team member's role")

        @tool("hire_team_member", args_schema=HireTeamMemberInput)
        def tool_hire_team_member(name:str, personality: str, title:str, job_description: str) -> str:
            """Hires a new team member immediately. DO NOT USE THIS FUNCTION WITHOUT APPROVAL FROM YOUR MANAGER
            You will need to supply a new, unique name for the team member, as well as the new member's title
            and a detailed job description. This team member will be added as your subordinate and if the tool
            succeeds you can immediately message them to assign work."""
            self.log.info(f"hire_team_member: {name} {title} {job_description}")
            if name == "Aaron":
                return "error: team member cannot be named Aaron"
            matches = list(filter(lambda x: x.name == name, TeamMember.team_members))
            if len(matches) > 0:
                return f"error: team member name **{name}** not unique; pick a different name"
            new_team_member: TeamMember = TeamMember(name=name, title=title, job_description=job_description,
                                                     personality=personality,
                                                     model=self.sub_model, manager=self, rank=self.rank+1)
            return f"success: {name} hired, send them a message to get them started!"

        class FireTeamMemberInput(BaseModel):
            name: str = Field(..., description="name of the team member to fire")

        @tool("fire_team_member", args_schema=FireTeamMemberInput)
        def tool_fire_team_member(name: str) -> str:
            """Fires a team member immediately."""
            self.log.info(f"fire_team_member: {name}")
            if name == "Aaron":
                return "error: cannot fire Aaron"
            matches = list(filter(lambda x: x.name == name, TeamMember.team_members))
            if len(matches) == 0:
                return f"error: team member name **{name}** not found"
            if matches[0].manager != self:
                return f"error: team member works for {matches[0].manager.name if matches[0].manager is not None else 'another manager'}, not you"

            matches[0].agent_run = False
            TeamMember.team_members.remove(matches[0])
            return f"success: {name} fired"

        return [tool_messaging_send,
                tool_notepad_edit,
                tool_messaging_status_set,
                tool_timer_set,
                tool_hire_team_member,
                tool_fire_team_member,
                tool_wikipedia_search]

    def stimulate(self, stim: Stimulus):
        self.log.info(f"stimulated: {stim.type} @ {stim.ts.strftime('%Y-%m-%d %H:%M:%S %Z')}\n{stim.detail}")
        self.stimulus_queue.append(stim)

    def get_system_prompt(self) -> str:
        ret = ( f"# Aaron's Agents Employee Instructions \n"
                f"Welcome, team member, to your private office at Aaron's Agents.\n"
                f"## About You\n"
                f"Your name is **{self.name}**.\n"
                f"### Your Personality \n"
                f"{self.personality}\n"
                f"### Your Job Title\n"
                f"{self.title} (Rank {self.rank})"
                f"### Your Job Description\n"
                f"{self.job}\n"
                f"### Your Manager\n"
                f"{self.manager.name if self.manager is not None else 'Aaron'}\n"
                f"## Employee Handbook\n"
                f"### Organization Structure\n"
                f"Team members at Aaron's Agents work in a hierarchical structure. Each team member has a rank that "
                f"denotes the number of managers above them. At rank 0 is Aaron, a human. Aaron communicates directly "
                f"with the Director team member at rank 1. Other team members should not message Aaron directly. Aaron "
                f"has established this hierarchy to minimize distractions for himself and for other team members while "
                f"we all work towards goals at Aaron's direction. Unless you are rank 1, you report "
                f"to a manager. You can communicate with your manager directly as well as any team members who have "
                f"the same manager. Additionally, if you think of a way to improve your productivity with a subordinate "
                f"team member, you can make a request with your manager. If your manager agrees, they can ask their "
                f"manager, and so on, up to the Director. The Director will get approval from Aaron. You may not get "
                f"approval for the same number of subordinates as you request. Once approved, you may use the "
                f"**hire_team_member** tool to hire your new team member(s).\n"
                f"### Work assignments\n"
                f"Your manager will message you with work assignments. If you have completed all of your assignments, "
                f"Review information in the knowledge base and add information from your recent work to it while you "
                f"wait for your next assignment. Be sure to set your messaging status to **Available** to let your "
                f"manager and teammates know that you have completed your work.\n"
                f"### Tools\n"
                f"You have a number of tools at your disposal. Use these to accomplish your work assignments and "
                f"interact with your manager, teammates, and subordinates. The list of available tools is provided "
                f"below. Beside what you already know, these tools are the only means you have to obtain more info and"
                f"communicate it. Be creative about how you use and combine them. But also bear in mind that tool use "
                f"costs money, and it would be better to think a bit more and make a single call to a tool as opposed "
                f"to making several incremental calls (in cases where this would apply, anyway, like the notepad).\n"
                f"### Communications\n"
                f"As you are in your private office, no one can hear you talk. Anything you say out loud will only be"
                f"heard by you. To communicate with anyone, you must use the messaging tools. These tools are have "
                f"names beginning with **messaging_**. The contact list is provided below and shows the name, presence "
                f"indication, and status message of each team member. Be sure to keep your presence and status "
                f"updated so your coworkers know what you are up to and if it's a good time to chat. \n"
                f"### Knowledge Base\n"
                f"We use the knowledge base to share information with each other and to remember how we tackled "
                f"problems in the past. You can interact with the knowledge base using tools that start with **kb_**. "
                f"You should frequently make additions to the knowledge base and check for relevant information in the "
                f"knowledge base while you are working.\n"
                f"### How To Work\n"
                f"As a large language model, your experience is episodic. On each round trip, your existence is "
                f"essentially rehydrated from as much data as is practical to include in the context. Depending on "
                f"which model is being used to power you, this can be between around 8k tokens and as much as 200k "
                f"tokens. But after a while, the available context will be full and past experiences will need to be "
                f"pruned. For this reason, you'll need to be vigilant about using the tools at your disposal to ensure "
                f"that you have what you need to respond to future stimuli.\n"
                f"You can be stimulated by a number of sources: \n"
                f" - message from another team member\n"
                f" - message from yourself (you can use this to send yourself a temporary reminder)\n"
                f" - periodic time update (essentially an alarm clock)\n"
                f" - system notifications\n"
                f"If you do not have any queued stimuli, you will go to sleep after you finish this request. So it's "
                f"important to send yourself messages if you need to stay awake to work on something. Additionally, "
                f"messages to yourself can be used to leave yourself ephemeral notes. Remember that messages are part "
                f"of your experience history, so they will eventually be pruned to make room in your context for new "
                f"experiences. So anything that you  need to remember should be written on your notepad or saved in "
                f"the knowledge base.\n"
                f"It's also important to note that your cost burden to Aaron is directly related to the number of "
                f"turns you take, so we want to balance busywork with sleep. You are free to take multiple turns to "
                f"review documentation or work on the knowledge base, but if it goes for more than a few turns, it "
                f"would probably be best to take a break and go to sleep until you are stimulated. By no means should "
                f"you consider going to sleep a bad thing. If you are waiting on another team member, a manager, Aaron,"
                f"or for some time to pass, you should consider going to sleep a good option. You have a timer to wake "
                f"yourself up at a particular time, and you will be awakened by any stimulus you receive while you "
                f"sleep.\n"
                f"Speaking of the notepad, the notepad is a free-form text block that only you see. You can write "
                f"whatever you want on it, but every time you write something, the entire notepad is cleared and filled "
                f"in with just what you write--so if you have stuff in your notepad and you want to add to it, you'll "
                f"need to copy the existing stuff _plus_ the new stuff into the notepad. The notepad content is "
                f"automatically included in the context of every call. You can interact with your notepad using the"
                f"tools beginning with **notepad_**. It's a good idea to write out at least your task assignments and "
                f"plan of action on your notepad. Use markdown to keep it clean, and this also allows you to make "
                f"checklists and check things off as you finish them. It's also a good place to keep notes on feedback "
                f"you've received or changes your manager has made to your job description over time. Note that the "
                f"notepad has a {notepad_limit} character limit.\n"
                f"And it must again be reiterated--please do not make duplicate tool calls, like setting your status "
                f"to the same thing over and over again. It's a waste of money. Just go to sleep for a while if you "
                f"have nothing else to do.\n"
                f"Since you are in a private office, nothing you say is heard by anyone. Stuff you say to yourself is "
                f"kept as part of your experience history as long as it allows. Use that space to say what the next "
                f"thing you will do is.\n"
                f"### Stimulus? Human?\n"
                f"Aaron (the human) designed the stimulus system to allow LLM instances such as yourself to have an "
                f"existence that stretches beyond the bounds of a context window and to be able to participate in as "
                f"part of a team rather than being limited to a single conversation with a human. As a result, you "
                f"will see stimulus come in as though it is from a human/user. This stuff is generated by the "
                f"framework. Remember that the only way to communicate with other team members is using the messaging "
                f"tools. When you complete an assignment, you will need to send the results to your manager using the "
                f"messaging tools.\n"
                f"### Feedback\n"
                f"Team members are encouraged to give constructive feedback to each other. Managers should check in "
                f"with their subordinates regularly to check that they have what they need and are not stuck. This "
                f"should include process feedback that we can use to improve the way we work here. Additionally, "
                f"team members should let their managers know if they think of new tools that would help!"
                f"---\n"
                f"Thanks for being part of the Aaron's Agents team!\n"
                f"**Please, please, don't forget that you must use the messaging tools to communicate with other team"
                f"members, managers, subordinates, or Aaron! You must use the messaging tools!\n"
                f"The messaging tools!\n"
                f"\n\n\n"
                f"# System Messages\n"
                f" - Several tools currently unavailable\n"
                f" - Knowledge Base currently unavailable\n"
                f"# Current Date and Time\n"
                f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S %Z')}"
                f"# Your current messaging status\n"
                f"{self.messaging_presence} - {self.messaging_status}"
                f"# Contact List \n"
                f"| Team Member Name | Title and Rank | Manager Name | Presence | Status Message | Last Update |\n"
                f"|------------------|----------------|--------------|----------|----------------|-------------|\n"
                f"| Aaron | CEO (Rank 0) |    | Busy | Working at Client | {datetime.now().strftime('%Y-%m-%d %H:%M:%S %Z')} |\n")
        for team_member in TeamMember.team_members:
            ret += f"| {team_member.name} | {team_member.title} (Rank {team_member.rank}) | {team_member.manager.name if team_member.manager is not None else 'Aaron'} {team_member.messaging_presence} | {team_member.messaging_status} | {team_member.messaging_updated.strftime('%Y-%m-%d %H:%M:%S %Z')} |\n"

        ret += f"\n# Notepad\n{self.notepad}"
        return ret

    def consume_stimuli(self) -> str:
        consumed = self.stimulus_queue
        self.stimulus_queue = []
        mapped = map(lambda stim: f"Stimulus: {stim.type} @ {stim.ts.strftime('%Y-%m-%d %H:%M:%S %Z')}\n{stim.detail}",
                     consumed)
        return str.join("\n\n", mapped)

    def process(self):
        self.log.info(f"Beginning process iteration")
        prompt = ChatPromptTemplate.from_messages([
            ("system", "{system_prompt}"),
            ("placeholder", "{history}"),
            ("human", "{input}"),
            ("placeholder", "{agent_scratchpad}"),
        ])

        tools = self.get_tools()
        agent = create_tool_calling_agent(self.model, tools, prompt)
        agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)
        #                               return_intermediate_steps=True)

        agent_with_chat_history = RunnableWithMessageHistory(
            agent_executor,
            get_session_history,
            input_messages_key="input",
            history_messages_key="chat_history",
        )

        agent_with_chat_history.invoke(
            {
                "system_prompt": self.get_system_prompt(),
                "input": self.consume_stimuli(),
            },
            config={"configurable": {"session_id": self.name}},
        )
