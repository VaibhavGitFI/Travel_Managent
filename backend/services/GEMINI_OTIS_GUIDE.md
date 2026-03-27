# Gemini Service - OTIS Voice Intelligence Guide

**Last Updated:** 2026-03-26
**Status:** Production Ready ✅

---

## Overview

The enhanced Gemini service provides voice-optimized AI intelligence for OTIS (Omniscient Travel Intelligence System). This guide explains the new capabilities added specifically for voice interactions.

---

## New Capabilities

### 1. Function Calling (`generate_with_functions`)

Enables OTIS to execute TravelSync actions via voice commands.

**Usage:**
```python
from services.gemini_service import gemini
from agents.otis_functions import OtisFunctionRegistry

# Get function definitions
registry = OtisFunctionRegistry()
functions = registry.get_functions_for_gemini()

# Process command with function calling
result = gemini.generate_with_functions(
    prompt="What pending approvals do I have?",
    functions=functions,
    system_instruction="You are OTIS...",
    model_type="flash"
)

# Check result type
if result["type"] == "function_call":
    # Gemini wants to call a function
    function_name = result["function_name"]
    parameters = result["parameters"]
    # Execute the function...
elif result["type"] == "text":
    # Gemini responded with text
    response = result["text"]
```

**Function Definition Format:**
```python
{
    "name": "get_pending_approvals",
    "description": "Get list of travel requests pending approval",
    "parameters": {
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "Maximum number of approvals to return"
            }
        }
    }
}
```

---

### 2. Voice-Optimized Generation (`generate_voice_optimized`)

Generates concise, natural speech responses optimized for voice output.

**Usage:**
```python
from services.gemini_service import gemini

# Build context
context = {
    "user_name": "Arjun",
    "user_role": "manager",
    "pending_approvals_count": 3,
    "upcoming_trips_count": 2
}

# Build conversation history
conversation_history = [
    {
        "user_input": "What's my schedule?",
        "assistant_response": "You have two meetings today..."
    }
]

# Generate voice response
response = gemini.generate_voice_optimized(
    prompt="What pending approvals do I have?",
    context=context,
    conversation_history=conversation_history,
    model_type="flash"
)

# Response: "You have three pending approvals. Mumbai trip for John,
# Delhi trip for Sarah, and Bangalore trip for Priya."
```

**Features:**
- Concise responses (2-3 sentences max)
- No markdown or formatting
- Numbers as words ("three" not "3")
- Natural speech patterns
- Context-aware responses

---

### 3. Proactive Suggestions (`generate_proactive_suggestion`)

Generates helpful suggestions based on user context.

**Usage:**
```python
from services.gemini_service import gemini

context = {
    "pending_approvals_count": 5,
    "upcoming_trips_count": 1,
    "pending_expenses_count": 3,
    "unread_notifications": 2
}

suggestion = gemini.generate_proactive_suggestion(
    context=context,
    model_type="flash"
)

# Example: "You have five pending approvals. Would you like me to review them?"
```

---

## Voice Response Formatting

### Automatic Cleaning (`_clean_for_voice`)

All voice responses are automatically cleaned:

**Before:**
```
**Trip Approved**
- Request ID: TR-2024-001
- Destination: Mumbai
- Amount: ₹15000
```

**After:**
```
Trip approved. Request ID TR-2024-001. Destination Mumbai. Amount fifteen thousand rupees.
```

**Transformations:**
- Removes markdown: `**bold**` → `bold`
- Removes lists: `- Item` → `Item`
- Removes headers: `## Title` → `Title`
- Converts abbreviations: `INR` → `rupees`, `km` → `kilometers`
- Cleans whitespace and formatting

---

## OTIS System Instructions

### Function Calling Mode

```python
system_instruction = """You are OTIS (Omniscient Travel Intelligence System).

**Function Calling Guidelines:**
1. When the user asks you to DO something, call the appropriate function
2. Use provided functions whenever possible
3. Extract parameters carefully from speech
4. If required parameter missing, ask user
5. After calling function, use voice_response directly

**Voice Response Rules:**
- Concise and natural
- No markdown or formatting
- Numbers as words
- Keep under 3 sentences
- Always confirm what you did
"""
```

### Simple Conversation Mode

```python
system_instruction = """You are OTIS, a voice assistant for TravelSync Pro.

**Identity:**
- Professional and efficient
- Indian English accent
- Speaking to {user_name}, a {user_role}

**Voice Guidelines:**
- Be concise (2-3 sentences max)
- Natural speech, not writing
- Numbers in word form
- No markdown or formatting
- Use Indian English expressions appropriately
"""
```

