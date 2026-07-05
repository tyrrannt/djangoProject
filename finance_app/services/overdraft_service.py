from decimal import Decimal
from datetime import date, timedelta
from typing import List, Dict, Any
from django.db.models import QuerySet
from finance_app.models import CreditAgreement, CreditTranche, CreditPaymentFact, CentralBankKeyRate

class OverdraftCalculationService:
    """
    Сервис для расчета платежей по овердрафту.
    Учитывает транши, погашения (по методу FIFO) и плавающую ставку (Ключевая ставка ЦБ + маржа).
    """

    def __init__(self, credit_agreement: CreditAgreement):
        self.agreement = credit_agreement
        self.margin = credit_agreement.interest_rate

    def is_leap_year(self, year: int) -> bool:
        return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)

    def get_days_in_year(self, year: int) -> int:
        return 366 if self.is_leap_year(year) else 365

    def calculate(self, end_date: date) -> Dict[str, Any]:
        tranches: QuerySet[CreditTranche] = self.agreement.tranches.all().order_by('date')
        payments: QuerySet[CreditPaymentFact] = self.agreement.payment_facts.all().order_by('payment_date')
        cb_rates: QuerySet[CentralBankKeyRate] = CentralBankKeyRate.objects.all().order_by('-date_from')

        if not tranches.exists():
            return {"daily_stats": [], "total_principal": Decimal('0.00'), "total_interest": Decimal('0.00')}

        start_date = tranches.first().date
        
        # State
        active_tranches = []  # list of dicts: {'id': int, 'date': date, 'principal': Decimal, 'accrued_interest': Decimal}
        tranche_idx = 0
        tranches_list = list(tranches)
        
        payment_idx = 0
        payments_list = list(payments)
        
        current_date = start_date
        daily_stats = []
        unpaid_unused_commission = Decimal('0.00')
        
        while current_date <= end_date:
            # 1. Add new tranches for the day
            while tranche_idx < len(tranches_list) and tranches_list[tranche_idx].date == current_date:
                active_tranches.append({
                    'id': tranches_list[tranche_idx].id,
                    'date': tranches_list[tranche_idx].date,
                    'maturity_date': tranches_list[tranche_idx].date + timedelta(days=self.agreement.tranche_repayment_days),
                    'principal': tranches_list[tranche_idx].amount,
                    'accrued_interest': Decimal('0.00'),
                    'is_overdue': False,
                    'days_left': self.agreement.tranche_repayment_days
                })
                tranche_idx += 1
                
            # 2. Process payments for the day
            daily_principal_payment = Decimal('0.00')
            daily_interest_payment = Decimal('0.00')
            while payment_idx < len(payments_list) and payments_list[payment_idx].payment_date == current_date:
                payment_fact = payments_list[payment_idx]
                if payment_fact.payment_type == 'interest':
                    daily_interest_payment += payment_fact.amount
                else:
                    daily_principal_payment += payment_fact.amount
                payment_idx += 1
                
            if daily_principal_payment > Decimal('0'):
                remaining_payment = daily_principal_payment
                # FIFO - погашаем старые транши
                for t in active_tranches:
                    if remaining_payment <= Decimal('0'):
                        break
                    if t['principal'] > Decimal('0'):
                        if t['principal'] >= remaining_payment:
                            t['principal'] -= remaining_payment
                            remaining_payment = Decimal('0')
                        else:
                            remaining_payment -= t['principal']
                            t['principal'] = Decimal('0')
                            
            if daily_interest_payment > Decimal('0'):
                remaining_int_payment = daily_interest_payment
                
                # Сначала погашаем накопившуюся комиссию за неиспользованный лимит
                if unpaid_unused_commission > Decimal('0'):
                    if unpaid_unused_commission >= remaining_int_payment:
                        unpaid_unused_commission -= remaining_int_payment
                        remaining_int_payment = Decimal('0')
                    else:
                        remaining_int_payment -= unpaid_unused_commission
                        unpaid_unused_commission = Decimal('0')

                # Затем FIFO - погашаем проценты старых траншей
                for t in active_tranches:
                    if remaining_int_payment <= Decimal('0'):
                        break
                    if t['accrued_interest'] > Decimal('0'):
                        if t['accrued_interest'] >= remaining_int_payment:
                            t['accrued_interest'] -= remaining_int_payment
                            remaining_int_payment = Decimal('0')
                        else:
                            remaining_int_payment -= t['accrued_interest']
                            t['accrued_interest'] = Decimal('0')
            
            # 3. Calculate Interest
            # Find applicable CB Rate
            applicable_cb_rate = Decimal('0.00')
            for rate_obj in cb_rates:
                if rate_obj.date_from <= current_date:
                    applicable_cb_rate = rate_obj.rate
                    break
                    
            total_rate_percent = applicable_cb_rate + self.margin
            days_in_year = self.get_days_in_year(current_date.year)
            
            # Расчет комиссии за неиспользованный лимит
            current_total_principal = sum(t['principal'] for t in active_tranches)
            unused_limit = max(Decimal('0.00'), self.agreement.amount - current_total_principal)
            daily_unused_commission = Decimal('0.00')
            if unused_limit > Decimal('0') and self.agreement.has_unused_limit_commission:
                rate = self.agreement.unused_limit_commission_rate
                daily_unused_commission = round(unused_limit * (rate / Decimal('100')) / Decimal(days_in_year), 6)
            
            unpaid_unused_commission += daily_unused_commission
            
            daily_stat = {
                'date': current_date,
                'total_principal': Decimal('0.00'),
                'total_daily_interest': Decimal('0.00'),
                'unused_limit': unused_limit,
                'daily_unused_commission': daily_unused_commission,
                'tranches': []
            }
            
            for t in active_tranches:
                # В високосном году делим на 366, в обычном на 365
                daily_interest = t['principal'] * (total_rate_percent / Decimal('100')) / Decimal(days_in_year)
                daily_interest = round(daily_interest, 6)
                t['accrued_interest'] += daily_interest
                
                days_left = (t['maturity_date'] - current_date).days
                t['days_left'] = days_left
                t['is_overdue'] = days_left < 0 and t['principal'] > Decimal('0')
                
                daily_stat['total_principal'] += t['principal']
                daily_stat['total_daily_interest'] += daily_interest
                daily_stat['tranches'].append({
                    'id': t['id'],
                    'principal': t['principal'],
                    'daily_interest': daily_interest,
                    'accrued_interest': t['accrued_interest']
                })
                
            daily_stats.append(daily_stat)
            current_date += timedelta(days=1)
            
        total_principal = sum(t['principal'] for t in active_tranches)
        unpaid_interest = sum(t['accrued_interest'] for t in active_tranches)
        
        # Calculate total paid interest
        total_paid_interest = sum(p.amount for p in payments_list if p.payment_type == 'interest' and p.payment_date <= end_date)
        
        # 'total_interest' в UI выводится как 'Всего начислено'. Мы будем отдавать текущий остаток, чтобы он уменьшался
        # либо можно сделать unpaid_interest + total_paid_interest, но ТЗ просит чтобы он уменьшался.
        total_interest = unpaid_interest
        
        return {
            'daily_stats': daily_stats,
            'total_principal': round(total_principal, 2),
            'total_interest': round(total_interest, 2),
            'total_paid_interest': round(total_paid_interest, 2),
            'unpaid_interest': round(unpaid_interest, 2),
            'total_unused_commission': round(unpaid_unused_commission, 2),
            'current_unused_limit': round(max(Decimal('0.00'), self.agreement.amount - total_principal), 2),
            'active_tranches': active_tranches
        }
