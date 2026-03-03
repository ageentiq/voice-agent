"""Knowledge base search tool for Claude."""

import structlog

from app.services import rag

logger = structlog.get_logger()

# Tool definition for Claude
KNOWLEDGE_BASE_TOOL = {
    "name": "search_knowledge_base",
    "description": (
        "البحث في قاعدة بيانات مشروع عين أُسُس للحصول على معلومات عن المشروع، الأسعار، المواصفات، "
        "الموقع، والخدمات المتاحة. استخدم هذه الأداة عندما يسأل العميل عن تفاصيل المشروع."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "سؤال البحث - ما الذي تريد معرفته عن المشروع",
            },
        },
        "required": ["query"],
    },
}


async def execute_search(query: str) -> str:
    """Execute knowledge base search and return formatted results."""
    try:
        results = await rag.search(query, n_results=3)

        if not results:
            return "لم يتم العثور على معلومات ذات صلة في قاعدة البيانات."

        formatted = []
        for r in results:
            score = r.get("relevance_score", 0)
            if score > 0.3:  # Only include relevant results
                formatted.append(r["text"])

        if not formatted:
            return "لم يتم العثور على معلومات ذات صلة كافية."

        return "\n---\n".join(formatted)

    except Exception as e:
        logger.error("Knowledge base search error", error=str(e))
        return "حدث خطأ أثناء البحث في قاعدة البيانات."
