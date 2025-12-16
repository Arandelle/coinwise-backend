from fastapi import APIRouter, Depends, HTTPException, Body
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple, List
import json
import os
import hashlib
import google.generativeai as genai
from bson import ObjectId
from pydantic import BaseModel
from database import db
from utils.auth import get_current_user

# Configure Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

router = APIRouter(prefix="/ai-insights", tags=["AI Insights"])

# In-memory cache (use Redis in production)
insights_cache: Dict[str, Tuple[dict, datetime]] = {}
user_requests: Dict[str, list] = {}


class InsightsRequest(BaseModel):
    """Request model for AI insights - all fields optional"""
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    category: Optional[str] = None


async def check_rate_limit(user_id: str, max_requests: int = 10, window_minutes: int = 60):
    """Rate limit: 10 requests per hour per user"""
    now = datetime.now()
    cutoff = now - timedelta(minutes=window_minutes)
    
    if user_id not in user_requests:
        user_requests[user_id] = []
    
    user_requests[user_id] = [req_time for req_time in user_requests[user_id] if req_time > cutoff]
    
    if len(user_requests[user_id]) >= max_requests:
        remaining_time = int((user_requests[user_id][0] + timedelta(minutes=window_minutes) - now).total_seconds() / 60)
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Try again in {remaining_time} minutes."
        )
    
    user_requests[user_id].append(now)


