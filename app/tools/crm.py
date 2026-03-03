"""CRM update tool for Claude."""

import structlog

from app.services import database

logger = structlog.get_logger()

# Tool definition for Claude
CRM_UPDATE_TOOL = {
    "name": "update_crm",
    "description": (
        "تحديث بيانات العميل في نظام إدارة العلاقات. استخدم هذه الأداة لحفظ معلومات جمعتها أثناء المكالمة "
        "مثل تفضيلات العميل أو ملاحظات مهمة."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "field": {
                "type": "string",
                "enum": [
                    "purchase_goal",
                    "purchase_method",
                    "rooms_or_area",
                    "budget_range",
                    "preference",
                    "note",
                ],
                "description": "نوع المعلومة المراد حفظها",
            },
            "value": {
                "type": "string",
                "description": "قيمة المعلومة",
            },
        },
        "required": ["field", "value"],
    },
}


async def execute_crm_update(
    call_id: str,
    customer_phone: str,
    field: str,
    value: str,
) -> str:
    """Execute CRM update for a customer."""
    try:
        db = database.get_db()

        # Update the call log's collected_info
        update_key = f"collected_info.{field}"
        if field == "preference":
            # Preferences are a list, push to array
            await db.call_logs.update_one(
                {"call_id": call_id},
                {"$push": {f"collected_info.preferences": value}},
            )
        else:
            await db.call_logs.update_one(
                {"call_id": call_id},
                {"$set": {update_key: value}},
            )

        logger.info(
            "CRM updated",
            call_id=call_id,
            field=field,
            value=value[:50],
        )

        return f"تم حفظ {field}: {value}"

    except Exception as e:
        logger.error("CRM update error", error=str(e), call_id=call_id)
        return f"حدث خطأ أثناء حفظ البيانات: {str(e)}"
