from django.shortcuts import render
from django.views.decorators.http import require_GET


@require_GET
def place_demo(request):
    return render(request, 'places/demo.html')
