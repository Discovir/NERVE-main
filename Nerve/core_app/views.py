from django.shortcuts import render


def home(request):
    return render(request, "home.html")

def dashboard(request):
    return render(request, "dashboard.html")

def enroll(request):
    return render(request, "enroll.html")

def verify(request):
    return render(request, "verify.html")
