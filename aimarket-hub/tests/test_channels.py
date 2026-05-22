"""Tests for payment channels — open, close, debit, refund."""

from aimarket_hub.channels import ChannelLedger, open_channel, close_channel, debit_channel, refund_channel


class TestChannelLedger:
    def setup_method(self):
        self.ledger = ChannelLedger()

    def test_open_channel(self):
        result = self.ledger.open(3.00)
        ch = result["channel"]
        assert ch["balance_usd"] == 3.00
        assert ch["status"] == "open"
        assert ch["channel_id"].startswith("ch_")

    def test_open_channel_invalid(self):
        result = self.ledger.open(-5.0)
        assert "error" in result

    def test_close_channel(self):
        result = self.ledger.open(5.00)
        ch_id = result["channel"]["channel_id"]
        settle = self.ledger.close(ch_id, "0xtest")
        assert settle["settlement"]["refund_usd"] == 5.00
        assert settle["settlement"]["status"] == "settled"

    def test_close_unknown(self):
        result = self.ledger.close("nonexistent")
        assert "error" in result

    def test_close_already_closed(self):
        result = self.ledger.open(1.00)
        ch_id = result["channel"]["channel_id"]
        self.ledger.close(ch_id)
        result = self.ledger.close(ch_id)
        assert "error" in result

    def test_debit_channel(self):
        result = self.ledger.open(5.00)
        ch_id = result["channel"]["channel_id"]
        result = self.ledger.debit(ch_id, 2.00)
        assert result["ok"] is True
        assert result["remaining_balance"] == 3.00

    def test_debit_insufficient(self):
        result = self.ledger.open(1.00)
        ch_id = result["channel"]["channel_id"]
        result = self.ledger.debit(ch_id, 5.00)
        assert "error" in result

    def test_refund_channel(self):
        result = self.ledger.open(5.00)
        ch_id = result["channel"]["channel_id"]
        self.ledger.debit(ch_id, 3.00)
        result = self.ledger.refund(ch_id, 3.00)
        assert result["ok"] is True
        assert result["remaining_balance"] == 5.00

    def test_get_channel(self):
        self.ledger.open(5.00)
        ch = self.ledger.get("nonexistent")
        assert ch is None

    def test_open_channel_max(self):
        result = self.ledger.open(10_000)
        assert "channel" in result

    def test_open_channel_over_max(self):
        result = self.ledger.open(20_000)
        assert "error" in result


class TestModuleFunctions:
    def test_open_close_roundtrip(self):
        result = open_channel(3.00)
        ch_id = result["channel"]["channel_id"]
        settle = close_channel(ch_id)
        assert settle["settlement"]["refund_usd"] == 3.00

    def test_debit_refund_functions(self):
        result = open_channel(10.00)
        ch_id = result["channel"]["channel_id"]
        debit_channel(ch_id, 3.00)
        refund_channel(ch_id, 1.00)
        settle = close_channel(ch_id)
        assert settle["settlement"]["used_usd"] == 2.00
        assert settle["settlement"]["refund_usd"] == 8.00
