from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timedelta
from typing import Optional
import json
import os
import google.generativeai as genai
from utils.auth import get_current_user
from database import db

# Configure Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

router = APIRouter(prefix="/ai-insights", tags=["AI Insights"])

@router.post("")
async def get_ai_insights(
    request_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """
    Generate AI-powered financial insights for the user using Gemini
    """
    try:
        # 1. Parse filters
        start_date = request_data.get('start_date')
        end_date = request_data.get('end_date')
        category = request_data.get('category')
        
        # Default to current month if not provided
        if not start_date:
            start_date = datetime.now().replace(day=1)
        else:
            start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            
        if not end_date:
            end_date = datetime.now()
        else:
            end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))

        # 2. Aggregate user's transaction data
        aggregated_data = await aggregate_user_transactions(
            user_id=str(current_user["_id"]),
            start_date=start_date,
            end_date=end_date,
            category=category
        )
        
        # 3. Check if user has enough data
        if aggregated_data['total_transactions'] == 0:
            return {
                "insights": None,
                "error": "Not enough transaction data to generate insights. Add more transactions first.",
                "data_summary": aggregated_data
            }

        # 4. Generate AI insights using Gemini
        insights = await generate_ai_insights_gemini(aggregated_data)
        
        return {
            "insights": insights,
            "data_summary": aggregated_data,
            "generated_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        print(f"Error generating AI insights: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to generate insights: {str(e)}")


async def aggregate_user_transactions(
    user_id: str,
    start_date: datetime,
    end_date: datetime,
    category: Optional[str] = None
) -> dict:
    """
    Aggregate transaction data from MongoDB
    """
    # Build match filter
    match_filter = {
        "user_id": user_id,
        "date": {"$gte": start_date, "$lte": end_date}
    }
    
    if category:
        match_filter["category"] = category

    # Aggregate by category
    category_pipeline = [
        {"$match": match_filter},
        {
            "$group": {
                "_id": "$category",
                "total": {"$sum": "$amount"},
                "count": {"$sum": 1}
            }
        }
    ]
    
    category_results = await db.transactions.aggregate(category_pipeline).to_list(length=None)
    
    # Aggregate top merchants/descriptions
    merchant_pipeline = [
        {"$match": {**match_filter, "amount": {"$lt": 0}}},  # Only expenses
        {
            "$group": {
                "_id": "$description",
                "total": {"$sum": "$amount"},
                "count": {"$sum": 1}
            }
        },
        {"$sort": {"total": 1}},  # Most negative (highest spending)
        {"$limit": 5}
    ]
    
    merchant_results = await db.transactions.aggregate(merchant_pipeline).to_list(length=None)
    
    # Calculate totals
    total_income = sum(cat['total'] for cat in category_results if cat['total'] > 0)
    total_expense = abs(sum(cat['total'] for cat in category_results if cat['total'] < 0))
    total_transactions = sum(cat['count'] for cat in category_results)
    
    # Format expense by category
    expense_by_category = {
        cat['_id']: {
            "total": abs(cat['total']),
            "count": cat['count'],
            "percentage": (abs(cat['total']) / total_expense * 100) if total_expense > 0 else 0
        }
        for cat in category_results if cat['total'] < 0
    }
    
    # Format income by source
    income_by_source = {
        cat['_id']: {
            "total": cat['total'],
            "count": cat['count']
        }
        for cat in category_results if cat['total'] > 0
    }
    
    # Format top merchants
    top_merchants = {
        merchant['_id']: {
            "total": abs(merchant['total']),
            "count": merchant['count'],
            "average": abs(merchant['total'] / merchant['count'])
        }
        for merchant in merchant_results
    }
    
    # Get previous month for comparison
    prev_start = start_date - timedelta(days=30)
    prev_match = {
        "user_id": user_id,
        "date": {"$gte": prev_start, "$lt": start_date}
    }
    prev_results = await db.transactions.aggregate([
        {"$match": prev_match},
        {"$group": {"_id": None, "total_expense": {"$sum": {"$cond": [{"$lt": ["$amount", 0]}, "$amount", 0]}}}}
    ]).to_list(length=1)
    
    prev_expense = abs(prev_results[0]['total_expense']) if prev_results else 0
    
    return {
        "period": f"{start_date.strftime('%B %Y')}",
        "date_range": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat()
        },
        "total_income": total_income,
        "total_expense": total_expense,
        "cash_flow": total_income - total_expense,
        "savings_rate": (total_income - total_expense) / total_income * 100 if total_income > 0 else 0,
        "total_transactions": total_transactions,
        "expense_by_category": expense_by_category,
        "income_by_source": income_by_source,
        "top_merchants": top_merchants,
        "comparison": {
            "previous_month_expense": prev_expense,
            "change": total_expense - prev_expense,
            "change_percentage": ((total_expense - prev_expense) / prev_expense * 100) if prev_expense > 0 else 0
        }
    }


