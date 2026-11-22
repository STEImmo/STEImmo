from smtplib import SMTPDataError, SMTPRecipientsRefused
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.db import transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .access import ROLE_APPLICANT, ROLE_EMPLOYEE, ROLE_GLOBAL_SETTINGS, ROLE_TENANT
from .decision_notifications import deliver_decision_notification, queue_decision_notification
from .models import (
    AbnahmeStatus,
    ApplicationReviewEvent,
    Bewerbung,
    BewerbungStatus,
    DecisionNotification,
    GlobalSettings,
    NotificationPreference,
    Person,
    Protokoll,
    ProtokollStatus,
    ProtokollTyp,
    UebergabeStatus,
    Wohnung,
)
from .notification_preferences import STAFF_GROUPS, USER_GROUPS, USER_MAIL_TYPES


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DECISION_NOTIFICATION_ORIGIN="https://steimmo.example",
)
class DecisionNotificationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        accounts = get_user_model().objects
        cls.applicant = accounts.create_user("applicant", email="applicant@example.test")
        cls.applicant.groups.add(Group.objects.get(name=ROLE_APPLICANT))
        cls.employee = accounts.create_user("employee", email="employee@example.test")
        cls.employee.groups.add(Group.objects.get(name=ROLE_EMPLOYEE))
        cls.other = accounts.create_user("other", email="other@example.test")
        cls.person = Person.objects.create(
            user=cls.applicant, vorname="Test", nachname="Person", email=cls.applicant.email
        )
        cls.unit = Wohnung.objects.create(gebaeudenummer="1", wohnungsnummer="04")
        cls.application = Bewerbung.objects.create(
            person=cls.person,
            wohnung=cls.unit,
            main_application_unlocked=True,
            submitted_at=timezone.now(),
        )

    def assert_mail_link(self, message, url, label):
        self.assertIn(f"{label}: {url}", message.body)
        html, mimetype = message.alternatives[0]
        self.assertEqual(mimetype, "text/html")
        self.assertIn(f'<a href="{url}">{label}</a>', html)

    def accept(self):
        self.client.force_login(self.employee)
        url = reverse("wohnungsverwaltung:employee_application_accept", args=[self.application.pk])
        return self.client.post(url)

    def test_acceptance_posts_send_one_message_with_an_owned_link(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.accept().status_code, 302)
            self.assertEqual(self.accept().status_code, 302)
        self.assertEqual(DecisionNotification.objects.count(), 1)
        message = mail.outbox[0]
        url = reverse("wohnungsverwaltung:main_application_status", args=[self.application.pk])
        self.assertEqual(message.to, [self.applicant.email])
        self.assert_mail_link(message, f"http://testserver{url}", "Eigene Hauptbewerbung öffnen")
        self.assertEqual(len(mail.outbox), 1)
        self.client.force_login(self.applicant)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_contract_already_sent_supersedes_pending_acceptance(self):
        self.accept()
        self.application.review_events.create(kind=ApplicationReviewEvent.Kind.CONTRACT_SENT)
        notice = DecisionNotification.objects.get()
        deliver_decision_notification(notice.pk)
        notice.refresh_from_db()
        self.assertEqual(notice.status, DecisionNotification.Status.SUPPRESSED)
        self.assertEqual(mail.outbox, [])

    def test_withdrawal_sends_once_to_authorized_staff(self):
        self.client.force_login(self.applicant)
        url = reverse("wohnungsverwaltung:application_withdraw", args=[self.application.pk])
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.post(url).status_code, 302)
            self.assertEqual(self.client.post(url).status_code, 404)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.employee.email])
        sentence = "Test Person hat die Bewerbung zurückgezogen."
        self.assertIn(sentence, mail.outbox[0].body)
        self.assertIn(sentence, mail.outbox[0].alternatives[0].content)
        detail_url = reverse(
            "wohnungsverwaltung:employee_application_detail", args=[self.application.pk]
        )
        self.assert_mail_link(
            mail.outbox[0], f"http://testserver{detail_url}", "Bewerbung in der Verwaltung öffnen"
        )

    def test_lowered_occupancy_limit_sends_sanitized_notice(self):
        Bewerbung.objects.filter(pk=self.application.pk).update(
            main_application_unlocked=False, submitted_at=None, personenanzahl=3
        )
        self.unit.max_occupants = 2
        with self.captureOnCommitCallbacks(execute=True):
            self.unit.save(update_fields=["max_occupants"])
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, BewerbungStatus.DECLINED)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("abgelehnt", mail.outbox[0].body)
        self.assertNotIn("Personen", mail.outbox[0].body)
        list_url = reverse("wohnungsverwaltung:pre_application_list")
        self.assert_mail_link(
            mail.outbox[0], f"https://steimmo.example{list_url}", "Meine Bewerbungen öffnen"
        )

    def test_rollback_cancels_the_notice_and_the_mail(self):
        with self.captureOnCommitCallbacks(execute=True) as callbacks, transaction.atomic():
            self.accept()
            transaction.set_rollback(True)
        self.assertEqual(callbacks, [])
        self.assertFalse(DecisionNotification.objects.exists())
        self.assertEqual(mail.outbox, [])

    def test_retry_checks_preferences_and_suppression_is_final(self):
        self.accept()
        notice = DecisionNotification.objects.get()
        with patch(
            "wohnungsverwaltung.decision_notifications.send_mail",
            side_effect=SMTPDataError(451, b"temporary"),
        ):
            deliver_decision_notification(notice.pk)
        notice.refresh_from_db()
        self.assertEqual(notice.status, DecisionNotification.Status.RETRY)
        self.application.refresh_from_db()
        self.assertIsNotNone(self.application.accepted_at)

        choice, _ = NotificationPreference.objects.update_or_create(
            account=self.applicant, defaults={"choices": {"application_decisions": "off"}}
        )
        deliver_decision_notification(notice.pk)
        choice.delete()
        deliver_decision_notification(notice.pk)
        notice.refresh_from_db()
        self.assertEqual(notice.status, DecisionNotification.Status.SUPPRESSED)
        self.assertEqual(notice.attempts, 1)
        self.assertEqual(mail.outbox, [])

    def test_switching_personal_category_off_and_on_suppresses_retry(self):
        self.accept()
        notice = DecisionNotification.objects.get()
        states = DecisionNotification.Status
        with patch(
            "wohnungsverwaltung.decision_notifications.send_mail",
            side_effect=SMTPDataError(451, b"temporary"),
        ):
            deliver_decision_notification(notice.pk)
        notice.refresh_from_db()
        self.assertEqual(notice.status, states.RETRY)

        self.client.force_login(self.applicant)
        url = reverse("profile:notifications")
        choices = dict.fromkeys(USER_GROUPS, "default")
        for version, choice in enumerate(("off", "on")):
            self.assertRedirects(
                self.client.post(
                    url, {**choices, "version": version, "application_decisions": choice}
                ),
                url,
            )
        deliver_decision_notification(notice.pk)
        notice.refresh_from_db()
        self.assertEqual(notice.status, states.SUPPRESSED)
        self.assertEqual(notice.attempts, 1)
        self.assertEqual(mail.outbox, [])

    def test_switching_staff_category_off_and_on_suppresses_pending_withdrawal(self):
        self.client.force_login(self.applicant)
        withdraw_url = reverse(
            "wohnungsverwaltung:application_withdraw", args=[self.application.pk]
        )
        self.assertEqual(self.client.post(withdraw_url).status_code, 302)
        notice = DecisionNotification.objects.get()

        self.client.force_login(self.employee)
        url = reverse("profile:notifications")
        choices = {key: "on" for key in STAFF_GROUPS if key != "application_changes"}
        self.assertRedirects(self.client.post(url, {**choices, "version": 0}), url)
        self.assertRedirects(
            self.client.post(url, {**choices, "version": 1, "application_changes": "on"}), url
        )
        deliver_decision_notification(notice.pk)
        notice.refresh_from_db()
        self.assertEqual(notice.status, DecisionNotification.Status.SUPPRESSED)
        self.assertEqual(mail.outbox, [])

    def test_switching_global_mail_type_off_and_on_suppresses_pending_decision(self):
        self.accept()
        notice = DecisionNotification.objects.get()
        self.employee.groups.add(Group.objects.get(name=ROLE_GLOBAL_SETTINGS))
        self.client.force_login(self.employee)
        url = reverse("verwaltung:global_settings")
        version = GlobalSettings.objects.get(pk=1).version
        choices = {key: "on" for key in USER_MAIL_TYPES if key != "application_accepted"}
        self.assertRedirects(self.client.post(url, {**choices, "version": version}), url)
        self.assertRedirects(
            self.client.post(
                url, {**choices, "version": version + 1, "application_accepted": "on"}
            ),
            url,
        )
        deliver_decision_notification(notice.pk)
        notice.refresh_from_db()
        self.assertEqual(notice.status, DecisionNotification.Status.SUPPRESSED)
        self.assertEqual(mail.outbox, [])

    def test_temporary_recipient_rejection_retries_up_to_limit(self):
        self.accept()
        notice = DecisionNotification.objects.get()
        error = SMTPRecipientsRefused({self.applicant.email: (450, b"temporary")})
        states = DecisionNotification.Status
        with patch(
            "wohnungsverwaltung.decision_notifications.send_mail", side_effect=error
        ) as send:
            for expected in (states.RETRY, states.RETRY, states.FAILED, states.FAILED):
                deliver_decision_notification(notice.pk)
                notice.refresh_from_db()
                self.assertEqual(notice.status, expected)
        self.assertEqual(send.call_count, 3)

    def test_initial_opt_out_prevents_queueing_for_delivery(self):
        preference = NotificationPreference.objects.create(
            account=self.applicant, choices={"application_decisions": "off"}
        )
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            self.accept()
        self.assertEqual(callbacks, [])
        notice = DecisionNotification.objects.get()
        preference.delete()
        deliver_decision_notification(notice.pk)
        notice.refresh_from_db()
        self.assertEqual(notice.status, DecisionNotification.Status.SUPPRESSED)
        self.assertEqual(mail.outbox, [])

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.dummy.EmailBackend")
    def test_demo_does_not_attempt_mail_delivery(self):
        with (
            patch("wohnungsverwaltung.decision_notifications.send_mail") as send,
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.accept()
        send.assert_not_called()
        self.assertEqual(
            DecisionNotification.objects.get().status, DecisionNotification.Status.SUPPRESSED
        )

    def test_owner_change_after_queue_prevents_disclosure(self):
        self.accept()
        Person.objects.filter(pk=self.person.pk).update(user=self.other)
        deliver_decision_notification(DecisionNotification.objects.get().pk)
        self.assertEqual(mail.outbox, [])

    def test_owner_change_during_render_prevents_delivery(self):
        self.accept()
        notice = DecisionNotification.objects.get()

        def reassign(*args, **kwargs):
            Person.objects.filter(pk=self.person.pk).update(user=self.other)
            return "<p>Gerenderte Nachricht</p>"

        with patch(
            "wohnungsverwaltung.decision_notifications.render_to_string", side_effect=reassign
        ):
            deliver_decision_notification(notice.pk)
        notice.refresh_from_db()
        self.assertEqual(notice.status, DecisionNotification.Status.SUPPRESSED)
        self.assertEqual(mail.outbox, [])

    def test_address_change_during_render_uses_current_account_address(self):
        self.accept()
        notice = DecisionNotification.objects.get()
        address = "updated@example.test"

        def change_address(*args, **kwargs):
            get_user_model().objects.filter(pk=self.applicant.pk).update(email=address)
            return "<p>Gerenderte Nachricht</p>"

        with patch(
            "wohnungsverwaltung.decision_notifications.render_to_string", side_effect=change_address
        ):
            deliver_decision_notification(notice.pk)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [address])

    def test_handover_requires_an_own_verified_pdf(self):
        self.applicant.groups.add(Group.objects.get(name=ROLE_TENANT))
        protocol = Protokoll.objects.create(
            person=self.person,
            wohnung=self.unit,
            status=ProtokollStatus.SIGNED,
            protokoll_typ=ProtokollTyp.MOVE_IN,
            uebergabe_status=UebergabeStatus.RENOVATED,
            abnahme_status=AbnahmeStatus.ACCEPTED,
            uebergabe_zeitpunkt=timezone.now(),
            dokument_pfad="missing.pdf",
            dokument_hash_sha256="abc",
        )
        with self.captureOnCommitCallbacks(execute=True):
            queue_decision_notification("handover_finalized", protocol.pk, "abc", self.applicant.pk)
        self.assertEqual(DecisionNotification.objects.get().status, "suppressed")
        self.assertEqual(mail.outbox, [])

        Protokoll.objects.filter(pk=protocol.pk).update(dokument_hash_sha256="def")
        with (
            patch("wohnungsverwaltung.decision_notifications.read_archived_pdf"),
            self.captureOnCommitCallbacks(execute=True),
        ):
            for _ in range(2):
                queue_decision_notification(
                    "handover_finalized", protocol.pk, "def", self.applicant.pk
                )
        self.assertEqual(len(mail.outbox), 1)
        pdf_url = reverse("wohnungsverwaltung:handover_protocol_pdf", args=[protocol.pk])
        self.assert_mail_link(
            mail.outbox[0], f"https://steimmo.example{pdf_url}", "Übergabeprotokoll als PDF öffnen"
        )
