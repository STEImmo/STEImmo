from django.test import TestCase
from django.urls import reverse


class FoundationViewTests(TestCase):
    def test_home_page_is_available(self) -> None:
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "STEImmo")

    def test_health_endpoint_checks_database_connection(self) -> None:
        response = self.client.get(reverse("health"))

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(
            response.content,
            '{"service": "steimmo", "status": "ok"}',
        )