async def generate_ai_insights_gemini(aggregated_data: dict) -> dict:
    """
    Call Gemini API to generate financial insights
    """
    
    # Initialize Gemini model with system instruction
    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
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
    
    # Prepare the prompt
    prompt = f"""Analyze this financial data and provide actionable insights.

User's Financial Data for {aggregated_data['period']}:

Income & Expenses:
- Total Income: ₱{aggregated_data['total_income']:,.2f}
- Total Expenses: ₱{aggregated_data['total_expense']:,.2f}
- Net Cash Flow: ₱{aggregated_data['cash_flow']:,.2f}
- Savings Rate: {aggregated_data['savings_rate']:.1f}%
- Total Transactions: {aggregated_data['total_transactions']}

Spending by Category:
{json.dumps(aggregated_data['expense_by_category'], indent=2)}

Income Sources:
{json.dumps(aggregated_data['income_by_source'], indent=2)}

Top Spending Patterns:
{json.dumps(aggregated_data['top_merchants'], indent=2)}

Month-over-Month:
- Previous Month Expense: ₱{aggregated_data['comparison']['previous_month_expense']:,.2f}
- Change: ₱{aggregated_data['comparison']['change']:,.2f} ({aggregated_data['comparison']['change_percentage']:.1f}%)

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
    "current_savings": {aggregated_data['cash_flow']},
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
        aggregated_data['expense_by_category'].items(),
        key=lambda x: x[1]['total']
    ) if aggregated_data['expense_by_category'] else ("Unknown", {"total": 0})
    
    savings_rate = aggregated_data['savings_rate']
    
    return {
        "financial_health_score": 8 if savings_rate > 30 else 6 if savings_rate > 15 else 4,
        "score_explanation": f"Your savings rate of {savings_rate:.1f}% is {'excellent' if savings_rate > 30 else 'good' if savings_rate > 15 else 'needs improvement'}",
        "money_leaks": [
            {
                "category": highest_category[0],
                "current_spending": highest_category[1]['total'],
                "potential_savings": highest_category[1]['total'] * 0.3,
                "annual_impact": highest_category[1]['total'] * 0.3 * 12,
                "action": f"Reduce {highest_category[0]} expenses by 30%",
                "severity": "high" if highest_category[1]['total'] > 3000 else "medium"
            }
        ],
        "doing_well": [
            f"You saved ₱{aggregated_data['cash_flow']:,.2f} this period",
            "You're tracking expenses regularly"
        ],
        "action_plan": [
            {
                "title": "Review highest expense",
                "description": f"Focus on {highest_category[0]}",
                "savings": highest_category[1]['total'] * 0.2,
                "timeframe": "This month",
                "difficulty": "medium"
            }
        ],
        "priority_alert": None if savings_rate > 10 else "Savings rate below 10%",
        "monthly_goal": {
            "target_savings": aggregated_data['total_income'] * 0.3,
            "current_savings": aggregated_data['cash_flow'],
            "percentage": (aggregated_data['cash_flow'] / (aggregated_data['total_income'] * 0.3) * 100) if aggregated_data['total_income'] > 0 else 0
        },
        "insights_summary": f"You earned ₱{aggregated_data['total_income']:,.2f} and spent ₱{aggregated_data['total_expense']:,.2f}."
    }