---

## Integration with OTIS Agent

### Process Flow

```
User Speech
    ↓
Speech-to-Text (Deepgram)
    ↓
OTIS Agent (otis_agent.py)
    ↓
Decision: Functions or Simple Chat?
    ↓
┌─────────────────────────────────┐
│ Function Calling Mode           │  Simple Conversation Mode
│                                 │
│ gemini.generate_with_functions  │  gemini.generate_voice_optimized
│         ↓                       │          ↓
│ Check result type               │  Get text response
│         ↓                       │          ↓
│ Execute function                │  Clean for voice
│         ↓                       │          ↓
│ Get voice_response              │  Speak response
└─────────────────────────────────┘
```

### OTIS Agent Implementation

```python
# In otis_agent.py
async def process_command(self, command_text: str) -> str:
    context = self._build_context_dict()
    conversation_history = self._get_conversation_history()

    if self._should_use_functions(command_text):
        # Function calling workflow
        functions = self._function_registry.get_functions_for_gemini()
        result = gemini.generate_with_functions(
            prompt=command_text,
            functions=functions,
            system_instruction=self._get_function_calling_system_instruction(),
            model_type="flash"
        )

        if result["type"] == "function_call":
            # Execute function
            function_result = await self._function_registry.execute_function(
                function_name=result["function_name"],
                parameters=result["parameters"],
                user_id=self.user_id,
                user_role=self.user.get("role")
            )
            response_text = function_result.get("voice_response")
        else:
            response_text = result["text"]
    else:
        # Simple conversation
        response_text = gemini.generate_voice_optimized(
            prompt=command_text,
            context=context,
            conversation_history=conversation_history,
            model_type="flash"
        )

    return response_text
```

---

## Context Building

### Context Dictionary Structure

```python
context = {
    # User info
    "user_name": "Arjun Kumar",
    "user_role": "manager",
    "user_department": "Sales",

    # Counts for proactive suggestions
    "pending_approvals_count": 3,
    "upcoming_trips_count": 2,
    "recent_expense_count": 5,
    "pending_expenses_count": 1,
    "unread_notifications": 2
}
```

This context is used by `_build_otis_system_instruction()` to create user-specific prompts:

```python
system_instruction = f"""You are OTIS...

**Identity:**
- Speaking to {context["user_name"]}, who is a {context["user_role"]}

**Context Awareness:**
- The user has {context["pending_approvals_count"]} pending approvals
- The user has {context["upcoming_trips_count"]} upcoming trips
- The user submitted {context["recent_expense_count"]} expenses recently
"""
```

---

## Conversation History

### Format

```python
conversation_history = [
    {
        "user_input": "What pending approvals do I have?",
        "assistant_response": "You have three pending approvals..."
    },
    {
        "user_input": "Approve the Mumbai trip",
        "assistant_response": "Done. I've approved John's Mumbai trip..."
    }
]
```

Only the last 5 turns are included to keep context manageable while maintaining continuity.

---

## Function Decision Heuristic

### When to Use Functions

The `_should_use_functions()` method decides based on keywords:

**Action Keywords:**
- approve, reject, create, add, update, edit, delete, remove
- submit, cancel, book, reserve, confirm

**Query Keywords:**
- get, show, list, check, find, search, what's, what are
- tell me, give me, display, pending, upcoming, recent

**Analytics Keywords:**
- report, stats, statistics, analysis, analytics
- spend, budget, total, summary, overview, dashboard

**Examples:**
- ✅ "What pending approvals do I have?" → Uses functions
- ✅ "Approve John's Mumbai trip" → Uses functions
- ✅ "Show me my travel stats" → Uses functions
- ❌ "What is TravelSync?" → Simple conversation
- ❌ "Thank you" → Simple conversation

---

## Error Handling

### Quota Exceeded

```python
result = gemini.generate_with_functions(...)
if result["type"] == "text" and result["text"] is None:
    # Gemini is in cooldown or unavailable
    fallback_response = "I'm having trouble processing that. Please try again."
```

### Function Call Failures

```python
function_result = await registry.execute_function(...)
if not function_result.get("success"):
    # Function failed
    error_response = function_result.get("voice_response")
    # e.g., "Sorry, I couldn't find that trip request."
```

---

## Testing

### Test Voice-Optimized Generation

```python
# test_gemini_voice.py
from services.gemini_service import gemini

context = {
    "user_name": "Arjun",
    "user_role": "manager",
    "pending_approvals_count": 3
}

response = gemini.generate_voice_optimized(
    prompt="What's pending?",
    context=context
)

print(response)
# Expected: "You have three pending approvals. Would you like me to list them?"
```

