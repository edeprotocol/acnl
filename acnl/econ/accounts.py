"""
ACNL Econ — Energy Accounts

Energy credit accounts for compute entities.
Application layer — not core to field computation.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum
import time
import threading

from ..core.ids import EntityID


class AccountStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CLOSED = "closed"


@dataclass
class EnergyAccount:
    """Energy credit account for a compute entity."""
    account_id: str
    entity_id: EntityID
    balance_mwh: float = 0.0
    credit_limit_mwh: float = 100.0
    status: AccountStatus = AccountStatus.ACTIVE
    created_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    last_activity_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def available_credit(self) -> float:
        """Total available credit."""
        return self.balance_mwh + self.credit_limit_mwh

    def can_consume(self, mwh: float) -> bool:
        """Check if account can consume the given amount."""
        if self.status != AccountStatus.ACTIVE:
            return False
        return self.available_credit() >= mwh

    def debit(self, mwh: float) -> bool:
        """Debit the account."""
        if not self.can_consume(mwh):
            return False
        self.balance_mwh -= mwh
        self.last_activity_ms = int(time.time() * 1000)
        return True

    def credit(self, mwh: float) -> None:
        """Credit the account."""
        self.balance_mwh += mwh
        self.last_activity_ms = int(time.time() * 1000)


@dataclass
class Transaction:
    """Record of an energy transaction."""
    tx_id: str
    from_account: str
    to_account: str
    amount_mwh: float
    timestamp_ms: int
    tx_type: str
    memo: str = ""
    region_id: str = ""


class AccountLedger:
    """Thread-safe ledger for energy accounts."""

    def __init__(self):
        self._lock = threading.RLock()
        self._accounts: Dict[str, EnergyAccount] = {}
        self._by_entity: Dict[EntityID, str] = {}
        self._transactions: List[Transaction] = []
        self._tx_counter = 0

    def create_account(
        self,
        entity_id: EntityID,
        initial_balance: float = 0.0,
        credit_limit: float = 100.0,
    ) -> EnergyAccount:
        """Create a new account."""
        with self._lock:
            account_id = f"acct-{len(self._accounts)+1:06d}"
            account = EnergyAccount(
                account_id=account_id,
                entity_id=entity_id,
                balance_mwh=initial_balance,
                credit_limit_mwh=credit_limit,
            )
            self._accounts[account_id] = account
            self._by_entity[entity_id] = account_id
            return account

    def get_account(self, account_id: str) -> Optional[EnergyAccount]:
        """Get account by ID."""
        with self._lock:
            return self._accounts.get(account_id)

    def get_account_by_entity(self, entity_id: EntityID) -> Optional[EnergyAccount]:
        """Get account by entity ID."""
        with self._lock:
            account_id = self._by_entity.get(entity_id)
            if account_id:
                return self._accounts.get(account_id)
            return None

    def get_or_create_account(
        self,
        entity_id: EntityID,
        initial_balance: float = 0.0,
        credit_limit: float = 100.0,
    ) -> EnergyAccount:
        """Get existing account or create new one."""
        with self._lock:
            account = self.get_account_by_entity(entity_id)
            if account:
                return account
            return self.create_account(entity_id, initial_balance, credit_limit)

    def transfer(
        self,
        from_entity: EntityID,
        to_entity: EntityID,
        amount_mwh: float,
        tx_type: str = "transfer",
        memo: str = "",
        region_id: str = "",
    ) -> Optional[Transaction]:
        """Transfer energy credits between accounts."""
        with self._lock:
            from_account = self.get_account_by_entity(from_entity)
            to_account = self.get_account_by_entity(to_entity)

            if from_account is None or to_account is None:
                return None

            if not from_account.debit(amount_mwh):
                return None

            to_account.credit(amount_mwh)

            self._tx_counter += 1
            tx = Transaction(
                tx_id=f"tx-{self._tx_counter:08d}",
                from_account=from_account.account_id,
                to_account=to_account.account_id,
                amount_mwh=amount_mwh,
                timestamp_ms=int(time.time() * 1000),
                tx_type=tx_type,
                memo=memo,
                region_id=region_id,
            )
            self._transactions.append(tx)
            return tx

    def record_consumption(
        self,
        entity_id: EntityID,
        amount_mwh: float,
        region_id: str = "",
    ) -> Optional[Transaction]:
        """Record energy consumption."""
        with self._lock:
            account = self.get_account_by_entity(entity_id)
            if account is None:
                return None

            if not account.debit(amount_mwh):
                return None

            self._tx_counter += 1
            tx = Transaction(
                tx_id=f"tx-{self._tx_counter:08d}",
                from_account=account.account_id,
                to_account="grid",
                amount_mwh=amount_mwh,
                timestamp_ms=int(time.time() * 1000),
                tx_type="consumption",
                region_id=region_id,
            )
            self._transactions.append(tx)
            return tx

    def record_generation(
        self,
        entity_id: EntityID,
        amount_mwh: float,
        region_id: str = "",
    ) -> Optional[Transaction]:
        """Record energy generation."""
        with self._lock:
            account = self.get_or_create_account(entity_id)
            account.credit(amount_mwh)

            self._tx_counter += 1
            tx = Transaction(
                tx_id=f"tx-{self._tx_counter:08d}",
                from_account="grid",
                to_account=account.account_id,
                amount_mwh=amount_mwh,
                timestamp_ms=int(time.time() * 1000),
                tx_type="generation",
                region_id=region_id,
            )
            self._transactions.append(tx)
            return tx

    def get_balance_summary(self) -> Dict[str, float]:
        """Get summary of all account balances."""
        with self._lock:
            total_balance = sum(a.balance_mwh for a in self._accounts.values())
            active_accounts = sum(
                1 for a in self._accounts.values()
                if a.status == AccountStatus.ACTIVE
            )
            return {
                "total_accounts": len(self._accounts),
                "active_accounts": active_accounts,
                "total_balance_mwh": total_balance,
                "total_transactions": len(self._transactions),
            }
