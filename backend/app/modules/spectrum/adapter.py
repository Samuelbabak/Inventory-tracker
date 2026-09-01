from dataclasses import dataclass
from typing import Any, Protocol


class TransientSpectrumError(Exception):
    pass


class PermanentSpectrumError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class SpectrumResult:
    transaction_reference: str


class SpectrumAdapter(Protocol):
    def post_issue(self, payload: dict[str, Any]) -> SpectrumResult: ...

    def find_transaction(self, business_reference: str) -> SpectrumResult | None: ...

    def health(self) -> dict[str, str]: ...

    def capabilities(self) -> dict[str, bool]: ...


class FakeSpectrumAdapter:
    def post_issue(self, payload: dict[str, Any]) -> SpectrumResult:
        business_reference = payload.get("business_reference")
        if not business_reference:
            raise PermanentSpectrumError("A stable business reference is required")
        return SpectrumResult(transaction_reference=f"FAKE-{business_reference}")

    def find_transaction(self, business_reference: str) -> SpectrumResult | None:
        return SpectrumResult(transaction_reference=f"FAKE-{business_reference}")

    def health(self) -> dict[str, str]:
        return {"status": "available", "adapter": "fake"}

    def capabilities(self) -> dict[str, bool]:
        return {
            "list_items": True,
            "list_jobs": True,
            "list_cost_codes": True,
            "post_issue": True,
            "post_receipt": False,
            "post_return": False,
            "post_adjustment": False,
            "find_transaction": True,
            "reconcile": True,
        }


class DisabledSpectrumAdapter:
    def post_issue(self, payload: dict[str, Any]) -> SpectrumResult:
        del payload
        raise PermanentSpectrumError("Spectrum integration is disabled")

    def find_transaction(self, business_reference: str) -> SpectrumResult | None:
        del business_reference
        raise PermanentSpectrumError("Spectrum integration is disabled")

    def health(self) -> dict[str, str]:
        return {"status": "disabled", "adapter": "disabled"}

    def capabilities(self) -> dict[str, bool]:
        return {
            "list_items": False,
            "list_jobs": False,
            "list_cost_codes": False,
            "post_issue": False,
            "post_receipt": False,
            "post_return": False,
            "post_adjustment": False,
            "find_transaction": False,
            "reconcile": False,
        }


def create_spectrum_adapter(adapter_name: str) -> SpectrumAdapter:
    if adapter_name == "fake":
        return FakeSpectrumAdapter()
    return DisabledSpectrumAdapter()
