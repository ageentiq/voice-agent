"""Analysis tool - Lead qualification and customer analysis."""

import structlog

from app.models.customer import CustomerAnalysis, LeadQuality, PurchaseGoal, PurchaseMethod
from app.services import database

logger = structlog.get_logger()

# Tool definition for Claude
ANALYSIS_TOOL = {
    "name": "analysis",
    "description": (
        "أداة تحليل وتأهيل العميل. استخدمها عند إنهاء المكالمة لتسجيل المعلومات المجمعة وتقييم جودة العميل. "
        "يجب استدعاؤها قبل إرسال رسالة الإنهاء."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "purchase_goal": {
                "type": "string",
                "enum": ["residential", "investment", "unknown"],
                "description": "هدف الشراء: سكني (residential) أو استثماري (investment) أو غير معروف (unknown)",
            },
            "purchase_method": {
                "type": "string",
                "enum": ["cash", "bank_financing", "unknown"],
                "description": "آلية الشراء: كاش (cash) أو تمويل بنكي (bank_financing) أو غير معروف (unknown)",
            },
            "rooms_or_area": {
                "type": "string",
                "description": "عدد الغرف أو المساحة المطلوبة",
            },
            "budget_range": {
                "type": "string",
                "description": "الميزانية أو النطاق السعري",
            },
            "preferences": {
                "type": "array",
                "items": {"type": "string"},
                "description": "تفضيلات العميل (قرب خدمات، واجهة، إلخ)",
            },
            "lead_quality": {
                "type": "string",
                "enum": ["hot", "warm", "cold", "not_interested"],
                "description": "تصنيف جودة العميل",
            },
            "interest_level": {
                "type": "integer",
                "minimum": 1,
                "maximum": 10,
                "description": "مستوى اهتمام العميل من 1 إلى 10",
            },
            "summary": {
                "type": "string",
                "description": "ملخص مختصر للمحادثة بالعربية",
            },
            "next_action": {
                "type": "string",
                "description": "الخطوة التالية الموصى بها",
            },
            "conversation_end_reason": {
                "type": "string",
                "description": "سبب إنهاء المكالمة",
            },
            "other_project_name": {
                "type": "string",
                "description": "اسم المشروع الآخر إذا كان العميل مهتمًا بمشروع آخر",
            },
        },
        "required": [
            "lead_quality",
            "interest_level",
            "summary",
            "conversation_end_reason",
        ],
    },
}


async def execute_analysis(
    call_id: str,
    customer_phone: str,
    customer_name: str,
    tool_input: dict,
) -> str:
    """Execute the analysis tool and save results."""
    try:
        analysis = CustomerAnalysis(
            call_id=call_id,
            customer_phone=customer_phone,
            customer_name=customer_name,
            purchase_goal=PurchaseGoal(tool_input.get("purchase_goal", "unknown")),
            purchase_method=PurchaseMethod(tool_input.get("purchase_method", "unknown")),
            rooms_or_area=tool_input.get("rooms_or_area"),
            budget_range=tool_input.get("budget_range"),
            preferences=tool_input.get("preferences", []),
            lead_quality=LeadQuality(tool_input["lead_quality"]),
            interest_level=tool_input["interest_level"],
            summary=tool_input["summary"],
            next_action=tool_input.get("next_action", ""),
            conversation_end_reason=tool_input["conversation_end_reason"],
            other_project_name=tool_input.get("other_project_name"),
        )

        await database.save_analysis(analysis)

        logger.info(
            "Analysis completed",
            call_id=call_id,
            lead_quality=analysis.lead_quality,
            interest_level=analysis.interest_level,
        )

        return f"تم حفظ تحليل العميل بنجاح. تصنيف: {analysis.lead_quality.value}, اهتمام: {analysis.interest_level}/10"

    except Exception as e:
        logger.error("Analysis tool error", error=str(e), call_id=call_id)
        return f"حدث خطأ أثناء حفظ التحليل: {str(e)}"
