# fx/services/payment.py
"""
Crypto payment service for subscription upgrades.

Supports:
  - USDT (ERC-20 on Ethereum)
  - BTC

Uses unique amounts (base price + small offset) to identify
which user made a payment to a single wallet address.

Verification via:
  - Etherscan API (USDT ERC-20 token transfers)
  - Blockchain.info API (BTC transactions)
"""
import asyncio
import logging
import random
import uuid
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_DOWN
from typing import Dict, Any, Optional, List, Tuple

import httpx
from sqlalchemy.orm import Session
from sqlalchemy import and_

from database.models import PaymentRequest, User
from database.repositories import UserRepository
from services.subscription import SubscriptionService
from config.settings import settings

logger = logging.getLogger(__name__)


# Configuration
class PaymentConfig:
    """Payment system configuration — set via environment variables"""
    
    # Wallet addresses
    USDT_WALLET: str = getattr(settings, 'USDT_WALLET_ADDRESS', '')
    BTC_WALLET: str = getattr(settings, 'BTC_WALLET_ADDRESS', '')
    
    # API keys for blockchain explorers
    ETHERSCAN_API_KEY: str = getattr(settings, 'ETHERSCAN_API_KEY', '')
    
    # USDT ERC-20 contract address (mainnet)
    USDT_CONTRACT: str = '0xdAC17F958D2ee523a2206206994597C13D831ec7'
    
    # Payment settings
    PAYMENT_EXPIRY_HOURS: int = 2  # How long a payment request stays valid
    UNIQUE_OFFSET_MIN: int = 1    # Minimum cents offset
    UNIQUE_OFFSET_MAX: int = 99   # Maximum cents offset
    MIN_CONFIRMATIONS_ETH: int = 12
    MIN_CONFIRMATIONS_BTC: int = 3
    
    # Polling
    POLL_INTERVAL_SECONDS: int = 60
    
    # Amount matching tolerance (to handle network fees eating into amount)
    AMOUNT_TOLERANCE: Decimal = Decimal('0.005')  # 0.5 cent tolerance


