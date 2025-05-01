from django.shortcuts import render, redirect
from .models import Donor, BloodRequest, CustomUser, Donation, DonorDonation
from appointment.models import Appointment  # Add this import
from .forms import CustomUserRegistrationForm, CustomLoginForm, PasswordResetSecurityForm, BloodRequestForm
from django.contrib.auth.hashers import make_password
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.db.models import Sum, Count
from datetime import datetime


def home(request):
    return render(request, 'home.html')

def show_donors(request):
    donors = Donor.objects.all()
    return render(request, 'donors.html', {'donors': donors})

def register_view(request):
    if request.method == 'POST':
        form = CustomUserRegistrationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Registration successful. Please login.")
            return redirect('login')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = CustomUserRegistrationForm()
    return render(request, 'register.html', {'form': form})

def user_login(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid credentials')
    return render(request, 'login.html')

def login_view(request):
    if request.method == 'POST':
        form = CustomLoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            # Remember me: set session expiry
            if not form.cleaned_data.get('remember_me'):
                request.session.set_expiry(0)
            messages.success(request, "You are now logged in.")
            return redirect('home')  # Replace with your desired redirect
        else:
            messages.error(request, "Invalid username or password.")
    else:
        form = CustomLoginForm()
    return render(request, 'login.html', {'form': form})


@login_required
def dashboard(request):
    # Get all donations for charts (this will be same for both admin and users)
    all_donations = Donation.objects.all()
    blood_data = get_blood_type_stats(all_donations)

    if request.user.is_superuser:
        context = {
            'total_donations': all_donations.count(),
            'pending_requests': BloodRequest.objects.filter(status='pending').count(),
            'available_units': all_donations.filter(status='available').count(),
            'total_appointments': Appointment.objects.all().count(),
        }
    else:
        # Get user-specific donations for personal stats
        user_donations = DonorDonation.objects.filter(donor__user=request.user)
        user_appointments = Appointment.objects.filter(user=request.user)
        
        context = {
            'total_donations': user_donations.count(),
            'pending_requests': BloodRequest.objects.filter(
                contact_name=request.user.get_full_name(), 
                status='pending'
            ).count(),
            'available_units': user_donations.filter(status='available').count(),
            'total_appointments': user_appointments.count(),
            'appointments_stats': {
                'pending': user_appointments.filter(status='pending').count(),
                'confirmed': user_appointments.filter(status='confirmed').count(),
                'cancelled': user_appointments.filter(status='cancelled').count()
            },
        }

    # Add chart data and titles that indicate these are overall statistics
    context.update({
        'blood_data': blood_data,
        'total_system_donations': all_donations.count(),
    })
    
    return render(request, 'dashboard.html', context)

def get_blood_type_stats(donations):
    blood_groups = ['A+', 'A-', 'B+', 'B-', 'O+', 'O-', 'AB+', 'AB-']
    return [donations.filter(blood_group=group).count() for group in blood_groups]


def user_logout(request):
    logout(request)
    return redirect('login')

def reset_password(request):
    if request.method == 'POST':
        form = PasswordResetSecurityForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            security_answer = form.cleaned_data['security_answer']
            password1 = form.cleaned_data['new_password1']
            password2 = form.cleaned_data['new_password2']

            try:
                user = CustomUser.objects.get(username=username)
            except CustomUser.DoesNotExist:
                messages.error(request, "User does not exist.")
                return redirect('reset_password')

            if user.security_answer.strip().lower() != security_answer.strip().lower():
                messages.error(request, "Security answer is incorrect.")
                return redirect('reset_password')

            if password1 != password2:
                messages.error(request, "Passwords do not match.")
                return redirect('reset_password')

            user.password = make_password(password1)
            user.save()
            messages.success(request, "Password reset successful! You can now log in.")
            return redirect('login')
    else:
        form = PasswordResetSecurityForm()

    return render(request, 'reset_password.html', {'form': form})


@login_required
def donate_view(request):
    if request.method == 'POST':
        try:
            # Get or create donor record
            donor, created = Donor.objects.get_or_create(
                user=request.user,
                defaults={
                    'blood_group': request.user.blood_group,
                    'city': request.user.city,
                    'phone': request.user.phone
                }
            )

            # Check last donation date
            last_donation_date = request.POST.get('last_donation')
            if last_donation_date:
                last_date = datetime.strptime(last_donation_date, '%Y-%m-%d').date()
                days_since_last = (datetime.now().date() - last_date).days
                if days_since_last < 56:
                    messages.error(request, f'You must wait 56 days between donations. {56-days_since_last} days remaining.')
                    return redirect('donate')

            # Create donation record
            donation = DonorDonation.objects.create(
                donor=donor,
                blood_group=request.POST.get('blood_group'),
                amount_ml=request.POST.get('amount_ml'),
                medical_conditions=request.POST.get('medical_conditions', ''),
                last_donation_date=last_donation_date if last_donation_date else None,
                status='pending'
            )

            messages.success(request, 'Thank you for your donation request! Our team will review your submission.')
            return redirect('dashboard')

        except Exception as e:
            messages.error(request, f'Error processing donation: {str(e)}')
            return redirect('donate')

    return render(request, 'donate.html')


def request_blood(request):
    if request.method == 'POST':
        form = BloodRequestForm(request.POST)
        if form.is_valid():
            blood_request = form.save(commit=False)
            blood_request.save()
            messages.success(request, "Blood request submitted successfully.")
            return redirect('dashboard')
        else:
            messages.error(request, "There were errors in your form. Please check and try again.")
    else:
        form = BloodRequestForm()
    
    # Remove recipient-based filtering since it's no longer available
    user_requests = BloodRequest.objects.order_by('-created_at')[:5]

    return render(request, 'request_blood.html', {
        'form': form,
        'user_requests': user_requests
    })

@login_required
def profile_view(request):
    if request.method == 'POST':
        user = request.user
        try:
            # Update basic information
            user.first_name = request.POST.get('first_name', '')
            user.last_name = request.POST.get('last_name', '')
            user.email = request.POST.get('email', '')
            user.phone = request.POST.get('phone', '')
            user.blood_group = request.POST.get('blood_group', '')
            user.city = request.POST.get('city', '')
            
            user.save()
            messages.success(request, 'Profile updated successfully!')
        except Exception as e:
            messages.error(request, f'Error updating profile: {str(e)}')
        return redirect('profile')

    # Get user's donation history
    donations = Donation.objects.filter(donor=request.user).order_by('-date')
    return render(request, 'profile.html', {
        'donations': donations,
        'user': request.user
    })

@login_required
def request_history(request):
    context = {}
    
    # Only check for superuser status
    if request.user.is_superuser:
        # Superuser sees all requests
        blood_requests = BloodRequest.objects.all()
    else:
        # Regular users see their own requests
        blood_requests = BloodRequest.objects.filter(contact_name=request.user.get_full_name())
    
    # Order by most recent first
    blood_requests = blood_requests.order_by('-created_at')
    
    context.update({
        'requests': blood_requests,
        'pending_count': blood_requests.filter(status='pending').count(),
        'total_count': blood_requests.count(),
        'is_admin': request.user.is_superuser  # Use superuser status instead of role
    })
    
    return render(request, 'request_history.html', context)

def is_superuser(user):
    return user.is_superuser

@user_passes_test(is_superuser)
def admin_donations(request):
    donations = DonorDonation.objects.all().order_by('-donation_date')  # Changed from date to donation_date
    context = {
        'donations': donations,
        'total_donations': donations.count(),
        'pending_donations': donations.filter(status='pending').count(),
        'approved_donations': donations.filter(status='approved').count()
    }
    return render(request, 'admin_donations.html', context)

@user_passes_test(is_superuser)
def admin_requests(request):
    requests = BloodRequest.objects.all().order_by('-created_at')
    context = {
        'requests': requests,
        'total_requests': requests.count(),
        'pending_requests': requests.filter(status='pending').count(),
        'urgent_requests': requests.filter(urgency__in=['high', 'critical']).count()
    }
    return render(request, 'admin_requests.html', context)

@user_passes_test(is_superuser)
def update_donation_status(request, donation_id, status):
    if request.method == 'POST':
        donation = get_object_or_404(DonorDonation, id=donation_id)
        if status in ['approved', 'rejected']:
            donation.status = status
            donation.save()
            return JsonResponse({'success': True})
    return JsonResponse({'success': False})

@user_passes_test(is_superuser)
def update_request_status(request, request_id, status):
    if request.method == 'POST':
        blood_request = get_object_or_404(BloodRequest, id=request_id)
        if status in ['approved', 'rejected']:
            blood_request.status = status
            blood_request.save()
            return JsonResponse({'success': True})
    return JsonResponse({'success': False})
