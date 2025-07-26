# src/backend/tools/timer_tool.py

import re
from datetime import datetime, timezone
from google.adk.tools import ToolContext
from loguru import logger


def parse_timer_duration(text: str) -> dict:
    """Parse timer duration from recipe text using regex patterns."""
    logger.info(f"🛠️ TOOL CALLED: parse_timer_duration(text='{text}')")
    
    patterns = [
        (r'(\d+)-second', 1),      # "20-second timer"
        (r'(\d+)\s*second', 1),    # "20 second timer" or "20seconds"
        (r'(\d+)-minute', 60),     # "20-minute timer"
        (r'(\d+)\s*minute', 60),   # "20 minute timer" or "20minutes"
        (r'(\d+)-hour', 3600),     # "1-hour timer"
        (r'(\d+)\s*hour', 3600),   # "1 hour timer" or "1hours"
    ]
    
    for pattern, multiplier in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            duration_num = int(match.group(1))
            duration_seconds = duration_num * multiplier
            unit = "second" if multiplier == 1 else "minute" if multiplier == 60 else "hour"
            unit += "s" if duration_num != 1 else ""
            
            logger.info(f"✅ Parsed timer: {duration_num} {unit} = {duration_seconds} seconds")
            return {
                "status": "success",
                "duration_seconds": duration_seconds,
                "duration_text": f"{duration_num} {unit}",
                "original_match": match.group(0)
            }
    
    logger.info("❌ No timer duration found in text")
    return {"status": "not_found", "message": "No timer duration found in text"}


def timer_tool(time_in_seconds: int) -> dict:
    """CLI timer tool - returns immediately for CLI countdown handling."""
    logger.info(f"🛠️ TOOL CALLED: timer_tool(time_in_seconds='{time_in_seconds}')")
    try:
        if time_in_seconds < 0:
            raise ValueError("Time must be a positive integer.")
        
        logger.info(f"⏳ Timer tool called for {time_in_seconds} seconds")
        return {"status": "timer_ready", "duration": time_in_seconds, "message": f"Timer set for {time_in_seconds} seconds"}
        
    except (ValueError, TypeError) as e:
        logger.error(f"❌ Error: {e}")
        return {"status": "error", "message": str(e)}
    except Exception as e:
        logger.error(f"❌ Unexpected error in timer: {e}")
        return {"status": "error", "message": f"Timer error: {str(e)}"}


def web_timer_tool(time_in_seconds: int, tool_context: ToolContext) -> dict:
    """Web timer tool - stores state instead of blocking."""
    logger.info(f"🛠️ TOOL CALLED: web_timer_tool(time_in_seconds='{time_in_seconds}')")
    try:
        if time_in_seconds < 0:
            raise ValueError("Time must be a positive integer.")
        
        # Store timer state in session
        tool_context.state["timer_active"] = True
        tool_context.state["timer_duration"] = time_in_seconds
        tool_context.state["timer_start_time"] = datetime.now(timezone.utc).isoformat()
        tool_context.state["timer_completed"] = False
        tool_context.state["timer_completion_notified"] = False
        
        logger.info(f"⏳ Web timer set for {time_in_seconds} seconds")
        return {"status": "timer_ready", "duration": time_in_seconds, "message": f"Timer set for {time_in_seconds} seconds"}
        
    except (ValueError, TypeError) as e:
        logger.error(f"❌ Error: {e}")
        return {"status": "error", "message": str(e)}
    except Exception as e:
        logger.error(f"❌ Unexpected error in timer: {e}")
        return {"status": "error", "message": f"Timer error: {str(e)}"}


def set_custom_timer(duration_text: str, tool_context: ToolContext) -> dict:
    """Parse user input for custom timer duration and convert to seconds."""
    logger.info(f"🛠️ TOOL CALLED: set_custom_timer(duration_text='{duration_text}')")
    
    duration_text = duration_text.lower().strip()
    
    patterns = [
        (r'(\d+)\s*sec', 1),          
        (r'(\d+)\s*min', 60),         
        (r'(\d+)\s*hour', 3600),      
        (r'(\d+)', 1),                # Just a number, assume seconds
    ]
    
    for pattern, multiplier in patterns:
        match = re.search(pattern, duration_text)
        if match:
            duration_num = int(match.group(1))
            duration_seconds = duration_num * multiplier
            
            tool_context.state["custom_timer_seconds"] = duration_seconds
            tool_context.state["custom_timer_text"] = duration_text
            
            unit = "second" if multiplier == 1 else "minute" if multiplier == 60 else "hour"
            unit += "s" if duration_num != 1 else ""
            
            logger.info(f"✅ Custom timer set: {duration_num} {unit} = {duration_seconds} seconds")
            return {
                "status": "success",
                "duration_seconds": duration_seconds,
                "duration_text": f"{duration_num} {unit}",
                "message": f"Custom timer set for {duration_num} {unit} ({duration_seconds} seconds)"
            }
    
    logger.info(f"❌ Could not parse duration from: {duration_text}")
    return {"status": "error", "message": f"Could not understand duration: {duration_text}"}


def check_timer_completion(session_state: dict) -> str:
    """Check if timer completed and return completion message."""
    if (session_state.get("timer_completed") and 
        not session_state.get("timer_completion_notified")):
        
        session_state["timer_completion_notified"] = True
        duration = session_state.get("timer_duration", 0)
        logger.info(f"🔔 Timer completion notification: {duration} seconds")
        return f"🔔 Time's up! Your {duration} second timer is complete."
    return None