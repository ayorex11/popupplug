from functools import wraps

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login


def login_required(view):
    """Like django's login_required, but tells the visitor why they landed on the login page."""
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.warning(request, "Please log in to continue.")
            return redirect_to_login(request.get_full_path())
        return view(request, *args, **kwargs)
    return wrapper


def flag_invalid(request, form):
    """Toast for a failed form submit, so errors are noticed even below the fold."""
    if request.method == "POST" and not form.is_valid():
        messages.error(request, "Please fix the highlighted fields and try again.")
