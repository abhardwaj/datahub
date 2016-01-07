from django.core.urlresolvers import reverse
from django.shortcuts import render_to_response, redirect, render
from django.contrib.auth import logout as django_logout, \
                                login as django_login
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.template.context import RequestContext
from account.forms import UsernameForm, \
                          RegistrationForm, \
                          LoginForm
from account.utils import provider_details, \
                          datahub_authenticate, \
                          delete_user
from django.http import HttpResponse, \
                        HttpResponseNotFound, \
                        HttpResponseNotAllowed


def login(request):
    """
    DataHub account login form.

    GET returns and HttpResponse containing the account login form.
    POST logs in name/email/password accounts.
    Other links from the page lead to Python Social Auth options (Google,
    Facebook, Twitter, etc).
    """
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username'].lower()
            password = form.cleaned_data['password']
            user = datahub_authenticate(username, password)
            if user is not None and user.is_active:
                django_login(request, user)
                return redirect('/')
            else:
                form.add_error(None, "Username and password do not match.")
        else:
            # Form isn't valid. Fall through to return it to the user with
            # errors.
            pass
    else:
        form = LoginForm()

    providers = provider_details()
    context = RequestContext(request, {
        'request': request,
        'user': request.user,
        'form': form,
        'providers': providers})
    return render_to_response('login.html', context_instance=context)


def register(request):
    """
    DataHub account registration form.

    GET returns an HttpResponse containing the account registration form.
    POST creates a name/email/password account and logs the new user in.
    Other links from the page lead to Python Social Auth options (Google,
    Facebook, Twitter, etc).
    """
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username'].lower()
            email = form.cleaned_data['email'].lower()
            password = form.cleaned_data['password']
            User.objects.create_user(username, email, password)
            # A signal handler in signals.py listens for the pre_save signal
            # and throws an IntegrityError if the user's email address is not
            # unique. Username uniqueness is handled by the model.
            #
            # In the future, another pre_save signal handler will check if a
            # DataHub database exists for the user and create one if it
            # doesn't exist. If the database cannot be created, that handler
            # will throw an exception.
            user = datahub_authenticate(username, password)
            if user is not None and user.is_active:
                django_login(request, user)
                return redirect('/')
        else:
            # Form isn't valid. Fall through and return it to the user with
            # errors.
            pass
    else:
        form = RegistrationForm()

    providers = provider_details()
    context = RequestContext(request, {
        'request': request,
        'user': request.user,
        'form': form,
        'providers': providers})
    return render_to_response('register.html', context_instance=context)


def get_user_details(request):
    """
    DataHub account registration form for social accounts.

    Gives new users a chance to choose a DataHub username and set their email
    address.

    Called by the Python Social Auth pipeline's get_user_details step. For
    more details, look for pipeline.py and the SOCIAL_AUTH_PIPELINE section
    of settings.py.
    """
    # Prepopulate the form with values provided by the identity provider.
    backend = request.session['partial_pipeline']['backend']
    try:
        details = request.session['partial_pipeline']['kwargs']['details']
    except KeyError:
        details = None
    try:
        # Include details about the social login being used,
        # e.g. "Authenticated as Facebook user Foo Bar."
        social = provider_details(backend=backend)
        social['username'] = details['username']
    except KeyError:
        social = None

    if request.method == 'POST':
        form = UsernameForm(request.POST)
        if form.is_valid():
            # Because of FIELDS_STORED_IN_SESSION, preferred_username will be
            # copied to the request dictionary when the pipeline resumes.
            d = {
                'preferred_username': form.cleaned_data['username'].lower(),
                'email': form.cleaned_data['email'].lower(),
            }
            request.session.update(d)

            # Once we have the password stashed in the session, we can
            # tell the pipeline to resume by using the "complete" endpoint
            return redirect('social:complete', backend=backend)
    else:
        form = UsernameForm(initial={'email': details['email']})

    context = RequestContext(request, {
        'form': form,
        'details': details,
        'social': social
        })

    return render(request, "username_form.html", context)


def logout(request):
    """
    Logs out the current user and clears their session data. Redirects to /.

    Doesn't throw any errors if the user isn't logged in.
    """
    django_logout(request)
    return redirect('/')


@login_required()
def settings(request):
    """
    DataHub account settings page.

    Shows the current user's username, email, and social logins, and gives
    links to change the email address, add or remove social logins, set a
    password for the account, and delete the account.
    """
    # Python Social Auth sets a `backends` context variable, which includes
    # which social backends are and are not associated with the current user.
    context = RequestContext(request)
    return render(request, 'account-settings.html', context)


@login_required()
def add_extra_login(request):
    """Enables logged in users to add more social logins to their account."""
    context = RequestContext(request, {
        'providers': provider_details(),
        })
    return render(request, 'add-login.html', context)


# Password resets are handled by the default Django account tools in
# browser/urls.py.


@login_required()
def verify_email(request):
    """
    Activates new users.

    Receives email verification link from new user email.
    """
    return HttpResponse('Not implemented yet.')


@login_required()
def delete(request):
    """
    Deletes a django user, database user, and any databases they own.

    Data from deleted databases is not saved.
    """
    if request.method == 'POST':
        username = request.user.get_username()
        try:
            delete_user(username=username, remove_db=True)
            return redirect(reverse('browser-home'))
        except User.DoesNotExist:
            return HttpResponseNotFound('User not found.')
    return HttpResponseNotAllowed(['POST'])