@router.post("")
async def get_ai_insights(
    current_user: dict = Depends(get_current_user),
    request_data: InsightsRequest = Body(default=InsightsRequest())
):
    """
    Generate AI-powered financial insights
    Returns CONVERSATIONAL insights with structured data
    
    Body is optional - if not provided, defaults to current month data
    """
    try:
        user_id = str(current_user.get("_id") or current_user.get("id"))
        
        # Check rate limit
        await check_rate_limit(user_id, max_requests=10, window_minutes=60)
        
        # Parse filters from Pydantic model
        start_date = request_data.start_date
        end_date = request_data.end_date
        category = request_data.category
        
        if not start_date:
            start_date = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            
        if not end_date:
            end_date = datetime.now()
        else:
            end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))

        # Create cache key
        cache_key = hashlib.md5(
            f"{user_id}:{start_date.date()}:{end_date.date()}:{category}".encode()
        ).hexdigest()
        
        # Check cache (valid for 4 hours for more frequent updates)
        if cache_key in insights_cache:
            cached_insights, cached_time = insights_cache[cache_key]
            cache_age = datetime.now() - cached_time
            
            if cache_age < timedelta(hours=4):
                return {
                    "insights": cached_insights,
                    "cached": True,
                    "cache_age_minutes": int(cache_age.total_seconds() / 60),
                    "generated_at": cached_time.isoformat()
                }
        
        # Aggregate transaction data
        aggregated_data = await aggregate_user_transactions(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
            category=category
        )
        
        # Check if user has enough data
        if aggregated_data['total_transactions'] < 3:
            return {
                "insights": {
                    "type": "insufficient_data",
                    "message": "Add at least 3 transactions to get personalized insights.",
                    "suggestion": "Start tracking your daily expenses to see your spending patterns."
                },
                "data_summary": aggregated_data
            }

        # Generate AI insights
        insights = await generate_ai_insights_gemini(aggregated_data)
        
        # Cache insights
        insights_cache[cache_key] = (insights, datetime.now())
        
        return {
            "insights": insights,
            "cached": False,
            "data_summary": aggregated_data,
            "generated_at": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error generating AI insights: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to generate insights: {str(e)}")


async def aggregate_user_transactions(
    user_id: str,
    start_date: datetime,
    end_date: datetime,
    category: Optional[str] = None
) -> dict:
    """Aggregate transaction data with enhanced metrics"""
    
    match_filter = {
        "user_id": user_id,
        "date": {"$gte": start_date, "$lte": end_date}
    }
    
    if category:
        match_filter["category_id"] = category

    # DEBUG: Log the match filter
    print(f"🔍 Querying transactions with filter: {match_filter}")
    
    # First, let's check what data exists
    sample_transactions = await db.transactions.find(match_filter).limit(5).to_list(length=5)
    print(f"📊 Sample transactions: {sample_transactions}")
    
    # Aggregate by category
    category_pipeline = [
        {"$match": match_filter},
        {
            "$addFields": {
                "category_id_obj": {
                    "$cond": {
                        "if": {"$eq": [{"$type": "$category_id"}, "string"]},
                        "then": {"$toObjectId": "$category_id"},
                        "else": "$category_id"
                    }
                }
            }
        },
        {
            "$lookup": {
                "from": "categories",
                "localField": "category_id_obj",
                "foreignField": "_id",
                "as": "category_info"
            }
        },
        {"$unwind": {"path": "$category_info", "preserveNullAndEmptyArrays": True}},
        {
            "$group": {
                "_id": {
                    "category_name": "$category_info.category_name",
                    "type": "$type"
                },
                "total": {"$sum": "$amount"},
                "count": {"$sum": 1},
                "type": {"$first": "$type"}
            }
        },
        {"$sort": {"total": -1}}
    ]
    
    category_results = await db.transactions.aggregate(category_pipeline).to_list(length=None)
    
    # Top merchants for expenses only
    merchant_pipeline = [
        {"$match": {**match_filter, "type": "expense"}},
        {
            "$group": {
                "_id": "$name",
                "total": {"$sum": "$amount"},
                "count": {"$sum": 1}
            }
        },
        {"$sort": {"total": 1}},  # Sort ascending (most negative first)
        {"$limit": 5}
    ]
    
    merchant_results = await db.transactions.aggregate(merchant_pipeline).to_list(length=None)
    
    # Calculate totals based on type field, not amount sign
    total_income = sum(cat['total'] for cat in category_results if cat['type'] == 'income')
    total_expense = abs(sum(cat['total'] for cat in category_results if cat['type'] == 'expense'))
    total_transactions = sum(cat['count'] for cat in category_results)
    
    # Format expenses by category (top 10)
    expense_categories = [
        {
            "name": cat['_id']['category_name'] or "Uncategorized",
            "total": abs(cat['total']),
            "count": cat['count'],
            "percentage": (abs(cat['total']) / total_expense * 100) if total_expense > 0 else 0
        }
        for cat in category_results if cat['type'] == 'expense'
    ]
    expense_categories.sort(key=lambda x: x['total'], reverse=True)
    expense_by_category = expense_categories[:10]
    
    # Format income by source
    income_categories = [
        {
            "name": cat['_id']['category_name'] or "Other Income",
            "total": cat['total'],
            "count": cat['count']
        }
        for cat in category_results if cat['type'] == 'income'
    ]
    
    # Top merchants (fix to show absolute values)
    top_merchants = [
        {
            "name": merchant['_id'],
            "total": abs(merchant['total']),  # Show as positive for display
            "count": merchant['count'],
            "average": round(abs(merchant['total']) / merchant['count'], 2)
        }
        for merchant in merchant_results
    ]
    
    # Previous period comparison
    prev_start = start_date - timedelta(days=30)
    prev_match = {"user_id": user_id, "date": {"$gte": prev_start, "$lt": start_date}}
    
    prev_results = await db.transactions.aggregate([
        {"$match": prev_match},
        {
            "$group": {
                "_id": "$type",
                "total": {"$sum": "$amount"}
            }
        }
    ]).to_list(length=None)
    
    # Parse previous period results by type
    prev_expense = 0
    prev_income = 0
    for result in prev_results:
        if result['_id'] == 'expense':
            prev_expense = abs(result['total'])
        elif result['_id'] == 'income':
            prev_income = result['total']
    
    return {
        "period": f"{start_date.strftime('%B %Y')}",
        "date_range": {
            "start": start_date.date().isoformat(),
            "end": end_date.date().isoformat()
        },
        "total_income": round(total_income, 2),
        "total_expense": round(total_expense, 2),
        "net_cash_flow": round(total_income - total_expense, 2),
        "savings_rate": round((total_income - total_expense) / total_income * 100, 2) if total_income > 0 else 0,
        "total_transactions": total_transactions,
        "expense_by_category": expense_by_category,
        "income_by_source": income_categories,
        "top_merchants": top_merchants,
        "comparison": {
            "previous_period_expense": round(prev_expense, 2),
            "previous_period_income": round(prev_income, 2),
            "expense_change": round(total_expense - prev_expense, 2),
            "expense_change_pct": round((total_expense - prev_expense) / prev_expense * 100, 2) if prev_expense > 0 else 0,
            "income_change_pct": round((total_income - prev_income) / prev_income * 100, 2) if prev_income > 0 else 0
        }
    }


async def generate_ai_insights_gemini(aggregated_data: dict) -> dict:
    """
    Call Gemini API to generate financial insights
    """
    
    # Initialize Gemini model with system instruction
    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash-lite",
        system_instruction="""You are a personal finance advisor for Filipino users. 
Your goal is to provide actionable, culturally-relevant financial insights and recommendations.

Key guidelines:
- Use Philippine Peso (₱) for all amounts
- Be encouraging but honest about financial habits
- Provide specific, implementable advice
- Consider Filipino lifestyle and expenses (jeepney, Jollibee, sari-sari stores, etc.)
- Focus on practical money-saving tips that work in the Philippines
- Be conversational and relatable
- Always respond in valid JSON format only, no markdown, no explanation text"""
    )
    
    # Prepare the prompt - FIX: Use correct field names
    prompt = f"""Analyze this financial data and provide actionable insights.

User's Financial Data for {aggregated_data['period']}:

Income & Expenses:
- Total Income: ₱{aggregated_data['total_income']:,.2f}
- Total Expenses: ₱{aggregated_data['total_expense']:,.2f}
- Net Cash Flow: ₱{aggregated_data['net_cash_flow']:,.2f}
- Savings Rate: {aggregated_data['savings_rate']:.1f}%
- Total Transactions: {aggregated_data['total_transactions']}

Spending by Category:
{json.dumps(aggregated_data['expense_by_category'], indent=2)}

Income Sources:
{json.dumps(aggregated_data['income_by_source'], indent=2)}

Top Spending Patterns:
{json.dumps(aggregated_data['top_merchants'], indent=2)}

Month-over-Month:
- Previous Month Expense: ₱{aggregated_data['comparison']['previous_period_expense']:,.2f}
- Change: ₱{aggregated_data['comparison']['expense_change']:,.2f} ({aggregated_data['comparison']['expense_change_pct']:.1f}%)

Return ONLY valid JSON in this exact structure (no markdown, no ```json blocks):

{{
  "financial_health_score": <number 1-10>,
  "score_explanation": "<brief explanation>",
  "money_leaks": [
    {{
      "category": "<category name>",
      "current_spending": <amount>,
      "potential_savings": <monthly savings>,
      "annual_impact": <potential_savings * 12>,
      "action": "<specific action>",
      "severity": "high|medium|low"
    }}
  ],
  "doing_well": [
    "<positive habit 1>",
    "<positive habit 2>"
  ],
  "action_plan": [
    {{
      "title": "<action title>",
      "description": "<what to do>",
      "savings": <monthly amount>,
      "timeframe": "<This week|This month>",
      "difficulty": "easy|medium|hard"
    }}
  ],
  "priority_alert": "<urgent issue or null>",
  "monthly_goal": {{
    "target_savings": <recommended target>,
    "current_savings": {aggregated_data['net_cash_flow']},
    "percentage": <(current/target)*100>
  }},
  "insights_summary": "<2-3 sentence overview>"
}}

Rules:
1. Identify 2-4 money leaks ranked by severity
2. Include 3-5 actionable items ordered by ease
3. Highlight 2-3 positive habits
4. Set priority_alert only for serious issues (savings < 10%, etc.)
5. Be specific with peso amounts and percentages"""

    try:
        # Generate response
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                temperature=0.7,
                top_p=0.95,
                top_k=40,
                max_output_tokens=8192,
            )
        )
        
        # Extract text
        response_text = response.text.strip()
        
        # Clean markdown if present
        if response_text.startswith('```json'):
            response_text = response_text[7:]
        if response_text.startswith('```'):
            response_text = response_text[3:]
        if response_text.endswith('```'):
            response_text = response_text[:-3]
        
        # Parse JSON
        insights = json.loads(response_text.strip())
        
        return insights
        
    except json.JSONDecodeError as e:
        print(f"Failed to parse Gemini response as JSON: {e}")
        print(f"Response was: {response_text}")
        
        # Fallback to mock data if JSON parsing fails
        return generate_mock_insights(aggregated_data)
        
    except Exception as e:
        print(f"Error calling Gemini API: {e}")
        raise Exception(f"Failed to generate AI insights: {str(e)}")


