"""Tests for the voice agent."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.customer import LeadQuality, PurchaseGoal, PurchaseMethod
from app.tools.analysis import execute_analysis


@pytest.mark.asyncio
async def test_execute_analysis():
    """Test analysis tool execution."""
    with patch("app.tools.analysis.database") as mock_db:
        mock_db.save_analysis = AsyncMock()

        tool_input = {
            "purchase_goal": "residential",
            "purchase_method": "cash",
            "rooms_or_area": "4 غرف",
            "budget_range": "1.5 - 2 مليون ريال",
            "preferences": ["قرب من المدارس", "واجهة شمالية"],
            "lead_quality": "hot",
            "interest_level": 8,
            "summary": "عميل مهتم بشراء فيلا سكنية 4 غرف بميزانية جيدة",
            "next_action": "جدولة زيارة للمشروع",
            "conversation_end_reason": "تم جمع كل المعلومات المطلوبة",
        }

        result = await execute_analysis(
            call_id="test-123",
            customer_phone="+966500000000",
            customer_name="خالد",
            tool_input=tool_input,
        )

        assert "تم حفظ" in result
        mock_db.save_analysis.assert_called_once()

        # Verify the analysis object
        analysis = mock_db.save_analysis.call_args[0][0]
        assert analysis.purchase_goal == PurchaseGoal.RESIDENTIAL
        assert analysis.purchase_method == PurchaseMethod.CASH
        assert analysis.lead_quality == LeadQuality.HOT
        assert analysis.interest_level == 8
        assert len(analysis.preferences) == 2
