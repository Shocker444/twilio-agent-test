import os
from retell import Retell, AsyncRetell
from dotenv import load_dotenv

load_dotenv()




client = Retell(
    api_key=os.environ.get("RETELL_API_KEY"),  # This is the default and can be omitted
)

phone_call_response = client.call.create_phone_call(
    from_number="+13502250931",
    to_number="+2349013135774",
)
print(phone_call_response.agent_id)





# Or, if you are using asyncio, initialize the asynchronous client:
# async_client = AsyncRetell(
#     api_key=os.environ.get("RETELL_API_KEY", "your-api-key"),
# )