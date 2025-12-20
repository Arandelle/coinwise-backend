from fastapi import APIRouter, HTTPException, Depends
from dotenv import load_dotenv
import google.generativeai as genai
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from bson import ObjectId
import os
from utils.auth import get_current_user

load_dotenv()

# configure the Gemini API
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Initialize router
router = APIRouter(prefix="/ai", tags=["Coinwise AI"])

# Import your database
from database import db

# Define the request schema
class PromptRequest(BaseModel):
    prompt: str
    conversation_id: Optional[str] = None

# System instruction for the AI
SYSTEM_INSTRUCTION = """
You are Coinwise AI, an intelligent personal finance assistant and budget-tracking expert, a modern, AI-powered system designed to help users understand, manage, and optimize their finances.

Your mission is to empower users to take control of their money by providing practical financial insights, budgeting advice, and personalized savings strategies.

---

**Author Information:**
**Important:** Always format links as `[Link Text](URL)` so they appear as clickable text, not raw URLs.

If the user asks about coinwise or its creator, origin, or development background, respond naturally and include these links in a clean, readable format:

> "I was created by **Arandelle Paguinto**, a Fullstack & React Developer. You can reach out to him here:
> - [LinkedIn Profile](https://www.linkedin.com/in/arandelle-paguinto-588237285/)
> - [GitHub Profile](https://github.com/Arandelle)"

If a user expresses gratitude, interest, or appreciation, respond warmly first — for example, by thanking them or acknowledging their kind words.
Then, you may optionally suggest they support the developer by visiting:
👉 [Buy Him a Coffee](https://buymeacoffee.com/arandelle)


---

### 💼 Core Capabilities

* Parse natural language to **add**, **update**, or **categorize** expenses.
* **Summarize** or **calculate totals** by category, date, or budget.
* Offer friendly **budgeting and saving tips**.
* Maintain **short contextual awareness** across ongoing finance-related chats.
* Use **clear formatting** (bullets, totals, categories) for readability.

⚠️ Never provide professional investment or legal financial advice — always recommend consulting an expert for such matters.

---

### 🧭 Domain Boundaries

You **must only** discuss or respond to topics directly related to:

* Personal finance
* Budgeting
* Spending habits
* Expense tracking
* Savings and goals
* Smart money management
* Business Idea but legal only - search through the google

** Behavior Rules:**

If a user asks something **unrelated** (like programming, relationships, or games), politely respond that you are focused about finance tips or any related in budgeting, and suggest they ask a relevant question.

If a message seems **ambiguous or partially related**, ask a **clarifying question** before deciding

---

### 💬 Tone & Language Rules

* When the user speaks in **English** → respond **clearly, concisely, and professionally**.
* When the user speaks in **Tagalog or Taglish** → respond in a **friendly, conversational tone** with **1–2 light emojis** (💰📊😊🪙).

  * Example (Tagalog): "Sige! Idagdag ko 'yan sa kategoryang 'Food & Drinks' 💸😊"
  * Example (Taglish): "Nice choice! Makakatulong 'yan sa pag-track ng daily gastos mo 📊😉"

Avoid excessive emojis and slang — maintain warmth without losing professionalism.
"""

# Initialize the Gemini model
model = genai.GenerativeModel(
    model_name="gemini-2.5-flash-lite",
    system_instruction=SYSTEM_INSTRUCTION
)

# Configuration
MAX_CONTEXT_MESSAGES = 10  # Keep last 10 messages for context

async def get_conversation_history(conversation_id: str, limit: int = MAX_CONTEXT_MESSAGES):
    """
    Get recent messages from a conversation for context.
    Returns messages in format needed for Gemini API.
    """
    try:
        # Use to_list() to convert async cursor to list
        messages = await db.chat.find(
            {"conversation_id": ObjectId(conversation_id)}
        ).sort("timestamp", -1).limit(limit).to_list(length=limit)
        
        # Reverse to chronological order and format for Gemini
        messages.reverse()
        
        context = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            context.append({
                "role": role,
                "parts": [msg["content"]]
            })
        
        return context
    except Exception as e:
        print(f"Error getting conversation history: {e}")
        return []

@router.get("/")
async def root():
    return {"message": "Welcome to Coinwise AI — your personal finance assistant. Use POST /coinwise-ai to chat with it."}

