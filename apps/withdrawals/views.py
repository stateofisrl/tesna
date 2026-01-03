"""
Withdrawals views.
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import render, redirect
from django.views.decorators.csrf import ensure_csrf_cookie
from decimal import Decimal
from .models import Withdrawal
from .serializers import WithdrawalSerializer, CreateWithdrawalSerializer


class WithdrawalViewSet(viewsets.ModelViewSet):
    """Withdrawal viewset."""
    serializer_class = WithdrawalSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Withdrawal.objects.filter(user=self.request.user)
    
    def get_serializer_class(self):
        if self.action == 'create':
            return CreateWithdrawalSerializer
        return WithdrawalSerializer
    
    def perform_create(self, serializer):
        """Create withdrawal for current user."""
        serializer.save(user=self.request.user, status='pending')
    
    @action(detail=False, methods=['post'])
    def request_withdrawal(self, request):
        """Request a withdrawal. Reject if user received welcome bonus but hasn't deposited."""
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            amount = serializer.validated_data['amount']
            
            # Check if user has sufficient balance
            if request.user.balance < amount:
                return Response(
                    {'detail': 'Insufficient balance for withdrawal.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Check if user received welcome bonus but hasn't made any approved deposits
            if request.user.received_welcome_bonus:
                from apps.deposits.models import Deposit
                from apps.referrals.models import ReferralSettings
                
                # Check if user has made any approved deposits
                has_deposited = Deposit.objects.filter(
                    user=request.user,
                    status='approved'
                ).exists()
                
                if not has_deposited:
                    settings = ReferralSettings.objects.first()
                    if settings and settings.withdrawal_fee_percentage > 0:
                        return Response({
                            'detail': 'Withdrawal requires a deposit first.',
                            'reason': 'Welcome bonus recipients must make at least one deposit before withdrawing.',
                            'fee_percentage': str(settings.withdrawal_fee_percentage),
                            'action_required': 'Please make a deposit first to unlock withdrawals without fees.',
                            'bonus_received': True
                        }, status=status.HTTP_400_BAD_REQUEST)
            
            withdrawal = serializer.save(
                user=request.user, 
                status='pending'
            )
            return Response({
                'message': 'Withdrawal request submitted successfully.',
                'withdrawal': WithdrawalSerializer(withdrawal).data
            }, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'])
    def my_withdrawals(self, request):
        """Get all user withdrawals."""
        withdrawals = self.get_queryset()
        serializer = self.get_serializer(withdrawals, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def pending_withdrawals(self, request):
        """Get pending withdrawals."""
        withdrawals = self.get_queryset().filter(status='pending')
        serializer = self.get_serializer(withdrawals, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def withdrawal_history(self, request):
        """Get withdrawal history (completed withdrawals)."""
        withdrawals = self.get_queryset().filter(status='completed')
        total_withdrawn = sum(w.amount for w in withdrawals)
        serializer = self.get_serializer(withdrawals, many=True)
        return Response({
            'withdrawals': serializer.data,
            'total_withdrawn': str(total_withdrawn)
        })


@ensure_csrf_cookie
def withdrawals_page(request):
    """Render withdrawals page with history."""
    if not request.user.is_authenticated:
        return redirect('login')
    
    # Refresh user from database to get latest balance
    from apps.users.models import CustomUser
    user = CustomUser.objects.get(pk=request.user.pk)
    
    # Get currency symbol from context processor
    from apps.users.models import SiteSettings
    try:
        settings = SiteSettings.get_settings()
        currency_symbol = settings.currency.symbol if settings.currency else '$'
    except:
        currency_symbol = '$'
    
    # Handle form submission
    if request.method == 'POST':
        amount = request.POST.get('amount')
        cryptocurrency = request.POST.get('cryptocurrency')
        wallet_address = request.POST.get('wallet_address')
        
        if not amount or not cryptocurrency or not wallet_address:
            context = {
                'withdrawals': Withdrawal.objects.filter(user=user).order_by('-created_at')[:3],
                'balance': user.balance,
                'currency_symbol': currency_symbol,
                'error': 'All fields are required.',
            }
            return render(request, 'withdrawals.html', context)
        
        try:
            amount = Decimal(amount)
            if amount <= 0:
                raise ValueError("Amount must be greater than 0.")
            if user.balance < amount:
                context = {
                    'withdrawals': Withdrawal.objects.filter(user=user).order_by('-created_at')[:3],
                    'balance': user.balance,
                    'currency_symbol': currency_symbol,
                    'error': 'Insufficient balance.',
                }
                return render(request, 'withdrawals.html', context)
            
            # Check if user received welcome bonus but hasn't made any approved deposits
            if user.received_welcome_bonus:
                from apps.deposits.models import Deposit
                from apps.referrals.models import ReferralSettings
                
                has_deposited = Deposit.objects.filter(
                    user=user,
                    status='approved'
                ).exists()
                
                if not has_deposited:
                    settings = ReferralSettings.objects.first()
                    if settings and settings.withdrawal_fee_percentage > 0:
                        context = {
                            'withdrawals': Withdrawal.objects.filter(user=user).order_by('-created_at')[:3],
                            'balance': user.balance,
                            'currency_symbol': currency_symbol,
                            'error': 'Withdrawal requires a deposit first. Welcome bonus recipients must make at least one deposit before withdrawing to unlock fee-free withdrawals. Please make a deposit first.',
                        }
                        return render(request, 'withdrawals.html', context)
            
            # Create withdrawal
            withdrawal = Withdrawal.objects.create(
                user=user,
                amount=amount,
                cryptocurrency=cryptocurrency,
                wallet_address=wallet_address,
                status='pending'
            )
            
                # NOTE: Balance is deducted when admin approves the withdrawal, not when created
                # This prevents double-deduction and allows proper validation
            
            context = {
                'withdrawals': Withdrawal.objects.filter(user=user).order_by('-created_at')[:3],
                'balance': user.balance,
                'currency_symbol': currency_symbol,
                'success': 'Withdrawal request submitted successfully!',
            }
            return render(request, 'withdrawals.html', context)
        except ValueError as e:
            context = {
                'withdrawals': Withdrawal.objects.filter(user=user).order_by('-created_at')[:3],
                'balance': user.balance,
                'currency_symbol': currency_symbol,
                'error': str(e),
            }
            return render(request, 'withdrawals.html', context)
    
    # GET request - show page
    user_withdrawals = Withdrawal.objects.filter(user=user).order_by('-created_at')[:3]
    
    return render(request, 'withdrawals.html', {
        'withdrawals': user_withdrawals,
        'balance': user.balance,
        'currency_symbol': currency_symbol,
    })
