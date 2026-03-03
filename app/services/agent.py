"""Claude agent service with tool use for voice conversations."""

import anthropic
import structlog

from app.config import settings
from app.prompts.sales_agent import build_system_prompt
from app.services import rag
from app.tools.analysis import ANALYSIS_TOOL, execute_analysis
from app.tools.crm import CRM_UPDATE_TOOL, execute_crm_update
from app.tools.knowledge_base import KNOWLEDGE_BASE_TOOL, execute_search

logger = structlog.get_logger()

TOOLS = [ANALYSIS_TOOL, KNOWLEDGE_BASE_TOOL, CRM_UPDATE_TOOL]


class VoiceAgent:
    """Claude-powered voice agent for customer service calls."""

    def __init__(
        self,
        call_id: str,
        customer_phone: str,
        customer_name: str,
        project_data: str = "",
    ):
        self.call_id = call_id
        self.customer_phone = customer_phone
        self.customer_name = customer_name
        self.project_data = project_data
        self.conversation_history: list[dict] = []
        self.should_end_call = False
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._system_prompt = build_system_prompt(customer_name, project_data)

    async def get_greeting(self) -> str:
        """Get the initial greeting for the call."""
        response = await self._send_message(
            "المكالمة بدأت. العميل رد على الهاتف. ابدأ بالتحية."
        )
        return response

    async def process_customer_input(self, text: str) -> str:
        """Process customer speech (transcribed text) and return agent response.

        Returns the agent's text response to be synthesized to speech.
        """
        if not text.strip():
            return ""

        response = await self._send_message(text)
        return response

    async def _send_message(self, user_text: str) -> str:
        """Send a message to Claude and process the response, handling tool use."""
        self.conversation_history.append({
            "role": "user",
            "content": user_text,
        })

        response = await self._client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=self._system_prompt,
            tools=TOOLS,
            messages=self.conversation_history,
        )

        # Process response - may involve multiple rounds of tool use
        return await self._process_response(response)

    async def _process_response(self, response) -> str:
        """Process Claude's response, handling tool calls recursively."""
        assistant_content = response.content
        self.conversation_history.append({
            "role": "assistant",
            "content": [block.model_dump() for block in assistant_content],
        })

        # Check if there are tool calls
        tool_use_blocks = [b for b in assistant_content if b.type == "tool_use"]
        text_blocks = [b for b in assistant_content if b.type == "text"]

        if not tool_use_blocks:
            # No tools, just return text
            return " ".join(b.text for b in text_blocks).strip()

        # Execute all tool calls
        tool_results = []
        for tool_block in tool_use_blocks:
            result = await self._execute_tool(tool_block.name, tool_block.input)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_block.id,
                "content": result,
            })

            # Check if analysis was called (signals end of conversation)
            if tool_block.name == "analysis":
                self.should_end_call = True

        # Send tool results back to Claude
        self.conversation_history.append({
            "role": "user",
            "content": tool_results,
        })

        # Get Claude's next response after tool use
        next_response = await self._client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=self._system_prompt,
            tools=TOOLS,
            messages=self.conversation_history,
        )

        return await self._process_response(next_response)

    async def _execute_tool(self, tool_name: str, tool_input: dict) -> str:
        """Execute a tool and return the result."""
        logger.info("Executing tool", tool=tool_name, call_id=self.call_id)

        if tool_name == "analysis":
            return await execute_analysis(
                call_id=self.call_id,
                customer_phone=self.customer_phone,
                customer_name=self.customer_name,
                tool_input=tool_input,
            )
        elif tool_name == "search_knowledge_base":
            return await execute_search(tool_input["query"])
        elif tool_name == "update_crm":
            return await execute_crm_update(
                call_id=self.call_id,
                customer_phone=self.customer_phone,
                field=tool_input["field"],
                value=tool_input["value"],
            )
        else:
            logger.warning("Unknown tool", tool=tool_name)
            return f"أداة غير معروفة: {tool_name}"

    def get_history(self) -> list[dict]:
        """Get conversation history."""
        return self.conversation_history