### Test Function Calling

```python
functions = [
    {
        "name": "get_pending_approvals",
        "description": "Get list of pending approvals",
        "parameters": {"type": "object", "properties": {}}
    }
]

result = gemini.generate_with_functions(
    prompt="Show me pending approvals",
    functions=functions
)

assert result["type"] == "function_call"
assert result["function_name"] == "get_pending_approvals"
```

---

## Best Practices

### 1. Always Clean Responses for Voice
```python
# ❌ Don't send raw Gemini output to TTS
response = gemini.generate(prompt)
await tts.speak(response)  # May contain markdown

# ✅ Use voice-optimized generation
response = gemini.generate_voice_optimized(prompt, context)
await tts.speak(response)  # Already cleaned
```

### 2. Provide Rich Context
```python
# ❌ Minimal context
context = {"user_name": "Arjun"}

# ✅ Rich context for better responses
context = {
    "user_name": "Arjun",
    "user_role": "manager",
    "pending_approvals_count": 3,
    "upcoming_trips_count": 2
}
```

### 3. Limit Conversation History
```python
# ✅ Only last 5 turns
conversation_history = session.conversation_history[-5:]
```

### 4. Handle Failures Gracefully
```python
response = gemini.generate_voice_optimized(...)
if not response:
    response = "I'm having trouble processing that. Could you try again?"
```

---

## Performance

### Latency Targets

| Operation | Target | Typical |
|-----------|--------|---------|
| `generate_with_functions` | <500ms | 300-400ms |
| `generate_voice_optimized` | <500ms | 300-400ms |
| `generate_proactive_suggestion` | <300ms | 200-300ms |

### Model Selection

- **flash** (gemini-2.5-flash): Default for OTIS, fastest
- **pro** (gemini-2.5-pro): Use for complex reasoning (not needed for voice)

---

## Examples

### Complete Voice Interaction

```python
# User: "Hey Otis, what pending approvals do I have?"

# 1. STT → "what pending approvals do I have"

# 2. OTIS Agent decides to use functions
should_use = agent._should_use_functions("what pending approvals do I have")
# Returns: True (contains "what" and "pending")

# 3. Get functions from registry
functions = registry.get_functions_for_gemini()

# 4. Call Gemini with functions
result = gemini.generate_with_functions(
    prompt="what pending approvals do I have",
    functions=functions,
    system_instruction="You are OTIS..."
)

# 5. Gemini decides to call get_pending_approvals
# result = {
#     "type": "function_call",
#     "function_name": "get_pending_approvals",
#     "parameters": {}
# }

# 6. Execute function
function_result = await registry.execute_function(
    function_name="get_pending_approvals",
    parameters={},
    user_id=123,
    user_role="manager"
)

# 7. Get voice response
response = function_result["voice_response"]
# "You have three pending approvals. Mumbai trip for John departing
# March twenty-eighth, Delhi trip for Sarah departing April second,
# and Bangalore trip for Priya departing April fifth."

# 8. TTS speaks the response
await tts.speak(response)
```

---

## Troubleshooting

### Issue: Responses contain markdown

**Cause:** Using `generate()` or `generate_with_history()` directly
**Solution:** Use `generate_voice_optimized()` or manually clean with `_clean_for_voice()`

### Issue: Numbers spoken as digits

**Cause:** Not cleaning response for voice
**Solution:** Response should be cleaned automatically, but numbers in TravelSync data need to be converted to words

### Issue: Function not being called

**Cause:** Function not in registry or prompt doesn't match heuristic
**Solution:** Check `_should_use_functions()` and function descriptions

### Issue: Long verbose responses

**Cause:** System instruction not emphasizing conciseness
**Solution:** Update system instruction to specify "2-3 sentences maximum"

---

## Future Enhancements

### Planned

1. **Multi-turn function calling** - Chain multiple functions in one conversation
2. **Function result formatting** - Better voice formatting of complex data
3. **Hindi language support** - Bilingual responses
4. **Emotion detection** - Adjust tone based on user emotion
5. **Streaming responses** - Real-time partial responses

### Under Consideration

- Voice activity detection integration
- Background noise filtering
- Multi-user conversations
- Voice authentication

---

## Support

For questions or issues:
1. Check `/backend/agents/OTIS_ARCHITECTURE.md` for architecture details
2. Review `/backend/agents/otis_agent.py` for usage examples
3. Check logs for Gemini errors: `logger.warning("[Gemini] ...")`

---

**Status:** Production ready for OTIS voice intelligence ✅
