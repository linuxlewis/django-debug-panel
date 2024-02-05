"""
Debug Panel middleware
"""
import threading
import time


try:
    from django.urls import reverse, resolve, Resolver404
except ImportError:
    from django.core.urlresolvers import reverse, resolve, Resolver404

from django.conf import settings
from debug_panel.cache import cache
import debug_toolbar.middleware
from debug_toolbar.toolbar import DebugToolbar

# the urls patterns that concern only the debug_panel application
import debug_panel.urls

def show_toolbar(request):
    """
    Default function to determine whether to show the toolbar on a given page.
    """
    if request.META.get('REMOTE_ADDR', None) not in settings.INTERNAL_IPS:
        return False

    return bool(settings.DEBUG)


debug_toolbar.middleware.show_toolbar = show_toolbar


class DebugPanelMiddleware(debug_toolbar.middleware.DebugToolbarMiddleware):
    """
    Middleware to set up Debug Panel on incoming request and render toolbar
    on outgoing response.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        """
        Try to match the request with an URL from debug_panel application.

        If it matches, that means we are serving a view from debug_panel,
        and we can skip the debug_toolbar middleware.

        Otherwise we fallback to the default debug_toolbar middleware.
        """

        try:
            res = resolve(request.path, urlconf=debug_panel.urls)
            return res.func(request, *res.args, **res.kwargs)
        except Resolver404:
            toolbar = None

            def handle_toolbar_created(sender, created_toolbar, **kwargs):
                nonlocal toolbar
                toolbar = created_toolbar

            DebugToolbar._created.connect(handle_toolbar_created)

            response = super().__call__(request)

            DebugToolbar._created.disconnect(handle_toolbar_created)

            if toolbar:
                # Render the toolbar again for the panel cache
                rendered = toolbar.render_toolbar()

                cache_key = "%f" % time.time()
                cache.set(cache_key, rendered)

                response['X-debug-data-url'] = request.build_absolute_uri(
                    reverse('debug_data', urlconf=debug_panel.urls, kwargs={'cache_key': cache_key}))

            return response
