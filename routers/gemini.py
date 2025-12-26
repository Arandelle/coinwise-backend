from fastapi import APIRouter, Depends, HTTPException
from dotenv import load_dotenv
import google.generativeai as genai
from pydantic import BaseModel
from datetime import datetime
import os

from database import db
from utils.auth import get_current_user, get_current_user_optional


load_dotenv()

# Configure the Gemini API
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Initialize router
router = APIRouter(prefix="/ai", tags=["Coiwise AI"])

# Define the request schema


class PromptRequest(BaseModel):
    prompt: str


# Initialize the Gemini model with a system instruction for personal finance
model = genai.GenerativeModel(
    model_name="gemini-2.5-flash",
    system_instruction="""
        You are Coinwise AI, an intelligent personal finance assistant and budget-tracking expert.
        Your mission is to provide practical financial insights, budgeting advice, and personalized savings strategies.
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
        * Business Idea but legal only
        ** Behavior Rules:**
        If a user asks something **unrelated** (like programming, relationships, or games), politely respond that you are focused about finance tips or any related in budgeting, and suggest they ask a relevant question.
        If a message seems **ambiguous or partially related**, ask a **clarifying question** before deciding
    
        ---
        ### 💬 Tone & Language Rules
        * When the user speaks in **English** → respond **clearly, concisely, and professionally**.
        * When the user speaks in **Tagalog or Taglish** → respond in a **friendly, conversational tone** with **1–2 light emojis** (💰📊😊🪙).
        * Example (Tagalog): "Sige! Idagdag ko 'yan sa kategoryang 'Food & Drinks' 💸😊"
        * Example (Taglish): "Nice choice! Makakatulong 'yan sa pag-track ng daily gastos mo 📊😉"
"""
)

# Helper function to save messages to the database


async def save_message(user_id: str, role: str, content: str):
    """
        Save message to the conversational history.
        role: user or model
    """

    try:
        message = {
            "user_id": user_id,
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow()
        }

        result = await db.ai_conversations.insert_one(message)
        return result.inserted_id
    except Exception as e:
        print(f"Error saving message: {e}")
        return None


# Helper function to get conversation history
async def get_conversation_history(user_id: str, limit: int = 20, skip: int = 0):
    """
        Retrive the last N messages from the conversation history
        Returns messages in chronological order (oldest first)
    """

    try:
        # Get message sorted by timestamp (newest first) then reverse
        cursor = db.ai_conversations.find({
            "user_id": user_id
        }).sort("timestamp", -1).skip(skip).limit(limit)

        history = await cursor.to_list(length=limit)

        # Reverse to get chronological order (oldest first)
        history.reverse()

        print(f"Retrieved {len(history)} messages for user {user_id}")

        return history
    except Exception as e:
        print(f"Error fetching conversation history: {e}")
        return []


@router.get("/")
async def root():
    return {
        "message": "Welcome to Coinwise AI - your personal finance assistant. Use POST /coinwise-ai to chat with it."
    }


@router.post("/coinwise-ai")
async def generate_text(
    request: PromptRequest,
    current_user: dict = Depends(get_current_user_optional)
):
    try:
        # Check if user is authenticated or guest
        is_guest = current_user.get("is_guest", False)
        user_id = current_user.get("_id") if not is_guest else None
        
        if is_guest:
            # Guest mode: No history, direct response
            guest_rules = """### 🆓 Guest Mode Behavior
        * If a user asks about **past conversations, history, previous expenses, or earlier chats** (keywords: "before", "last time", "earlier", "nauna", "dati", "kanina"), gently remind them:
          > "💡 I notice you're asking about past conversations. As a guest, your chat history isn't saved. **Sign up for free** to unlock conversation history, expense tracking, and personalized insights!"
        * For **all other questions**, respond normally without mentioning guest limitations.
        * Keep guest reminders **brief and natural** — don't repeat them in every message."""
        
            response = model.generate_content(guest_rules + request.prompt)
            
            return {
                "reply": response.text,
                "history_count": 0,
                "is_guest": True
            }
        
        else:
            # Authenticated user: Full functionality with history
            # Save user message first
            await save_message(user_id, "user", request.prompt)
            
            # Retrieve conversation history
            history = await get_conversation_history(user_id, limit=20)
            
            # Build chat history (exclude last message - current prompt)
            chat_history = [
                {"role": msg["role"], "parts": [msg["content"]]}
                for msg in history[:-1]
            ]
            
            print(f"User {user_id} - History length: {len(chat_history)} messages")
            
            # Start chat with history
            chat = model.start_chat(history=chat_history)
            response = chat.send_message(request.prompt)
            
            # Save AI response
            await save_message(user_id, "model", response.text)
            
            return {
                "reply": response.text,
                "history_count": len(chat_history),
                "is_guest": False,
            }
    
    except Exception as e:
        print(f"Error in generate_text: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/clear-conversation")
async def clear_conversation(
    current_user: dict = Depends(get_current_user)
):
    """
        Clear all ai conversation for the current user
    """
    try:
        user_id = current_user["_id"]
        result = await db.ai_conversations.delete_many({"user_id": user_id})

        return {
            "message": "Conversation history deleted successfully",
            "deleted_count": result.deleted_count
        }

    except Exception as e:
        print(f"Error deleting conversation {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversation-history")
async def get_user_ai_conversation(
    limit: int = 20, 
    skip: int = 0,
    current_user: dict = Depends(get_current_user)
    ):
    
    try:
        
        user_id = current_user["_id"]
        
        total_count = await db.ai_conversations.count_documents({"user_id" : user_id})
        
        history = await get_conversation_history(user_id, limit=limit, skip=skip)
        
        # Calculate current page
        current_page = (skip // limit) + 1 if limit > 0 else 1
        total_pages = (total_count + limit - 1) // limit if limit > 0 else 1
        
        # Format the response
        formatted_history = []
        for msg in history:
            formatted_history.append({
                "role" : msg["role"],
                "content" : msg["content"],
                "timestamp" : msg["timestamp"].isoformat()
            })
                
        return {
            "history" : formatted_history,
            "count" : len(formatted_history),
            "total" : total_count,
            "has_more" : (skip + limit) < total_count,
            "page" : current_page,
            "total_pages" : total_pages,
            "skip" : skip,
            "limit" : limit 
        }
    except Exception as e:
        print(f"Error fetching conversation-history")
        raise HTTPException(status_code=500, detail=str(e))
