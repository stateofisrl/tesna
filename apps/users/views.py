"""
User views and API endpoints.
"""

from rest_framework import viewsets, status
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.contrib.auth import get_user_model, authenticate
from django.contrib.auth import login as django_login
from django.contrib.auth import logout as django_logout
from django.contrib.auth.tokens import default_token_generator
from django.shortcuts import render, redirect
from django.http import HttpResponseNotFound, HttpResponse
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.utils import timezone
from datetime import datetime
from decimal import Decimal
from django.conf import settings
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from rest_framework.authtoken.models import Token
from .serializers import (
    UserRegistrationSerializer, UserProfileSerializer, 
    UserUpdateSerializer, UserLoginSerializer
)
from .emails import send_password_reset_email

User = get_user_model()


class UserViewSet(viewsets.ModelViewSet):
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    queryset = User.objects.all()
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'register':
            return UserRegistrationSerializer
        elif self.action in ['login', 'token_login']:
            return UserLoginSerializer
        elif self.action == 'update_profile':
            return UserUpdateSerializer
        return UserProfileSerializer
    
    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def register(self, request):
        """Register a new user."""
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            token, created = Token.objects.get_or_create(user=user)
            bonus_info = serializer.context.get('welcome_bonus_info')
            payload = {
                'message': 'Registration successful',
                'user': UserProfileSerializer(user).data,
                'token': token.key
            }
            if bonus_info:
                payload['welcome_bonus'] = bonus_info
            return Response(payload, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def login(self, request):
        """Login user."""
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            password = serializer.validated_data['password']
            
            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                return Response(
                    {'detail': 'Invalid credentials'},
                    status=status.HTTP_401_UNAUTHORIZED
                )
            
            # Authenticate using email (USERNAME_FIELD) instead of username
            user = authenticate(username=email, password=password)
            if user:
                # Create token and also log the user into the session so
                # API clients using session authentication will be able to
                # make subsequent authenticated requests without the token.
                token, created = Token.objects.get_or_create(user=user)
                # Do not create a Django session here; return token only so
                # frontend can authenticate via TokenAuth without affecting
                # the site's session cookie (prevents swapping admin session).
                return Response({
                    'message': 'Login successful',
                    'user': UserProfileSerializer(user).data,
                    'token': token.key
                }, status=status.HTTP_200_OK)
            else:
                return Response(
                    {'detail': 'Invalid credentials'},
                    status=status.HTTP_401_UNAUTHORIZED
                )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def token_login(self, request):
        """Login and return token only (do not create a Django session).

        Use this from the frontend when you want to authenticate API calls
        via TokenAuth without touching the session cookie (prevents swapping
        the admin session when testing in the same browser).
        """
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            password = serializer.validated_data['password']

            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                return Response({'detail': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)

            # Authenticate using email (USERNAME_FIELD) instead of username
            user = authenticate(username=email, password=password)
            if user:
                token, created = Token.objects.get_or_create(user=user)
                return Response({
                    'message': 'Login successful',
                    'user': UserProfileSerializer(user).data,
                    'token': token.key
                }, status=status.HTTP_200_OK)
            return Response({'detail': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def logout(self, request):
        """Logout user."""
        try:
            request.user.auth_token.delete()
        except AttributeError:
            pass
        return Response({'message': 'Logout successful'}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['put'], permission_classes=[IsAuthenticated])
    def update_profile(self, request):
        """Update current user's profile (frontend settings page)."""
        serializer = UserUpdateSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({
                'message': 'Profile updated successfully',
                'user': UserProfileSerializer(request.user).data
            }, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get', 'put'], permission_classes=[IsAuthenticated])
    def me(self, request):
        """Get or update current user profile. Refreshes from DB to ensure latest data."""
        if request.method == 'GET':
            # Refresh from database to ensure latest balance/earnings are returned
            user = User.objects.get(pk=request.user.pk)
            serializer = UserProfileSerializer(user)
            return Response(serializer.data)
        
        elif request.method == 'PUT':
            # Refresh before update to avoid stale data
            user = User.objects.get(pk=request.user.pk)
            serializer = UserUpdateSerializer(user, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                # Refresh again after save to return latest state
                user.refresh_from_db()
                return Response({
                    'message': 'Profile updated successfully',
                    'user': UserProfileSerializer(user).data
                }, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def request_password_reset(self, request):
        """Request password reset - sends email with reset link."""
        email = request.data.get('email')
        if not email:
            return Response({'detail': 'Email is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user = User.objects.get(email=email)
            # Generate token
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            
            # Build reset link
            if settings.DEBUG:
                reset_link = f"http://127.0.0.1:8001/reset-password/{uid}/{token}/"
            else:
                domain = settings.ALLOWED_HOSTS[0] if settings.ALLOWED_HOSTS and settings.ALLOWED_HOSTS[0] != '*' else 'yourdomain.com'
                reset_link = f"https://{domain}/reset-password/{uid}/{token}/"
            
            # Send email
            send_password_reset_email(user, reset_link)
            
            return Response({
                'message': 'Password reset email sent. Please check your inbox.'
            }, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            # Don't reveal if user exists or not
            return Response({
                'message': 'If an account exists with this email, you will receive a password reset link.'
            }, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def reset_password(self, request):
        """Reset password with token."""
        uid = request.data.get('uid')
        token = request.data.get('token')
        new_password = request.data.get('new_password')
        
        if not all([uid, token, new_password]):
            return Response({'detail': 'Missing required fields'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user_id = force_str(urlsafe_base64_decode(uid))
            user = User.objects.get(pk=user_id)
            
            if default_token_generator.check_token(user, token):
                user.set_password(new_password)
                user.save()
                return Response({
                    'message': 'Password has been reset successfully'
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'detail': 'Invalid or expired reset link'
                }, status=status.HTTP_400_BAD_REQUEST)
        except (User.DoesNotExist, ValueError, TypeError):
            return Response({
                'detail': 'Invalid reset link'
            }, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def dashboard(self, request):
        """Get user dashboard data."""
        user = request.user
        return Response({
            'user': UserProfileSerializer(user).data,
            'balance': str(user.balance),
            'total_invested': str(user.total_invested),
            'total_earnings': str(user.total_earnings),
        }, status=status.HTTP_200_OK)


@ensure_csrf_cookie
def dashboard_view(request):
    """Render dashboard template with real data from database."""
    if not request.user.is_authenticated:
        return redirect('login')
    
    user = request.user
    from apps.investments.models import UserInvestment
    from apps.deposits.models import Deposit
    from apps.withdrawals.models import Withdrawal
    from apps.referrals.models import CommissionTransaction
    
    # Get user data
    active_investments = UserInvestment.objects.filter(user=user, status='active')
    recent_deposits = Deposit.objects.filter(user=user).order_by('-created_at')[:3]
    recent_referral_tx = CommissionTransaction.objects.filter(user=user).order_by('-created_at')[:5]
    
    # Build unified transaction history (last 50)
    transactions = []
    # Deposits
    for d in Deposit.objects.filter(user=user).order_by('-created_at')[:100]:
        transactions.append({
            'created_at': d.created_at,
            'type': 'Deposit',
            'details': f"{d.cryptocurrency}",
            'amount': d.amount,
            'currency': d.cryptocurrency,
            'status': d.status,
        })
    # Withdrawals
    for w in Withdrawal.objects.filter(user=user).order_by('-created_at')[:100]:
        transactions.append({
            'created_at': w.created_at,
            'type': 'Withdrawal',
            'details': f"{w.cryptocurrency}",
            'amount': w.amount,
            'currency': w.cryptocurrency,
            'status': w.status,
        })
    # Investments
    for inv in UserInvestment.objects.filter(user=user).order_by('-created_at')[:100]:
        transactions.append({
            'created_at': inv.created_at,
            'type': 'Investment',
            'details': getattr(inv.plan, 'name', 'Investment'),
            'amount': inv.amount,
            'currency': 'USD',
            'status': inv.status,
        })
    # Referral commission transactions
    for tx in CommissionTransaction.objects.filter(user=user).order_by('-created_at')[:100]:
        if tx.transaction_type == 'welcome_bonus':
            status = 'Credited'
            details = 'Welcome bonus'
        else:
            status = 'Paid' if tx.transaction_type == 'commission_paid' else ('Cancelled' if tx.transaction_type == 'commission_cancelled' else 'Recorded')
            details = 'Referral commission'
        transactions.append({
            'created_at': tx.created_at,
            'type': 'Referral',
            'details': details,
            'amount': tx.amount,
            'currency': 'USD',
            'status': status,
        })
    # Sort and limit
    transactions.sort(key=lambda x: x['created_at'], reverse=True)
    transaction_history = transactions[:8]
    popup = request.session.pop('welcome_bonus_popup', None)

    # Account Summary statistics
    from django.db.models import Sum
    total_deposits = Deposit.objects.filter(user=user, status='approved').aggregate(
        total=Sum('amount')
    )['total'] or 0
    
    active_investments_count = active_investments.count()
    
    total_withdrawn = Withdrawal.objects.filter(user=user, status='completed').aggregate(
        total=Sum('amount')
    )['total'] or 0
    
    referral_earnings = CommissionTransaction.objects.filter(
        user=user, transaction_type='commission_paid'
    ).aggregate(total=Sum('amount'))['total'] or 0

    return render(request, 'dashboard.html', {
        'balance': user.balance,
        'total_invested': user.total_invested,
        'total_earnings': user.total_earnings,
        'active_investments': active_investments,
        'recent_deposits': recent_deposits,
        'recent_referral_tx': recent_referral_tx,
        'transaction_history': transaction_history,
        'welcome_bonus_popup': popup,
        'total_deposits': total_deposits,
        'active_investments_count': active_investments_count,
        'total_withdrawn': total_withdrawn,
        'referral_earnings': referral_earnings,
    })


def _build_transaction_list(user, type_filter=None, status_filter=None, start=None, end=None, limit=None):
    from apps.investments.models import UserInvestment
    from apps.deposits.models import Deposit
    from apps.withdrawals.models import Withdrawal
    from apps.referrals.models import CommissionTransaction

    records = []
    type_filter = (type_filter or 'all').lower()

    def in_range(dt):
        if start and dt < start:
            return False
        if end and dt > end:
            return False
        return True

    if type_filter in ('all', 'deposit'):
        qs = Deposit.objects.filter(user=user).order_by('-created_at')
        if limit:
            qs = qs[:limit]
        for d in qs:
            if not in_range(d.created_at):
                continue
            if status_filter and d.status.lower() != status_filter:
                continue
            records.append({
                'created_at': d.created_at,
                'type': 'Deposit',
                'details': f"{d.cryptocurrency}",
                'amount': d.amount,
                'currency': d.cryptocurrency,
                'status': d.status,
            })

    if type_filter in ('all', 'withdrawal'):
        qs = Withdrawal.objects.filter(user=user).order_by('-created_at')
        if limit:
            qs = qs[:limit]
        for w in qs:
            if not in_range(w.created_at):
                continue
            if status_filter and w.status.lower() != status_filter:
                continue
            records.append({
                'created_at': w.created_at,
                'type': 'Withdrawal',
                'details': f"{w.cryptocurrency}",
                'amount': w.amount,
                'currency': w.cryptocurrency,
                'status': w.status,
            })

    if type_filter in ('all', 'investment'):
        qs = UserInvestment.objects.filter(user=user).order_by('-created_at')
        if limit:
            qs = qs[:limit]
        for inv in qs:
            if not in_range(inv.created_at):
                continue
            if status_filter and inv.status.lower() != status_filter:
                continue
            records.append({
                'created_at': inv.created_at,
                'type': 'Investment',
                'details': getattr(inv.plan, 'name', 'Investment'),
                'amount': inv.amount,
                'currency': 'USD',
                'status': inv.status,
            })

    if type_filter in ('all', 'referral'):
        qs = CommissionTransaction.objects.filter(user=user).order_by('-created_at')
        if limit:
            qs = qs[:limit]
        for tx in qs:
            if not in_range(tx.created_at):
                continue
            if tx.transaction_type == 'welcome_bonus':
                status = 'Credited'
                details = 'Welcome bonus'
            else:
                status = 'Paid' if tx.transaction_type == 'commission_paid' else (
                    'Cancelled' if tx.transaction_type == 'commission_cancelled' else 'Recorded'
                )
                details = 'Referral commission'
            if status_filter and status.lower() != status_filter:
                continue
            records.append({
                'created_at': tx.created_at,
                'type': 'Referral',
                'details': details,
                'amount': tx.amount,
                'currency': 'USD',
                'status': status,
            })

    records.sort(key=lambda x: x['created_at'], reverse=True)
    return records


def transactions_page(request):
    if not request.user.is_authenticated:
        return redirect('login')

    # Parse filters
    type_filter = (request.GET.get('type') or 'all').lower()
    status_filter = (request.GET.get('status') or '').lower() or None
    start_str = request.GET.get('start')
    end_str = request.GET.get('end')
    page = request.GET.get('page', 1)
    page_size = min(max(int(request.GET.get('page_size', 20)), 1), 100)

    start = None
    end = None
    try:
        if start_str:
            start = timezone.make_aware(datetime.strptime(start_str, '%Y-%m-%d'))
        if end_str:
            # include full day end
            end = timezone.make_aware(datetime.strptime(end_str, '%Y-%m-%d')) + timezone.timedelta(days=1)
    except Exception:
        start = None
        end = None

    records = _build_transaction_list(request.user, type_filter, status_filter, start, end)

    paginator = Paginator(records, page_size)
    try:
        page_obj = paginator.page(page)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    return render(request, 'transactions.html', {
        'page_obj': page_obj,
        'paginator': paginator,
        'type_filter': type_filter,
        'status_filter': status_filter or '',
        'start': start_str or '',
        'end': end_str or '',
        'page_size': page_size,
    })


def transactions_export(request):
    if not request.user.is_authenticated:
        return redirect('login')

    type_filter = (request.GET.get('type') or 'all').lower()
    status_filter = (request.GET.get('status') or '').lower() or None
    start_str = request.GET.get('start')
    end_str = request.GET.get('end')

    start = None
    end = None
    try:
        if start_str:
            start = timezone.make_aware(datetime.strptime(start_str, '%Y-%m-%d'))
        if end_str:
            end = timezone.make_aware(datetime.strptime(end_str, '%Y-%m-%d')) + timezone.timedelta(days=1)
    except Exception:
        start = None
        end = None

    records = _build_transaction_list(request.user, type_filter, status_filter, start, end)

    import csv
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="transactions.csv"'
    writer = csv.writer(response)
    writer.writerow(['Date', 'Type', 'Details', 'Amount', 'Currency', 'Status'])
    for r in records:
        writer.writerow([
            timezone.localtime(r['created_at']).strftime('%Y-%m-%d %H:%M:%S'),
            r['type'],
            r['details'],
            f"{r['amount']}",
            r.get('currency', ''),
            r['status'],
        ])
    return response


@ensure_csrf_cookie
def login_page(request):
    """Render login page and handle form POST (for template-based login)."""
    if request.method == 'GET':
        if request.user.is_authenticated:
            return redirect('dashboard')
        return render(request, 'login.html')

    # POST: process form
    email = request.POST.get('email')
    password = request.POST.get('password')
    if not email or not password:
        return render(request, 'login.html', {'error': 'Please provide email and password.'})

    user = authenticate(request, username=email, password=password)
    if user is not None:
        django_login(request, user)
        return redirect('dashboard')

    return render(request, 'login.html', {'error': 'Invalid credentials.'})


@ensure_csrf_cookie
def register_page(request):
    """Render register page and handle form POST (for template-based registration)."""
    if request.method == 'GET':
        if request.user.is_authenticated:
            return redirect('dashboard')
        return render(request, 'register.html')

    # POST: process form
    email = request.POST.get('email')
    username = request.POST.get('username')
    first_name = request.POST.get('first_name')
    last_name = request.POST.get('last_name')
    password = request.POST.get('password')
    password2 = request.POST.get('password2')

    if not all([email, username, first_name, last_name, password, password2]):
        return render(request, 'register.html', {'error': 'All fields are required.'})

    if password != password2:
        return render(request, 'register.html', {'error': 'Passwords do not match.'})

    if len(password) < 8:
        return render(request, 'register.html', {'error': 'Password must be at least 8 characters.'})

    if User.objects.filter(email=email).exists():
        return render(request, 'register.html', {'error': 'Email already registered.'})

    if User.objects.filter(username=username).exists():
        return render(request, 'register.html', {'error': 'Username already taken.'})

    try:
        user = User.objects.create_user(
            email=email,
            username=email,  # Use email as username for authentication
            first_name=first_name,
            last_name=last_name,
            password=password
        )
        # Handle referral code if provided (from form or URL param)
        referral_code = request.POST.get('referral_code') or request.GET.get('ref')
        if referral_code:
            try:
                from apps.referrals.models import Referral, ReferralSettings, CommissionTransaction
                referrer = User.objects.get(referral_code=referral_code)
                # Avoid self-referral
                if referrer != user:
                    # Create referral if not already linked
                    Referral.objects.get_or_create(referrer=referrer, referred=user)
                    
                    # Apply welcome bonus if configured
                    settings = ReferralSettings.objects.first()
                    if (
                        settings
                        and settings.is_active
                        and settings.welcome_bonus_enabled
                        and settings.welcome_bonus_amount > 0
                    ):
                        bonus_amount = settings.welcome_bonus_amount
                        user.balance = Decimal(user.balance or 0) + Decimal(bonus_amount)
                        user.total_earnings = Decimal(user.total_earnings or 0) + Decimal(bonus_amount)
                        user.save(update_fields=['balance', 'total_earnings'])
                        
                        CommissionTransaction.objects.create(
                            commission=None,
                            user=user,
                            amount=bonus_amount,
                            transaction_type='welcome_bonus'
                        )
                        
                        # Mark user as received bonus
                        user.received_welcome_bonus = True
                        user.save(update_fields=['received_welcome_bonus'])
                        
                        # Store popup info for post-redirect notice
                        request.session['welcome_bonus_popup'] = {
                            'amount': str(bonus_amount),
                            'message': settings.welcome_bonus_message,
                        }

                        print(f"[REGISTRATION] Applied welcome bonus of ${bonus_amount} to {user.email}")
            except User.DoesNotExist:
                pass
        django_login(request, user)
        return redirect('dashboard')
    except Exception as e:
        return render(request, 'register.html', {'error': f'Registration failed: {str(e)}'})


def logout_view(request):
    """Log out the current session and redirect to login page."""
    try:
        # Best-effort: remove DRF token if present for this user
        if request.user.is_authenticated:
            try:
                request.user.auth_token.delete()
            except Exception:
                pass
    finally:
        django_logout(request)
    return redirect('login')


def dev_login_as(request):
    """Development helper: instantly log in as a user by email.

    Only available when DEBUG=True. Useful to verify SSR pages quickly.
    Example: /dev/login-as/?email=user@example.com
    """
    if not settings.DEBUG:
        return HttpResponseNotFound('Not available in production')
    email = request.GET.get('email', 'user@example.com')
    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return redirect('login')
    # Log in with explicit backend to create session in dev helper
    django_login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    return redirect('dashboard')


def settings_page(request):
    """Render settings page with quick links to referrals, support, profile, and logout."""
    if not request.user.is_authenticated:
        return redirect('login')
    return render(request, 'settings.html')
