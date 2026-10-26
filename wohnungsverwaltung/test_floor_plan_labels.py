from xml.etree import ElementTree

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Wohnung, WohnungStatus


class FloorPlanLabelTests(TestCase):
    def test_every_status_shows_full_apartment_label_on_each_floor(self):
        for floor in range(5):
            number = "1" if floor == 0 else f"{floor}01"
            unit = Wohnung.objects.create(
                gebaeudenummer="1", wohnungsnummer=number, etage=floor, groesse_qm="25.27"
            )
            for status in (WohnungStatus.FREE, WohnungStatus.TAKEN, WohnungStatus.BLOCKED):
                with self.subTest(floor=floor, status=status):
                    unit.status = status
                    unit.save(update_fields=["status"])
                    response = self.client.get(
                        reverse("wohnungsverwaltung_public:floor_view", args=[floor])
                    )
                    html = response.content.decode()
                    start = html.index('<svg class="floor-plan')
                    end = html.index("</svg>", start) + len("</svg>")
                    plan = ElementTree.fromstring(html[start:end])
                    captions = plan.findall(".//text[@class='plan-number']")
                    self.assertEqual(
                        [label.text for label in captions], [f"Wohnung {unit.display_number}"]
                    )
                    self.assertNotIn("Whg.", html[start:end])
                    links = plan.findall(".//a")
                    if status == WohnungStatus.FREE:
                        self.assertEqual(len(links), 1)
                        self.assertEqual(
                            links[0].get("href"),
                            reverse(
                                "wohnungsverwaltung_public:apartment_detail_placeholder",
                                args=[unit.pk],
                            ),
                        )
                    else:
                        self.assertEqual(links, [])
                        self.assertEqual(
                            [label.text for label in plan.findall(".//text[@class='plan-status']")],
                            ["Nicht verfügbar"],
                        )
                        self.assertContains(response, 'class="plan-apartment is-unavailable"')

    def test_taken_and_blocked_apartments_keep_details_and_requests_private(self):
        self.client.force_login(get_user_model().objects.create_user(username="plan-access"))
        for status in (WohnungStatus.TAKEN, WohnungStatus.BLOCKED):
            unit = Wohnung.objects.create(
                gebaeudenummer="1", wohnungsnummer="401", etage=4, status=status
            )
            for endpoint in ("apartment_detail_placeholder", "viewing_request"):
                with self.subTest(status=status, endpoint=endpoint):
                    response = self.client.get(
                        reverse("wohnungsverwaltung_public:" + endpoint, args=[unit.pk])
                    )
                    self.assertEqual(response.status_code, 404)