# Payment Service
class PaymentService:
    """Creates and manages crypto payment requests"""
    
    def __init__(self, db_session: Session):
        self.db = db_session
        self.user_repo = UserRepository(db_session)
        self.sub_service = SubscriptionService(db_session)
        self.config = PaymentConfig()
    
    def create_payment_request(
        self,
        user_id: int,
        plan_tier: str,
        billing_period: str = 'monthly',
        currency: str = 'USDT'
    ) -> Dict[str, Any]:
        """
        Create a pending payment request with a unique amount.
        
        The unique amount = base plan price + random cents offset.
        This offset identifies the payment when it arrives at the wallet.
        """
        user = self.user_repo.get_by_telegram_id(user_id)
        if not user:
            raise ValueError("User not found")
        
        plan = self.sub_service.get_plan(plan_tier)
        if not plan:
            raise ValueError(f"Plan '{plan_tier}' not found")
        
        # Cancel any existing pending requests for this user
        self._cancel_pending(user.id)
        
        # Get base price
        if billing_period == 'yearly':
            base_amount = Decimal(str(plan.price_yearly))
        else:
            base_amount = Decimal(str(plan.price_monthly))
        
        if base_amount <= 0:
            raise ValueError("Cannot create payment for free plan")
        
        # Generate unique amount
        unique_amount = self._generate_unique_amount(base_amount, currency)
        
        # Get wallet address and network
        if currency.upper() in ('USDT', 'USDC'):
            wallet = self.config.USDT_WALLET
            network = 'ERC20'
        elif currency.upper() == 'BTC':
            wallet = self.config.BTC_WALLET
            network = 'BTC'
        else:
            raise ValueError(f"Unsupported currency: {currency}")
        
        if not wallet:
            raise ValueError(f"No wallet configured for {currency}")
        
        # Create payment request
        payment = PaymentRequest(
            uuid=str(uuid.uuid4()),
            user_id=user.id,
            plan_tier=plan_tier,
            billing_period=billing_period,
            base_amount=base_amount,
            unique_amount=unique_amount,
            currency=currency.upper(),
            wallet_address=wallet,
            network=network,
            status='pending',
            expires_at=datetime.utcnow() + timedelta(hours=self.config.PAYMENT_EXPIRY_HOURS)
        )
        
        self.db.add(payment)
        self.db.commit()
        
        logger.info(
            f"Payment request created: user={user_id}, plan={plan_tier}, "
            f"amount={unique_amount} {currency}, expires={payment.expires_at}"
        )
        
        return {
            'payment_id': payment.uuid,
            'amount': str(unique_amount),
            'currency': currency.upper(),
            'wallet_address': wallet,
            'network': network,
            'plan': plan_tier,
            'billing_period': billing_period,
            'expires_at': payment.expires_at.isoformat(),
            'expires_in_minutes': self.config.PAYMENT_EXPIRY_HOURS * 60
        }
    
    def _generate_unique_amount(self, base_amount: Decimal, currency: str) -> Decimal:
        """
        Generate a unique amount by adding a random cents offset.
        Ensures no other pending payment has the same amount.
        """
        max_attempts = 50
        
        for _ in range(max_attempts):
            # Random offset between 1 and 99 cents
            offset_cents = random.randint(
                self.config.UNIQUE_OFFSET_MIN,
                self.config.UNIQUE_OFFSET_MAX
            )
            
            if currency.upper() == 'BTC':
                # For BTC, use satoshi-level offset (0.00000001 - 0.00000099)
                offset = Decimal(str(offset_cents)) / Decimal('100000000')
            else:
                # For USDT/USDC, use cent-level offset
                offset = Decimal(str(offset_cents)) / Decimal('100')
            
            unique_amount = (base_amount + offset).quantize(
                Decimal('0.0001') if currency.upper() == 'BTC' else Decimal('0.01'),
                rounding=ROUND_DOWN
            )
            
            # Check no other pending payment has this exact amount
            existing = self.db.query(PaymentRequest).filter(
                and_(
                    PaymentRequest.unique_amount == unique_amount,
                    PaymentRequest.currency == currency.upper(),
                    PaymentRequest.status == 'pending',
                    PaymentRequest.expires_at > datetime.utcnow()
                )
            ).first()
            
            if not existing:
                return unique_amount
        
        # Fallback: use timestamp-based offset
        ts_offset = Decimal(str(int(datetime.utcnow().timestamp()) % 100)) / Decimal('100')
        return base_amount + ts_offset
    
    def _cancel_pending(self, user_id_db: int):
        """Cancel all pending payment requests for a user"""
        pending = self.db.query(PaymentRequest).filter(
            and_(
                PaymentRequest.user_id == user_id_db,
                PaymentRequest.status == 'pending'
            )
        ).all()
        
        for p in pending:
            p.status = 'cancelled'
        
        if pending:
            self.db.commit()
            logger.info(f"Cancelled {len(pending)} pending payments for user_id={user_id_db}")
    
    def get_pending_payment(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user's current pending payment, if any"""
        user = self.user_repo.get_by_telegram_id(user_id)
        if not user:
            return None
        
        payment = self.db.query(PaymentRequest).filter(
            and_(
                PaymentRequest.user_id == user.id,
                PaymentRequest.status == 'pending',
                PaymentRequest.expires_at > datetime.utcnow()
            )
        ).first()
        
        if not payment:
            return None
        
        return {
            'payment_id': payment.uuid,
            'amount': str(payment.unique_amount),
            'currency': payment.currency,
            'wallet_address': payment.wallet_address,
            'network': payment.network,
            'plan': payment.plan_tier,
            'billing_period': payment.billing_period,
            'expires_at': payment.expires_at.isoformat(),
            'minutes_left': max(0, int((payment.expires_at - datetime.utcnow()).total_seconds() / 60))
        }
    
    def expire_stale_payments(self) -> int:
        """Mark expired pending payments as expired"""
        expired = self.db.query(PaymentRequest).filter(
            and_(
                PaymentRequest.status == 'pending',
                PaymentRequest.expires_at < datetime.utcnow()
            )
        ).all()
        
        for p in expired:
            p.status = 'expired'
        
        if expired:
            self.db.commit()
        
        return len(expired)



# Blockchain Watcher
class BlockchainWatcher:
    """
    Polls blockchain APIs to detect incoming payments.
    Matches transactions to pending PaymentRequests by unique amount.
    """
    
    def __init__(self, db_session: Session, notification_service=None):
        self.db = db_session
        self.notification = notification_service
        self.sub_service = SubscriptionService(db_session)
        self.config = PaymentConfig()
        self.http_client: Optional[httpx.AsyncClient] = None
        
        # Track last checked block/timestamp to avoid re-scanning
        self._last_eth_block: Optional[int] = None
        self._last_btc_timestamp: Optional[int] = None
    
    async def start(self):
        """Start the HTTP client"""
        self.http_client = httpx.AsyncClient(timeout=30.0)
    
    async def stop(self):
        """Stop the HTTP client"""
        if self.http_client:
            await self.http_client.aclose()
    
    async def check_payments(self):
        """
        Main polling method — called by background task.
        Checks for new transactions matching pending payments.
        """
        if not self.http_client:
            await self.start()
        
        # Expire stale payments first
        payment_service = PaymentService(self.db)
        expired_count = payment_service.expire_stale_payments()
        if expired_count > 0:
            logger.info(f"Expired {expired_count} stale payment requests")
        
        # Get all pending payments
        pending = self.db.query(PaymentRequest).filter(
            and_(
                PaymentRequest.status == 'pending',
                PaymentRequest.expires_at > datetime.utcnow()
            )
        ).all()
        
        if not pending:
            return
        
        # Group by currency
        usdt_pending = [p for p in pending if p.currency == 'USDT']
        btc_pending = [p for p in pending if p.currency == 'BTC']
        
        if usdt_pending and self.config.USDT_WALLET:
            await self._check_usdt_payments(usdt_pending)
        
        if btc_pending and self.config.BTC_WALLET:
            await self._check_btc_payments(btc_pending)
    
    # ==================== USDT (ERC-20) ====================
    
    async def _check_usdt_payments(self, pending: List[PaymentRequest]):
        """Check Etherscan for USDT transfers to our wallet"""
        if not self.config.ETHERSCAN_API_KEY:
            logger.warning("Etherscan API key not configured, skipping USDT check")
            return
        
        try:
            # Get recent ERC-20 token transfers to our wallet
            params = {
                'module': 'account',
                'action': 'tokentx',
                'contractaddress': self.config.USDT_CONTRACT,
                'address': self.config.USDT_WALLET,
                'page': 1,
                'offset': 50,  # Last 50 transfers
                'sort': 'desc',
                'apikey': self.config.ETHERSCAN_API_KEY
            }
            
            response = await self.http_client.get(
                'https://api.etherscan.io/api',
                params=params
            )
            data = response.json()
            
            if data.get('status') != '1' or not data.get('result'):
                return
            
            transactions = data['result']
            
            for tx in transactions:
                # Only incoming transfers (to our wallet)
                if tx['to'].lower() != self.config.USDT_WALLET.lower():
                    continue
                
                # USDT has 6 decimals
                amount = Decimal(tx['value']) / Decimal('1000000')
                tx_hash = tx['hash']
                confirmations = int(tx.get('confirmations', 0))
                block_number = int(tx.get('blockNumber', 0))
                
                # Match against pending payments
                await self._match_payment(
                    pending, amount, tx_hash, confirmations,
                    block_number, self.config.MIN_CONFIRMATIONS_ETH
                )
                
        except Exception as e:
            logger.error(f"Etherscan API error: {e}")
    
    # ==================== BTC ====================
    
    async def _check_btc_payments(self, pending: List[PaymentRequest]):
        """Check Blockchain.info for BTC payments to our wallet"""
        try:
            response = await self.http_client.get(
                f'https://blockchain.info/rawaddr/{self.config.BTC_WALLET}',
                params={'limit': 20}
            )
            data = response.json()
            
            transactions = data.get('txs', [])
            
            for tx in transactions:
                tx_hash = tx['hash']
                block_height = tx.get('block_height')
                latest_block = data.get('latest_block', {}).get('height', 0)
                
                if block_height:
                    confirmations = latest_block - block_height + 1
                else:
                    confirmations = 0
                
                # Sum outputs to our address
                total_received = Decimal('0')
                for output in tx.get('out', []):
                    if output.get('addr') == self.config.BTC_WALLET:
                        # BTC amount is in satoshis
                        total_received += Decimal(str(output['value'])) / Decimal('100000000')
                
                if total_received > 0:
                    await self._match_payment(
                        pending, total_received, tx_hash, confirmations,
                        block_height or 0, self.config.MIN_CONFIRMATIONS_BTC
                    )
                    
        except Exception as e:
            logger.error(f"Blockchain.info API error: {e}")
    
    # ==================== Payment Matching ====================
    
    async def _match_payment(
        self,
        pending: List[PaymentRequest],
        amount: Decimal,
        tx_hash: str,
        confirmations: int,
        block_number: int,
        min_confirmations: int
    ):
        """Match a blockchain transaction to a pending payment request"""
        
        # Check if this TX was already processed
        existing = self.db.query(PaymentRequest).filter(
            PaymentRequest.tx_hash == tx_hash
        ).first()
        if existing:
            # Update confirmations if already matched
            if existing.status == 'confirmed' and confirmations >= min_confirmations:
                await self._activate_payment(existing)
            elif existing.confirmations != confirmations:
                existing.confirmations = confirmations
                self.db.commit()
            return
        
        # Find matching pending payment by amount (within tolerance)
        tolerance = self.config.AMOUNT_TOLERANCE
        
        for payment in pending:
            expected = Decimal(str(payment.unique_amount))
            
            if abs(amount - expected) <= tolerance:
                # Match found
                logger.info(
                    f"Payment matched: tx={tx_hash[:16]}..., "
                    f"amount={amount}, expected={expected}, "
                    f"user_id={payment.user_id}, plan={payment.plan_tier}"
                )
                
                payment.tx_hash = tx_hash
                payment.confirmed_amount = amount
                payment.confirmations = confirmations
                payment.block_number = block_number
                payment.confirmed_at = datetime.utcnow()
                
                if confirmations >= min_confirmations:
                    await self._activate_payment(payment)
                else:
                    payment.status = 'confirmed'
                    self.db.commit()
                    
                    # Notify user that payment is seen but awaiting confirmations
                    if self.notification:
                        user = self.db.query(User).filter(User.id == payment.user_id).first()
                        if user:
                            await self.notification.send_telegram(
                                user.telegram_id,
                                f"⏳ *Payment Detected*\n\n"
                                f"We see your payment of {amount} {payment.currency}.\n"
                                f"Waiting for {min_confirmations} confirmations "
                                f"({confirmations} so far).\n\n"
                                f"Your {payment.plan_tier.title()} plan will activate automatically."
                            )
                
                return  # Only match one payment per TX
    
    async def _activate_payment(self, payment: PaymentRequest):
        """Activate subscription after payment is fully confirmed"""
        if payment.status == 'activated':
            return
        
        payment.status = 'activated'
        payment.activated_at = datetime.utcnow()
        
        # Get user
        user = self.db.query(User).filter(User.id == payment.user_id).first()
        if not user:
            logger.error(f"Cannot activate payment {payment.uuid}: user not found")
            return
        
        # Upgrade subscription
        try:
            result = self.sub_service.upgrade_user(
                user_id=user.telegram_id,
                plan_tier=payment.plan_tier,
                billing_period=payment.billing_period,
                payment_method='crypto',
                payment_id=payment.uuid,
                tx_hash=payment.tx_hash or ''
            )
            
            self.db.commit()
            
            logger.info(
                f"Subscription activated: user={user.telegram_id}, "
                f"plan={payment.plan_tier}, tx={payment.tx_hash}"
            )
            
            # Notify user
            if self.notification:
                duration = '1 year' if payment.billing_period == 'yearly' else '30 days'
                await self.notification.send_telegram(
                    user.telegram_id,
                    f"✅ *Payment Confirmed — {payment.plan_tier.title()} Plan Activated!*\n\n"
                    f"💰 Amount: {payment.confirmed_amount} {payment.currency}\n"
                    f"📅 Duration: {duration}\n"
                    f"⏰ Expires: {result['expiry'][:10]}\n\n"
                    f"🔗 TX: `{payment.tx_hash[:20]}...`\n\n"
                    f"Enjoy your upgraded features! Use /help to see what's available."
                )
                
        except Exception as e:
            logger.error(f"Failed to activate subscription for payment {payment.uuid}: {e}")
            payment.status = 'failed'
            self.db.commit()
