from django.test import TestCase, override_settings
from django.urls import reverse


class AuthPagePatternTests(TestCase):
    def test_login_registration_and_confirmation_share_the_selected_design(self):
        for name in ("login", "register", "register_verify"):
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertContains(response, 'class="auth-layout"')
                self.assertContains(response, "auth-moving-in.webp")
                self.assertContains(response, 'method="post"')
                self.assertContains(response, 'name="csrfmiddlewaretoken"')
                self.assertNotContains(response, "Designvorschau")

    def test_invalid_login_keeps_email_and_explains_the_error(self):
        response = self.client.post(
            reverse("login"),
            {"username": "unknown@example.test", "password": "IncorrectPassword!4826"},
        )
        self.assertContains(response, 'value="unknown@example.test"')
        self.assertContains(response, 'role="alert"')
        self.assertNotContains(response, 'value="IncorrectPassword!4826"')

    def test_missing_login_fields_have_accessible_field_errors(self):
        response = self.client.post(reverse("login"), {})
        self.assertContains(response, 'id="id_username_error"')
        self.assertContains(response, 'aria-invalid="true"')
        self.assertContains(response, 'aria-describedby="id_username_error"')

    def test_registration_keeps_names_and_describes_password_mismatch(self):
        response = self.client.post(
            reverse("register"),
            {
                "vorname": "Test",
                "nachname": "Name",
                "email": "registration-ui@example.test",
                "password1": "FjordTanne!4826",
                "password2": "OtherPassword!4826",
            },
        )
        self.assertContains(response, 'value="Test"')
        self.assertContains(response, "Die Passwörter stimmen nicht überein.")
        self.assertContains(response, 'id="id_password2_error"')
        self.assertContains(response, 'id="id_password1_helptext"')

    def test_login_and_registration_keep_the_selected_apartment_on_form_and_switch(self):
        target = "/wohnungen/test/besichtigung/"
        for name, other in (("login", "register"), ("register", "login")):
            with self.subTest(page=name):
                response = self.client.get(reverse(name), {"next": target})
                self.assertContains(response, f'name="next" value="{target}"')
                self.assertContains(response, f'href="{reverse(other)}?next=%2Fwohnungen')

    def test_confirmation_forms_use_distinct_email_ids(self):
        response = self.client.get(reverse("register_verify"))
        self.assertContains(response, 'id="id_email"', count=1)
        self.assertContains(response, 'id="id_resend_email"', count=1)

    @override_settings(DEBUG=True)
    def test_design_comparison_route_has_been_removed(self):
        self.assertEqual(self.client.get("/design/konto/").status_code, 404)