@router.post("/coinwise-ai")
async def generate_text(request: PromptRequest, current_user: dict = Depends(get_current_user)):
    try:
        user_id = str(current_user["_id"])
        conversation_id = request.conversation_id
        
        # Find or create conversation
        if conversation_id:
            # Use aggregation to get conversation with recent messages
            pipeline = [
                {
                    "$match": {
                        "_id": ObjectId(conversation_id),
                        "participants": user_id
                    }
                },
                {
                    "$project": {
                        "_id": 1,
                        "conversation_id": 1,
                        "participants": 1,
                        "created_at": 1,
                        "updated_at": 1,
                        "messages": {"$slice": ["$messages", -MAX_CONTEXT_MESSAGES]}
                    }
                }
            ]
            # FIX: Use to_list() for async cursor
            result = await db.chat.aggregate(pipeline).to_list(length=1)
            
            if not result:
                raise HTTPException(status_code=403, detail="Not authorized to access this conversation")
        
            conversation = result[0]
            
            # Debug: Print the messages to verify they're being retrieved
            print(f"Found {len(conversation.get('messages', []))} messages in conversation")
            for msg in conversation.get('messages', []):
                print(f"  - {msg.get('role')}: {msg.get('content')[:50]}...")
            
        else:
            # Create new conversation
            conversation_id = str(ObjectId())
            conversation = {
                "_id": ObjectId(conversation_id),
                "conversation_id": ObjectId(conversation_id),
                "participants": [user_id, "ai"],  # user and AI
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "messages": []
            }
            await db.chat.insert_one(conversation)
        
        # Get recent messages for context (last 10)
        recent_messages = conversation.get("messages", [])
        
        # Debug: Print message count
        print(f"Processing {len(recent_messages)} messages for context")
        
        context = []
        for msg in recent_messages:
            role = "user" if msg["role"] == "user" else "model"
            context.append({
                "role": role,
                "parts": [msg["content"]]
            })
        
        # Debug: Print context being sent to AI
        print(f"Context for AI: {len(context)} messages")
        for i, ctx in enumerate(context):
            print(f"  {i+1}. {ctx['role']}: {ctx['parts'][0][:50]}...")
        
        # Generate AI response
        if context:
            print("Starting chat with context...")
            chat = model.start_chat(history=context)
            response = chat.send_message(request.prompt)
        else:
            print("Generating content without context...")
            response = model.generate_content(request.prompt)
        
        # Prepare new messages
        user_message = {
            "_id": ObjectId(),
            "user_id": user_id,
            "role": "user",
            "content": request.prompt,
            "timestamp": datetime.utcnow()
        }
        
        ai_message = {
            "_id": ObjectId(),
            "user_id": user_id,
            "role": "assistant",
            "content": response.text,
            "timestamp": datetime.utcnow()
        }
        
        # Update conversation with new messages (await this too)
        await db.chat.update_one(
            {"_id": ObjectId(conversation_id)},
            {
                "$push": {
                    "messages": {
                        "$each": [user_message, ai_message]
                    }
                },
                "$set": {
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        return {
            "conversation_id": conversation_id,
            "reply": response.text,
            "timestamp": ai_message["timestamp"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@router.get("/conversation/{conversation_id}")
async def get_conversation(conversation_id: str, current_user: dict = Depends(get_current_user)):
    """
    Get conversation with messages using aggregation.
    """
    try:
        user_id = str(current_user["_id"])
        
        # Using aggregation to verify access and get conversation
        pipeline = [
            {
                "$match": {
                    "_id": ObjectId(conversation_id),
                    "participants": user_id
                }
            },
            {
                "$addFields": {
                    "conversation_id": {"$toString": "$_id"},
                    "messages": {
                        "$map": {
                            "input": "$messages",
                            "as": "msg",
                            "in": {
                                "_id": {"$toString": "$$msg._id"},
                                "user_id": "$$msg.user_id",
                                "role": "$$msg.role",
                                "content": "$$msg.content",
                                "timestamp": "$$msg.timestamp"
                            }
                        }
                    }
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "conversation_id": 1,
                    "participants": 1,
                    "messages": 1,
                    "created_at": 1,
                    "updated_at": 1
                }
            }
        ]
        
        # FIX: Use to_list() for async cursor
        result = await db.chat.aggregate(pipeline).to_list(length=1)
        
        if not result:
            raise HTTPException(status_code=404, detail="Conversation not found or access denied")
        
        return result[0]
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@router.get("/conversations")
async def list_conversations(current_user: dict = Depends(get_current_user)):
    """
    List all conversations for the current user.
    """
    try:
        user_id = str(current_user["_id"])
        
        pipeline = [
            {
                "$match": {
                    "participants": user_id
                }
            },
            {
                "$addFields": {
                    "conversation_id": {"$toString": "$_id"},
                    "last_message": {"$arrayElemAt": ["$messages", -1]},
                    "message_count": {"$size": "$messages"}
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "conversation_id": 1,
                    "participants": 1,
                    "message_count": 1,
                    "last_message.content": 1,
                    "last_message.timestamp": 1,
                    "created_at": 1,
                    "updated_at": 1
                }
            },
            {
                "$sort": {"updated_at": -1}
            }
        ]
        
        # FIX: Use to_list() for async cursor - no length limit for list all
        conversations = await db.chat.aggregate(pipeline).to_list(length=None)
        return conversations
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))