import asyncio
from droidrun import DroidAgent, DroidrunConfig, AgentConfig, AdbTools
from llama_index.llms.litellm import LiteLLM
import os

async def main():

    llm = LiteLLM(
        model="openrouter/google/gemini-2.0-flash-001",
        api_key=os.environ.get("OPENROUTER_API_KEY")
    )

    droid_agent = DroidAgent(
"Sync Tuesday's class schedule from WhatsApp to Alarms.Step 1: Open WhatsApp, search for the contact 'teacher', and open the chat.Step 2: Find the message or file named 'tuesday_only_timetable'. Open it and take a screenshot to extract the class times for Tuesday.Step 3: Close WhatsApp and open the Gemini App.Step 4: For each class time found in Step 2, type a command to Gemini: 'Set an alarm for [Time]'.Step 5: Confirm the alarm is set before moving to the next one." ,     
     config=DroidrunConfig(
            agent=AgentConfig(max_steps=100)),
            llms = llm,
            tools=AdbTools()
        )
    
    await droid_agent.run()

    
if __name__ == "__main__":
    asyncio.run(main())

