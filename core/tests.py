from django import forms
from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.http import Http404
from django.template.loader import render_to_string
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import include, path, reverse

from core import views
from wohnungsverwaltung.upload_limits import upload_too_large_response


def failing_view(request, code):
    errors = {400: SuspiciousOperation, 403: PermissionDenied, 404: Http404, 500: RuntimeError}
    raise errors[code]("private-error-details")


urlpatterns = [path("failure/<int:code>/", failing_view), path("", include("config.urls"))]
handler400 = "core.views.bad_request"
handler403 = "core.views.permission_denied"
handler404 = "core.views.page_not_found"
handler500 = "core.views.server_error"


@override_settings(DEBUG=False, ROOT_URLCONF="core.tests", ALLOWED_HOSTS=["testserver"])
class ErrorPageTests(SimpleTestCase):
    def test_error_handlers_keep_status_and_hide_internal_details(self):
        self.client.raise_request_exception = False
        for code in (400, 403, 404, 500):
            with self.subTest(code=code):
                response = self.client.get(f"/failure/{code}/")
                self.assertContains(response, "STE Immobilien", status_code=code)
                self.assertContains(response, 'href="/"', status_code=code)
                self.assertNotContains(response, "private-error-details", status_code=code)

    def test_unknown_url_uses_designed_not_found_page(self):
        response = self.client.get("/unknown-private-path/")
        self.assertContains(response, "Seite nicht gefunden", status_code=404)
        self.assertNotContains(response, "unknown-private-path", status_code=404)

    def test_csrf_failure_explains_how_to_retry_without_exposing_reason(self):
        response = views.csrf_failure(RequestFactory().post("/"), reason="private-csrf-details")
        self.assertContains(response, "Seite neu", status_code=403)
        self.assertNotContains(response, "private-csrf-details", status_code=403)

    def test_upload_limit_page_preserves_limits_message_and_security_headers(self):
        response = upload_too_large_response("Eine Datei überschreitet das Limit von 8 MiB.")
        self.assertContains(response, "8 MiB", status_code=413)
        self.assertContains(response, "Upload zu groß", status_code=413)
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_missing_csrf_token_uses_error_page_and_still_rejects_submission(self):
        response = Client(enforce_csrf_checks=True).post("/accounts/logout/")
        self.assertContains(response, "Bitte erneut versuchen", status_code=403)


class SharedFormFieldTests(SimpleTestCase):
    def test_required_field_exposes_help_and_error_targets(self):
        class ExampleForm(forms.Form):
            name = forms.CharField(label="Name", help_text="Bitte den Namen eingeben.")

        form = ExampleForm(data={})
        self.assertFalse(form.is_valid())
        markup = render_to_string("wohnungsverwaltung/_form_field.html", {"field": form["name"]})
        self.assertIn('for="id_name"', markup)
        self.assertIn('aria-label="Pflichtfeld"', markup)
        self.assertIn('id="id_name_helptext"', markup)
        self.assertIn('id="id_name_error"', markup)
        self.assertIn('aria-invalid="true"', markup)
        for target in form["name"].aria_describedby.split():
            self.assertIn(f'id="{target}"', markup)

    def test_optional_field_is_not_marked_as_required(self):
        class ExampleForm(forms.Form):
            note = forms.CharField(required=False, label="Hinweis")

        markup = render_to_string(
            "wohnungsverwaltung/_form_field.html", {"field": ExampleForm()["note"]}
        )
        self.assertNotIn('aria-label="Pflichtfeld"', markup)


class FoundationViewTests(TestCase):
    def test_home_page_is_available(self) -> None:
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "STE Immobilien eGbR")

    def test_health_endpoint_checks_database_connection(self) -> None:
        response = self.client.get(reverse("health"))

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(
            response.content,
            '{"service": "steimmo", "status": "ok"}',
        )
