from langchain_core.tools import tool
from datetime import datetime

sample_db = {
    "12345": {
        "name": "John Doe",
        "email": "[EMAIL_ADDRESS]",
        "phone": "1234567890",
        "address": "123 Main St",
        "city": "New York",
        "state": "NY",
        "zip": "10001",
        "country": "USA",
        "created_at": datetime.now().strftime("%a %b %#d, %Y"),
        "DUI_status": "Pending case",
        "case_description": "Possession of Narcotics"
    },
    "12346": {
        "name": "John Doe",
        "email": "[EMAIL_ADDRESS]",
        "phone": "1234567890",
        "address": "123 Main St",
        "city": "New York",
        "state": "NY",
        "zip": "10001",
        "country": "USA",
        "created_at": datetime.now().strftime("%a %b %#d, %Y"),
        "DUI_status": "Pending case",
        "case_description": "Reckless Driving"
    },
    "12347": {
        "name": "John Doe",
        "email": "[EMAIL_ADDRESS]",
        "phone": "1234567890",
        "address": "123 Main St",
        "city": "New York",
        "state": "NY",
        "zip": "10001",
        "country": "USA",
        "created_at": datetime.now().strftime("%a %b %#d, %Y"),
        "DUI_status": "Pending case",
        "case_description": "DUI"
    }
}

@tool(parse_docstring=True)
async def get_customer_data(
    customer_id: str,
):
    """Returns the details of a customer when the tool is called.
    
    Args:
        customer_id: The ID of the customer to retrieve.

    Returns:
        A string containing the customer details.
    """
    
    return sample_db.get(customer_id, "Customer not found")


tools = [get_customer_data]
tool_dict = {tool.name: tool for tool in tools}