def generate_mock_insights(aggregated_data: dict) -> dict:
    """Fallback mock insights if API fails"""
    highest_category = max(
        aggregated_data['expense_by_category'],
        key=lambda x: x['total']
    ) if aggregated_data['expense_by_category'] else {"name": "Unknown", "total": 0}
    
    savings_rate = aggregated_data['savings_rate']
    
    return {
        "financial_health_score": 8 if savings_rate > 30 else 6 if savings_rate > 15 else 4,
        "score_explanation": f"Your savings rate of {savings_rate:.1f}% is {'excellent' if savings_rate > 30 else 'good' if savings_rate > 15 else 'needs improvement'}",
        "money_leaks": [
            {
                "category": highest_category['name'],
                "current_spending": highest_category['total'],
                "potential_savings": highest_category['total'] * 0.3,
                "annual_impact": highest_category['total'] * 0.3 * 12,
                "action": f"Reduce {highest_category['name']} expenses by 30%",
                "severity": "high" if highest_category['total'] > 3000 else "medium"
            }
        ],
        "doing_well": [
            f"You saved ₱{aggregated_data['net_cash_flow']:,.2f} this period",
            "You're tracking expenses regularly"
        ],
        "action_plan": [
            {
                "title": "Review highest expense",
                "description": f"Focus on {highest_category['name']}",
                "savings": highest_category['total'] * 0.2,
                "timeframe": "This month",
                "difficulty": "medium"
            }
        ],
        "priority_alert": None if savings_rate > 10 else "Savings rate below 10%",
        "monthly_goal": {
            "target_savings": aggregated_data['total_income'] * 0.3,
            "current_savings": aggregated_data['net_cash_flow'],
            "percentage": (aggregated_data['net_cash_flow'] / (aggregated_data['total_income'] * 0.3) * 100) if aggregated_data['total_income'] > 0 else 0
        },
        "insights_summary": f"You earned ₱{aggregated_data['total_income']:,.2f} and spent ₱{aggregated_data['total_expense']:,.2f}."
    }