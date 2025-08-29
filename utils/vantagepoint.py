# Vantagepoint API utilities for vacation and employee data
import httpx
import logging
import json
import os
import re
import xmltodict
from typing import Optional, Dict, Any
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

VP_BASE_URL = os.environ.get("VP_BASE_URL")
PROCEDURE = os.environ.get("VP_SP_GETVACATION")

async def get_vacation_days(payload: Dict[str, Any], token: Optional[str]) -> Optional[Dict[str, Any]]:
    """
    Get vacation days for a specific employee using the Vantagepoint API.
    
    Args:
        payload (dict): Request payload containing employee information
        token (str): Access token for Vantagepoint API
        
    Returns:
        dict: Parsed vacation data or None if the API call fails
        
    Raises:
        httpx.HTTPError: If the API call fails
    """
    access_token = token
    
    url = f"{VP_BASE_URL}/api/Utilities/InvokeCustom/{PROCEDURE}"
    
    logger.debug(f"[GET /get_vacation_days] Request URL: {url}")
    logger.debug(f"[GET /get_vacation_days] Payload: {payload}")
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/xml",
        "Content-Type": "application/json"
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
    
    xml = response.text
    # Remove leading/trailing quotes if present
    xml = xml.strip()
    if xml.startswith('"') and xml.endswith('"'):
        xml = xml[1:-1]
    
    # Handle escaped characters - decode them properly
    xml = xml.encode().decode('unicode_escape')
    
    # Remove the schema block
    xml = re.sub(r'<xs:schema.*?</xs:schema>', '', xml, flags=re.DOTALL)
    # Remove empty <Table></Table> elements
    xml = re.sub(r'<Table>\s*</Table>', '', xml, flags=re.DOTALL)
    # Remove any control characters (non-printable)
    xml = re.sub(r'[^\x09\x0A\x0D\x20-\x7E]+', '', xml)
    # Strip leading/trailing whitespace again
    xml = xml.strip()
    
    logger.debug(f"[GET /get_vacation_days] Cleaned XML: {xml[:500]}...")  # Log first 500 chars for brevity
    
    # Parse the XML to dict
    parsed_xml = xmltodict.parse(xml)
    
    # Extract vacation balance data and clean up field names
    try:
        # Navigate to the Table data
        new_dataset = parsed_xml.get('NewDataSet', {})
        table_data = new_dataset.get('Table', {})
        
        # Extract and clean up the vacation data
        vacation_data = {
            "employee_id": table_data.get('Employee'),
            "starting_balance": float(table_data.get('Starting_x0020_Balance', 0)) if table_data.get('Starting_x0020_Balance') else None,
            "current_balance": float(table_data.get('Current_x0020_Balance', 0)) if table_data.get('Current_x0020_Balance') else None
        }
        
        logger.debug(f"Extracted vacation data: {vacation_data}")
        return vacation_data
        
    except Exception as e:
        logger.error(f"Error parsing vacation XML data: {e}")
        logger.debug(f"Parsed XML structure: {parsed_xml}")
        # Return the raw parsed XML as fallback
        return parsed_xml
