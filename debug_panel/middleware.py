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
from debug_toolbar.utils import clear_stack_trace_caches

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
            # Decide whether the toolbar is active for this request.
            if not show_toolbar(request) or DebugToolbar.is_toolbar_request(request):
                return self.get_response(request)

            toolbar = DebugToolbar(request, self.get_response)

            # Activate instrumentation ie. monkey-patch.
            for panel in toolbar.enabled_panels:
                panel.enable_instrumentation()
            try:
                # Run panels like Django middleware.
                response = toolbar.process_request(request)
            finally:
                clear_stack_trace_caches()
                # Deactivate instrumentation ie. monkey-unpatch. This must run
                # regardless of the response. Keep 'return' clauses below.
                for panel in reversed(toolbar.enabled_panels):
                    panel.disable_instrumentation()

            # Generate the stats for all requests when the toolbar is being shown,
            # but not necessarily inserted.
            for panel in reversed(toolbar.enabled_panels):
                panel.generate_stats(request, response)
                panel.generate_server_timing(request, response)

            # Always render the toolbar for the history panel, even if it is not
            # included in the response.
            rendered = toolbar.render_toolbar()

            for header, value in self.get_headers(request, toolbar.enabled_panels).items():
                response.headers[header] = value

            rendered = toolbar.render_toolbar()

            cache_key = "%f" % time.time()
            cache.set(cache_key, rendered)

            response['X-debug-data-url'] = request.build_absolute_uri(
                reverse('debug_data', urlconf=debug_panel.urls, kwargs={'cache_key': cache_key}))

            return response
